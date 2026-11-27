# Mapping Objects to Redis Hash in Spring Data Redis

## 1. Lesson Objectives

When using Redis as a store for Java objects, a common choice is to represent each object as a **Redis Hash**: a Redis key containing a collection of `field → value` pairs. Spring Data Redis provides a mechanism to convert back and forth between objects and this structure, allowing the application to operate in Java while still leveraging Redis Hash commands.

After this lesson, you will be able to:

- Explain the difference between a **Redis key**, a **hash field**, and a **field value**.
- Use `@RedisHash`, `@Id`, and a Redis Repository to save and read objects.
- Predict how simple fields, nested objects, lists, and maps are represented in a Redis Hash.
- Distinguish default Repository mapping from using `HashOperations` or `HashMapper`.
- Customize data conversion, handle indexes, TTL, references, and partial updates.
- Identify issues when overwriting an entire hash, changing Java class structure, or performing concurrent updates.

## 2. How Does a Redis Hash Store an Object?

Suppose an application has a customer:

~~~java
Customer customer = new Customer(
    "c-101",
    "lan@example.com",
    "Lan",
    new Address("Hanoi", "VN")
);
~~~

We can represent that object in Redis using **one key** named `customers:c-101` and multiple **fields**:

~~~text
Redis key: customers:c-101
Redis type: hash

id              -> c-101
email           -> lan@example.com
displayName     -> Lan
address.city    -> Hanoi
address.country -> VN
_class          -> com.example.redis.domain.Customer
~~~

Here:

| Component | Meaning |
|---|---|
| `customers:c-101` | Key of the record in Redis, typically composed of the *keyspace* and ID. |
| `id`, `email`, `address.city` | Fields inside the hash; each field has its own name. |
| `c-101`, `lan@example.com`, `Hanoi` | Values Redis stores for each field. |
| `_class` | Java type metadata so the converter can reconstruct the object. |

You can visualize the data flow as:

~~~text
Customer (Java)
    |
    | MappingRedisConverter / RedisConverter
    v
Map<field, byte[]> -- written to --> Redis Hash "customers:c-101"
    ^
    | read and convert back
    |
Customer (Java)
~~~

**A Redis Hash is not a JSON document.** With a Hash, `address.city` is a Redis field name, not a JSON access operator. Redis only knows about byte-based fields and values; Spring Data Redis is responsible for interpreting field names, Java types, and how to reconstruct the object.

If you manage data manually with `StringRedisTemplate`, you can also create a hash directly:

~~~redis
HSET customers:c-101 id c-101 email lan@example.com displayName Lan
HGET customers:c-101 email
HGETALL customers:c-101
TYPE customers:c-101
~~~

These commands illustrate the Hash structure. For data managed by a Repository, you should use the Repository to write so that related indexes and metadata stay synchronized.

## 3. Two Layers to Distinguish

Spring Data Redis supports multiple ways to work with Hashes:

| Usage | Main Components | Level of Automation | Suitable Scenarios |
|---|---|---|---|
| **Redis Repository** | `@RedisHash`, `CrudRepository`, `MappingRedisConverter` | Automatically manages keyspace, ID, mapping, and configured indexes. | Storing Java entities with CRUD operations. |
| **Direct Hash Operations** | `RedisTemplate` / `StringRedisTemplate`, `HashOperations` | Application chooses key, field, serialization, and data lifecycle. | Per-field caching, reading/writing individual fields, simple structured data. |
| **HashMapper + HashOperations** | `HashMapper`, `ObjectHashMapper`, `JacksonHashMapper` | Mapper converts object to map; application calls Redis directly. | Wanting control over Hash format without using a Repository. |

All three approaches can coexist in a project, but **you should not arbitrarily write to the same key using multiple mechanisms**. They may use different serializers, metadata, and index management strategies.

The next section focuses on the **Object-to-Hash Mapping mechanism of Redis Repository**.

## 4. Complete Example with Redis Repository

### 4.1. Setup

A Spring Boot project needs the `spring-boot-starter-data-redis` dependency. If using Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
~~~

If the project uses a Spring Boot BOM/parent, let the BOM manage the versions of Spring Data libraries; avoid arbitrarily mixing incompatible versions.

Run a local Redis instance, for example:

~~~bash
docker run --rm --name redis-mapping-demo -p 6379:6379 redis:7-alpine
~~~

Configure the connection in `src/main/resources/application.yml`:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
~~~

Spring Boot typically auto-configures the Redis connection, templates, and repository support when the dependency and package structure match. For plain Spring configurations or repositories outside the scan scope, configure `@EnableRedisRepositories` accordingly.

### 4.2. Declaring the Nested Class

File `Address.java`:

~~~java
package com.example.redis.domain;

public class Address {
    private String city;
    private String country;

    public Address() {
    }

    public Address(String city, String country) {
        this.city = city;
        this.country = country;
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }

    public String getCountry() {
        return country;
    }

    public void setCountry(String country) {
        this.country = country;
    }
}
~~~

`Address` does not need `@RedisHash`: here it is a nested part inside `Customer`, mapped into the fields of the hash storing the customer.

### 4.3. Declaring the Redis Entity

File `Customer.java`:

~~~java
package com.example.redis.domain;

import java.util.ArrayList;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("customers")
public class Customer {

    @Id
    private String id;

    @Indexed
    private String email;

    private String displayName;
    private Address address;
    private List<String> tags = new ArrayList<>();

    public Customer() {
    }

    public Customer(String id, String email, String displayName, Address address) {
        this.id = id;
        this.email = email;
        this.displayName = displayName;
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

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public Address getAddress() {
        return address;
    }

    public void setAddress(Address address) {
        this.address = address;
    }

    public List<String> getTags() {
        return tags;
    }

    public void setTags(List<String> tags) {
        this.tags = tags;
    }
}
~~~

Meaning of the annotations:

- `@RedisHash("customers")` selects the `customers` **keyspace**. The entity's Redis key will be of the form `customers:<id>`.
- `@Id` (from `org.springframework.data.annotation`) indicates the identifier field. If the ID is `null` when saving via a Repository, Spring Data can generate an ID; if provided upfront like `c-101`, that ID is used to build the key.
- `@Indexed` requests the creation of a **secondary index** for `email`, supporting Repository queries based on this field's value.
- `displayName`, `address`, and `tags` are regular properties, mapped according to default rules.

Note that `@RedisHash` is not the JPA `@Entity` annotation. Redis Repository uses its own mapping mechanism and does not create SQL tables.

### 4.4. Declaring the Repository

File `CustomerRepository.java`:

~~~java
package com.example.redis.repository;

import java.util.Optional;

import org.springframework.data.repository.CrudRepository;
import com.example.redis.domain.Customer;

public interface CustomerRepository extends CrudRepository<Customer, String> {

    Optional<Customer> findByEmail(String email);
}
~~~

`CrudRepository<Customer, String>` defines the entity type and ID type. The `findByEmail` method relies on the index declared with `@Indexed`. Redis does not automatically create secondary indexes like relational databases; if you omit the index annotation and still expect to query by email, you cannot assume that query will work by default.

### 4.5. Writing and Reading an Object

Example `CommandLineRunner` placed in a class scanned by Spring Boot:

~~~java
package com.example.redis;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

import com.example.redis.domain.Address;
import com.example.redis.domain.Customer;
import com.example.redis.repository.CustomerRepository;

@SpringBootApplication
public class RedisMappingApplication {

    public static void main(String[] args) {
        SpringApplication.run(RedisMappingApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(CustomerRepository repository) {
        return args -> {
            Customer customer = new Customer(
                "c-101",
                "lan@example.com",
                "Lan",
                new Address("Hanoi", "VN")
            );
            customer.setTags(List.of("vip", "newsletter"));

            repository.save(customer);

            repository.findById("c-101")
                .ifPresent(found -> System.out.println(found.getDisplayName()));

            repository.findByEmail("lan@example.com")
                .ifPresent(found -> System.out.println(found.getId()));
        };
    }
}
~~~

Saving an entity with `save` converts the Java state into Hash fields. `findById` performs the reverse direction, reading the Hash and reconstructing `Customer`, including `Address` and `tags`. If the data read from Redis has been manually modified into an incompatible format, the reverse mapping step may fail or return unexpected data.

### 4.6. Observing Results with Redis CLI

In Redis CLI, run:

~~~redis
TYPE customers:c-101
HGETALL customers:c-101
HGET customers:c-101 address.city
HGET customers:c-101 email
SMEMBERS customers:email:lan@example.com
~~~

Ignoring the field order in the `HGETALL` output, you may see value pairs like:

~~~text
_class          = com.example.redis.domain.Customer
id              = c-101
email           = lan@example.com
displayName     = Lan
address.city    = Hanoi
address.country = VN
tags.[0]        = vip
tags.[1]        = newsletter
~~~

The `_class` name is written according to the Java type mapping configuration; the section below introduces how to change it to an alias. `SMEMBERS customers:email:lan@example.com` illustrates a Set used as a secondary index containing the ID `c-101`. Besides the main hash, the Repository may create additional keys for managing the keyspace, indexes, or TTL.

**Do not use `KEYS *` to scan data on large production Redis instances.** When you need to find keys matching a pattern for diagnostics, prefer `SCAN` with a controlled scope.

## 5. Default Mapping Rules of RedisConverter

Redis Repository uses `RedisConverter`, typically `MappingRedisConverter`, to convert Java properties into field-name and byte-value pairs. Typical rules:

| Java Property Type | Example | Fields That May Appear in Redis Hash |
|---|---|---|
| Simple value | `String name = "Lan"` | `name = Lan` |
| Number, boolean, enum | `int age = 30` | `age = 30` after conversion to Redis data |
| Byte array | `byte[] avatar` | Field `avatar` with binary value |
| Nested object | `address.city = "Hanoi"` | `address.city = Hanoi` |
| List of simple values | `tags = ["vip", "new"]` | `tags.[0] = vip`; `tags.[1] = new` |
| Map of simple values | `labels = {"tier": "gold"}` | `labels.[tier] = gold` |
| List of objects | `addresses[0].city` | `addresses.[0].city = Hanoi` |
| Map containing objects | `places["home"].city` | `places.[home].city = Hanoi` |

These field names reflect the **property path**, using dots and square brackets according to mapping conventions. Map keys when flattened must belong to an appropriate simple type group, such as String or Number.

Some points to remember:

1. The examples show values in human-readable form. Underneath, Redis stores byte sequences, so exact results also depend on converters and serializers.
2. A `null` property does not mean a default "null value" in a Redis Hash; usually no corresponding field exists. When reading back, pay attention to Java defaults and business logic.
3. For nested interfaces or abstract types, Spring Data may need additional `_class` metadata to determine the concrete type.
4. The order of fields in a Redis Hash is not the order of properties in the Java class; do not write code that depends on `HGETALL` order.
5. Renaming Java fields or changing property types can cause previously saved Hash data to stop mapping correctly. Design a compatibility strategy when upgrading schemas.

### Why Not Just Use a Single JSON Field?

There are two ways to represent the same data:

~~~text
Approach A — Redis Hash, flattened:
    address.city    = Hanoi
    address.country = VN

Approach B — A single field containing JSON:
    address = {"city":"Hanoi","country":"VN"}
~~~

Approach A fits the default Repository mapping mechanism and allows accessing by hash field when the naming convention is known. Approach B keeps the child object as an independent value, but reading/modifying its inner content requires JSON logic or an appropriate converter. These two approaches should not be treated as the same storage format.

## 6. Customizing Type Names and Data Conversion

### 6.1. Shortening Type Metadata with `@TypeAlias`

By default, the `_class` field may contain the full class name:

~~~text
_class = com.example.redis.domain.Customer
~~~

To avoid storing long package names in the data, add:

~~~java
import org.springframework.data.annotation.TypeAlias;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("customers")
@TypeAlias("customer")
public class Customer {
    // Properties and constructors as in the previous example.
}
~~~

When Spring Data recognizes this alias in the mapping context, the data can be written as:

~~~text
_class = customer
~~~

An alias is part of the data contract: keep it stable or plan a migration if you change the alias, entity scanning configuration, or class structure. Do not arbitrarily delete `_class` because the converter may need type information to read the object back, especially for polymorphic types.

### 6.2. `RedisCustomConversions`

If you want to turn a complex type into a single binary field, you can register a pair of write/read converters. For example, instead of flattening `address.city` and `address.country`, we represent `Address` as a UTF-8 JSON string in a single `address` field.

Illustrative code (using a Jackson `ObjectMapper` configured appropriately for the application):

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class AddressToBytes implements Converter<Address, byte[]> {
    private final ObjectMapper objectMapper;

    public AddressToBytes(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public byte[] convert(Address address) {
        try {
            return objectMapper.writeValueAsBytes(address);
        } catch (Exception exception) {
            throw new IllegalArgumentException("Cannot serialize Address", exception);
        }
    }
}

@ReadingConverter
public class BytesToAddress implements Converter<byte[], Address> {
    private final ObjectMapper objectMapper;

    public BytesToAddress(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public Address convert(byte[] bytes) {
        try {
            return objectMapper.readValue(bytes, Address.class);
        } catch (Exception exception) {
            throw new IllegalArgumentException("Cannot deserialize Address", exception);
        }
    }
}
~~~

Register both converters into `RedisCustomConversions` in the Repository configuration, for example:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.convert.RedisCustomConversions;

@Configuration
public class RedisConversionConfiguration {

    @Bean
    RedisCustomConversions redisCustomConversions(ObjectMapper objectMapper) {
        return new RedisCustomConversions(List.of(
            new AddressToBytes(objectMapper),
            new BytesToAddress(objectMapper)
        ));
    }
}
~~~

The snippet requires imports matching your project's `Address` and Jackson `ObjectMapper`. For applications with custom Redis configuration, ensure the `RedisCustomConversions` bean is actually picked up by the `MappingRedisConverter` in use.

Logical result:

~~~text
Before customization:
    address.city    = Hanoi
    address.country = VN

After customizing Address <-> byte[]:
    address = {"city":"Hanoi","country":"VN"}
~~~

Converters taking/returning `Map<String, byte[]>` also allow controlling multiple hash fields at once. When choosing this customization, pay special attention to field name stability and the ability to read old data.

**Note on indexes:** Spring Data's secondary index discovery mechanism does not automatically adapt to a custom converter. Writing an object into a single field does not mean all child properties remain queryable as before.

## 7. Using HashOperations When You Want Per-Field Operations

Repository fits when the business unit is **an entity**. If you only want to store a few independent fields, `StringRedisTemplate` and `HashOperations` are simpler.

~~~java
import java.util.Map;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class CustomerCache {

    private final StringRedisTemplate redis;

    public CustomerCache(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void put(String id, String email, String displayName) {
        redis.opsForHash().putAll(
            "customer-cache:" + id,
            Map.of("email", email, "displayName", displayName)
        );
    }

    public String findEmail(String id) {
        Object value = redis.opsForHash().get("customer-cache:" + id, "email");
        return value == null ? null : value.toString();
    }

    public void rename(String id, String displayName) {
        redis.opsForHash().put("customer-cache:" + id, "displayName", displayName);
    }
}
~~~

This is a **manual** mechanism: you explicitly construct the `customer-cache:<id>` key, choose fields, and do not automatically get `@Indexed` or `@RedisHash`. Using a separate namespace helps avoid conflicts with keys managed by Repositories.

`opsForHash().put(...)` typically corresponds to writing a single field; `opsForHash().entries(...)` reads all fields. If a key has many fields or large values, reading the entire Hash can consume network and memory; choose commands according to your needs.

## 8. What Is HashMapper and How Does It Differ from RedisConverter?

`HashMapper<T, K, V>` is the contract for converting a Java object to `Map<K, V>` and vice versa:

~~~java
Map<K, V> toHash(T object);
T fromHash(Map<K, V> hash);
~~~

Several options depending on the Spring Data Redis version:

- `ObjectHashMapper`: maps an object into a map with byte-based fields/values.
- `BeanUtilsHashMapper`: based on JavaBeans and supported properties.
- `JacksonHashMapper`: uses Jackson 3, with options to represent nested structures or flatten them.
- `Jackson2HashMapper`: uses Jackson 2; newer Spring Data Redis lines mark it deprecated, so check documentation and your project version before choosing.

Conceptual example with `ObjectHashMapper`:

~~~java
HashMapper<Object, byte[], byte[]> mapper = new ObjectHashMapper();

Map<byte[], byte[]> hash = mapper.toHash(customer);

// HashOperations with matching hash key/value serializers
hashOperations.putAll("mapped-customers:c-101", hash);

Map<byte[], byte[]> saved = hashOperations.entries("mapped-customers:c-101");
Customer restored = (Customer) mapper.fromHash(saved);
~~~

Here `hashOperations` must be declared with types and serializers compatible with `byte[]`; the snippet is meant to clarify the mapper's role. With `HashMapper`, you **manually manage** Redis keys, TTL, and indexes, whereas Redis Repository integrates these features based on entity configuration.

Specifically, **a Repository's RedisConverter is not synonymous with JacksonHashMapper**. Both handle the object ↔ Hash problem, but they have different data structures and integration models. You cannot arbitrarily swap in a mapper and expect it to read every Hash written by a Repository.

### 8.1. Flattening with JacksonHashMapper

Suppose a class has an `address` property. When using a non-flattening Jackson mapper, the Hash may contain:

~~~text
address = {"city":"Hanoi","country":"VN"}
~~~

When flatten mode is enabled, it may become:

~~~text
address.city    = Hanoi
address.country = VN
~~~

The flatten mode of Jackson mapper has limitations for property names or map keys containing dots or square brackets because they can conflict with JSON paths. If you choose flattening, design field names appropriately and test reverse mapping in the library version you are using.

## 9. Mapping Associations Between Entities with `@Reference`

Not every nested object should have all its fields copied into the main Hash. If a customer references another account stored independently, you can declare:

~~~java
@RedisHash("customers")
public class Customer {
    @Id
    private String id;

    @Reference
    private Customer referredBy;

    // Appropriate constructor and accessors.
}
~~~

Instead of copying the entire `referredBy` object, the hash stores a Redis key reference such as:

~~~text
referredBy = customers:c-077
~~~

When reading the object, Spring Data can resolve the reference to build the link. However:

- Saving the parent object **does not automatically save** changes to the referenced object; you must save the referenced entity separately.
- This is not a foreign key with integrity constraints like in a relational database.
- Indexes on properties belonging to the referenced entity are not automatically resolved like indexes on direct properties.

Therefore, weigh **embedding** versus **referencing** based on update cycles and how data is read.

## 10. How Does the `@Indexed` Index Relate to Mapping?

Redis does not provide arbitrary queries over Hash fields like `SELECT ... WHERE`. Spring Data Redis supports certain queries through a **secondary index** maintained outside the main Hash.

Example:

~~~java
@RedisHash("customers")
public class Customer {
    @Id private String id;
    @Indexed private String email;
}
~~~

When saving a customer with email `lan@example.com`, in addition to the `customers:c-101` hash, the repository mechanism may store an equivalent relation:

~~~redis
SADD customers:email:lan@example.com c-101
~~~

`findByEmail("lan@example.com")` relies on the index to find the ID and then reads the entity. Similarly, some nested properties can be marked as indexed if appropriate.

Important points:

- `@Indexed` creates additional Redis Sets and update overhead; only index fields needed for queries.
- Indexes are typically updated when the application writes/deletes through the Repository. If you modify a Hash directly with `HSET`, the index may not reflect that change.
- An index Set does not guarantee uniqueness on its own. `@Indexed` is not equivalent to a `UNIQUE` constraint.
- Evaluate consistency, index recovery, and key expiration behavior before using Redis Repository as the primary data source for systems requiring strong constraints.

## 11. Time To Live (TTL) of Hash Entities

A Hash can expire automatically. In a Repository, the simplest approach is declaring a fixed TTL on the class:

~~~java
@RedisHash(value = "sessions", timeToLive = 3600)
public class SessionInfo {
    @Id
    private String id;
    private String username;
}
~~~

`3600` here is in **seconds**. After saving, you can check:

~~~redis
TTL sessions:s-101
~~~

For a per-entity variable TTL, you can use a field annotated with `@TimeToLive`:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.TimeToLive;

@RedisHash("sessions")
public class SessionInfo {
    @Id
    private String id;

    @TimeToLive
    private Long secondsRemaining;

    // Appropriate constructor, getters, and setters.
}
~~~

Do not place `@TimeToLive` simultaneously on both a method and a property of the same class. When reading data back, the TTL value may reflect remaining time rather than the originally configured duration. Index cleanup and expiration event emission also depend on the expiration/keyspace notification mechanism and Redis configuration.

If you mix manual write operations with Repositories, verify whether those operations preserve the expected TTL. Depending on the Redis command used, updating a field versus replacing the entire key can have different TTL behaviors.

## 12. Partial Updates and Overwrite Risks

An easily overlooked point: **writing an object using Redis Repository's Object-to-Hash mechanism may delete the old Hash content and rebuild it from the new object state**. Fields added by other systems that are not part of the mapping will be lost.

Example:

~~~text
Hash before save:
    id           = c-101
    displayName  = Lan
    legacyFlag   = keep-me

Java object has no legacyFlag property.

After repository.save(customer):
    id           = c-101
    displayName  = Lan
    (legacyFlag is gone)
~~~

Therefore:

- Do not use a Repository-managed key to store unmapped fields unless there is a clear governance mechanism.
- If multiple processes update different fields, a read → modify → `save` operation may overwrite changes from another process.
- `save` is not a "merge all untouched fields" operation and does not automatically provide optimistic locking like JPA.

When you only want to modify a single property, Spring Data offers `PartialUpdate` via `RedisKeyValueTemplate`:

~~~java
import org.springframework.data.redis.core.PartialUpdate;
import org.springframework.data.redis.core.RedisKeyValueTemplate;

public void updateCustomerName(RedisKeyValueTemplate template) {
    PartialUpdate<Customer> update =
        new PartialUpdate<Customer>("c-101", Customer.class)
            .set("displayName", "Lan Nguyen")
            .set("address.city", "Da Nang");

    template.update(update);
}
~~~

`PartialUpdate` supports `set`, `del`, and optional TTL updates. It suits small-scoped changes, though updating complex structures (collections, maps, objects) may still require multiple Redis operations; paths into properties handled by a custom converter as a single field may not support deep updates like `address.city`.

**A per-field update does not automatically resolve all concurrency conflicts.** When correctness depends on check-and-write or multiple keys changing consistently, design an appropriate synchronization protocol—such as a Redis transaction with `WATCH` or a Lua script—and clearly define the consistency scope to guarantee.

## 13. Choosing the Right Mapping Strategy

| Requirement | Recommendation |
|---|---|
| CRUD by ID on a Java entity, needing Repository and managed indexes | `@RedisHash` + `CrudRepository` |
| Only need to update a few Hash fields, managing keys manually | `StringRedisTemplate.opsForHash()` |
| Want to map a Java object to a Map before writing | `HashMapper` + `HashOperations` |
| Want to store a child object in a single binary/JSON field | `RedisCustomConversions` or an appropriate HashMapper |
| Want to look up by a non-ID property | Consider `@Indexed` and index overhead |
| Want to limit lifetime | `@RedisHash(timeToLive=...)` or `@TimeToLive` |
| Want relationships between independently stored entities | Consider `@Reference` and managing the referenced objects |

When choosing Redis to store entities, also consider data recovery, Redis persistence configuration, schema evolution, query requirements, index consistency, and data criticality. Object-to-Hash Mapping makes reading/writing easier for the application; it does not turn Redis into a relational database.

## 14. Common Errors and How to Handle Them

### 14.1. `findById` Returns Empty Even Though the Key Is Visible

Check whether the actual key has the exact `keyspace:id` format, which Redis database is connected, the Redis key type (`TYPE` must be `hash`), and the key serializer. Two strings that look identical in the CLI may not have the same byte representation as a key created by another template.

### 14.2. Cannot Query by Email

Verify that the property has `@Indexed`, that data was saved through the Repository after enabling the index, and that the index was created in Redis. Adding the annotation in code does not retroactively index existing legacy records.

### 14.3. Reading a Child Object Fails After Renaming a Field

For example, the old version stored `address.city`, and the new version changed it to `address.town`. The converter does not automatically know those two names are equivalent. You need to migrate old data, support compatible reading, or have a cache eviction and rebuild policy.

### 14.4. Manually Added Fields Disappear After `save`

The usual cause is that the Repository rewrites the entire Hash content from mapped properties. The solution is to add the field to the mapping model if appropriate, or move data owned by another component to a separate key.

### 14.5. Hash Is Readable in CLI but Fails to Deserialize into a Java Object

Check the `_class` field, custom converters, changed package/class names, field data types, and object instantiation capability (constructors, property accessors). Mixing JDK serialization, JSON serializers, and Hash mapping is a common cause of incompatibility.

### 14.6. TTL or Secondary Index Behaves Unexpectedly

Check the `TTL` of the main key, secondary indexes, and keyspace notifications configuration. Keys supporting indexes and expiration have their own behavior; do not assume directly editing a field via Redis CLI triggers the Repository's full index maintenance flow.

## 15. Guided Practice Exercise

Build a customer storage feature with `Customer`, `Address`, and `CustomerRepository` from Section 4.

1. Run Redis, start the application, and save a customer with ID `c-101`, email `lan@example.com`, address `Hanoi`, and two tags.
2. Use `TYPE` and `HGETALL` to confirm the record is a Redis Hash; observe the fields `address.city`, `tags.[0]`, and `_class`.
3. Call `findById("c-101")` and `findByEmail("lan@example.com")` to compare lookup by ID versus lookup via secondary index.
4. Change `address.city` to `Da Nang` using `PartialUpdate`; read the object back through the Repository.
5. Use Redis CLI to add a `debugFlag` field to the hash; then call `repository.save(customer)` to observe the full-rewrite rule.
6. Try `@TypeAlias("customer")` with new test data and observe the `_class` field. Note how existing data is read when changing type metadata configuration.
7. If using a dedicated Redis instance for practice, add a short TTL to a test entity and watch `TTL` decrease over time.

Self-assessment questions:

- At what Redis level do `customers:c-101` and `address.city` differ?
- Why is `@Indexed` not equivalent to a unique constraint?
- When should `HashOperations` be used instead of `CrudRepository`?
- Why can adding a field with `HSET` and then calling `save` cause that field to disappear?
- When should a child object be embedded, and when should `@Reference` be used?
- How does a custom converter storing the entire `Address` in the `address` field affect accessing `address.city`?

## 16. Takeaways

- **Redis key** identifies the entity's Hash; **hash field** identifies each property inside.
- `@RedisHash` defines the keyspace, `@Id` defines the ID, and `MappingRedisConverter` performs bidirectional Java ↔ Redis Hash mapping.
- Complex properties, collections, and maps are typically flattened into path-based field names. `_class` metadata helps reconstruct Java types.
- `@Indexed` uses additional Redis structures to support lookups; index maintenance is tied to the Repository mechanism.
- `save` may rewrite the entire Hash; use `PartialUpdate` or direct Hash APIs when selective updates are needed, while considering consistency.
- `HashMapper` and `RedisConverter` serve different integration styles. Serializers and Hash formats must be consistent between writing and reading.

### Official References

- [Spring Data Redis — Object-to-Hash Mapping](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/mapping.html)
- [Spring Data Redis — Redis Repositories: Usage](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/usage.html)
- [Spring Data Redis — Hash Mapping / HashMapper](https://docs.spring.io/spring-data/redis/reference/redis/hash-mappers.html)
- [Spring Data Redis — Secondary Indexes](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/indexes.html)
- [Spring Data Redis — Time To Live](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html)
