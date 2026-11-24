# Cleaning up collections, keys, indexes, or data between tests

When testing Spring Boot applications using **non-SQL data**, a test can pass when run alone yet fail in a full suite because data from an earlier test remains in MongoDB, Redis, Elasticsearch, or object storage. An old document inflates a query result by one extra item; a leftover Redis key causes a cache to return stale data; a MongoDB unique index dropped alongside its collection keeps duplicate-key tests from catching violations; or an Elasticsearch index retains old mappings and fails only in CI. Such failures are often misdiagnosed as business logic bugs when the real root cause is that **tests lack controlled preconditions and postconditions**.

This Knowledge lesson focuses on **cleaning up collections, keys, indexes, or data between tests**, within the **Non-SQL Data** group of the **Spring Boot – testing** module. The goal is not to call the most aggressive delete command possible, but to **establish safe, repeatable test data boundaries that never harm other tests or production environments**.

Examples apply to **Java 17+, Spring Boot 3.5.x, Spring Data MongoDB 4.5.x, Spring Data Redis 3.5.x, JUnit Jupiter 5, and Testcontainers 1.21.x**. The runnable portion uses separate MongoDB and Redis containers with `@DataMongoTest`/`@DataRedisTest`, `@BeforeEach`/`@AfterEach`, `MongoTemplate`, `StringRedisTemplate`, and `@DynamicPropertySource`. Elasticsearch/OpenSearch, multi-tier caches, and object storage are covered through patterns and snippets because APIs vary by engine/version.

**Non-negotiable rule:** Never run `FLUSHALL`, `DROP DATABASE`, full bucket/index deletions, or overly broad prefix cleanups on any system not verified as a **dedicated test environment**.

## 1. Learning objectives

After this lesson, you will be able to:

- Explain why leftover NoSQL data makes tests **flaky** and how to detect contamination.
- Inventory what needs cleanup: documents, collections, indexes, keys, TTLs, cache entries, search indexes, aliases, and object prefixes.
- Choose between **data deletion**, **namespace isolation**, **database/container isolation**, and **fresh resources per test**.
- Know how `MongoTemplate.remove(...)` differs from `dropCollection(...)` in **keeping vs. deleting indexes**.
- Recreate required **unique indexes** after dropping a Mongo collection rather than relying on default auto-index creation.
- Clean up Redis keys by **tracked list of created keys** or dedicated namespace; distinguish `SCAN`, `KEYS`, `DEL`, `UNLINK`, `FLUSHDB`, and `FLUSHALL`.
- Design deterministic TTL/expiration tests without relying on sleeping a few milliseconds.
- Understand Elasticsearch index lifecycles, aliases, mappings, and near-real-time refresh.
- Use Testcontainers, dynamic connection properties, and test slices without depending on locally pre-installed Mongo/Redis on laptops.
- Protect parallel tests, Spring TestContext caching, retries, test failures, and cleanup failures.
- Write integration tests checking **preconditions – behavior – postconditions – cleanup** rather than only asserting a return value.

## 2. Why does non-SQL data easily contaminate tests?

A typical flaky scenario unfolds like this:

```text
Test A
  -> writes Mongo document id=profile-1
  -> writes Redis key cache:profile:profile-1
  -> asserts PASS
  -> skips cleanup

Test B
  -> expects Mongo query to return only one document
  -> inserts another document
  -> query returns two documents => FAIL

Test C
  -> expects cache miss
  -> Test A's Redis key still exists => FAIL

Running Test B/C individually can PASS.
Running the suite in order A -> B -> C FAILS.
```

Contamination can hide outside return values: in the DB, Redis, index metadata, in-JVM caches, stream offsets, object storage, search aliases, or even asynchronous tasks left running by a previous test.

An ideal test never needs another test to "clean up after it". Changing execution order or re-running any single test should never alter its outcome. In practice, combine **isolation and cleanup** instead of relying on a single JUnit annotation.

## 3. Categorizing resources and cleanup approaches

| Store | Data unit | Metadata unit | Narrowest cleanup | Consequences to remember |
|---|---|---|---|---|
| MongoDB | Document | Collection, index, TTL index | `remove(Query, Type)` | Keeps indexes; query must scope tenant/run properly |
| MongoDB | Collection | Indexes in collection | `dropCollection(Type)` | **Deletes all indexes on the collection** |
| Redis | Key/value, hash, set, stream | TTL, consumer group, key namespace | `delete(key)` or owned key set | Does not affect other keys if exact names are tracked |
| Redis | Multiple keys | Keyspace | `SCAN` with owned prefix then `DEL`/`UNLINK` | SCAN is not an atomic snapshot; beware concurrent writers |
| Elasticsearch/OpenSearch | Document | Index, mapping, alias, template | Delete document-by-ID or dedicated test index | Near-real-time search; deleting index also deletes mappings/shards |
| Object storage | Object/version | Bucket, version, lifecycle policy | Delete by run's object keys/prefix | Versioned buckets retain versions/delete markers |
| Cassandra | Rows | Keyspace/table schema | Partition-scoped delete or dedicated keyspace | Tombstones/compaction make cleanup behave differently from SQL |
| Neo4j | Nodes/relationships | Constraints/indexes | Delete run's subgraph | Relationships exist; never wipe a shared graph |
| In-process cache | Entries | Cache manager/config | Evict test-owned keys | Does not clear external Mongo/Redis |
| Message broker | Message/offset | Topic/consumer group | Unique topic/group or purge on test infra | Offsets and events can linger after tests |

Despite using the same word "**index**", a Mongo index and an Elasticsearch index are two completely different things: a Mongo index is a collection's lookup/constraint structure; an Elasticsearch index is the **storage unit for documents and mappings**. Do not apply one deletion strategy to both.

## 4. Priority order: isolate first, clean up second

An effective strategy generally prioritizes:

1. **Dedicated container or service instance for the suite** using Testcontainers.
2. **Dedicated database/index/bucket/prefix per test class or test run**.
3. **Unique identifiers per test** when parallel execution is needed.
4. **Scoped cleanup** after use, using the exact keys/document IDs created.
5. **Postcondition checks** that fail the run if cleanup itself fails.
6. **Upfront cleanup** in cases where a killed JVM might leave debris from a prior run.

Not every test needs a brand-new container per method. Longer-lived containers paired with dedicated namespaces are usually faster; however, tests must never share each other's data. When data or risk demands absolute separation, separate test classes or separate databases can be worth the cost.

### 4.1. Four easily confused terms

- **Isolation:** inability to affect data outside your own test's scope.
- **Setup/reset:** bringing the test environment into its required precondition state before the test.
- **Teardown/cleanup:** deleting resources created after the test finishes.
- **Disposal:** destroying the entire container/database/bucket owned by the suite/run.

If post-test cleanup is skipped because a process was abruptly killed, **container disposal or namespace TTL** serves as the backup layer. A crashed container on shared staging must never leave orphaned data behind indefinitely with no owner.

## 5. `@BeforeEach` or `@AfterEach`?

Both serve distinct roles:

```java
@BeforeEach
void prepare() {
    // Verify preconditions and create required schemas/indexes.
}

@AfterEach
void cleanup() {
    // Delete the exact resources just created by the test.
}
```

`@BeforeEach` can clear leftover data **if it is guaranteed to sit inside the test's own isolated database/index/namespace**. `@AfterEach` keeps the environment clean and surfaces cleanup failures. A solid pattern uses both, while never running **broad deletes** on shared databases.

**Crucial trap:** `@AfterEach` is not guaranteed to run in every scenario. JVM kills, lost Docker daemons, timeouts, or machine crashes can prevent teardown. Therefore:

- With ephemeral containers, the entire environment vanishes when the container is destroyed.
- With shared test infrastructure, use prefixes containing run IDs, TTLs, and a permission-scoped garbage collector.
- With object storage, delete versions and delete markers too if the bucket is versioned.
- Within a single container running parallel tests, per-test namespaces prevent one test's cleanup from deleting another test's data.

### 5.1. What if the test passes yet cleanup fails?

Cleanup is part of the test contract. If a test's business logic passes yet `@AfterEach` fails to clean up its keys/documents, **the test run must fail**; never `catch(Exception ignored)` to hide contamination. When preserving state for debugging is needed, make it an explicit diagnostic mode with an owner/TTL and never on production resources.

## 6. MongoDB: deleting documents differs from dropping collections

Two operations:

```java
// Snippet inside a test with MongoTemplate mongo.
// Delete all Profile documents; collection/indexes remain.
mongo.remove(new Query(), Profile.class);

// Drop the entire Profile collection along with its indexes.
mongo.dropCollection(Profile.class);
```

**Biggest difference:** `remove(...)` preserves the collection and its unique/TTL/text indexes; `dropCollection(...)` destroys indexes too. If you drop a collection holding `UNIQUE(email)` and insert again without recreating the index, duplicate emails will succeed. A test reporting "both inserts succeeded" is not necessarily a Mongo bug; cleanup itself may have wiped the constraint.

Recent Spring Data MongoDB versions **do not enable auto-index creation by default**. Even when enabled, auto-index creation does not guarantee indexes magically reappear after a collection is dropped and recreated within the same application lifecycle. Therefore, tests must **explicitly ensure indexes** after a reset, or execute the real tested migration/index initializer.

### 6.1. When to use `remove`?

Use it when:

- Collection schema/indexes are fixed and migration is not under test.
- You want to clear documents before each method while preserving unique/TTL indexes.
- Tests run against an **isolated test database** and you want less overhead than drop/create collection.
- You can scope deletion by `runId`/`tenantId` without touching other data.

Scoped example:

```java
// Snippet: only when Profile has a testRunId field and data is test-only.
mongo.remove(
        Query.query(Criteria.where("testRunId").is(runId)),
        Profile.class);
```

Never pass an unfiltered `new Query()` on a collection shared by multiple tests/tenants in a shared database. A "missing WHERE" in NoSQL is just as dangerous as a SQL `DELETE` without `WHERE`.

### 6.2. When to use `dropCollection`?

Use it when:

- The collection belongs exclusively to this test class/run and is not shared.
- Both documents and collection indexes/mappings need resetting.
- You are explicitly testing the **drop → recreate → ensure index** lifecycle.

After dropping, if the contract requires a unique index:

```java
mongo.createCollection(Profile.class);
mongo.indexOps(Profile.class)
        .ensureIndex(new Index()
                .on("email", Sort.Direction.ASC)
                .unique());
```

This is a snippet; `Profile`, `mongo`, and imports appear in the sample project. For production migrations, index creation must be controlled; tests should ideally invoke the real migration rather than a hand-written copy.

## 7. MongoDB: verify indexes, not just data

If the test database requires indexes, verifying them is also part of the contract.

```java
List<IndexInfo> info =
        mongo.indexOps(Profile.class).getIndexInfo();

assertTrue(info.stream().anyMatch(index ->
        index.isUnique()
        && index.isIndexForFields(List.of("email"))));
```

The lines above are a snippet requiring imports. They catch missing unique indexes. However, metadata inspection alone is not enough to prove **duplicates are actually rejected by the DB**; also test inserting two documents with different `_id`s and identical email, expecting `DuplicateKeyException`.

Indexes requiring dedicated tests include:

- **Unique/compound indexes:** duplicate combinations are rejected.
- **TTL indexes:** documents expire per policy, though Mongo's TTL monitor runs asynchronously so never assert millisecond-exact deletion.
- **Text/geospatial indexes:** queries/scores/sorts need realistic fixtures and proper indexes.
- **Partial indexes:** filter expressions match properly without blocking out-of-scope documents.
- **Collation:** case/accent sensitivity of uniqueness/search matches the contract.
- **Sparse indexes:** missing vs. null differences when uniqueness is a real risk.

**Never drop a production index just to reproduce a test.** Use a test database and dedicated migration/index initializers. When testing index lifecycle specifically, intentionally drop/recreate **only an index you own**, then assert the outcome.

## 8. Redis: keys outlive the JVM

Redis is external state; JUnit recreating a controller or Spring context does not automatically wipe Redis keys.

Example:

```text
it:pricing:run-123:quote:BOOK = 216000 (TTL 60s)
it:pricing:run-999:quote:BOOK = 240000 (TTL 60s)
app:session:real-user-42      = sensitive data (DO NOT TOUCH)
```

If test cleanup runs `FLUSHDB`, it wipes **every key** in the selected Redis logical database, including sessions and caches outside the test. `FLUSHALL` is even broader: it wipes every database on the instance. In Redis Cluster, logical DB semantics also differ; never rely on separate DB numbers as sufficient isolation.

**Safe pattern:**

```text
it:<suite>:<runId>:<testId>:<objectType>:<objectId>
```

Concrete example:

```text
it:cleanup:7f2a:user:41
it:cleanup:7f2a:cart:41
```

When fixture key names are known upfront, **track `Set<String> ownedKeys`** and clean up exactly those keys. If a background job creates keys that are hard to enumerate upfront, use an exclusive test namespace and `SCAN` by prefix.

### 8.1. `DEL`, `UNLINK`, `EXPIRE`, and TTL

- **`DEL`:** deletes keys and returns the count of deleted keys.
- **`UNLINK`:** unlinks keys from the keyspace and reclaims memory asynchronously; helpful for large values when appropriate.
- **`EXPIRE`/TTL:** sets an expiration time, never a substitute for explicit teardown. Expiration timing is not a millisecond-accurate timer.
- **`PERSIST`:** removes TTL so a key persists indefinitely, not cleanup; use carefully in tests.
- **`FLUSHDB`/`FLUSHALL`:** broad wipes; **only** consider on an exclusively owned Redis container instance when a full reset is genuinely needed.

Tests using TTL can verify the value and a positive TTL without waiting for expiration:

```java
redis.opsForValue().set(
        key, "ready", Duration.ofMinutes(5));

Long seconds = redis.getExpire(
        key, TimeUnit.SECONDS);

assertNotNull(seconds);
assertTrue(seconds > 0);
```

This is a snippet. When a contract genuinely requires a key to vanish after its TTL, use bounded eventual assertions/Awaitility or system expiry tests; **never write `Thread.sleep(500)` assuming the server deleted it the instant sleep ends**.

## 9. `SCAN` and `KEYS`: understand their exact scope

`StringRedisTemplate.keys(pattern)` sends the Redis **`KEYS`** command; on large keyspaces it can block and stall the server. Spring Data Redis recommends `scan(ScanOptions)` for larger datasets.

```java
// Snippet: with StringRedisTemplate redis and a dedicated namespace.
ScanOptions options = ScanOptions.scanOptions()
        .match(namespace + "*")
        .count(100)
        .build();

try (Cursor<String> cursor = redis.scan(options)) {
    while (cursor.hasNext()) {
        String key = cursor.next();
        // Process only if the key belongs to this test's namespace.
    }
}
```

**Important Redis SCAN caveats:**

- `SCAN` iterates the keyspace via a cursor; it is not an atomic snapshot.
- Under concurrent mutations, keys may appear more than once or be missed.
- `COUNT` is a hint to the server, not a guarantee of exact batch size per iteration.
- Always use `try-with-resources` to close the cursor.
- If **guaranteed** cleanup is needed alongside concurrent writers, isolate namespaces or stop writers/wait for jobs to finish before teardown.
- In Redis Cluster, scanning across the cluster may require per-node handling or appropriate client APIs; do not assume one `SCAN` covers every cluster shard.

**Never run `SCAN match("*")` and delete every key on a shared instance.** Whenever ownership is uncertain, halt cleanup and isolate the environment first.

## 10. MongoDB Testcontainers: a dedicated database for tests

Testcontainers launches MongoDB in a Docker container, avoiding reliance on a local MongoDB holding stale data from prior runs. Use:

```java
@Container
static final MongoDBContainer MONGO =
        new MongoDBContainer(DockerImageName.parse("mongo:7.0"));
```

and:

```java
@DynamicPropertySource
static void mongoProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.data.mongodb.uri",
            () -> MONGO.getReplicaSetUrl(DATABASE));
}
```

These are snippets; the runnable project shows the complete class in Section 18. `@DynamicPropertySource` injects the dynamic host/port into Spring's Environment. `getReplicaSetUrl(DATABASE)` targets a specific test database; Testcontainers manages ports and container lifecycle.

Choosing a database name per test run/class reduces collisions if a MongoDB instance is reused across classes:

```java
private static final String DATABASE =
        "it_" + UUID.randomUUID().toString().replace("-", "");
```

Even on a **fresh container owned by one test class**, a UUID adds an extra layer of safety. If Testcontainers reuse is enabled or multiple suites share a container, isolated namespaces/databases become essential alongside lifecycle/cache awareness.

### 10.1. Do not rely solely on random document IDs

Random document IDs prevent primary key collisions, yet **do not prevent data contamination** when tests call `findAll()`, count, or aggregate across the whole collection. Therefore, combine random IDs with separate databases/collections or `runId`-filtered queries.

## 11. Redis Testcontainers: dynamic ports and dedicated namespaces

A Redis container can use `GenericContainer`:

```java
@Container
static final GenericContainer<?> REDIS =
        new GenericContainer<>(
                DockerImageName.parse("redis:7.4-alpine"))
                .withExposedPorts(6379);
```

Properties for Spring Boot 3.5:

```java
@DynamicPropertySource
static void redisProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.data.redis.host", REDIS::getHost);
    registry.add("spring.data.redis.port",
            () -> REDIS.getMappedPort(6379));
}
```

Never hardcode `localhost:6379`. Testcontainers exposes Redis on a dynamic host/port, especially in CI or remote Docker. If production Redis uses TLS/passwords/ACLs, a plain Redis test container does not verify those security layers; add separate transport/security tests per risk.

**Managing test data keys:** Inside the test class, build a UUID namespace and record keys in `ownedKeys` before writing. After each method, call `redis.delete(ownedKeys)`. This avoids `KEYS` and `FLUSHDB` completely.

## 12. Spring Boot test slices and their limits

Spring Boot 3.5 provides dedicated annotations:

| Test | Main components loaded | What does it NOT prove? |
|---|---|---|
| `@DataMongoTest` | Mongo mapping/template/repositories and Mongo auto-configs | Full business services, Redis, HTTP controllers |
| `@DataRedisTest` | Redis connection/template/repositories for the slice | Mongo, HTTP, full service wiring |
| `@DataElasticsearchTest` | Elasticsearch slice components | External Elastic Cloud networking/gateways |
| `@SpringBootTest` | Full application context per test config | Never turns remote dependencies into production |
| Plain non-Spring test | Pure cleanup policy/namespace helpers | Never executes real backends |

In the runnable project, **the Mongo test and Redis test are separate classes**, each starting its **own container**. Consequently, a Mongo unique-index test does not require Redis, and a Redis TTL test does not require Mongo.

When testing a use case involving **both real Mongo and real Redis** (e.g., saving a document and invalidating a cache), use `@SpringBootTest` with both containers and assert side-effect ordering. **Two passing slice tests do not prove cross-store consistency.**

## 13. Do not confuse context caching with data reset

Spring TestContext caches `ApplicationContext` instances to speed up suites. It **does not reset**:

- MongoDB documents or indexes.
- Redis keyspace or remaining TTLs.
- Elasticsearch indexes or aliases.
- Object storage objects.
- Uncleaned singleton local caches or queues.
- Background jobs still actively writing.

`@DirtiesContext` tells Spring to close and rebuild the context, yet **does not guarantee external data is cleared** and adds significant overhead. Never slap `@DirtiesContext` onto every method to hide data contamination.

Ideally, tests use isolated namespaces, `@BeforeEach` checks preconditions, `@AfterEach` cleans up owned data, and `@DirtiesContext` is reserved strictly for cases where **context state itself** was mutated and cannot be reset safely.

## 14. Index lifecycle: MongoDB and Elasticsearch differ

### 14.1. MongoDB indexes live inside collections

`dropCollection` wipes the collection's indexes. When tests need uniqueness, recreate the index beforehand. `remove` keeps indexes intact. Advanced index options such as partial filters, sparse, TTL, and collation cannot be verified by index name alone; inspect metadata and runtime behavior.

### 14.2. An Elasticsearch index is a data resource

In Elasticsearch/OpenSearch:

- An **index** holds documents, mappings, and settings; deleting the index deletes that entire resource.
- An **alias** can point to one or more indexes, so deleting an underlying index does not match deleting an application alias.
- **Index templates** may apply when indexes are created; tests must load matching templates/mappings.
- **Refresh** governs when written documents appear in search; an acknowledged write is not necessarily immediately searchable.
- **Delete by query** can run asynchronously, race concurrent writers, and require failure/refresh handling.
- **ILM/lifecycle policies** and rollovers can generate new index names; cleanup targeting a single hardcoded name easily misses rolled-over indexes.

**Test pattern:** create a uniquely named index such as `it-order-search-<run-id>`, configure mappings, write fixtures, refresh/wait per contract, assert search results, and delete **only the index created by this run**. Never delete `orders-*` on a shared cluster.

### 14.3. Do not test search using Mongo rules

Mongo `IndexOperations.ensureIndex(...)` does not apply to Elasticsearch. Search clients, index creation/deletion, refreshes, and mapping semantics are completely different. For engine-specific bugs, use Testcontainers Elasticsearch/OpenSearch or an isolated sandbox cluster instead of faking API calls.

## 15. Cleanup principles beyond Mongo/Redis

### 15.1. Object storage (S3/MinIO/GCS)

Write object keys under a scoped prefix:

```text
it/<suite>/<run-id>/profile/avatar.png
it/<suite>/<run-id>/report/result.json
```

After the test, delete only objects under the allocated prefix and verify absence per backend semantics. With **versioning**, deleting an object may simply add a delete marker while older versions continue consuming storage; use version-aware cleanup/lifecycle rules inside a **dedicated test bucket**. Never use a production bucket just because you added a prefix.

### 15.2. Cassandra

Do not truncate shared keyspaces/tables, especially under parallel tests. Use a dedicated test keyspace or partition keys containing a run ID, cleaning up by partition in the test environment. Tombstones and compaction mean "deleting" differs from immediate physical reclamation.

### 15.3. Neo4j

When each test creates its own subgraph, tag nodes with `testRunId` and delete only owned nodes/relationships. Unconditional `MATCH (n) DETACH DELETE n` can destroy other tests' graphs if run on a shared database.

### 15.4. In-memory caches and Spring Cache

`@Cacheable` may back onto Caffeine/ConcurrentMap, Redis, or other providers. `CacheManager.getCache("x").clear()` clears that context's cache — if backed by a shared Redis cache, it can wipe keys belonging to other tests. Use key scopes/namespaces and isolated test `CacheManager` instances whenever possible.

### 15.5. Search index names and alias migrations

When testing versioned aliases, create a run-scoped alias, switch it to a new index, assert old/new documents per contract, and then clean up both the alias and all run-created indexes. Never confuse removing an alias with deleting documents.

## 16. Runnable project: file layout and boundaries

We build a minimal Spring Boot project with a `Profile` document and test-managed Redis keys.

```text
nosql-cleanup-demo/
  build.gradle
  settings.gradle
  src/main/java/com/example/nosqlcleanup/
    NoSqlCleanupApplication.java
    Profile.java
  src/test/java/com/example/nosqlcleanup/
    ProfileMongoCleanupTest.java
    RedisKeyCleanupTest.java
```

**Assumptions:**

- Java 17+ and Spring Boot **3.5.x**.
- Active Docker daemon with Testcontainers allowed to pull `mongo:7.0` and `redis:7.4-alpine`.
- Tests spin up **dedicated** containers; no pre-installed Mongo/Redis needed on the host.
- Maven/Gradle can reach Maven Central or an appropriate internal registry.
- No profiles or environment variables point to production databases.

The example pins **Spring Boot 3.5.16** in `build.gradle`. If your project is locked to a different 3.5.x patch version, keep APIs matching your verified version; do not bump plugin versions blindly just to run an example.

## 17. Gradle project and application code

**`settings.gradle`**

```groovy
rootProject.name = 'nosql-cleanup-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
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
    implementation 'org.springframework.boot:spring-boot-starter-data-mongodb'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:mongodb'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The Spring Boot BOM manages common Testcontainers artifacts in the 3.5 branch. If your project uses another BOM or corporate-pinned versions, verify dependency resolution before running. Never enable Testcontainers reuse on shared CI without an explicit isolation policy.

**`src/main/java/com/example/nosqlcleanup/NoSqlCleanupApplication.java`**

```java
package com.example.nosqlcleanup;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class NoSqlCleanupApplication {

    public static void main(String[] args) {
        SpringApplication.run(NoSqlCleanupApplication.class, args);
    }
}
```

**`src/main/java/com/example/nosqlcleanup/Profile.java`**

```java
package com.example.nosqlcleanup;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "profiles")
public class Profile {

    @Id
    private String id;
    private String email;
    private String displayName;

    public Profile() {
    }

    public Profile(
            String id, String email, String displayName) {
        this.id = id;
        this.email = email;
        this.displayName = displayName;
    }

    public String getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getDisplayName() {
        return displayName;
    }
}
```

This is a simple MongoDB entity. `@Id` maps to `_id`; the collection name is `profiles`. `email` illustrates a **unique index**, not a real user-data schema. Use `.test` addresses in fixtures, never placing real emails/PII into CI logs.

## 18. MongoDB integration tests: drop, recreate, ensure index

**`src/test/java/com/example/nosqlcleanup/ProfileMongoCleanupTest.java`**

```java
package com.example.nosqlcleanup;

import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.Index;
import org.springframework.data.mongodb.core.index.IndexInfo;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@DataMongoTest
class ProfileMongoCleanupTest {

    private static final String DATABASE = "it_"
            + UUID.randomUUID().toString().replace("-", "");

    @Container
    static final MongoDBContainer MONGO =
            new MongoDBContainer(
                    DockerImageName.parse("mongo:7.0"));

    @DynamicPropertySource
    static void mongoProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.mongodb.uri",
                () -> MONGO.getReplicaSetUrl(DATABASE));
    }

    @Autowired
    MongoTemplate mongo;

    @BeforeEach
    void resetCollectionAndRequiredIndex() {
        // Only the collection inside this class's Testcontainer database.
        mongo.dropCollection(Profile.class);
        mongo.createCollection(Profile.class);

        mongo.indexOps(Profile.class).ensureIndex(
                new Index()
                        .on("email", Sort.Direction.ASC)
                        .unique());

        assertEquals(0L, mongo.count(new Query(), Profile.class));
    }

    @AfterEach
    void dropOnlyOwnedCollection() {
        mongo.dropCollection(Profile.class);
        assertFalse(mongo.collectionExists(Profile.class));
    }

    @Test
    void startsWithNoStaleDocuments() {
        assertEquals(0L, mongo.count(new Query(), Profile.class));

        mongo.insert(new Profile(
                "p-1", "one@example.test", "An"));

        assertEquals(1L, mongo.count(new Query(), Profile.class));
        assertEquals("An",
                mongo.findById("p-1", Profile.class)
                        .getDisplayName());
    }

    @Test
    void uniqueIndexIsPresentAfterEveryReset() {
        List<IndexInfo> indexes =
                mongo.indexOps(Profile.class).getIndexInfo();

        assertTrue(indexes.stream().anyMatch(index ->
                index.isUnique()
                && index.isIndexForFields(List.of("email"))));

        mongo.insert(new Profile(
                "p-2", "same@example.test", "Mai"));

        assertThrows(DuplicateKeyException.class, () ->
                mongo.insert(new Profile(
                        "p-3", "same@example.test", "Minh")));
    }

    @Test
    void deletingDocumentsKeepsIndexMetadata() {
        mongo.insert(new Profile(
                "p-4", "four@example.test", "Lan"));

        mongo.remove(new Query(), Profile.class);

        assertEquals(0L, mongo.count(new Query(), Profile.class));

        List<IndexInfo> indexes =
                mongo.indexOps(Profile.class).getIndexInfo();

        assertTrue(indexes.stream().anyMatch(index ->
                index.isUnique()
                && index.isIndexForFields(List.of("email"))));
    }
}
```

### 18.1. Why is this test more trustworthy than "save then findAll"?

- Every test enters `@BeforeEach` with a cleanly reset collection in **the test class's own database**.
- The unique index is **re-ensured after reset**, so the test preserves constraints.
- The tests check document counts, email uniqueness, and the difference between `remove` and `dropCollection`.
- `@AfterEach` drops the collection and asserts it is gone; cleanup failures fail the test.
- The database name includes a UUID, reducing collision risk even if runs share a container/backend.
- Does not rely on execution order across the three `@Test` methods, and never adds `@TestMethodOrder` to mask contamination.

### 18.2. Limitations of the Mongo demo

- The test does not use Mongo transactions or sessions, so it does not prove multi-document transactions.
- Does not include TTL indexes or partial indexes, only a unique index.
- Does not run against real MongoDB Atlas, a sharded cluster, or an auth/TLS-enabled environment.
- The container is a small external MongoDB instance managed by Testcontainers, without production infrastructure.
- `@DataMongoTest` does not test full Spring Boot business services or HTTP mapping.
- Within the same class, if JUnit **parallel methods** are enabled on the same database/collection, one method can drop another method's collection. The example assumes **sequential method execution**. For parallel runs, use a **per-method** database/collection namespace or disable parallelism for this test group.

## 19. Redis integration tests: namespace + owned keys + TTL

**`src/test/java/com/example/nosqlcleanup/RedisKeyCleanupTest.java`**

```java
package com.example.nosqlcleanup;

import java.time.Duration;
import java.util.HashSet;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.redis.DataRedisTest;
import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.ScanOptions;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@DataRedisTest
class RedisKeyCleanupTest {

    private static final int REDIS_PORT = 6379;

    @Container
    static final GenericContainer<?> REDIS =
            new GenericContainer<>(
                    DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(REDIS_PORT);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add("spring.data.redis.port",
                () -> REDIS.getMappedPort(REDIS_PORT));
    }

    @Autowired
    StringRedisTemplate redis;

    // JUnit Jupiter creates one test class instance per method by default.
    private final String namespace =
            "it:cleanup:" + UUID.randomUUID() + ":";

    private final Set<String> ownedKeys = new HashSet<>();

    private String ownedKey(String suffix) {
        String key = namespace + suffix;
        ownedKeys.add(key);
        return key;
    }

    @AfterEach
    void deleteOnlyKeysCreatedByThisTest() {
        if (!ownedKeys.isEmpty()) {
            redis.delete(ownedKeys);
        }
        for (String key : ownedKeys) {
            assertFalse(Boolean.TRUE.equals(redis.hasKey(key)));
        }
    }

    @Test
    void stringKeyIsReadableAndOwnedByTest() {
        String key = ownedKey("profile:p-1");

        redis.opsForValue().set(key, "An");

        assertEquals("An", redis.opsForValue().get(key));
        assertTrue(Boolean.TRUE.equals(redis.hasKey(key)));
    }

    @Test
    void hashKeyIsAlsoCleanedUpBySameOwnershipList() {
        String key = ownedKey("profile:p-2");

        redis.opsForHash().put(key, "name", "Mai");
        redis.opsForHash().put(key, "role", "reader");

        assertEquals("Mai",
                redis.opsForHash().get(key, "name"));
        assertEquals("reader",
                redis.opsForHash().get(key, "role"));
    }

    @Test
    void ttlIsCheckedWithoutSleeping() {
        String key = ownedKey("session:p-3");

        redis.opsForValue().set(
                key, "active", Duration.ofMinutes(5));

        Long ttlSeconds = redis.getExpire(
                key, TimeUnit.SECONDS);

        assertNotNull(ttlSeconds);
        assertTrue(ttlSeconds > 0L);
        assertEquals("active", redis.opsForValue().get(key));
    }

    @Test
    void scanCanFindOnlyCurrentTestNamespace() {
        String keyA = ownedKey("product:BOOK");
        String keyB = ownedKey("product:PEN");

        redis.opsForValue().set(keyA, "available");
        redis.opsForValue().set(keyB, "available");

        ScanOptions options = ScanOptions.scanOptions()
                .match(namespace + "*")
                .count(100)
                .build();

        Set<String> seen = new HashSet<>();
        try (Cursor<String> cursor = redis.scan(options)) {
            while (cursor.hasNext()) {
                seen.add(cursor.next());
            }
        }

        assertTrue(seen.contains(keyA));
        assertTrue(seen.contains(keyB));
        assertTrue(seen.stream()
                .allMatch(key -> key.startsWith(namespace)));
    }
}
```

### 19.1. Why does cleanup use `ownedKeys`?

- The test knows the exact keys it created.
- Both a Hash and a String live under **the same key namespace**, so `redis.delete(key)` cleans up either.
- Avoids scanning the entire Redis keyspace.
- Avoids `FLUSHDB` or `FLUSHALL`, protecting sessions/caches of other tests.
- Keys are registered **before writing**, so if a write succeeds and the test subsequently throws, `@AfterEach` still knows to delete the key.
- After cleanup, the test re-checks `hasKey(...)`. That also catches Redis connection failures during teardown.

### 19.2. Cases where individual key tracking is impossible

If a background job creates new keys dynamically under a namespace, tracking `ownedKeys` upfront is insufficient. In a **dedicated Redis test container/instance**, you can scan `it:cleanup:<runId>:*` and delete discovered keys. Stop jobs/writers before cleanup and keep in mind `SCAN` does not guarantee an atomic snapshot. Never run that algorithm on a shared namespace used by other teams.

### 19.3. What does the Redis test not protect yet?

- That TTL **literally expires after exactly five minutes**; the test only verifies the TTL was set.
- Redis Cluster, Sentinel, replication, failover, eviction policies, or memory pressure.
- Spring Cache annotations/proxy key generators of business services.
- Redis transactions/Lua scripting or multi-client concurrency.
- Real production authentication/TLS/ACLs.

When these factors pose critical risks, add specialized adapter/configuration tests in a controlled environment.

## 20. Running the sample suite and interpreting results

With Docker running and a Gradle wrapper in the project:

```bash
./gradlew test --tests com.example.nosqlcleanup.ProfileMongoCleanupTest --tests com.example.nosqlcleanup.RedisKeyCleanupTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests com.example.nosqlcleanup.ProfileMongoCleanupTest --tests com.example.nosqlcleanup.RedisKeyCleanupTest
```

If creating a new project without a Gradle wrapper, generate one using your development environment's Gradle or IDE and commit it per project policy. In a multi-module build, run the appropriate `:your-module:test` task.

**Expected test method counts:**

| Class | Test count | What is observed |
|---|---:|---|
| `ProfileMongoCleanupTest` | 3 | Clean collection, unique index, `remove` vs. `drop` |
| `RedisKeyCleanupTest` | 4 | String key, Hash key, TTL, prefix `SCAN` |
| **Total** | **7** | Independent Mongo and Redis test slices |

When Docker, images, network permissions, dependencies, and sources match the example, tests are expected to pass and Gradle reports `BUILD SUCCESSFUL`. **This is an expected outcome from reviewing the code and APIs**, not a claim that Docker/Gradle were executed in the current repository.

There is no fixed business stdout. Mongo/Redis container IDs, host ports, and startup logs vary per run. JUnit HTML reports normally appear at `build/reports/tests/test/index.html` and XML at `build/test-results/test/`.

### 20.1. Why not use `@Transactional` rollback like JDBC?

MongoDB and Redis do not automatically participate together in a Spring JDBC transaction. Mongo has its own transactions when a replica set/session and transaction manager are configured; Redis has `MULTI/EXEC` semantics and many APIs do not auto-enlist into Spring transactions like JDBC. **Do not put `@Transactional` on a test and assume both Mongo documents and Redis keys roll back together.**

In this example, **explicit cleanup** is the contract. For a use case writing to both Mongo and Redis, design consistency/failure recovery and test each boundary.

## 21. Cleanup by key vs. cleanup by pattern

Comparison:

| Option | Safety | When appropriate |
|---|---|---|
| `redis.delete("it:run:test:key")` | High when key belongs to test | Single known key |
| `redis.delete(ownedKeys)` | High when tracked thoroughly | Single test creating multiple keys |
| `SCAN match("it:run:*")` then delete | Moderate with exclusive namespace | Background job creates unpredictable keys |
| `KEYS "it:run:*"` then delete | Can block depending on keyspace size | Small, isolated Redis only; not preferred |
| `FLUSHDB` | Very dangerous on shared DBs | Exclusive Redis instance only |
| `FLUSHALL` | Very dangerous on shared instances | Almost never needed for method tests |

A namespace must be **collision-free**. A prefix like `test:*` is unsafe if multiple builds share Redis. A prefix containing `runId`/`testId` generated before the test prevents Build A from deleting Build B's keys.

Because pattern cleanup interprets Redis glob characters (such as `*`, `?`), never construct namespaces from unsanitized input; stick to safe ASCII alphanumeric/hyphen/UUID characters.

## 22. Cleanup and parallel test execution

JUnit 5 can execute tests in parallel when enabled. Under parallelism:

- Two Mongo methods sharing a database/collection and running `dropCollection` will race.
- Two Redis methods using separate keys can run concurrently more safely, provided test instance lifecycles and client thread-safety are sound.
- An Elasticsearch index alias updated by Test A can alter Test B's query results.
- Spring context caching reusing singleton Mongo/Redis clients does not provide data isolation.
- Creating one container per class does not isolate **methods within that class** if they share one collection.

**Four ways to handle this:**

1. Disable parallel execution for test classes sharing a collection.
2. Create a **per-method collection name** and pass it explicitly to `MongoTemplate`.
3. Create a **per-method database** or container when the cost is acceptable.
4. Guard parallel tests with resource locks on shared state.

In JUnit Jupiter you can use:

```java
// Illustrative snippet: placed on a class sharing a single collection.
@Execution(ExecutionMode.SAME_THREAD)
class SequentialMongoTests {
    // ...
}
```

Requires imports `org.junit.jupiter.api.parallel.Execution` and `ExecutionMode`. This is not a file in the runnable example; when enabling parallel classes/methods in a repo, define clear isolation policies. **Never rely on execution order to hide bugs.**

## 23. Automatic MongoDB indexes: the drop/recreate trap

If a domain model declares:

```java
// Snippet inside a @Document class.
@Indexed(unique = true)
private String email;
```

do not assume that after `mongo.dropCollection(Profile.class)`, the unique index will immediately reappear. Index creation has its own lifecycle and auto-index creation may be disabled by default. When tests need indexes:

- Run the application's **real index migration/setup**, or
- Call `ensureIndex(...)` explicitly after resetting.
- Assert both index metadata and duplicate-insert behavior.
- Keep all operations inside the test database.

**A common bug:** a test catches `DuplicateKeyException` on its first run (because bootstrap created the index), then after another test drops the collection, the duplicate test runs again and fails to throw because the index vanished. "Fixing" it by removing the assertion destroys integrity protection. The real fix is **recreating the index deterministically** or switching cleanup from `drop` to `remove`.

## 24. Elasticsearch search: eventual visibility and index cleanup

Near-real-time search engines do not behave like Mongo CRUD.

A test doing:

```text
PUT document -> HTTP acknowledged
immediate GET/search -> document may not appear in search yet
DELETE document -> immediate search -> may still appear
```

can be flaky because of refresh cycles. Remedies:

- Use an **appropriate refresh policy for tests**, or invoke the refresh API on the **test index** after writes/deletes when the contract expects immediate queries.
- When modeling real-world eventual consistency, use bounded eventual assertions instead of forcing fake strong consistency.
- Give each test/run its own index name; clean up aliases and indexes **owned by the run**.
- Avoid `Thread.sleep(1000)` as a default solution; refresh timings vary under load and CI.
- If tested APIs trigger asynchronous indexing pipelines, wait until the job completes before cleanup; otherwise a still-running job can recreate data after the test already ran cleanup.

**Index metadata is also a fixture.** If expected searches rely on custom analyzers/mappings, deleting only documents while reusing stale mappings keeps tests from reflecting new migrations. When testing schema migrations, create a fresh index using the target version's mappings.

## 25. TTL, cache expiration, and virtual time

Redis `EXPIRE` and Mongo TTL indexes do not promise "deleted at the exact JUnit wall-clock millisecond".

- Redis uses lazy and active expiration; keys disappear on access or during periodic background sweeps.
- Mongo's TTL monitor runs on a background interval, so documents are not guaranteed to vanish the instant their timestamp passes.
- Caffeine/local caches have their own clocks and eviction policies.
- Elasticsearch ILM involves lifecycle delays.

**To test TTL properly:**

1. Verify that the TTL/`expires-at` **was configured** accurately right after writing.
2. If actual expiry must be tested, use a bounded timeout and observe until the key/document vanishes rather than demanding millisecond precision.
3. When domain logic relies on clocks, inject `Clock.fixed` and unit test without waiting on real wall time.
4. Do not equate **domain-level token expiration** with physical backend cleanup: a token may be logically expired before the backend deletes its key.

Often the best combination is **unit tests for time logic**, **a few integration tests for real TTLs**, and explicit teardown cleanup rather than waiting on expiration.

## 26. What happens when cleanup fails mid-way?

Suppose a test creates three resources:

```text
Mongo profile document
Redis cache key
Elasticsearch search document
```

If teardown deletes Mongo first and the Mongo connection fails, code should not bail out immediately and skip Redis/Elasticsearch silently. Execute separate cleanup steps, collect failures via JUnit extensions/`finally`, and **propagate all failures** after attempting the remaining cleanups.

Conceptual pseudo-code:

```text
cleanupFailures = []

try deleteMongoOwnedData
catch error: collect error

try deleteRedisOwnedKeys
catch error: collect error

try deleteSearchOwnedIndex
catch error: collect error

if cleanupFailures not empty:
    fail test run with all cleanup errors
```

**This is pseudo-code**, not runnable Java/Gradle. In real implementations, use proper exception aggregation so the first error is never lost; never escalate to broad wipes when ownership is unknown.

If both the test and cleanup fail, report both the **test failure** and the **teardown failure**. Retaining resources for debugging must follow security and retention policies, never leaving PII-bearing test artifacts alive indefinitely for convenience.

## 27. Managing data by test run and CI

In CI, generate a run ID:

```text
build-20261108-17823
```

It must prevent collisions across branches and reruns. When reading CI job identifiers from environment variables, validate and sanitize characters to fit database/index/bucket/key naming rules. Never put secrets inside resource names.

A simple inventory:

| Field | Example |
|---|---|
| Owner | CI job or local developer test profile |
| Run ID | `it-17823-a42b` |
| Backend | Mongo/Redis/Elasticsearch |
| Resource | database, collection, key prefix, index alias |
| Created at | timestamp for operational cleanup |
| TTL | max lifetime if a job dies |
| Cleanup strategy | afterEach/afterAll/container disposal/janitor |
| Safety guard | verified test host/environment, prefix allowlist |

With ephemeral Testcontainers, the runtime/container lifecycle already provides strong protection. On shared staging, use a dedicated janitor scoped exclusively to deleting test resources; never grant broad production delete rights.

## 28. Test fixture data must be trustworthy

An issue unrelated to cleanup directly yet often blamed on it: fixtures built from unstable real data.

**Do:**

- Use synthetic IDs/emails that cannot collide across runs.
- Build fixtures in setup from an explicit factory/builder.
- Assert counts and IDs within your test's scope rather than assuming the entire DB holds only one document when other tests exist.
- Filter queries by run ID/tenant ID when a backend is shared.
- Set up the exact indexes/mappings/schemas needed by queries under test.
- Separate "normal", "duplicate", "expired", and "invalid" fixtures with clear names.
- Keep seed data deterministic whenever tests are not verifying randomness.

**Avoid:**

- Hardcoding document IDs shared by parallel tests.
- Ordering tests sequentially as `testCreate`, `testUpdate`, `testDelete`.
- Waiting on TTLs to expire data left by earlier tests.
- Comparing full collection counts without isolation.
- Dropping indexes without a plan to recreate them.
- Auto-updating fixtures from live state on every run.

## 29. Common failure modes and resolutions

| Symptom | Possible cause | Fix |
|---|---|---|
| Passes locally, fails in CI depending on order | Leftover data from earlier tests | Isolate namespaces, setup/teardown |
| Mongo duplicates not rejected | Index dropped or never ensured | Recreate unique index and assert metadata |
| Mongo query returns extra documents | Collection holds stale fixtures | Per-test DB/collection or scoped deletes |
| Unexpected Redis test cache hit | Key name reused, TTL still active | Run-specific keys, tracked cleanup |
| Redis test fails to delete keys | Connection failed or key missing from `ownedKeys` | Fail on teardown error, track keys before write |
| Redis `KEYS` slows down suite | Scanning whole keyspace | Use targeted keys or `SCAN` |
| `FLUSHDB` wipes another environment's data | Shared Redis logical DB | Dedicated instance only, avoid broad commands |
| Search misses newly written record | Refresh has not occurred yet | Test refresh policy / bounded eventual assertions |
| Wrong Elasticsearch mapping after another test | Shared index with old mappings | Unique index + recreate mappings |
| Object storage "deleted" yet versions remain | Versioning/delete markers | Version-aware cleanup / dedicated test bucket |
| TTL test passes before expiring | Asserted only TTL was set, not actual expiry | Add separate eventual-expiry test if required |
| Fresh Spring context cache yet data remains | External DB/cache outlives Spring context | Clean external state; do not abuse `@DirtiesContext` |
| Test deletes active test's data | Shared collection/prefix under parallel tests | Per-method namespace or resource locks |
| Docker missing, Testcontainers fails | CI lacks daemon/socket/image access | Configure Docker runtime and image pull permissions |
| Cleanup runs against wrong cluster | Wrong property/environment override | Dynamic properties + test-only credentials + guards |
| Mongo `dropCollection` runs, index disappears | Auto-index does not recreate itself | Call `ensureIndex` after every reset |
| Test failure hides cleanup error | Teardown only logs and swallows error | Aggregate/propagate cleanup failures |

## 30. Practice exercises

### Exercise A — Mongo collections and unique indexes

Test A calls `dropCollection(Profile.class)`, after which inserting two users with the same email and different IDs succeeds. Previously duplicates threw `DuplicateKeyException`. What must be fixed? Contrast `remove(new Query())` and `dropCollection`.

**Answer:** Dropping the collection deleted the unique index. To clear only documents, use `remove`; if dropping is needed, call `createCollection` and `ensureIndex(unique)` before inserting.

### Exercise B — Leftover Redis cache from an earlier test

Test B expects a cache miss on `user:41`, yet Test A left that key in Redis. Should you relax the assertion to accept a cache hit?

**Answer:** No. Use test-specific namespaces/keys, clean up after tests, and assert preconditions. Only accept a hit when testing a hit scenario intentionally.

### Exercise C — Is `FLUSHDB` safe?

Two CI jobs share the same Redis instance/logical DB. One test calls `FLUSHDB` in `@AfterEach`. What happens, and what is the fix?

**Answer:** It can wipe the other job's keys. Use a dedicated Redis instance or per-job prefixes + tracked keys, never flush a shared database.

### Exercise D — Flaky TTL test

A test sets a 1-second TTL, calls `Thread.sleep(1000)`, and asserts the Redis key is gone. Why is it flaky?

**Answer:** Scheduling, network latency, timer resolution, and server expiration processing vary. Use bounded eventual assertions and verify TTL metadata instead of hard sleeps.

### Exercise E — Elasticsearch index vs. Mongo index

Test X deletes Elasticsearch index `it-orders-123`. Test Y drops a Mongo unique index on `profiles`. Do both operations have the same impact?

**Answer:** No. An Elasticsearch index holds documents and mappings; a Mongo index is a query/constraint structure on a collection. Each needs a different recreation and test strategy.

### Exercise F — Spring context vs. external data

A team puts `@DirtiesContext` on a test and claims "all Redis keys were wiped because the Spring context restarted". Is that true?

**Answer:** No. Context caching/lifecycle does not clean external Redis. Delete keys or isolate namespaces/containers explicitly.

### Exercise G — Parallel Mongo tests

Two JUnit methods share database `it_shared` and collection `profiles`; both run `@BeforeEach dropCollection`. Which test can fail?

**Answer:** Any test querying or inserting while the other method drops the collection. Use per-method collections/databases, resource locks, or `SAME_THREAD`.

### Exercise H — What is an index fixture?

The unique index on `email` must exist so the API rejects duplicates. Is asserting Mongo count equals 0 before the test enough to verify the precondition?

**Answer:** No. A count of 0 does not prove the index exists. Ensure the index and verify both metadata and duplicate rejection.

### Exercise I — Test logic passes yet cleanup fails

A test inserts into Mongo and Redis successfully, yet `@AfterEach` fails to connect to Redis. Should it merely log a warning and report PASS?

**Answer:** No. A cleanup failure is an independent failure that must be surfaced to prevent poisoning subsequent runs. Fail the run and maintain janitor/TTL or container disposal safeguards.

### Exercise J — Choosing test levels

You want to test cache invalidation when a Mongo profile changes. Are two separate slice tests enough?

**Answer:** Not yet. You need a `@SpringBootTest` or targeted integration test wiring the real service with real Mongo/Redis clients in a test environment to assert the update + cache invalidation workflow; keep slice tests to isolate individual boundaries.

## 31. Completion checklist

- [ ] Backend under test is **test-only**, never a production database/index/bucket.
- [ ] Every created resource has a clear owner/run ID.
- [ ] I know whether cleanup deletes documents or entire collections/indexes/mappings.
- [ ] MongoDB `dropCollection` deletes indexes, and tests recreate required indexes.
- [ ] Unique/TTL/partial indexes are verified via both metadata and contractual behavior.
- [ ] Redis keys use namespaces preventing collisions with other tests.
- [ ] I prefer deleting tracked key lists rather than reckless `FLUSHALL`/`FLUSHDB`.
- [ ] When using `SCAN`, I account for non-atomic iteration and close the cursor.
- [ ] Redis TTL/expiration tests do not rely on arbitrary sleeps.
- [ ] Elasticsearch indexes, aliases, templates, and refreshes are treated as test resources.
- [ ] Object storage versioning and prefix cleanup are handled if used.
- [ ] Testcontainers and `@DynamicPropertySource` supply accurate dynamic hosts/ports.
- [ ] `@DataMongoTest` and `@DataRedisTest` are used when only data slices are needed.
- [ ] Business workflows spanning Mongo + Redis have their own integration tests where needed.
- [ ] Each test defines clear preconditions and scoped cleanup.
- [ ] Cleanup failures fail the test run instead of swallowing exceptions.
- [ ] `@DirtiesContext` is never treated as a substitute for cleaning external data.
- [ ] When parallel tests are enabled, databases/collections/indexes/key prefixes are separated or resource-locked.
- [ ] Fixture data is synthetic and free of real credentials/PII.
- [ ] Tests do not depend on execution order or leftover CI keys/indexes.
- [ ] H2/JPA transaction rules are never assumed to apply to Mongo/Redis.
- [ ] Untested production aspects (TLS, clustering, failover, production mappings) are stated honestly.

**Conclusion:** Cleaning up data between tests is not merely deleting as fast as possible. With **MongoDB**, separate document cleanup from collection/index lifecycles. With **Redis**, key ownership and namespaces determine safety; TTL does not replace cleanup, and `SCAN` does not replace isolation. With **Elasticsearch/object storage**, indexes/aliases/mappings and object versioning add metadata and consistency semantics you must manage. Reliable tests start from isolated resources, build deterministic fixtures/indexes, test behavior on matching backends, clean up by owner — and **fail loudly when cleanup fails**.

### Official references

- Spring Boot 3.5 — Testing Testcontainers, `@Container`, `@DynamicPropertySource`: https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html
- Spring Boot 3.5 — Test slices (`@DataMongoTest`, `@DataRedisTest`): https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html
- Spring Data MongoDB — Collection and Index Management: https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-collection-management.html
- Spring Data MongoDB — Index Creation Lifecycle: https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping-index-management.html
- Spring Data Redis — `RedisTemplate.scan(ScanOptions)` / `keys(...)`: https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/core/RedisTemplate.html
- Testcontainers — MongoDB module: https://java.testcontainers.org/modules/databases/mongodb/
- Redis — SCAN semantics: https://redis.io/docs/latest/commands/scan/
- Redis — Key expiration: https://redis.io/docs/latest/commands/expire/
- Elasticsearch — Index management: https://www.elastic.co/guide/en/elasticsearch/reference/current/indices.html
- JUnit Jupiter — Test Instance Lifecycle and Before/After callbacks: https://junit.org/junit5/docs/current/user-guide/
