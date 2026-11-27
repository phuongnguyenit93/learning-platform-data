# Distinguishing Repository Hash Mapping from JSON via RedisTemplate

## 1. Both Store Java Objects in Redis, Yet the Data Can Look Very Different

Suppose a Spring Boot application has a customer object:

~~~java
Customer customer = new Customer(
        "c-101",
        "linh@example.com",
        "Nguyen Linh",
        new Address("Hanoi")
);
~~~

This object can be stored in Redis in two common ways:

1. Using **Spring Data Redis Repository** with `@RedisHash` and `CrudRepository`. Spring Data Redis maps the entity's properties into **fields inside a Redis Hash**.
2. Using **RedisTemplate** configured with a JSON serializer, then calling `opsForValue().set(...)`. Redis stores **a single String value** whose content is JSON representing the entire object.

Both allow the program to read a `Customer` object back, yet the storage format, Redis commands, querying, and data updates are completely different.

~~~text
                   Java Object Customer
                            |
              +-------------+--------------+
              |                            |
              v                            v
   Redis Repository                 RedisTemplate<String, Customer>
   @RedisHash + save(...)           + JSON value serializer
              |                            |
     Map each property               Serialize whole object as JSON
              |                            |
              v                            v
        Redis HASH                    Redis STRING
   key: customers:c-101          key: customer:json:c-101
   field email -> ...            value: {"id":"c-101", ...}
   field fullName -> ...
   field address.city -> ...
              |                            |
        HGET / HGETALL                  GET / SET
~~~

**Important point:** the class name `RedisTemplate` does not decide whether data is a Hash or JSON. **The operations/commands invoked** determine the Redis data type; **the serializer** determines how objects and values convert between Java and bytes.

## 2. Two Distinct Concepts: Object Mapping and Serialization

Redis is a key–value data store with multiple data types such as String, Hash, Set, List, and Sorted Set.

- **Object mapping:** determines which Redis field corresponds to each Java property, what key the object uses, which property is the identifier, which indexes to maintain, and how to reconstruct the object on read.
- **Serialization:** converts a Java value into a byte sequence for storage and decodes bytes back into a Java value on read. For example, a JSON serializer turns `Customer` into JSON text as bytes.
- **Redis data type:** determines which commands can operate on a key. Hash uses `HSET`, `HGET`, `HGETALL`; String uses `SET`, `GET`. Even if a String contains JSON, Redis still treats it as a String.

A Redis Hash can hold multiple `field → value` pairs:

~~~text
customers:c-101            (Redis HASH)
  email          -> "linh@example.com"
  fullName       -> "Nguyen Linh"
  address.city   -> "Hanoi"
  _class         -> "com.example.Customer"  (metadata if mapping config uses it)
~~~

A Redis String can contain JSON:

~~~json
{
  "id": "c-101",
  "email": "linh@example.com",
  "fullName": "Nguyen Linh",
  "address": {
    "city": "Hanoi"
  }
}
~~~

In the JSON example, the entire text block is **a single value** at key `customer:json:c-101`. Redis does not treat `email` or `address.city` as Hash fields accessible with `HGET`.

> Distinguish JSON stored in a Redis String from **RedisJSON**, a separate data type and command set available when the RedisJSON module is present. Saving JSON via `opsForValue().set(...)` does not create RedisJSON data and does not enable `JSON.GET` or `JSON.SET`.

## 3. Approach 1 — Repository Mapping Entities to Redis Hash

### 3.1. Declaring an Entity with @RedisHash

In Spring Data Redis, `@RedisHash` marks a class that uses entity mapping for Redis Repositories. The value `"customers"` is the **keyspace** — the logical prefix of keys belonging to this entity type.

~~~java
package com.example.redis;

import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("customers")
public class Customer {

    @Id
    private String id;

    @Indexed
    private String email;

    private String fullName;
    private Address address;

    public Customer() {
    }

    public Customer(
            String id,
            String email,
            String fullName,
            Address address) {
        this.id = id;
        this.email = email;
        this.fullName = fullName;
        this.address = address;
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

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String fullName) {
        this.fullName = fullName;
    }

    public Address getAddress() {
        return address;
    }

    public void setAddress(Address address) {
        this.address = address;
    }
}
~~~

The `Address` class is a value object nested inside `Customer`:

~~~java
package com.example.redis;

public class Address {

    private String city;

    public Address() {
    }

    public Address(String city) {
        this.city = city;
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }
}
~~~

In this snippet:

- `@Id` marks the identifier used to construct the entity's Redis key.
- `@RedisHash("customers")` specifies the entity's keyspace.
- `@Indexed` instructs the Repository mechanism to maintain a secondary index on `email`, supporting certain property-based queries.
- `address` is a nested object; Spring Data Redis's default Hash mapper can flatten its properties into field paths like `address.city`.

Exact field representations, `_class` metadata, nested layouts, and auxiliary key sets can depend on the Spring Data Redis version, property types, and custom converters. Do not treat illustrated fields as an immutable byte-format contract.

### 3.2. Repository Saving and Retrieving Entities

~~~java
package com.example.redis;

import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, String> {

    List<Customer> findByEmail(String email);
}
~~~

Declare Redis Repository enablement if the project does not already auto-configure it:

~~~java
package com.example.redis;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.repository.configuration.EnableRedisRepositories;

@Configuration
@EnableRedisRepositories(basePackageClasses = CustomerRepository.class)
public class RedisRepositoryConfiguration {
}
~~~

Assuming the application has a `RedisConnectionFactory` from Spring Boot configuration and the proper Spring Data Redis dependencies, usage code can be:

~~~java
Customer saved = repository.save(new Customer(
        "c-101",
        "linh@example.com",
        "Nguyen Linh",
        new Address("Hanoi")
));

Customer loaded = repository.findById("c-101")
        .orElseThrow();

List<Customer> foundByEmail =
        repository.findByEmail("linh@example.com");
~~~

`save(...)` delegates to Spring Data Redis to convert the object into Hash fields. `findById(...)` locates the corresponding Hash and reconstructs `Customer`. With `@Indexed`, `findByEmail(...)` can use the secondary index maintained by the Repository; it does not mean Redis natively supports arbitrary queries like a relational database.

### 3.3. What Does the Physical Data Look Like?

Under standard mapping configuration, the primary key has an illustrative form:

~~~text
customers:c-101
~~~

Inspect via Redis CLI:

~~~redis
TYPE customers:c-101
HGETALL customers:c-101
~~~

The `TYPE` command returns `hash` when the key is stored as a standard Redis Hash by the Repository. `HGETALL` displays mapped fields, for example:

~~~text
email         -> linh@example.com
fullName      -> Nguyen Linh
address.city  -> Hanoi
_class        -> com.example.redis.Customer
~~~

The example illustrates structure only; actual data may contain an `id` field, type metadata, or different field names depending on mapping rules.

Beyond the main Hash key, the Repository may maintain a **Set holding keyspace identifiers**, **Sets for secondary indexes**, and other metadata. Thus, a single `repository.save(...)` call can touch multiple Redis keys, not just one Hash.

This enables `findAll()` and queries on indexed properties, though it also adds storage, update, and cleanup costs when needed.

### 3.4. Why Does Repository Suit an Entity Model?

Repositories provide an entity-centric programming style:

~~~java
repository.save(customer);
repository.findById("c-101");
repository.deleteById("c-101");
repository.findByEmail("linh@example.com");
~~~

The program works with Java types and identifiers, while Spring Data Redis manages Hash persistence, metadata, and Repository indexes.

However, this is **not a miniature relational ORM**: Redis Repositories do not automatically provide arbitrary filtering, sorting, table joins, aggregations, or SQL-style transactions. Indexes and query capabilities must be designed around what Spring Data Redis actually supports.

## 4. Approach 2 — RedisTemplate Saving the Whole Object as JSON

### 4.1. Configuring Explicit Serializers

`RedisTemplate` is a flexible Redis operations API. When you want to store a Java object as JSON in a **Redis String**, configure serializers for keys and values.

Example for Spring Data Redis 3.x:

~~~java
package com.example.redis;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class CustomerJsonRedisConfiguration {

    @Bean("customerJsonRedisTemplate")
    public RedisTemplate<String, Customer> customerJsonRedisTemplate(
            RedisConnectionFactory connectionFactory) {

        RedisTemplate<String, Customer> template = new RedisTemplate<>();
        template.setConnectionFactory(connectionFactory);

        template.setKeySerializer(new StringRedisSerializer());
        template.setValueSerializer(
                new Jackson2JsonRedisSerializer<>(Customer.class)
        );

        template.afterPropertiesSet();
        return template;
    }
}
~~~

`StringRedisSerializer` ensures key names appear as human-readable strings. `Jackson2JsonRedisSerializer<Customer>` writes `Customer` objects as JSON and reads JSON back into `Customer`.

Serializer class names and constructors can vary across Spring Data Redis/Jackson versions. If using a version other than 3.x, check that version's API. The core idea remains **configuring serializers compatible with the data and Java types to read**.

Do not assume every `RedisTemplate` stores JSON: an unconfigured `RedisTemplate` may default to Java/JDK serialization for values, producing binary data that is hard to read and hard to share across systems.

### 4.2. Writing and Reading with ValueOperations

~~~java
package com.example.redis;

import java.time.Duration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class CustomerJsonCache {

    private final RedisTemplate<String, Customer> redis;

    public CustomerJsonCache(
            @Qualifier("customerJsonRedisTemplate")
            RedisTemplate<String, Customer> redis) {
        this.redis = redis;
    }

    public void save(Customer customer) {
        String key = "customer:json:" + customer.getId();

        redis.opsForValue().set(
                key,
                customer,
                Duration.ofMinutes(30)
        );
    }

    public Customer findById(String id) {
        return redis.opsForValue().get("customer:json:" + id);
    }

    public void deleteById(String id) {
        redis.delete("customer:json:" + id);
    }
}
~~~

Using `opsForValue()` means operating on a **Redis String**, not a Redis Hash. With a JSON serializer, the flow is:

~~~text
Java customer
    |
    | Jackson2JsonRedisSerializer
    v
JSON bytes: {"id":"c-101","email":"linh@example.com",...}
    |
    | SET customer:json:c-101 <bytes> EX <ttl>
    v
Redis STRING
    |
    | GET customer:json:c-101
    v
JSON bytes
    |
    | Jackson2JsonRedisSerializer
    v
Java customer
~~~

Even though the `Customer` class in the previous example has `@RedisHash` and `@Indexed`, calling `opsForValue().set(...)` **does not trigger** the Repository mechanism to create a Redis Hash or update `@Indexed` indexes. Those are two independent access paths.

### 4.3. Inspecting Data in Redis

After calling `CustomerJsonCache.save(...)`, you can inspect:

~~~redis
TYPE customer:json:c-101
GET customer:json:c-101
TTL customer:json:c-101
~~~

Typical output:

~~~text
TYPE -> string

GET  -> {"id":"c-101","email":"linh@example.com",
         "fullName":"Nguyen Linh","address":{"city":"Hanoi"}}

TTL  -> remaining seconds
~~~

`GET` reads **the entire JSON value**. You cannot run:

~~~redis
HGET customer:json:c-101 email
~~~

because the key has Redis type String, not Hash; Redis will return a wrong-type error (`WRONGTYPE`).

Conversely:

~~~redis
GET customers:c-101
~~~

cannot read the Hash saved by the Repository either. You must use matching Hash commands, or let the Repository reconstruct the Java object.

## 5. RedisTemplate Can Also Use Hashes: Don't Confuse API Names with Storage Formats

At least three scenarios must be clearly distinguished:

| Access Method | Typical Java API | Redis Data Type | Conversion Mechanism |
|---|---|---|---|
| **Redis Repository** | `repository.save(entity)` | Hash for root entity | Spring Data Redis entity mapper; manages identity and indexes |
| **RedisTemplate + JSON** | `template.opsForValue().set(key, entity)` | String | JSON serializer configured for values |
| **RedisTemplate + HashOperations** | `template.opsForHash().put(key, field, value)` | Hash | Code picks fields explicitly; Hash key/value serializers per configuration |

Manual Hash operations example:

~~~java
import org.springframework.data.redis.core.StringRedisTemplate;

public void saveSomeFields(StringRedisTemplate redis) {
    String key = "customer:manual:c-101";

    redis.opsForHash().put(key, "email", "linh@example.com");
    redis.opsForHash().put(key, "fullName", "Nguyen Linh");

    Object email = redis.opsForHash().get(key, "email");
    System.out.println(email);
}
~~~

`StringRedisTemplate` uses strings for keys, fields, and values. This snippet creates a **Redis Hash**, yet it is **not** a Repository call: it does not automatically build `Customer`, does not create `@Indexed` indexes, and does not apply `@RedisHash` mapping rules.

Hence, the statement "RedisTemplate saves JSON, Repository saves Hash" is only accurate when comparing **a JSON-configured RedisTemplate using `opsForValue()`** against **a Repository mapping to Redis Hashes**. `RedisTemplate` itself is not limited to JSON.

## 6. Comparing by Practical Design Decisions

| Criterion | Repository + @RedisHash | RedisTemplate + JSON via opsForValue |
|---|---|---|
| **Physical unit of data** | Multiple fields inside an entity Hash | One String containing JSON of the whole object |
| **Read by ID** | `findById(id)` reconstructs object from Hash | `GET` then deserialize JSON |
| **Write object** | `save(entity)` via mapping, manages auxiliary keys if any | `SET key json`, typically overwrites key value |
| **Read single property** | Can use `HGET` on physical Hash if mapping is understood; Repository typically returns entity | Cannot `HGET` a property inside a JSON String; must read and parse JSON or change data model |
| **Update single field via Redis command** | Hash supports `HSET`; be careful when mixing with Repository | `SET` typically replaces the entire String |
| **Property indexes** | Supports `@Indexed` and secondary indexes | Not created automatically; must maintain manually if needed |
| **TTL** | `@RedisHash(timeToLive = ...)`, `@TimeToLive`, and Repository config | Use `set(key, value, Duration)`, `expire(...)`, or other TTL operations |
| **Nested structures** | Usually mapped to field paths, customizable via converters | JSON preserves text-based object/array structure |
| **Cross-app interoperability** | Must understand field conventions, metadata, and mapping | JSON is usually easier to read and exchange once schema is agreed |
| **Storage and performance** | Depends on field count/length, Hash encoding, indexes, and access patterns | Depends on JSON size, serializer, decode frequency, and update style |
| **Primary risk** | Auxiliary keys/indexes drift if edited directly; mapping compatibility required | Full-value overwrites, lack of indexes, read–modify–write races |

There is no rule that "Hash is always faster than JSON" or "JSON is always more compact than Hash." A small Hash can benefit from Redis's memory-efficient encodings, yet many fields and secondary indexes also add overhead. JSON can be easier to exchange and debug, though reading a single property still usually requires fetching and decoding the whole object.

When designing, benchmark with your application's actual object sizes, access patterns, and load.

## 7. Deeper Look at Property Changes and Indexes

### 7.1. Repository Manages the Link Between Entity and Index

Example:

~~~java
@Indexed
private String email;
~~~

Suppose we save a customer with email `linh@example.com`, then use the Repository to update it to `linh.new@example.com`:

~~~java
Customer c = repository.findById("c-101").orElseThrow();
c.setEmail("linh.new@example.com");
repository.save(c);
~~~

When using the proper Repository API, Spring Data Redis updates secondary indexes associated with indexed properties.

However, if another task edits the field directly using:

~~~redis
HSET customers:c-101 email "linh.new@example.com"
~~~

then the field inside the Hash changed, while index sets maintained by the Repository **may still reflect the old email**. As a result, `findById(...)` and `findByEmail(...)` risk showing inconsistent state.

**Rule:** if a Redis Hash is owned by a Repository, prefer updating through the Repository or an update mechanism that understands metadata and indexes. Do not arbitrarily invoke `HSET` on the same keyspace simply because it is convenient.

### 7.2. JSON Has No Automatic Repository Index

Even if JSON contains an `email` property, calling:

~~~java
jsonTemplate.opsForValue().set("customer:json:c-101", customer);
~~~

does not tell Redis to index `email`. `@Indexed` on the Java class has no effect when saving through `opsForValue()`.

If business requirements need email lookups, the options are:

- Maintain a dedicated lookup mapping, such as `customer:by-email:<email> -> <id>`, and keep updates/deletes consistent.
- Choose Repository when required queries match indexes supported by Spring Data Redis.
- Use another appropriate query/indexing system if complex filtering, sorting, and searching are required.

Do not treat calling `KEYS customer:json:*`, fetching every JSON payload, and filtering in Java as a regular query strategy: it requires scanning huge key sets and deserializing many objects.

### 7.3. Is Updating a Single Property Always Cheaper with a Hash?

At the Redis command level, a Hash supports:

~~~redis
HSET customers:c-101 fullName "Linh Nguyen"
~~~

whereas a JSON String stored with `SET` does not let you use `HSET` to update one JSON field.

However, when the application acts via `repository.save(entity)`, the Repository layer may rewrite multiple fields or update related metadata. **Do not infer that `save(...)` always emits only a single `HSET` for the changed field.**

If single-field updates need optimization, choose an appropriate API and consider metadata synchronization requirements. Meanwhile, if the JSON value is a small object mostly read and written as one unit, `GET`/`SET` can be simpler and well-suited.

## 8. Write Contention: Avoiding Lost Updates

Suppose two requests read JSON concurrently:

~~~text
T1: GET customer:json:c-101 -> {fullName:"Linh", city:"Hanoi"}
T2: GET customer:json:c-101 -> {fullName:"Linh", city:"Hanoi"}

T1: modifies fullName -> "Nguyen Linh"
T2: modifies city -> "Da Nang"

T1: SET whole JSON {fullName:"Nguyen Linh", city:"Hanoi"}
T2: SET whole JSON {fullName:"Linh", city:"Da Nang"}
                                     ^
                        T1's fullName change is lost
~~~

A single `SET` command is atomic in Redis, but **the sequence GET → modify in Java → SET is not automatically atomic**. If the data holds critical state under concurrent writes, apply contention controls such as `WATCH`/transactions, Lua scripts, versioning, or another suitable design.

With a Redis Hash, `HSET key fullName ...` and `HSET key city ...` on **two independent fields** avoid the whole-document overwrite shown here. However, cross-field invariants, multi-command writes, and Repository index updates still require an explicit consistency strategy.

A single `repository.save(...)` call does not mean all Hash writes, metadata, and secondary index updates execute as a single ACID transaction. Depending on execution flow and configuration, multiple Redis commands may occur.

## 9. Serializers Are Part of the Data Contract

In `RedisTemplate`, different serializers serve distinct purposes:

| Serializer | Role |
|---|---|
| `keySerializer` | Encodes Redis keys |
| `valueSerializer` | Encodes values in `opsForValue()` |
| `hashKeySerializer` | Encodes field names when using `opsForHash()` |
| `hashValueSerializer` | Encodes field values when using `opsForHash()` |

These serializers **do not change the Redis data type**. For example, configuring JSON for `hashValueSerializer` and calling `opsForHash().put(...)` produces a Hash whose field contains JSON—it does not turn the whole key into a JSON String.

Example:

~~~java
// Redis Hash: field "settings" can contain JSON if hashValueSerializer is JSON.
template.opsForHash().put("customer:hash:c-101", "settings", settings);

// Redis String: value is JSON if valueSerializer is JSON.
template.opsForValue().set("customer:json:c-101", customer);
~~~

Because reading relies on the serializer, one app writing JSON while another reads with a JDK serializer—or vice versa—fails to decode even though the key exists.

For data shared across services, agree on:

- Key names and namespace conventions.
- Redis data type for each key group.
- Value format and character encoding.
- Required/optional fields, schema changes, and missing-field behavior.
- Whether Java type metadata appears in JSON and rules for handling types.

Some JSON serializers embed type metadata such as `_class` to support polymorphism; typed serializers do not need to do so. Do not assume the JSON layout observed from one serializer is the default for every `RedisTemplate`.

## 10. Common Mistakes When Mixing Both Mechanisms

### Mistake 1: Using GET to Read a Repository-Managed Key

~~~java
// Repository saved at "customers:c-101" as a Hash.
Customer customer = repository.findById("c-101").orElseThrow();

// This command uses GET, not HGETALL.
Customer wrong = jsonTemplate.opsForValue().get("customers:c-101");
~~~

The second line sends `GET` to a Redis Hash and may receive `WRONGTYPE`. Changing the serializer will not fix a physical data-type mismatch.

### Mistake 2: SETting JSON Over a Hash Key

~~~java
// Do not do this on keys managed by a Repository.
jsonTemplate.opsForValue().set("customers:c-101", customer);
~~~

`SET` can **replace the key's existing value**, even if the previous value was a Hash. Afterward, the Repository cannot read the key because its type became String, while secondary index keys may remain behind and become inconsistent.

This is why **distinct namespaces** are mandatory when both storage approaches coexist:

~~~text
customers:c-101          -> Repository / HASH
customer:json:c-101      -> RedisTemplate + JSON / STRING
~~~

### Mistake 3: Thinking @RedisHash Auto-Configures RedisTemplate

~~~java
@RedisHash("customers")
class Customer {
    // ...
}
~~~

This annotation tells the Repository mapper how to store the entity. It does not select a JSON serializer for every `RedisTemplate<Customer>` bean, does not turn `opsForValue()` into `opsForHash()`, and does not apply TTLs to every key written via Template.

### Mistake 4: Using HSET Directly While Still Expecting @Indexed

If the Repository maintains an email index, updating the email field straight via `HSET` leaves the index stale. Agree on data ownership and update paths.

### Mistake 5: Calling JSON "RedisJSON"

JSON stored in a Redis String is read via `GET`. Commands like `JSON.GET`/`JSON.SET` belong to RedisJSON and require server-side RedisJSON support. They do not automatically work on a plain Redis String containing JSON.

### Mistake 6: Equating Speed with Byte Size of One Sample Object

Comparisons must account for index volume, Hash size, object depth, per-field update frequency, serialization overhead, and network round-trips. Benchmarking a single small object write/read is insufficient to generalize across all production scenarios.

## 11. TTL and Data Lifecycle

Both mechanisms support expiring data, though configured differently.

**Repository:**

~~~java
@RedisHash(value = "customers", timeToLive = 1800)
public class Customer {
    // ...
}
~~~

`timeToLive` here is in seconds per the annotation mechanism. You can also declare a `@TimeToLive` property when per-entity flexible expirations are needed.

Spring Data Redis may require expiration tracking and shadow copies for expiration events depending on configuration; thus Repository TTL is not always just a simple `EXPIRE` call when considering full metadata lifecycle.

**RedisTemplate + JSON:**

~~~java
jsonTemplate.opsForValue().set(
        "customer:json:c-101",
        customer,
        java.time.Duration.ofMinutes(30)
);
~~~

Here TTL is a parameter of writing the value to Redis. Calling `opsForValue().set(key, value)` without a TTL on the same key with a standard `SET` command clears any existing TTL unless a TTL-preserving mechanism is used.

If lifetimes must follow business rules, clarify when TTL starts, renews, or stays unchanged on updates. Those rules are independent of choosing Hash versus JSON String.

## 12. Practice: Verifying Both Storage Approaches

Using a development Redis instance, create a customer with identical data:

~~~java
Customer c = new Customer(
        "c-101",
        "linh@example.com",
        "Nguyen Linh",
        new Address("Hanoi")
);

repository.save(c);
customerJsonCache.save(c);
~~~

Then in Redis CLI:

~~~redis
TYPE customers:c-101
TYPE customer:json:c-101

HGETALL customers:c-101
GET customer:json:c-101

TTL customers:c-101
TTL customer:json:c-101
~~~

Expected observations:

1. `TYPE customers:c-101` is `hash`; `TYPE customer:json:c-101` is `string`.
2. `HGETALL` reads the Hash's field/value pairs; `GET` reads the JSON string.
3. TTL on the two keys can differ: the first Repository example had no TTL configured, while the JSON path set a 30-minute expiration.
4. Results of `repository.findByEmail(...)` depend on the `@Indexed` index maintained by the Repository; it does not query `customer:json:c-101`.

You can also use size-inspection commands:

~~~redis
HLEN customers:c-101
STRLEN customer:json:c-101

MEMORY USAGE customers:c-101
MEMORY USAGE customer:json:c-101
~~~

`HLEN` counts fields in the Hash; `STRLEN` measures byte length of the Redis String; `MEMORY USAGE` estimates Redis memory allocated per key. These measurements exclude full model overhead, especially secondary indexes created by the Repository outside the primary Hash key.

Do not extrapolate numbers from a single sample object directly into production performance conclusions.

## 13. Which Approach Fits Each Requirement?

### Scenario A: Managing an Entity Type Needing ID Lookup and a Few Indexed Properties

Example: session objects or simple profiles queried by a few fixed fields.

Repository is worth considering when required queries are supported by Redis Repositories. It keeps CRUD code at the entity level, though you must still understand index limits, auxiliary keys, and safe update patterns.

### Scenario B: Caching Computed Results or API Responses

Example: precomputed product details JSON, looked up by product code, rarely edited field-by-field.

`RedisTemplate` with a JSON serializer and `opsForValue()` is usually simpler: direct single-key access, whole-object read/write, and TTL set on write. There is no need to build a Repository just to store short-lived cache values.

### Scenario C: Updating a Few Independent Counters, Flags, or Fields

If the use case genuinely needs per-field operations and does not need Repository aggregate mapping, direct `HashOperations` or specialized Redis commands may fit better. Choosing a Redis Hash here is a design decision that does not require `@RedisHash`.

### Scenario D: Complex Multi-Condition Search and Stable Pagination

Do not assume either Redis Repository or JSON String suffices out of the box. Check indexing/query capabilities, consistency requirements, ordering, and pagination; a dedicated data store or search/indexing engine may be needed.

### Scenario E: Multiple Services in Multiple Languages Reading Shared Data

JSON with an agreed schema is usually easier to exchange across platforms. Repository Hashes can still be read by other services if keyspace, field, metadata, and encoding conventions are published; however, Spring Data Redis's internal mapping is not meant to serve as a stable cross-service protocol.

## 14. What If You Want to Migrate from Repository Hash to JSON?

You cannot simply swap the serializer and read legacy Hash keys as JSON. Treat this as a **data migration**, because the Redis data types differ.

A design-safe migration plan:

1. Define a new namespace, such as `customer:json:<id>`, with a clear JSON schema.
2. Read legacy entities via the Repository or a compatible Hash reader.
3. Write new data via `RedisTemplate` JSON and verify read-back.
4. Decide how to handle concurrent changes during migration: controlled dual-writes, synchronization, or a maintenance window as required.
5. Switch application read traffic to the new keys once verified.
6. Plan expiration/cleanup of legacy data, including Hashes, keyspace sets, and secondary indexes created by the Repository.

If the data is non-critical cache that can be regenerated, it is often easier to switch namespaces and let old keys expire by TTL. For business state data, carefully evaluate consistency during the transition.

Avoid deleting and overwriting within the Repository namespace while older application threads are still active.

## 15. Self-Check Questions

**Question 1.** `Customer` has `@RedisHash`. If you use `RedisTemplate<String, Customer>` with a JSON serializer and call `opsForValue().set(...)`, does Redis store a Hash or a String?

**Answer:** A Redis String. `@RedisHash` does not turn `ValueOperations` into the Repository mechanism. The JSON serializer determines the byte payload of the String value.

**Question 2.** You saved `customers:c-101` via a Repository. Can you run `GET customers:c-101` to retrieve JSON?

**Answer:** No. That key is typically a Redis Hash; `GET` is for Strings and returns `WRONGTYPE` on a Hash.

**Question 3.** Can `RedisTemplate` be used to store Hashes?

**Answer:** Yes. Use `opsForHash()` and configure matching serializers. However, manual Hash operations do not grant Repository mapping, metadata, or indexes.

**Question 4.** The JSON contains an `email` field—will `@Indexed` automatically help `opsForValue()` search by email?

**Answer:** No. `@Indexed` belongs to Repository mapping and indexing, and does not apply to Redis JSON Strings written via Template.

**Question 5.** To change a Repository entity's email, should you run `HSET` directly on the Hash key?

**Answer:** Be very careful. If the field is indexed, editing the Hash directly bypasses secondary index updates. Update through a mechanism that manages mapping and indexes.

**Question 6.** If you only cache JSON by ID and do not need property queries, why might `RedisTemplate` be a better fit?

**Answer:** Because the application only needs `SET`/`GET` and TTL on a known key; JSON offers a simple whole-object representation without extra Repository and index management overhead for that use case.

## 16. Things to Remember

- `@RedisHash` + **Redis Repository** maps entities into Redis Hashes, with identity, metadata, and secondary indexes when configured.
- `RedisTemplate` + **JSON value serializer** + `opsForValue()` stores JSON inside a Redis String. `RedisTemplate` can also work with Hashes, Sets, Lists, and other data types.
- **Redis data type** determines whether you use `GET` or `HGET`. **Serializer** determines how data turns back into Java objects. These two concepts do not replace each other.
- Repository and Template can be combined in the same application, provided namespaces and data ownership are separated to avoid `WRONGTYPE`, key overwrites, and stale indexes.
- Choose the storage option based on **actual access and update patterns**, query needs, TTL, consistency, data sharing, and operational cost.

### References

- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html).
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html).
- [Redis — Hashes](https://redis.io/docs/latest/develop/data-types/hashes/).
- [Redis — TYPE](https://redis.io/docs/latest/commands/type/).
