# Identifying Entities with @Id in Spring Data Redis

## 1. The Role of Identifiers When Mapping Entities to Redis

Redis is a key–value store. To store a Java object as retrievable data, the application needs to answer the question: **Under which Redis key does this object live?** In Spring Data Redis Repositories, `@Id` marks the entity's identifier property, while `@RedisHash` specifies the keyspace used to store that entity.

Suppose the application manages a customer with code `c-1001`:

~~~java
@RedisHash("customers")
public class Customer {
    @Id
    private String id;
    private String displayName;
}
~~~

When saving a `Customer` with `id = "c-1001"`, the Redis Repository typically represents the entity as a Redis Hash under the key:

~~~text
customers:c-1001
~~~~~~~~~ ~~~~~~
keyspace   ID
~~~

Two concepts must be distinguished:

- **`@Id`**: tells Spring Data which field represents the identity of a record; the Repository uses it to locate the object to find, save, update, or delete.
- **`@RedisHash("customers")`**: chooses the keyspace name, i.e., the prefix part of the key in Redis.

The part after `:` is neither the Java class name nor a separate key that you pass directly to Redis. It is the value of the `@Id` property after Spring Data converts it into the form used in the key.

For example, two entities can have the same ID while belonging to two different keyspaces:

~~~text
customers:c-1001
orders:c-1001
~~~

They are two distinct Redis keys. Conversely, two objects of the same type, same keyspace, and same ID point to **the same storage identity**, so a later save operation can overwrite the content of the earlier object.

> **Key point:** `@Id` identifies an entity within Spring Data Redis's keyspace. It does not automatically create unique constraints across arbitrary business properties, does not provide foreign keys, and does not turn Redis into a relational database.

## 2. Choosing the Right Annotation

Imports for Redis Repository:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
~~~

Do not confuse `org.springframework.data.annotation.Id` with `jakarta.persistence.Id` commonly used in JPA.

| Annotation | Role |
| --- | --- |
| `@Id` | Declares the property used as the identifier for Spring Data |
| `@RedisHash` | Declares an entity mapped to a Redis Hash; can specify keyspace and default TTL |
| `@Indexed` | Requests creation of a secondary index supporting lookup by property |
| `@TimeToLive` | Represents the entity's remaining time to live under the Repository mechanism |

A property like `email` annotated with `@Indexed` still **does not replace** `@Id`. The ID is the primary address of the entity; secondary indexes only support querying by other values.

In a simple model, placing `@Id` on a field is the cleanest and easiest approach to maintain. If using property access via getters or custom mapping configurations, keep the mapping style consistent across the entire entity.

## 3. Complete Example with Spring Boot and Redis Repository

The sample application needs the `spring-boot-starter-data-redis` dependency. Spring Boot typically auto-configures the Redis connection and Redis Repositories when the corresponding starter is present. If configuring manually, you can use `@EnableRedisRepositories` and specify the package scope to scan.

### 3.1. Connection Configuration

Example `application.yml` for Redis running on a development machine:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
~~~

In a real application, address, TLS, authentication, and topology depend on the deployment environment. They do not change the meaning of `@Id`.

### 3.2. `Customer` Entity

~~~java
package example.redis.customer;

import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("customers")
public class Customer {

    @Id
    private String id;

    private String displayName;
    private String email;

    public Customer() {
        // For object instantiation when reading data.
    }

    public Customer(String id, String displayName, String email) {
        this.id = id;
        this.displayName = displayName;
        this.email = email;
    }

    public String getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }

    public String getEmail() {
        return email;
    }

    public void setId(String id) {
        this.id = id;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
~~~

Important points:

1. `id` is the identifier property; in this example it has type `String` for easy exchange with Redis and APIs.
2. `displayName` and `email` are regular data properties of the entity.
3. The `customers` prefix is part of the storage contract. Changing it makes the Repository look in a different set of Redis keys.
4. A no-arg constructor and setters make the example easy to use with the mapping mechanism. Spring Data also supports other instantiation styles, but this style is straightforward for learning `@Id`.

### 3.3. Repository Using the Matching ID Type

~~~java
package example.redis.customer;

import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, String> {
}
~~~

The second generic argument, `String`, must match the type of the `@Id` property in `Customer`.

Thanks to `CrudRepository`, we get common operations:

~~~java
repository.save(customer);
repository.findById("c-1001");
repository.existsById("c-1001");
repository.deleteById("c-1001");
~~~

There is no need to manually concatenate `"customers:" + id` when calling these methods; the Repository uses the entity's metadata to determine the keyspace and physical key.

### 3.4. Service for Creating, Finding, Updating, and Deleting

~~~java
package example.redis.customer;

import java.util.Optional;
import java.util.UUID;

import org.springframework.stereotype.Service;

@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Customer create(String displayName, String email) {
        String id = UUID.randomUUID().toString();
        Customer customer = new Customer(id, displayName, email);
        return repository.save(customer);
    }

    public Optional<Customer> find(String id) {
        return repository.findById(id);
    }

    public Optional<Customer> rename(String id, String newDisplayName) {
        return repository.findById(id).map(customer -> {
            customer.setDisplayName(newDisplayName);
            return repository.save(customer);
        });
    }

    public void delete(String id) {
        repository.deleteById(id);
    }
}
~~~

These methods illustrate a consistent principle: when creating a new record, assign an ID; when updating, **keep the same ID** and modify the data fields.

At the API level, the ID returned from `create` should be retained by the client to call `find` or `rename`. This is the stable identifier for retrieving the entity, independent of name or email changes.

## 4. How Is a Redis Key Constructed from @Id?

Consider the entity:

~~~java
Customer customer = new Customer(
    "c-1001",
    "Nguyen An",
    "an@example.test"
);

customerRepository.save(customer);
~~~

Conceptual mapping:

~~~text
Java object
+------------------------+
| Customer               |
| id          = c-1001   | --+
| displayName = Nguyen An|   |
| email       = ...      |   |
+------------------------+   |
                             v
           @RedisHash("customers") + @Id
                             |
                             v
                     Redis Hash
                 key: customers:c-1001
                 fields: displayName, email,
                         mapping metadata (if any)
~~~

In Redis Repository's default storage mode, the Redis key contains the ID; the converter maps the remaining properties into Redis Hash fields. The detailed structure may include a type metadata field, such as `_class`. Do not treat this physical layout as a fixed contract for manipulating with raw Redis commands while the application still uses the Repository.

Spring Data Redis Repository may also maintain auxiliary structures to support listing entities and secondary indexes. Therefore, saving or deleting a Redis Hash directly with `HSET`/`DEL` is **not fully equivalent** to `repository.save`/`repository.deleteById`.

### Observing via Redis CLI

After running `repository.save` with ID `c-1001`, you can inspect:

~~~bash
redis-cli TYPE customers:c-1001
redis-cli HGETALL customers:c-1001
redis-cli EXISTS customers:c-1001
redis-cli SCAN 0 MATCH 'customers:*' COUNT 100
~~~

`TYPE` typically returns `hash`. `HGETALL` displays the Hash data; actual field names and metadata depend on mapping configuration. `SCAN` is only for inspecting keys by prefix; it is not part of the Repository contract and does not replace lookup by ID.

An example of partial data might look like:

~~~text
1) "_class"
2) "example.redis.customer.Customer"
3) "displayName"
4) "Nguyen An"
5) "email"
6) "an@example.test"
~~~

This is an **illustration**, not a mandatory output template. The point to remember is that the ID appears in the **Redis key**, while the entity is mapped as a Hash inside.

## 5. ID Is Identity, Not a Freely Mutable Property

Suppose Redis already holds:

~~~text
customers:c-1001  ->  {displayName: "Nguyen An"}
~~~

Then the application changes the object's ID as well and calls `save`:

~~~java
Customer customer = repository.findById("c-1001").orElseThrow();

customer.setId("c-2002");
repository.save(customer);
~~~

At this point, the Repository determines the save target from the **new ID** `c-2002`. It has no obligation to treat that operation as a command to "rename the Redis key and clean up the old key." Depending on prior data, the key `customers:c-1001` may still remain, leading to two records for what the application previously considered one customer.

A safer design is:

- Treat the ID as **business-immutable** after entity creation.
- If an identifier must change, write a deliberate migration process: verify the new ID is unused, create the new data, update related references, remove the old record, and handle failures between steps.
- If you only want to change a name or email, update only those fields and keep the original ID.

Do not use email or phone number as the ID simply because they appear unique. They can change, contain personal information, and require separate normalization rules. A synthetic, stable identifier like a UUID is usually simpler.

## 6. Generating IDs: Manual Assignment, UUID, and Business Identifiers

There are three common approaches.

| ID Choice | Example | When Appropriate | Points to Consider |
| --- | --- | --- | --- |
| Application-generated UUID | `e3f1...` | Multiple instances creating entities concurrently | Hard for humans to read, long |
| Stable business ID | `customer-2026-001` | A standard code-issuing system already exists | Needs a mechanism to prevent duplicates |
| ID from an external system | `crm-84291` | Redis is a replica/cache of source data | Must preserve namespace and issuing source |

### Explicitly Assigning a UUID

~~~java
String id = UUID.randomUUID().toString();

Customer customer = new Customer(
    id,
    "Tran Binh",
    "binh@example.test"
);

Customer saved = repository.save(customer);
System.out.println(saved.getId());
~~~

Assigning before calling `save` clarifies the source of ID generation and gives the service an identifier right away for logging, returning in APIs, or linking with other systems.

Some Spring Data mechanisms support generating an identifier when the ID property is unset, but details depend on the adapter, ID type, and library version. **Do not assume every ID type is auto-generated by Redis Repository in the way your application expects.** If uniqueness and ID format are business requirements, define an explicit ID-issuing rule in the application.

### What Does "Unique" Mean?

Distinguish between:

- **Unique within a keyspace**: two different customers must not receive the same ID if stored together in `customers`.
- **System-wide unique**: not strictly required; ID `42` can validly appear in both `customers:42` and `orders:42`.
- **Uniqueness of other properties**: `@Id` does not guarantee that emails or phone numbers won't repeat.

If you must use short, incrementing identifiers, design a dedicated allocator, for example based on `INCR` or the business database. Account for multiple instances, data resets, runtime environments, and collision avoidance. `@Id` only consumes an already issued identifier; it does not solve the entire ID allocation problem.

## 7. How Do @Id and @Indexed Differ?

The ID is the primary access path:

~~~java
repository.findById("c-1001");
~~~

However, if you want to find a customer by email:

~~~java
repository.findByEmail("an@example.test");
~~~

Redis has no built-in concept of automatically "scanning every field of every Hash like SQL." Spring Data Redis Repository can create a **secondary index** for properties annotated with `@Indexed`.

Example:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("customers")
public class Customer {

    @Id
    private String id;

    private String displayName;

    @Indexed
    private String email;

    // Constructors, getters, and setters similar to the previous example.
}
~~~

Repository adds a lookup method:

~~~java
import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, String> {

    List<Customer> findByEmail(String email);
}
~~~

Comparison:

| Property | `@Id` | `@Indexed` |
| --- | --- | --- |
| Purpose | Defines the entity's identity | Supports querying by value |
| Affects the primary Redis key | Yes | No |
| API example | `findById(id)` | `findByEmail(email)` |
| Can there be multiple per entity? | One logical identifier | Multiple fields can be indexed |
| Guarantees uniqueness? | Requires non-colliding ID allocation in keyspace | Does not create a unique constraint by default |

A customer with ID `c-1001` remains the same entity when their email changes. Indexes must be maintained through Repository operations. If you edit the Hash directly via Redis CLI while the Repository manages indexes, the system can end up with indexes out of sync with data.

## 8. When Saving an Entity with an Existing ID

Suppose two objects share the same ID:

~~~java
Customer first = new Customer(
    "c-1001",
    "Nguyen An",
    "an@example.test"
);

Customer second = new Customer(
    "c-1001",
    "New Name",
    "new@example.test"
);

repository.save(first);
repository.save(second);
~~~

Both saves target `customers:c-1001`. The second operation updates the data associated with that same identity rather than creating "two rows" with a duplicate primary key.

**Do not treat `save` as a mechanism that enforces create-only uniqueness.** If business rules require "create only if not yet present," checking `existsById` and then calling `save` is not safe under concurrency:

~~~java
if (!repository.existsById(id)) {
    repository.save(customer); // Another request could still slip in between.
}
~~~

Between the two operations, another instance could already have created an entity with the same ID. When atomicity is required, choose an appropriate conditional mechanism (such as `SET ... NX` or a Lua script in Redis for a custom-designed key structure, or a transaction/unique constraint in a durable data store) and consider how Repository indexes are maintained. Do not mechanically replace `repository.save` with `SET NX` on the same key because the Repository also handles Hash mapping and metadata.

## 9. Finding, Checking Existence, and Deleting via ID

With a `String` ID type:

~~~java
String id = "c-1001";

Optional<Customer> customer = repository.findById(id);
boolean exists = repository.existsById(id);

repository.deleteById(id);
~~~

All of these operations start from a logical ID; the Repository resolves the Redis key using the keyspace and converter.

### Non-existent ID

If no entity exists under the corresponding key, `findById` returns `Optional.empty()`. In a REST API, this is often mapped to HTTP 404; in batch jobs, it may be skipped or logged depending on requirements.

Do not use an `existsById` result as a guarantee that a subsequent `findById` will succeed, because another process or TTL expiration could remove the key between the two commands.

### Deleting by ID

`deleteById` expresses the intent to delete an entity managed by the Repository. It is preferable to guessing the Redis key and calling `DEL`, especially when secondary indexes or auxiliary structures exist.

If you call `redisTemplate.delete("customers:" + id)` directly, Redis may delete the primary Hash while structures maintained by the Repository risk not being updated accordingly. Once you choose Redis Repository, use the Repository consistently for the entity lifecycle.

## 10. How Does @Id Relate to TTL?

`@Id` explains **which entity** is being accessed; TTL explains **how long the entity remains valid**. They are independent mechanisms that both participate in the storage lifecycle.

Example:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash(value = "login-sessions", timeToLive = 1800)
public class LoginSession {
    @Id
    private String id;

    private String userId;

    // Constructors, getters, setters...
}
~~~

Meaning:

- `login-sessions` is the keyspace.
- `id` is the session identifier.
- `timeToLive = 1800` declares a default lifetime of 1,800 seconds under the Redis Repository mechanism.

A session with ID `s-42` corresponds to a Redis key like `login-sessions:s-42`. When the key expires, `findById("s-42")` no longer returns the entity.

**Expiration does not automatically generate a new ID.** If the application needs to refresh a session, it must decide whether to keep or rotate the ID according to security and business rules. Reusing an expired ID can cause confusion between old and new sessions in systems with listeners or asynchronous tasks; consider using a new session ID or a separate generation number.

When using Repository features like TTL and secondary indexes, let the Repository manage saves/deletes to maintain the best possible consistency within the limits of Redis notifications.

## 11. Root Entity ID vs. Nested Object ID

In an aggregate stored under a single Redis key, the `@Id` of the **root entity** determines the storage address. Child objects are not necessarily independent entities just because they have a field named `id` in Java.

Example:

~~~java
@RedisHash("orders")
public class Order {

    @Id
    private String id;

    private ShippingAddress shippingAddress;

    // Constructors, getters, setters...
}

public class ShippingAddress {
    private String city;
    private String street;

    // Constructors, getters, setters...
}
~~~

Conceptually, `orders:o-10` stores the fields of `Order` and the address data mapped inside it. `ShippingAddress` in this example has no Repository or independent Redis key like `shipping-addresses:...`.

If `ShippingAddress` needs its own lifecycle, lookups, and independent updates, design it as an independent aggregate with its own `@RedisHash` and `@Id`, then decide how to store the reference between the two aggregates. Redis Repository does not automatically provide all of JPA's foreign-key, cascade, and join behaviors.

## 12. What Is the Impact of Changing Keyspace or ID Type?

The storage identifier depends on both:

~~~text
Redis key = keyspace + separator + converted ID
~~~

Therefore, two changes must be treated as **storage schema changes**.

### Changing the Keyspace

Before:

~~~java
@RedisHash("customers")
~~~

After:

~~~java
@RedisHash("customer-profiles")
~~~

Same ID `c-1001`, but different physical keys:

~~~text
customers:c-1001
customer-profiles:c-1001
~~~

Without data migration, the new application may fail to find old entities. Redis retains the old keys until they are deleted or their TTL expires.

### Changing the ID Type

Before:

~~~java
@Id
private String id;
~~~

After:

~~~java
@Id
private Long id;
~~~

Changing the Java type can alter ID conversion, data parsing, Repository generic types, and API formats. Do not assume an old Redis key is automatically compatible with the new model. Check the ID format, legacy read path, and migration strategy.

Even changing ID formatting from the string `"0012"` to the number `12` can represent different keys. Do not convert IDs to numbers if leading zeros carry meaning.

## 13. Common Errors and How to Spot Them

| Symptom | Possible Cause | Approach |
| --- | --- | --- |
| `findById` always returns empty even though data is visible in Redis | Keyspace, ID, DB, or storage format differs from Repository | Compare `@RedisHash`, ID type, and actual Redis key |
| Changing email creates a new record | Application used email as ID and mutated the ID | Use an immutable ID and keep email as a regular property |
| Two create-customer requests overwrite each other | Colliding ID allocator, `save` with same ID | Generate non-colliding IDs; use conditional creation when needed |
| Hash exists but indexed query finds nothing | Data was written directly via Redis commands without updating indexes | Use Repository or rebuild indexes consistently |
| Deleted via `DEL` but Repository results behave strangely | Auxiliary structures/secondary indexes were not updated | Use `deleteById` to manage lifecycle |
| ID unrecognized after changing type | ID conversion and repository generics out of sync | Keep type consistent, migrate legacy data |
| Entity not found after renaming `@RedisHash` | Redis key prefix changed | Plan a keyspace migration |
| `findById` used to work, then returns empty | TTL expired or another process deleted it | Distinguish identity from expiration lifetime |

### Using the JPA Annotation by Mistake

Avoid this in a Redis entity if you intend to use the Spring Data Redis Repository mechanism:

~~~java
import jakarta.persistence.Id; // Annotation for JPA models.
~~~

Explicitly declare:

~~~java
import org.springframework.data.annotation.Id;
~~~

If the same class is used across multiple persistence mechanisms, annotations and mapping configurations can overlap. It is usually better to have models tailored to each storage technology rather than assuming one annotation carries the same semantics everywhere.

### Confusing the ID with the Full Redis Key

Do not pass the already-prefixed physical key as an ordinary ID:

~~~java
repository.findById("customers:c-1001"); // Wrong if the actual ID is "c-1001".
~~~

The correct call is:

~~~java
repository.findById("c-1001");
~~~

The Repository prepends the keyspace automatically. If you assign `"customers:c-1001"` to `@Id`, the application may end up creating a key like `customers:customers:c-1001`, making data lookups confusing.

## 14. When to Use Repository vs. RedisTemplate?

`@Id` has meaning within **Spring Data's entity mapping model**. If code only uses `StringRedisTemplate` or `RedisTemplate` for raw key operations, `@Id` on a Java class does not automatically take effect.

Comparison:

| Task | Redis Repository | RedisTemplate |
| --- | --- | --- |
| Saving a Java entity | `repository.save(customer)` | Manually choose key, serializer, and structure |
| Looking up by ID | `repository.findById(id)` | Manually assemble Redis key and read data |
| Identifying via `@Id` | Yes | Not automatically activated just because the object has the annotation |
| Keyspace via `@RedisHash` | Yes | Managed manually |
| Repository secondary indexes | Yes, when configured properly | Designed and maintained manually |
| Controlling specialized Redis commands | Abstracted via Repository | More flexible |

If the application primarily works with domain entities (customers, login sessions, shopping carts), Redis Repository helps standardize identity and reduce manual key concatenation.

If the application only needs a counter, lock, list, or simple key–value cache, `RedisTemplate` may be a better fit. When using it, however, identity and key naming are the code's responsibility, not `@Id`'s.

## 15. Mini Practice Exercise

Goal: observe that **keeping the ID updates the same entity; changing the ID points to a different Redis key**.

Set up Redis and the `Customer`/`CustomerRepository` example from Section 3. From a snippet executed in the application:

~~~java
Customer first = repository.save(
    new Customer("demo-1", "Initial Name", "first@example.test")
);

Customer loaded = repository.findById("demo-1").orElseThrow();
loaded.setDisplayName("Updated Name");
repository.save(loaded);

System.out.println(
    repository.findById("demo-1")
              .orElseThrow()
              .getDisplayName()
);
// Updated Name

Customer another = repository.save(
    new Customer("demo-2", "Another Customer", "second@example.test")
);

System.out.println(repository.existsById("demo-1")); // true
System.out.println(repository.existsById("demo-2")); // true
~~~

Inspect the keys:

~~~bash
redis-cli TYPE customers:demo-1
redis-cli TYPE customers:demo-2
redis-cli HGETALL customers:demo-1
redis-cli HGETALL customers:demo-2
~~~

In this example, `demo-1` and `demo-2` are independent because their IDs differ; changing `displayName` does not change the ID.

After observing, clean up the data using the Repository:

~~~java
repository.deleteById("demo-1");
repository.deleteById("demo-2");
~~~

Cleaning up via the Repository ensures the repository's own data management steps run alongside deletion.

## 16. Frequently Asked Questions

**What happens if `@Id` is omitted?**

Spring Data may recognize an identifier property by convention in some cases, but explicitly declaring `@Id` removes ambiguity and clarifies the model's intent. In documentation and sample code, always use the explicit annotation.

**Must `@Id` be of type `String`?**

Not necessarily. However, `String` is convenient for examples and APIs. When choosing another type, consider Spring Data's ID conversion support, key string stability, and compatibility with existing stored data.

**Can an auto-incrementing `Long` be used like a SQL primary key?**

You can design an application with numeric IDs, but `@Id` by itself is not equivalent to JPA's `@GeneratedValue(strategy = IDENTITY)`. You need an appropriate ID allocation strategy, especially across multiple instances.

**Can there be two `@Id` fields on the same entity?**

No. A Redis aggregate needs a single clear logical identifier. If the domain has a composite key, design a stable ID type/string and explicit encoding rules instead of expecting Redis Repository to support SQL-style composite primary keys automatically.

**Do I also need to store the ID as a field inside the Redis Hash?**

In the Repository model, the ID already participates in the primary Redis key. Let the converter decide how to represent the entity inside the Hash. Only store an additional business ID field if there is a specific reason; avoid creating two potentially conflicting sources of truth.

**Does changing `@Id` automatically rename the old Redis key?**

Do not treat changing an ID value as a rename operation. Assigning a new ID means choosing a new storage address; if you want a migration, actively handle old data and references.

**Does using `@Id` prevent concurrent requests from overwriting each other?**

No. The ID helps two requests locate the same entity; concurrent write control, conditional creation, and business consistency require additional appropriate mechanisms.

**If a Redis key is removed by TTL, is the ID still valid?**

The ID value on the client is still a string, but it no longer points to an existing entity. `findById` will not find data after the key expires.

## 17. Key Takeaways for Entity Design

- Place `@Id` from `org.springframework.data.annotation.Id` on a property representing a stable identity.
- Use `@RedisHash("...")` to pick a consistent keyspace; understand that the Redis key typically takes the form `keyspace:id`.
- In `CrudRepository<Entity, IdType>`, `IdType` must match the `@Id` type.
- Issue IDs using clear rules; application-generated UUIDs are a straightforward option.
- Keep the ID when updating data; treat changing an ID as moving to a new storage identity.
- Distinguish `@Id` from `@Indexed`, TTL, unique constraints, and concurrency control mechanisms.
- When using a Repository, prefer the Repository to save/delete entities so related mapping structures remain maintained.
- Consider migration before changing keyspace, ID type, or ID encoding conventions.

## References

- [Spring Data Redis – Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html)
- [Spring Data Redis – Object-to-Hash Mapping](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/mapping.html)
- [Spring Data Commons – Object Mapping Fundamentals](https://docs.spring.io/spring-data/commons/reference/object-mapping.html)
- [Spring Data Commons – Core Concepts (Repositories)](https://docs.spring.io/spring-data/commons/reference/repositories/core-concepts.html)
