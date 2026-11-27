# Semantics of `save`, `findById`, `existsById`, and `deleteById` in Spring Data Redis

## 1. The Four Core Operations of a Redis Repository

Spring Data Redis provides Repositories that let you work with Java objects as entities with an **identifier (ID)**. For an entity annotated with `@RedisHash`, the Repository can store the object in Redis as a Hash, retrieve it by ID, check its existence, and delete it.

The four most common methods are:

~~~java
<S extends T> S save(S entity);
Optional<T> findById(ID id);
boolean existsById(ID id);
void deleteById(ID id);
~~~

These signatures come from Spring Data's `CrudRepository<T, ID>` contract. They represent four distinct intents:

| Method | Intent | Result | Key point to remember |
|---|---|---|---|
| `save(entity)` | Save the object's current state by ID | Returns the saved entity | May **create or overwrite** a record with the same ID; not by default a partial update of a few fields |
| `findById(id)` | Read and convert the Redis Hash into a Java object | `Optional<T>` | Returns `Optional.empty()` when not found, never `null` |
| `existsById(id)` | Check whether a record exists for the ID | `boolean` | Only a point-in-time check; does not lock the record |
| `deleteById(id)` | Delete the record with the given ID | `void` | Normally ignored if no record exists; does not return a deleted count |

The goal of this lesson is to understand the **semantics** of each operation, especially when data changes, keys expire, multiple processes update concurrently, or a Redis Hash contains extra fields not declared in the Java class.

## 2. Data Model: ID, Keyspace, and Redis Hash

Suppose there is a Java class `Article` with ID `a-101`. When using:

~~~java
@RedisHash("articles")
public class Article {
    @Id
    private String id;
    private String title;
}
~~~

The Repository typically stores the entity in a Redis key:

~~~text
Redis key: articles:a-101
Redis type: hash

id     -> a-101
title  -> Spring Data Redis
_class -> com.example.redis.model.Article
~~~

Where:

- `articles` is the **keyspace**, declared in `@RedisHash("articles")`.
- `a-101` is the **ID** of the entity.
- `articles:a-101` is the **Redis key** of the record.
- `id`, `title`, and `_class` are **fields of the Redis Hash**.

General form:

~~~text
@RedisHash("<keyspace>") + @Id <id>
                 |
                 v
       Redis key "<keyspace>:<id>"
                 |
                 v
         Hash of entity fields
~~~

The exact key name and encoding may depend on mapping configuration, serializers, and IDs. This lesson's examples use a standard Repository configuration with `String` IDs.

**Distinction:** `findById("a-101")` takes the **ID** `a-101`, not the full string `articles:a-101`. The Repository builds the Redis key according to the entity type's keyspace.

## 3. Minimal Spring Boot Example

### 3.1. Dependency and Redis Connection

In a Spring Boot project using Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
~~~

Or with Gradle:

~~~gradle
implementation 'org.springframework.boot:spring-boot-starter-data-redis'
~~~

To let Spring Boot manage compatible versions, use the appropriate Spring Boot BOM/parent or plugin for your project.

Example `application.yml` configuration:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
~~~

Run Redis locally for development with Docker if no Redis service is running yet:

~~~bash
docker run --rm --name redis-repository-demo -p 6379:6379 redis:7-alpine
~~~

### 3.2. Declaring the Entity

File `src/main/java/com/example/redis/model/Article.java`:

~~~java
package com.example.redis.model;

import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("articles")
public class Article {

    @Id
    private String id;

    private String title;

    @Indexed
    private String category;

    private int viewCount;

    public Article() {
    }

    public Article(String id, String title, String category, int viewCount) {
        this.id = id;
        this.title = title;
        this.category = category;
        this.viewCount = viewCount;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public String getCategory() {
        return category;
    }

    public void setCategory(String category) {
        this.category = category;
    }

    public int getViewCount() {
        return viewCount;
    }

    public void setViewCount(int viewCount) {
        this.viewCount = viewCount;
    }
}
~~~

`@Id` resides in the `org.springframework.data.annotation` package. `@Indexed` is added to illustrate that the Repository also manages **secondary indexes** outside the main Redis Hash; it is not required when operating only by ID.

### 3.3. Declaring the Repository

File `src/main/java/com/example/redis/repository/ArticleRepository.java`:

~~~java
package com.example.redis.repository;

import com.example.redis.model.Article;
import org.springframework.data.repository.CrudRepository;

public interface ArticleRepository extends CrudRepository<Article, String> {
}
~~~

In `CrudRepository<Article, String>`:

- `Article` is the stored object type.
- `String` is the data type of the `@Id` field.
- The four methods studied here are inherited, with no need to write SQL or Redis commands manually.

Place the `@SpringBootApplication` startup class in the parent package `com.example.redis` so Spring Boot can discover entities and Repositories under common conventions. When Repositories are outside the scan scope, configure Repository scanning accordingly, such as with `@EnableRedisRepositories`.

## 4. `save(entity)`: Saving an Object by ID

### 4.1. Creating New When No Record Exists for the ID

Suppose Redis does not yet have the key `articles:a-101`:

~~~java
Article article = new Article(
    "a-101",
    "Learning Redis Repository",
    "spring",
    10
);

Article saved = articleRepository.save(article);
System.out.println(saved.getId()); // a-101
~~~

Logical state:

~~~text
Before save:
    articles:a-101          (does not exist)

After save:
    articles:a-101          (Redis Hash)
        id        = a-101
        title     = Learning Redis Repository
        category  = spring
        viewCount = 10
        _class    = ...
~~~

The Repository takes the ID, determines the keyspace, converts Java properties into appropriate fields, and persists the data. If `@Indexed` is enabled, the save operation can also update auxiliary keys used to look up by `category`.

### 4.2. Same ID: Overwriting State, Not Creating a Second Record

~~~java
Article updated = new Article(
    "a-101",
    "Advanced Redis Repository",
    "backend",
    25
);

articleRepository.save(updated);
~~~

Two `save` calls using the same ID `a-101` correspond to **a single Redis key** `articles:a-101`. The second call writes the new state of that entity; it does not create `articles:a-102` or append "another row" like an append operation.

| Field | Before second save | After second save |
|---|---|---|
| `id` | `a-101` | `a-101` |
| `title` | Learning Redis Repository | Advanced Redis Repository |
| `category` | spring | backend |
| `viewCount` | 10 | 25 |

Important point: `save` is an operation that persists **entity state**. With standard Object-to-Hash Mapping in Redis Repository, updating may **delete the old Hash contents and write the fields from the new object**. Therefore, do not think of `save` as an `HSET` command that only modifies differing fields.

Example:

~~~text
Hash before:
    id          = a-101
    title       = Learning Redis
    viewCount   = 10
    debugFlag   = manually-added

Java object passed to save:
    id          = a-101
    title       = Advanced Redis
    viewCount   = 20
    (no debugFlag property)

Hash after Repository save:
    id          = a-101
    title       = Advanced Redis
    viewCount   = 20
    (debugFlag may be removed)
~~~

If another application manages `debugFlag`, store it in a separate key or incorporate it explicitly into the data model. Mixing manual field writes with `repository.save` on the same key easily causes data loss.

### 4.3. When the ID Is Unassigned

For an entity with `@Id String id`, Spring Data Redis can generate an ID when saving an object whose ID is still `null`:

~~~java
Article newArticle = new Article(
    null,
    "Article without ID",
    "java",
    0
);

Article saved = articleRepository.save(newArticle);
String generatedId = saved.getId();
~~~

The new ID becomes the identifier portion of the Redis key. **Always use the object returned by `save`** for subsequent operations: per the Spring Data contract, the returned object may be modified or replaced during saving, so do not assume it is always the exact same initial Java instance.

If you want to update an existing record, keep and reuse the **exact ID**. Creating a new object with a `null` ID and calling `save` generally produces another entity rather than updating the existing record.

### 4.4. Changing the ID Does Not Mean Renaming the Key

Suppose `a-101` was saved, and then the object's ID is changed to `a-999` and `save` is called:

~~~java
Article article = articleRepository.findById("a-101").orElseThrow();
article.setId("a-999");

articleRepository.save(article);
~~~

Now the new ID points to the new key `articles:a-999`. Do not assume the old record `articles:a-101` is automatically deleted. To truly migrate an identifier, design business logic to create the new key, update references, and deliberately delete the old key.

**Design rule:** An entity's ID should remain stable throughout the record's lifecycle.

### 4.5. `save` Is Not an Insert-Only Guarantee

`save` has no built-in condition like "create only if ID does not exist" (`INSERT IF ABSENT`). If two calls use the same ID, the later call may overwrite the earlier value.

If the system needs to **prevent duplicate IDs** or guarantee creation only when a key does not yet exist, use an appropriate conditional/atomic mechanism compatible with Redis and how the Repository manages indexes, rather than calling `existsById` followed by `save`.

## 5. `findById(id)`: Reading a Hash and Reconstructing the Object

### 5.1. When the Record Exists

~~~java
Optional<Article> maybeArticle =
    articleRepository.findById("a-101");

maybeArticle.ifPresent(article ->
    System.out.println(article.getTitle())
);
~~~

Logically, the Repository performs:

~~~text
findById("a-101")
      |
      v
Select key "articles:a-101"
      |
      v
Read Redis Hash fields
      |
      v
Convert Hash -> Article
      |
      v
Optional containing Article
~~~

If the data was saved in the expected structure, `getId()` returns `a-101`, and `getTitle()` receives the value from the Hash.

`findById` relies on the entity's **ID/key**. You do not need `@Indexed` on `title` or `category` to look up by ID; secondary indexes serve other query patterns.

### 5.2. When No Record Exists

~~~java
Optional<Article> missing =
    articleRepository.findById("not-found");

System.out.println(missing.isEmpty()); // true
~~~

The result is `Optional.empty()`. Therefore, the following code is inappropriate when a record may be missing:

~~~java
Article article = articleRepository.findById("not-found").get();
// NoSuchElementException because the Optional is empty.
~~~

Handle it according to business requirements:

~~~java
Article article = articleRepository.findById("a-101")
    .orElseThrow(() ->
        new IllegalArgumentException("Article does not exist: a-101")
    );
~~~

In a REST API layer, a missing record is typically translated into HTTP 404 by an appropriate exception handler. The Repository itself does not decide HTTP status codes.

### 5.3. A Hash May Exist Yet Java Mapping Still Fails

`Optional.empty()` applies when **the entity is not found by ID**. If the key exists but its contents were altered into an invalid format, type metadata mismatches, or the converter cannot instantiate the object, reading may throw a conversion error. Do not assume every Redis failure turns into `Optional.empty()`.

Common causes:

- The key does not hold a Hash as expected by the Repository.
- A field contains a data type that cannot be converted into the Java property.
- The class name, `@TypeAlias`, or class structure changed without migrating old data.
- A different serializer/mapper wrote directly to the Repository-managed key.

### 5.4. `findById` Normally Reads the Entire Entity Contents

Because the goal is to reconstruct a complete `Article`, this operation normally reads the Hash fields. If you only want to know whether the key exists, `existsById` expresses that intent more directly; if you need the entity contents, simply call `findById` without calling `existsById` first.

## 6. `existsById(id)`: Checking Existence at a Point in Time

### 6.1. `true` or `false` Result

~~~java
boolean beforeSave = articleRepository.existsById("a-101");

articleRepository.save(
    new Article("a-101", "Getting Started with Redis", "spring", 1)
);

boolean afterSave = articleRepository.existsById("a-101");
~~~

If no other actor modifies the data and the key does not expire between calls, `beforeSave` is `false` and `afterSave` is `true`.

Semantically, `existsById` asks Redis whether the record at the ID's key is currently present. With a standard Redis Repository, it can rely on a key existence check equivalent to `EXISTS`. It **does not mean** reading and validating the entire `Article` payload.

### 6.2. `true` Does Not Guarantee the Object Can Be Read

A key may be present while its contents do not conform to the format required by the Repository's converter. Therefore:

~~~java
if (articleRepository.existsById("a-101")) {
    // Cannot assume the data will always map into a valid Article.
}
~~~

When you need the data, read via `findById` and handle data errors if needed.

### 6.3. Check-Then-Act Is Not Atomic

The following snippet is prone to race conditions:

~~~java
if (!articleRepository.existsById("a-101")) {
    articleRepository.save(
        new Article("a-101", "New", "spring", 0)
    );
}
~~~

Two processes can interleave:

~~~text
Time        Process A                  Process B
---------   -----------------------    -----------------------
t1          existsById -> false
t2                                     existsById -> false
t3          save(article A)
t4                                     save(article B)
t5          Final record depends on write order
~~~

Even though both A and B saw `false`, the "save only if absent" condition **is not guaranteed** by chaining two independent methods.

Similarly, `existsById` returning `true` does not guarantee that `findById` immediately afterward will find the data: the key may be deleted or expire in between.

### 6.4. Choosing `existsById` vs. `findById`

**Only need a yes/no answer:**

~~~java
boolean exists = articleRepository.existsById(id);
~~~

**Need to read properties for processing:**

~~~java
Optional<Article> found = articleRepository.findById(id);

if (found.isPresent()) {
    Article article = found.get();
    // Use the loaded data.
}
~~~

Avoid:

~~~java
if (articleRepository.existsById(id)) {
    Article article = articleRepository.findById(id).orElseThrow();
    // Two round trips; data can still change between the two calls.
}
~~~

## 7. `deleteById(id)`: Deleting a Record by ID

### 7.1. Deleting a Saved Entity

~~~java
articleRepository.save(
    new Article("a-101", "To be deleted", "spring", 0)
);

articleRepository.deleteById("a-101");

boolean exists = articleRepository.existsById("a-101");
System.out.println(exists); // false if no concurrent write intervened
~~~

Logically, after `deleteById`, the entity key `articles:a-101` no longer exists. The Redis Repository also handles related management metadata, such as indexes maintained by the Repository itself according to the active version and configuration.

Do not equate `deleteById` with the application issuing only a single Redis `DEL` command, because the Repository may perform multiple operations to maintain secondary indexes and entity tracking data.

### 7.2. Deleting a Non-Existent ID

According to the `CrudRepository` contract, if no matching entity exists, `deleteById` is a no-op:

~~~java
articleRepository.deleteById("not-found");
// An existing record is not required for the delete call to succeed.
~~~

This makes deletion **idempotent in terms of final state**: calling it again still converges toward the state where the record is absent. However, each call may still issue Redis operations and encounter infrastructure errors; "ignored when absent" does not mean all errors are swallowed.

### 7.3. The Method Returns `void`, Not Whether Anything Was Actually Deleted

~~~java
articleRepository.deleteById("a-101");
~~~

You cannot tell from the return value whether the key previously existed. If business logic must distinguish "existed" from "never existed", you must build a dedicated feedback mechanism. Reading before deleting is a simple option but **is not atomic**, so it may be unsuitable when exact results are required under concurrency.

### 7.4. Deleting by ID Does Not Delete an Entire Object Graph

If `Article` holds a reference (`@Reference`) to an independent entity, `deleteById` must not be interpreted as a JPA-style cascade delete. Clearly define which records are managed and explicitly delete dependent entities when business logic requires it.

## 8. Complete Lifecycle: Save, Read, Check, Delete

Place the following in a Spring Boot application class:

~~~java
package com.example.redis;

import com.example.redis.model.Article;
import com.example.redis.repository.ArticleRepository;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class RedisRepositoryApplication {

    public static void main(String[] args) {
        SpringApplication.run(RedisRepositoryApplication.class, args);
    }

    @Bean
    CommandLineRunner demonstrate(ArticleRepository repository) {
        return args -> {
            String id = "a-101";

            // 1. Clean up any record from a previous run if present.
            repository.deleteById(id);

            System.out.println(repository.existsById(id)); // false

            // 2. Save a new record.
            Article first = new Article(
                id, "Redis Repository Basics", "spring", 5
            );
            Article saved = repository.save(first);

            System.out.println(saved.getId());              // a-101
            System.out.println(repository.existsById(id)); // true

            // 3. Read it back.
            Article loaded = repository.findById(id)
                .orElseThrow();
            System.out.println(loaded.getTitle());

            // 4. Update by saving the new state.
            loaded.setTitle("Advanced Redis Repository");
            loaded.setViewCount(6);
            repository.save(loaded);

            Article afterUpdate = repository.findById(id)
                .orElseThrow();
            System.out.println(afterUpdate.getTitle());
            System.out.println(afterUpdate.getViewCount());

            // 5. Delete and attempt to read again.
            repository.deleteById(id);
            System.out.println(repository.existsById(id)); // false
            System.out.println(repository.findById(id).isEmpty()); // true

            // 6. Repeated delete when absent.
            repository.deleteById(id);
        };
    }
}
~~~

Expected state progression of the primary key when no other process intervenes:

~~~text
No record exists
    |
    | save(Article{id="a-101", title="Redis Repository Basics"})
    v
articles:a-101 exists
    |
    | findById("a-101")      -> Optional<Article>
    | existsById("a-101")    -> true
    |
    | save(Article{id="a-101", title="Advanced Redis Repository"})
    v
articles:a-101 still exists, holding the new state
    |
    | deleteById("a-101")
    v
articles:a-101 does not exist
    |
    | findById("a-101")      -> Optional.empty()
    | existsById("a-101")    -> false
    | deleteById("a-101")    -> no-op for non-existent ID
~~~

Note that the output comments in the example assume Redis is available, properly configured, and free from concurrent writes or deletes from other sources.

## 9. Observing Redis Directly to Understand Behavior

If you pause the example after the save step and before the delete step, you can use `redis-cli` to observe the primary key.

After `save`:

~~~redis
TYPE articles:a-101
HGETALL articles:a-101
HGET articles:a-101 title
EXISTS articles:a-101
~~~

Logical output:

~~~text
TYPE       -> hash
HGETALL    -> includes id, title, category, viewCount, _class...
HGET title -> value of title
EXISTS     -> 1
~~~

After `deleteById`:

~~~redis
EXISTS articles:a-101
TYPE articles:a-101
HGETALL articles:a-101
~~~

Typical output:

~~~text
EXISTS  -> 0
TYPE    -> none
HGETALL -> no fields
~~~

Comparison table:

| Intent | Repository | Illustrative Redis CLI |
|---|---|---|
| Save object | `save(article)` | May include Hash write commands and metadata/index operations |
| Read object | `findById(id)` | Read Hash + convert data into Java |
| Check key | `existsById(id)` | `EXISTS articles:a-101` |
| Delete object | `deleteById(id)` | Delete primary key and handle related bookkeeping data |

**Redis CLI commands are only for illustrating the mechanism.** Do not use manual `HSET` or `DEL` instead of the Repository on the same key if you rely on secondary indexes, TTLs, keyspace metadata, or Spring Data Redis converters.

## 10. TTL: Present Now, Gone Later

A Redis entity can expire automatically. Example of a separate data type:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash(value = "temporary-articles", timeToLive = 60)
public class TemporaryArticle {

    @Id
    private String id;

    private String title;

    // Constructors and corresponding accessors.
}
~~~

`timeToLive = 60` sets a 60-second TTL for records saved under this configuration. The lifecycle can look like:

~~~text
t = 0s:
    save(entity)
    existsById(id) = true
    findById(id)   = Optional containing entity

t > 60s (after Redis processes expiration):
    existsById(id) = false
    findById(id)   = Optional.empty()
~~~

When needed, you can confirm the TTL with Redis CLI:

~~~redis
TTL temporary-articles:some-id
~~~

Several things to know:

- `existsById` does not guarantee the key will still exist on the next operation; the TTL can expire immediately after the check.
- `findById` does not distinguish whether a key is absent because it was never created, was deleted via the Repository, or expired.
- Calling `save` on an entity with TTL typically reapplies the expiration duration according to the configuration or the entity's current TTL property. Keep this in mind when using `save` as an update operation.
- Handling expiration events and cleaning secondary indexes has its own mechanism, depending on Redis keyspace notifications and Spring Data Redis configuration. Do not blindly treat secondary indexes as proof that an entity exists.

Besides a fixed TTL on `@RedisHash`, Spring Data Redis also supports a `@TimeToLive` property to manage TTL per entity. When short-lived storage is required, choose a consistent policy.

## 11. How Do Secondary Indexes Affect the Four Operations?

In the example, `Article.category` has `@Indexed`:

~~~java
@Indexed
private String category;
~~~

This annotation asks the Repository to maintain an index structure for querying by category, for example via a derived query method:

~~~java
public interface ArticleRepository
        extends CrudRepository<Article, String> {

    Iterable<Article> findByCategory(String category);
}
~~~

When calling:

~~~java
repository.save(new Article("a-101", "A", "spring", 1));
repository.save(new Article("a-101", "A", "backend", 1));
repository.deleteById("a-101");
~~~

The Repository must manage the association between the ID and indexed values when re-saving or deleting the entity. Therefore, the effects of `save` and `deleteById` can extend beyond the primary Hash `articles:a-101`.

Conversely:

- `findById` looks up by the ID's key and does not need to query the category index.
- `existsById` checks existence by ID and does not imply verifying that all secondary indexes are in sync.
- If you manually run `HSET` to change category in the Hash, the index can go out of sync with the actual data.
- `@Indexed` is not a unique constraint. Two `Article`s with different IDs can have the same category.

In a real application, only index properties that are truly queried, and route entity modifications through mechanisms that properly maintain indexes.

## 12. Updating a Single Field: Why Is `save` Sometimes Unsuitable?

Suppose you only want to increment `viewCount` from 10 to 11. An intuitive approach:

~~~java
Article article = repository.findById("a-101").orElseThrow();
article.setViewCount(article.getViewCount() + 1);
repository.save(article);
~~~

This is straightforward and suitable when there are no strict concurrent updates. However, two processes can both read `10`, both compute `11`, and both call `save`; the final result is `11` instead of `12`. This is a form of **lost update**.

~~~text
A reads viewCount = 10
B reads viewCount = 10
A sets 11 and saves
B sets 11 and saves
Result: 11 (one increment lost)
~~~

For high-concurrency counters, consider an atomic Redis update suited to Hashes, such as `HINCRBY`, instead of the read -> increment -> `save` sequence. Example using an application-managed key:

~~~redis
HINCRBY article-counters:a-101 views 1
~~~

Using a dedicated key `article-counters:a-101` avoids interfering with the entity Hash owned by the Repository. If the counter must live in the same entity, explicitly design synchronization between atomic counter updates and any `save` calls.

Spring Data Redis also provides `PartialUpdate` to selectively update specific properties on a Repository-managed key:

~~~java
import org.springframework.data.redis.core.PartialUpdate;
import org.springframework.data.redis.core.RedisKeyValueTemplate;

public void rename(RedisKeyValueTemplate template) {
    PartialUpdate<Article> update =
        new PartialUpdate<Article>("a-101", Article.class)
            .set("title", "New Title");

    template.update(update);
}
~~~

`PartialUpdate` avoids re-saving the entire object in appropriate cases, but **does not automatically turn** read–compute–write sequences into atomic operations, and its behavior with custom converters, collections, or indexes must be evaluated before applying.

## 13. When Do You Need Transactions, Locks, or Version Checks?

The four methods inherited from `CrudRepository` express CRUD operations, but a sequence of multiple calls is not automatically an atomic transaction.

Example business condition:

> Only allow deleting an article if its current status is `DRAFT`.

Code snippet:

~~~java
Article article = repository.findById(id).orElseThrow();

if ("DRAFT".equals(article.getStatus())) {
    repository.deleteById(id);
}
~~~

This only illustrates the idea when an entity has a `status` property; `Article` in the first example did not declare that property. The issue is that another process could change the status to `PUBLISHED` between the check and the delete.

To guarantee constraints in a concurrent environment, choose a synchronization mechanism suited to the data domain and Redis operations: conditional updates, version-control mechanisms supported by your library version, `WATCH`/`MULTI`, a Lua script, or a different data-writing design. You must also assess secondary index and TTL updates if stepping outside the Repository.

A single Redis command can execute atomically, but **multiple Repository methods called sequentially** do not automatically form an atomic operation with respect to other clients.

## 14. Input Errors and Infrastructure Errors

### 14.1. Passing `null`

Spring Data Repository contracts require non-null arguments in positions such as:

~~~java
repository.save(null);
repository.findById(null);
repository.existsById(null);
repository.deleteById(null);
~~~

These calls violate the method contract and typically throw `IllegalArgumentException`. Do not use `null` to represent "not found". For `findById`, use `Optional.empty()`.

### 14.2. Redis Unreachable

Network errors, Redis downtime, timeouts, or authentication failures are **operational errors**, not "entity does not exist". Do not convert all exceptions from `findById` into `Optional.empty()` or from `existsById` into `false`, as that masks real outages.

### 14.3. Keyspace or ID Differs from Expectations

~~~java
repository.findById("articles:a-101"); // Wrong intent if actual ID is "a-101".
repository.findById("a-101");          // Correct ID.
~~~

If Redis CLI shows `articles:a-101` but the Repository cannot find it, check the entity type, keyspace, ID, serializer configuration, and connected Redis database.

### 14.4. Using `save` as a Partial Update

If an object only has `id` and `title` populated, other Java properties may hold default values (`null`, `0`, etc.) when saved. Saving that object does not mean preserving all old fields. When only a few fields need updating, read the full entity before modifying or use an appropriate selective update mechanism.

### 14.5. Using `existsById` as a Uniqueness Guarantee

Checking `false` and then calling `save` does not prevent another process from creating the same ID. Enforcing uniqueness requires a conditional atomic mechanism rather than relying on this method pair.

### 14.6. Manually Deleting Redis Keys Instead of `deleteById`

If the Repository manages secondary indexes, running `DEL articles:a-101` directly may leave indexes uncleaned compared to deleting via the Repository. Unless you have explicitly built your own metadata cleanup mechanism, let the Repository delete the entities it manages.

## 15. Business Scenarios and Method Selection

| Scenario | Suitable approach | Reason |
|---|---|---|
| Create an article with a new ID | `save(newArticle)` | Writes entity state to Redis |
| Fully update an article with a known ID | `save(article)` | Saves the new state under the same key |
| Display article details | `findById(id)` | Needs properties; handles `Optional.empty()` |
| Only show "article exists/does not exist" | `existsById(id)` | Avoids reconstructing the whole entity |
| Delete article by ID | `deleteById(id)` | Deletes using Repository mechanics |
| Add article only if key does not exist, even under concurrency | Conditional atomic write mechanism | `existsById` + `save` has a race condition |
| Increment view count under high traffic | Dedicated atomic Redis counter | `findById` -> increment -> `save` can lose updates |
| Modify a single property | `PartialUpdate` or suitable field-update strategy | Reduces risk of overwriting the entire Hash |
| Must know for sure "an existing record was actually deleted" | Design a dedicated delete operation with atomic feedback | `deleteById` returns `void` |

## 16. State-Based Practice Exercises

### Exercise 1: Observing Create and Update

Write a program:

~~~java
Article first = new Article("lab-1", "Title A", "redis", 1);
repository.save(first);

Article second = new Article("lab-1", "Title B", "redis", 2);
repository.save(second);

Article result = repository.findById("lab-1").orElseThrow();
System.out.println(result.getTitle());
~~~

Predict the printed output, the number of primary Redis keys, and what happens to a field that only existed in the old Hash record.

### Exercise 2: Handling `Optional` Properly

~~~java
String title = repository.findById("unknown")
    .map(Article::getTitle)
    .orElse("(no article)");

System.out.println(title);
~~~

Explain why there is no need to call `existsById("unknown")` before this snippet.

### Exercise 3: Checking Before and After Delete

~~~java
String id = "lab-2";

repository.save(new Article(id, "To delete", "java", 0));
System.out.println(repository.existsById(id));

repository.deleteById(id);
System.out.println(repository.existsById(id));

repository.deleteById(id);
System.out.println(repository.findById(id).isPresent());
~~~

Predict the output assuming no concurrent access or TTL interference. Why is the second `deleteById` not a "record does not exist" error?

### Exercise 4: Concurrent Read -> Modify -> Save

Suppose two threads both load `Article{viewCount=100}`, increment by 1, and call `save`. Describe execution orders that can yield 101 instead of 102. Propose a Redis counter design that prevents lost increments.

### Exercise 5: TTL

Create an entity with `@RedisHash(timeToLive = 10)`. Save it with `save`, and check `existsById` and `findById` before and after Redis expires the key. Explain why reading `Optional.empty()` does not tell you whether the entity was explicitly deleted or expired automatically.

## 17. Key Takeaways

- `save` persists **entity state by ID**; when the ID already exists, the record at the same key is updated and fields outside the mapping model may be lost. Always treat the returned object as the result of the save operation.
- `findById` returns **`Optional<T>`**, so handle the not-found case explicitly. Reading malformed Hash data can still throw errors.
- `existsById` returns **`boolean`** at the time of the check; it does not lock data and does not guarantee preconditions for a subsequent `save`/`deleteById`.
- `deleteById` deletes by ID and returns **`void`**; non-existent IDs are ignored per the Repository contract.
- With `@RedisHash`, the ID is combined with the keyspace to determine the Redis key. The Repository may also manage secondary indexes and TTLs, so not every method can be treated as a single standalone Redis command.
- Business flows requiring compare-and-set, exact counters, or protection against concurrent overwrites need appropriate synchronization beyond calling the four CRUD methods sequentially.

### Further Reading

- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html)
- [Spring Data Redis — Redis Repositories: Usage](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/usage.html)
- [Spring Data Redis — Object-to-Hash Mapping](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/mapping.html)
- [Spring Data Redis — Secondary Indexes](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/indexes.html)
- [Spring Data Redis — Time To Live](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html)
- [Spring Data Commons — Core Concepts / Repository interfaces](https://docs.spring.io/spring-data/commons/reference/repositories/core-concepts.html)
