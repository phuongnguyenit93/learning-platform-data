# How Keys Are Formed from Keyspace and Identifier in Redis Repositories

When using **Spring Data Redis Repository**, developers typically work with a Java object via `save()`, `findById()`, and `deleteById()`, without manually concatenating key name strings before every Redis command. However, Redis still stores data at specific **physical keys**. Spring Data Redis determines an entity's key using two primary pieces of information: the **keyspace** (the namespace for the entity type) and the **identifier** (`id`) of each record.

Understanding this mechanism explains why calling `findById("u-100")` reads `customers:u-100`, why two entities with the same ID can still be stored separately, and why scanning keys with the `customers` prefix sometimes reveals keys that the application did not create directly.

## 1. What Are Keyspace and Identifier?

A **keyspace** in the context of Redis Repositories is a logical name for a group of objects of the same type, similar to a *namespace* or storage prefix. An **identifier** is the value that distinguishes each object within that group. An entity key is typically formed according to the convention:

```text
Redis key = <keyspace> + ":" + <id>
```

Examples:

| Keyspace | ID | Entity key in Redis |
|---|---|---|
| `customers` | `u-100` | `customers:u-100` |
| `customers` | `u-101` | `customers:u-101` |
| `orders` | `u-100` | `orders:u-100` |
| `sessions` | `8e23` | `sessions:8e23` |

Two takeaways follow from the table above:

- **Same keyspace, different ID:** two independent entities, such as `customers:u-100` and `customers:u-101`.
- **Same ID, different keyspace:** still two distinct physical keys, such as `customers:u-100` and `orders:u-100`.

For a given entity type, the **(keyspace, id) pair** determines the entity's address in Redis. `id` does not have to be unique across the entire Redis server, but it must be stable and unique within the keyspace of the data type being stored.

> This is the key-naming mechanism of **Spring Data Redis Repository**. The Redis server itself knows nothing about "entities", "repositories", or `@Id`; to Redis, `customers:u-100` is simply a key name consisting of bytes.

## 2. Configuring Keyspace with `@RedisHash`

Example of building a customer entity:

```java
package example.redis;

import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("customers")
public class Customer {

    @Id
    private String id;

    private String fullName;

    private String email;

    public Customer() {
    }

    public Customer(String id, String fullName, String email) {
        this.id = id;
        this.fullName = fullName;
        this.email = email;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String fullName) {
        this.fullName = fullName;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
```

In this example:

- `@RedisHash("customers")` specifies that the **keyspace** is `customers`.
- `@Id` marks the `id` property as Spring Data's **entity identifier**.
- `id = "u-100"` leads to the logical key `customers:u-100`.
- Other properties such as `fullName` and `email` are mapped into the entity's data; they **do not automatically change the primary key name**.

`@RedisHash` is not the name of a pre-existing Redis Hash. This annotation provides mapping metadata to Spring Data Redis: when writing a `Customer`, the repository stores the entity contents under the key formed from the keyspace and id, typically using the Redis **HASH** data type.

Conceptually:

```text
Customer Java object
  id       = "u-100"
  fullName = "Nguyen An"
  email    = "an@example.test"
         |
         v
@RedisHash("customers") + @Id("u-100")
         |
         v
Primary key in Redis: customers:u-100
Redis type: HASH
Fields: fullName, email, ... (may include Java type metadata)
```

Physical field names, metadata such as `_class`, and value conversion depend on the `RedisConverter`/mapping configuration. The diagram illustrates the rule for naming the **entity key**, without guaranteeing that every byte of the HASH contents is identical across all configurations.

### What Happens If `@RedisHash("...")` Is Omitted?

Spring Data Redis has a mechanism to determine the keyspace via entity metadata and mapping configuration. If an explicit keyspace is not specified, the inferred name may be tied to the Java type name or the conventions of the current configuration. For data that must survive class/package refactorings, **declare a clear, stable keyspace** to prevent unintended physical key renames.

Besides `@RedisHash`, a project can configure entity keyspaces via `KeyspaceConfiguration` and `@EnableRedisRepositories`. This is suitable when you want to centralize namespace naming conventions in configuration rather than placing them directly on classes. Regardless of how it is declared, runtime execution needs **a consistent keyspace rule** for each entity type.

## 3. `@Id`: Which Property Is Used to Form the Key?

The repository identifies the ID through Spring Data metadata, typically `org.springframework.data.annotation.Id`. When saving:

```java
Customer customer = new Customer(
        "u-100",
        "Nguyen An",
        "an@example.test"
);

customerRepository.save(customer);
```

The main result to understand:

```text
keyspace  = "customers"
entity id = "u-100"
Redis key = "customers:u-100"
```

The `String` type is convenient for illustration, though identifiers can be other types if the application's mapping supports converting them into a key representation. For example, a numeric ID `42` typically produces the suffix `42`; composite ID objects should have an explicit conversion rule rather than relying on the default `toString()`.

### Where Do IDs Come From?

There are two common approaches:

1. **The application supplies the ID before saving**, such as `"u-100"`, a business code, a UUID generated at the service layer, or an identifier from another system.
2. **Spring Data Redis assigns an ID for a new entity** when the ID type and mapping path support auto-generation (for instance, an unset `String` field can often receive a UUID). Always use the ID value returned/populated on the entity after `save()`, rather than predicting the generated key name yourself.

Example with an unassigned `String id`:

```java
Customer customer = new Customer(
        null,
        "Tran Binh",
        "binh@example.test"
);

Customer saved = customerRepository.save(customer);
String assignedId = saved.getId();

System.out.println("Repository ID: " + assignedId);
System.out.println("Expected key: customers:" + assignedId);
```

The resulting `assignedId` is the authoritative source to retrieve the entity later:

```java
customerRepository.findById(assignedId);
```

Do not derive the ID from `fullName` or `email` if those fields can change. Choosing a stable identifier is a data design decision; Spring Data Redis simply executes the configured mapping.

## 4. How Does the Repository Execute `save()`, `findById()`, and `deleteById()`?

Repository declaration:

```java
package example.redis;

import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, String> {
}
```

Once the project has configured the Redis connection and enabled Redis repositories, Spring Data generates an implementation for the interface above. The relationship between Java calls and primary keys can be pictured as follows:

| Repository call | Entity/id | Targeted primary key |
|---|---|---|
| `save(customer)` | `customer.id = "u-100"` | `customers:u-100` |
| `findById("u-100")` | `"u-100"` | `customers:u-100` |
| `existsById("u-100")` | `"u-100"` | `customers:u-100` |
| `deleteById("u-100")` | `"u-100"` | `customers:u-100` |

Example of a complete lifecycle:

```java
Customer first = new Customer(
        "u-100", "Nguyen An", "an@example.test");

// Create or overwrite the entity sharing the same primary key.
customerRepository.save(first);

Customer loaded = customerRepository.findById("u-100")
        .orElseThrow();

loaded.setFullName("Nguyen An Binh");
customerRepository.save(loaded);

boolean stillExists = customerRepository.existsById("u-100");

customerRepository.deleteById("u-100");
```

Updating `fullName` does not change `id`, so the repository still targets the key `customers:u-100`. If two requests save two `Customer` objects with the same keyspace and id, they operate on **a single logical key**; they are not two distinct records. When you need to prevent overwrites from concurrent updates, you must design an appropriate synchronization or versioning mechanism, as the key name alone does not guarantee consistency.

### Changing an ID Differs from Changing a Normal Property

Suppose an old entity resides at `customers:u-100`, and the application later sets `id` to `u-200` and calls `save()`. The new storage address is `customers:u-200`; that operation should not be understood as a **RENAME** command that automatically deletes the old key. Depending on the execution path, the old key may still exist or auxiliary data may not be cleaned up as expected.

Therefore, typically:

- Choose the ID once when creating the entity; keep it **immutable** across business updates.
- If an ID change is truly needed, build an explicit migration workflow: read the old key, save data under the new ID, update related references, delete the old ID, and handle failures between steps.
- Do not treat `setId(...)` on an already saved object as an atomic Redis key rename.

## 5. Keyspaces Do Not Appear Only in HASH Key Names

A common surprise: Redis Repositories can also maintain **auxiliary keys** to manage entities within the same keyspace and serve indexed queries. Consequently, after saving a `Customer`, you may see multiple keys starting with `customers`, even if only one object was saved.

Conceptual example:

```text
customers:u-100          -> HASH containing Customer u-100 data
customers:u-101          -> HASH containing Customer u-101 data
customers                -> SET assisting in tracking entities of the keyspace
customers:email:...      -> secondary index key, if corresponding @Indexed exists
```

Exact index key names, data types, SET members, and metadata depend on the entity type, serializer, library version, and configuration. The important rule is that **primary entity keys** and **repository bookkeeping keys** are not the same thing.

### Why Does a `customers` Key Exist When Entities Live at `customers:u-100`?

Spring Data Redis Repository uses keyspace information to support operations such as `findAll()` or `count()` without arbitrarily scanning the entire Redis server with `KEYS *`. A common approach is maintaining a Redis **SET** tied to the keyspace to track saved entities.

Thus:

```text
HGETALL customers:u-100  -> read the HASH of one entity
TYPE customers           -> may be the keyspace management SET
SMEMBERS customers       -> inspect members in the keyspace management SET
```

A manual `HSET customers:u-999 ...` command only creates/modifies the HASH and **does not guarantee** that the management structures needed by the repository are updated. As a result, `findById("u-999")` may behave differently from `findAll()`, or indexed queries may miss the entity. To preserve the full repository model, write data through the repository or consistently maintain all auxiliary structures according to the mapping contract.

### Secondary Indexes When Using `@Indexed`

Suppose you want to find customers by email:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("customers")
public class Customer {
    @Id
    private String id;

    private String fullName;

    @Indexed
    private String email;

    // Constructor, getters, and setters similar to the previous example.
}
```

The repository can declare:

```java
import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, String> {

    List<Customer> findByEmail(String email);
}
```

`@Indexed` tells Spring Data Redis to maintain a secondary query structure for the `email` property. An index key can incorporate information about the keyspace, field name, and field value, with an index SET referencing matching entities. That is why running `SCAN MATCH customers*` returns more than just customer HASH keys.

**A keyspace is not a relational table.** Redis Repositories build several data structures to offer a Spring Data-like API; they do not turn Redis into an RDBMS with foreign key constraints, arbitrary queries, or default multi-key transactions.

## 6. Inspecting Key Creation with `redis-cli`

Suppose you called:

```java
customerRepository.save(new Customer(
        "u-100", "Nguyen An", "an@example.test"));
```

You can observe this in a lab environment:

```bash
# Check the type of the primary key.
redis-cli TYPE customers:u-100

# Read fields in the HASH.
redis-cli HGETALL customers:u-100

# Check TTL of the entity key.
redis-cli TTL customers:u-100

# Check the type of the supporting structure at the keyspace name itself.
redis-cli TYPE customers

# If TYPE customers returns "set", you can inspect its members.
redis-cli SMEMBERS customers

# Inspect keys with the prefix; use SCAN to avoid blocking like KEYS.
redis-cli SCAN 0 MATCH 'customers*' COUNT 100
```

`SCAN` only returns a partial result set per step. When the cursor is non-zero, you must keep calling it with the new cursor until completion. The `customers*` pattern is *pattern matching*, not a repository query, and does not distinguish primary HASH keys from SET/auxiliary keys. Always use `TYPE` to identify an object before reading it.

If Redis is running in **Cluster** mode, inspecting a single node only shows keys currently belonging to that node. In contrast, a `findById()` operation with a specific key is typically routed by a cluster-aware client to the slot holding that key. Do not conclude a key is missing simply because `SCAN` on one node did not show it.

## 7. Why Can't You Arbitrarily Mix an `id` into Another Type's Keyspace?

Compare two repositories:

```java
@RedisHash("customers")
class Customer {
    @Id String id;
    // ...
}

@RedisHash("orders")
class Order {
    @Id String id;
    // ...
}
```

With the same `id = "42"`, Spring Data Redis routes the entities to:

```text
Customer(id="42") -> customers:42
Order(id="42")    -> orders:42
```

The two keys are independent because they have different keyspaces. If both classes share `@RedisHash("shared")`, the same ID `42` targets the same key `shared:42`. Entity type metadata and HASH data can collide; giving repositories or classes different names **does not create separate storage areas** when they share a keyspace.

Therefore, when designing:

- Dedicate separate keyspaces to entity types whose data needs isolation.
- Share a keyspace only if you intentionally design a shared format and management strategy.
- Use stable, consistent keyspaces across service versions accessing the same data.
- When multiple applications connect to one Redis server, consider adding a system or environment prefix such as `billing:customers` or `test:customers` if sharing a server; preventing name collisions is the application's responsibility.

The keyspace name is part of the **data storage contract**, analogous to a database table name in terms of deployment compatibility. Changing `@RedisHash("customers")` to `@RedisHash("clients")` causes the new repository to look for IDs under the new prefix, while old keys remain named `customers:...`. Changing the annotation does not automatically migrate data.

## 8. Colons in IDs and Keyspaces: What Does the Generated Key Name Mean?

The `:` character is a human-readable convention to separate key name segments. Redis does not treat it as a hierarchical structure with a schema.

For example:

```text
keyspace = "customers"
id       = "tenant-a:u-100"

key = "customers:tenant-a:u-100"
```

This key is still **a single Redis key**; Redis does not treat `tenant-a` as a sub-table or automatically establish a relationship between `tenant-a` and `u-100`. However, if multiple parts of a system manually build or split key strings, an ID containing the delimiter can confuse parsing logic.

Several useful guidelines:

| Concern | Recommendation |
|---|---|
| ID contains `:` | Acceptable if clearly defined by the system, but do not parse keys using `split(":")` assuming exactly two parts |
| Email or URL as ID | Consider mutability, length, special characters, sensitive data in keys, and collisions |
| Composite ID `tenant + user` | Define normalization/escaping or a stable identifier to avoid multiple formats representing the same entity |
| Renaming an entity prefix | Requires a migration strategy for both primary data and secondary indexes |
| Multiple teams or environments sharing Redis | Use clear namespaces to avoid key collisions |

Do not use `id` as a substitute for all queryable attributes. If you need to look up by `email`, `phone`, or `status`, design appropriate indexes or use a dedicated queryable data source; packing every field into the key name will not make Redis Repositories automatically generate queries on them.

## 9. Relationship Between Keyspace, ID, and Hash Slots in Redis Cluster

In Redis Cluster, the **physical key name** is the input Redis uses to compute the hash slot (0–16383). For example:

```text
customers:u-100 ── hash slot ──> primary A
customers:u-101 ── hash slot ──> primary C
customers       ── hash slot ──> primary B
```

The diagram is illustrative: exact slots and primaries are determined by the hashing algorithm and active topology. Sharing the `customers:` prefix **does not mean** two keys reside on the same primary. The keyspace management key `customers` can also be in a different slot from entity keys `customers:<id>`.

This matters because a single repository `save()` call may need to write:

1. the entity's main HASH;
2. the keyspace entity-tracking structure;
3. secondary indexes for `@Indexed` properties;
4. TTL-related metadata, if enabled.

Auxiliary keys can belong to multiple hash slots. **Do not infer** from a single `repository.save()` call that all those physical modifications constitute one atomic Redis command across the cluster. `CROSSSLOT` limits, transactions, pipelining, and multi-key operations depend on the specific API, implementation, and Redis Cluster configuration.

A common Redis technique to force related keys into the same slot is using a *hash tag* inside `{...}`. However, putting the same fixed tag into every key of an entire keyspace concentrates all data into one slot, causing load imbalance. Do not alter Redis Repository key-naming conventions or add hash tags broadly without evaluating distribution needs and index structures.

## 10. Does TTL Change How Keys Are Formed?

No. TTL controls the lifespan of the **entity key**, not the components used to assemble `keyspace:id`.

Example of setting a default TTL for an entity:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash(value = "sessions", timeToLive = 300)
public class LoginSession {
    @Id
    private String id;

    private String userId;

    // Constructor, getters, and setters.
}
```

With ID `s-10`, the entity key is still named `sessions:s-10`; `timeToLive = 300` (seconds) only sets the expiration duration for that key. You can inspect it:

```bash
redis-cli TTL sessions:s-10
```

In some Spring Data Redis configurations, TTL also involves expiration event listeners, index updates, and temporary copies (*shadow copy/phantom copy*) used for events. Therefore, even after the primary HASH expires, related auxiliary keys may remain visible for a period or require cleanup mechanisms. Do not assume all repository metadata disappears at the exact same millisecond as the primary entity key.

If you use `@TimeToLive` on an entity property to provide dynamic TTLs, the expiration calculation can vary per instance, but the formula forming the **primary key** from keyspace and id remains the same.

## 11. Common Mistakes When Reasoning About Key Names

### Mistake 1: "The ID is `u-100`, why does `GET u-100` return nothing?"

The repository stores the entity under keyspace `customers`, so the primary key is `customers:u-100`. Furthermore, entity data is typically stored in a HASH, so `GET customers:u-100` does not match that data type; use `HGETALL` when inspecting via Redis CLI, and use `findById("u-100")` in the application.

### Mistake 2: "Renaming the class caused data to no longer be found"

Check the actual keyspace before and after renaming. If the keyspace is fixed via `@RedisHash("customers")`, renaming the Java class usually does not change the primary prefix; however, Java type metadata inside the HASH may still need attention. If you let the system infer the keyspace from entity type metadata, renaming the class or namespace can result in a different key name. Data migration must handle both primary keys and auxiliary repository keys.

### Mistake 3: "`findById()` finds it, but `findAll()` or `findByEmail()` misses data"

Check whether the record was written through the repository or via manual Redis commands. Creating only the main HASH does not guarantee that keyspace tracking sets and indexes were created/updated. If TTLs or out-of-band writes/deletes cause auxiliary structures to drift out of sync, scanning or querying via indexes may also differ from direct ID reads.

### Mistake 4: "`SCAN MATCH customers*` returns more keys than the number of customers"

Key-pattern matching operates at the physical Redis keyspace level: it can return entity HASHes, keyspace management SETs, and secondary indexes. Check `TYPE` on each key or use appropriate repository APIs to work with entities.

### Mistake 5: "Two classes with the same ID and same `@RedisHash` overwrite each other"

Two independent Java classes can still map to the same Redis address if they share the same keyspace and id. Change the naming of namespaces or ensure they intentionally share a common storage model.

### Mistake 6: "Setting a new `id` and calling `save()` should make the old key vanish automatically"

Under the keyspace/id composition rule, a new ID identifies a new address. Deleting the old data is a separate business step and cannot be assumed simply from saving an object whose ID was modified.

## 12. Complete Example: From Java Objects to Redis Keys

Suppose a system has two data types:

```java
@RedisHash("customers")
class Customer {
    @Id String id;
    String name;
}

@RedisHash("orders")
class Order {
    @Id String id;
    String customerId;
}
```

When saved:

```text
Customer{id="42", name="Mai"}
    -> customers:42

Order{id="42", customerId="42"}
    -> orders:42

Order{id="43", customerId="42"}
    -> orders:43
```

`orders:42` and `orders:43` may contain the property `customerId = "42"`, but Redis Repository **does not automatically create a foreign key** to `customers:42`. The reference property is just data on Order unless the application builds its own referencing or indexing mechanism.

If `customers:42` is deleted, Redis does not automatically delete `orders:42` or `orders:43`; conversely, deleting `orders:42` does not affect `customers:42`. Key formation rules distinguish storage addresses rather than encoding business relationships or cascading deletes.

To find all orders for a customer, you need an appropriate query structure (for example, a secondary index on `customerId`, if supported by your model and version) rather than assuming all orders with the same `customerId` are placed together under a single Redis key.

## 13. Design Decisions to Lock Down Early

| Decision | Impact on keys and repositories |
|---|---|
| Entity keyspace name | Determines the physical prefix and data compatibility across upgrades |
| ID type and generation source | Determines the suffix, entity retrievability, and identifier collisions |
| ID delimiter/normalization conventions | Prevents confusion when debugging, changing formats, or integrating multiple services |
| Whether multiple entities share a keyspace | Affects risk of overwrites and metadata collisions |
| Whether `findAll()` or property queries are needed | Determines auxiliary structures and indexes the repository must maintain |
| Whether TTL or Redis Cluster is used | Affects auxiliary key lifecycles, slot distribution, performance, and consistency |
| Whether manual Redis writes run alongside repositories | Requires unified management of HASHes, keyspace sets, and indexes |

A simple, sustainable convention for typical use cases is to assign an **explicit keyspace per entity type**, use an **immutable ID unique within the keyspace**, manage the lifecycle through the repository, and manipulate physical keys directly only when you fully understand the auxiliary metadata created by Spring Data Redis.

## 14. Self-Check

1. An entity declares `@RedisHash("products")` and `@Id String id = "p-5"`. What is the primary key?  
   **Answer:** `products:p-5`.
2. A `Customer` and an `Order` both have ID `"42"`, with keyspaces `customers` and `orders` respectively. Do they overwrite each other?  
   **Answer:** No, because the physical keys are `customers:42` and `orders:42`.
3. Why might `SCAN MATCH customers*` find keys that are not customer HASHes?  
   **Answer:** The repository may create keyspace management SETs, indexes, and auxiliary metadata under the same prefix.
4. Why might manually running `HSET customers:u-100` and then calling `findAll()` fail to return the expected result?  
   **Answer:** A manual `HSET` command does not reliably synchronize auxiliary structures managed by the repository.
5. Does changing `@RedisHash("customers")` to `@RedisHash("clients")` automatically migrate data?  
   **Answer:** No; those are two different physical namespaces, so a migration workflow is required if you want to keep existing data.
6. Does `@RedisHash(timeToLive = 300)` turn the key `sessions:s-10` into `sessions:300:s-10`?  
   **Answer:** No; TTL affects expiration duration and does not become part of the key name.

## 15. Conclusion

Redis Repositories form an **entity's primary key** from its **keyspace** and **identifier** following the common rule `<keyspace>:<id>`. `@RedisHash` establishes the namespace, and `@Id` establishes the value distinguishing each entity. That is why `findById(id)` can access the right data without the application manually assembling key name strings.

Because repositories also maintain tracking sets and secondary indexes, understanding the primary key name is only the starting point. When debugging, changing keyspaces, using TTLs, deploying Redis Cluster, or mixing manual Redis operations with repositories, you must account for **all related physical keys** and their lifecycles.

## References

- [Spring Data Redis Reference — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html): entity mapping, keyspaces, and repository supporting components.
- [Spring Data Redis Reference — Keyspaces](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/keyspaces.html): declaring `@RedisHash` and configuring keyspaces.
- [Spring Data Redis Reference — Object-to-Hash Mapping](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/mapping.html): converting Java objects to Redis Hashes.
- [Spring Data Redis Reference — Indexes](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/indexes.html): secondary indexes used in repository queries.
- [Spring Data Redis Reference — Time To Live](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html): TTL, expiration events, and effects on repository data.
- [Redis — Data types](https://redis.io/docs/latest/develop/data-types/): distinguishing Redis Hash, Set, and other key value types.
