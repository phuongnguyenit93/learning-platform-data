# Creating Secondary Indexes with `@Indexed`

In Spring Data Redis, Redis Repositories allow storing a Java entity as a Redis Hash and retrieving it via its identifier (`@Id`). However, many business requirements need to find objects by another attribute: email, account status, external order code, or city. Redis does not automatically create a search engine for every Hash field. A **secondary index** is a mechanism that helps the application find the IDs of entities sharing the same attribute value without scanning every Hash sequentially.

With **Spring Data Redis Repositories**, the `@Indexed` annotation declares a property that needs to be indexed. The framework writes additional index data when saving the entity and uses that index for supported repository query methods.

This lesson focuses on `org.springframework.data.redis.core.index.Indexed` in the `@RedisHash` model, how Redis Sets store the *attribute value → ID* relationship, querying by index, and the consequences when data changes.

## 1. Why Is Looking Up by ID Not Enough?

Suppose Redis contains customer profiles:

| ID | Email | Status | City |
| --- | --- | --- | --- |
| `c-101` | `lan@example.test` | `ACTIVE` | Hà Nội |
| `c-102` | `minh@example.test` | `ACTIVE` | Đà Nẵng |
| `c-103` | `hoa@example.test` | `BLOCKED` | Hà Nội |

With `CrudRepository<Customer, String>`, finding `c-101` using `findById("c-101")` is direct: Spring Data Redis knows the key storing the entity from the keyspace and ID.

However, to answer the question *"who is the customer with email `lan@example.test`?"*, the application needs another lookup path. Without secondary data structures or a dedicated search engine, Redis Hash does not provide a general-purpose command equivalent to:

~~~sql
SELECT * FROM customers WHERE email = 'lan@example.test';
~~~

Spring Data Redis can maintain a Redis Set representing the email value:

~~~text
customers:email:lan@example.test  →  { "c-101" }
customers:status:ACTIVE           →  { "c-101", "c-102" }
customers:address.city:Hà Nội     →  { "c-101", "c-103" }
~~~

When querying by email, the repository reads the corresponding set of IDs and then loads the entity Hashes. The key names here illustrate the default convention; the actual format can vary depending on keyspace, mapping, and version.

**`@Indexed` does not change the primary structure of the entity.** It adds Redis structures for lookup purposes. A duplicate value can be associated with multiple IDs because a Set holds multiple elements; an index does not automatically guarantee uniqueness.

## 2. How `@Indexed` Works in Context

Key components of the model:

| Component | Role |
| --- | --- |
| `@RedisHash("customers")` | Declares an entity stored as a Redis Hash, with keyspace `customers` |
| `@Id` | Marks the identifier used to retrieve the entity |
| `@Indexed` | Marks a property that needs a secondary index for queries |
| `CrudRepository` | Provides `save`, `findById`, `deleteById`, and supported query methods |
| Redis Hash | Stores the content of each entity |
| Redis Set | Holds the IDs associated with an indexed value |

Import the right annotation:

~~~java
import org.springframework.data.redis.core.index.Indexed;
~~~

This is an annotation belonging to **Spring Data Redis**. Do not confuse it with indexing annotations in JPA, MongoDB, full-text search, or another library.

**Important scope:** `@Indexed` takes effect when objects are written through the mapping mechanism of **Spring Data Redis repositories**. If you manually save JSON into Redis using `RedisTemplate.opsForValue().set(...)`, an arbitrary serializer will not automatically create secondary index Redis Sets like a repository does.

## 3. Declaring an Entity with Secondary Indexes

The example uses two classes: `Customer` is the root entity, and `Address` is a nested object inside the entity. The `Address` class is stored as embedded data, not referenced as a separate Redis Hash.

**`Customer.java`**

~~~java
package com.example.redis.customer;

import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("customers")
public class Customer {

    @Id
    private String id;

    @Indexed
    private String email;

    @Indexed
    private String status;

    private Address address;

    public Customer() {
        // Constructor for Spring Data to instantiate the object.
    }

    public Customer(String id, String email, String status, Address address) {
        this.id = id;
        this.email = email;
        this.status = status;
        this.address = address;
    }

    public String getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public Address getAddress() {
        return address;
    }

    public void setAddress(Address address) {
        this.address = address;
    }
}
~~~

**`Address.java`**

~~~java
package com.example.redis.customer;

import org.springframework.data.redis.core.index.Indexed;

public class Address {

    @Indexed
    private String city;

    private String street;

    public Address() {
    }

    public Address(String city, String street) {
        this.city = city;
        this.street = street;
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }

    public String getStreet() {
        return street;
    }

    public void setStreet(String street) {
        this.street = street;
    }
}
~~~

Meaning:

- `email` and `status` have `@Indexed` directly on the root entity.
- `address.city` is indexed because `city` inside the nested `Address` object has `@Indexed`.
- `address.street` is still stored in the Hash, but without a secondary index.
- `id` serves as the primary identifier; there is no need to add `@Indexed` just to call `findById`.

When querying a nested property, the property path is resolved according to the object structure, such as `address.city`.

### Avoid Confusing Embedded Properties with References

In the example, `Address` is an **embedded value object**. Spring Data Redis can map and index properties inside it. Using `@Reference` points to another entity that has its own storage and lifecycle; you should not assume that a repository will traverse a reference, index all properties of the referenced object, and support SQL-like join queries.

## 4. Writing the Repository and Querying by Index

**`CustomerRepository.java`**

~~~java
package com.example.redis.customer;

import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, String> {

    List<Customer> findByEmail(String email);

    List<Customer> findByStatus(String status);

    List<Customer> findByAddress_City(String city);

    List<Customer> findByEmailAndStatus(String email, String status);
}
~~~

Spring Data parses the method name and identifies the properties to look up. For indexed fields:

~~~java
Customer lan = new Customer(
    "c-101",
    "lan@example.test",
    "ACTIVE",
    new Address("Hà Nội", "Phố Huế")
);

Customer minh = new Customer(
    "c-102",
    "minh@example.test",
    "ACTIVE",
    new Address("Đà Nẵng", "Hải Châu")
);

repository.save(lan);
repository.save(minh);

List<Customer> byEmail =
    repository.findByEmail("lan@example.test");

List<Customer> activeCustomers =
    repository.findByStatus("ACTIVE");

List<Customer> inHaNoi =
    repository.findByAddress_City("Hà Nội");

List<Customer> activeLan =
    repository.findByEmailAndStatus("lan@example.test", "ACTIVE");
~~~

Semantically, the results are:

| Method | Expected IDs |
| --- | --- |
| `findByEmail("lan@example.test")` | `c-101` |
| `findByStatus("ACTIVE")` | `c-101`, `c-102` |
| `findByAddress_City("Hà Nội")` | `c-101` |
| `findByEmailAndStatus("lan@example.test", "ACTIVE")` | `c-101` |

The method name `findByAddress_City` uses an underscore to explicitly mark the nested property boundary. This naming style prevents the parser from ambiguously interpreting concatenated property names.

In the example, `findByEmailAndStatus` is a combined-condition query using a logical intersection between two indexed ID sets. The ability to combine conditions and the supported query operators depend on Redis Repository capabilities; it does not equate to a full SQL query engine.

### Queries Depend Exactly on the Indexed Value

`@Indexed` works best for **exact-value lookups**. If the email in Redis is `lan@example.test`, then `findByEmail("LAN@example.test")` is not automatically equivalent. This mechanism does not perform case-insensitive matching, Unicode normalization, fuzzy search, or substring search by default.

If the system treats emails as case-insensitive, define a consistent normalization rule before saving and before querying. For example, you can normalize the email according to the application's business policy and store the normalized value as an indexed property.

## 5. Inside Redis: Sets Mapping Values to IDs

With `@RedisHash("customers")`, the entity key typically has the form:

~~~text
customers:c-101
~~~

The Hash representing the customer data may include equivalent fields:

~~~text
email         → lan@example.test
status        → ACTIVE
address.city  → Hà Nội
address.street→ Phố Huế
_class        → type metadata if used by the mapper
~~~

In addition to the Hash, Redis Repository writes index sets. Logical model:

~~~text
                               save(Customer)
                                     │
                                     ▼
                             Spring Data Mapper
                        ┌────────────┼─────────────┐
                        ▼            ▼             ▼
                   Redis Hash    Email Index    Status Index
                  customers:c-101   (SET)          (SET)
                        │            │             │
                   source data      c-101          c-101
                                     │
                                     ▼
                               findByEmail(...)
                                     │
                                     ▼
                         fetch IDs from Redis Set
                                     │
                                     ▼
                          load Hash by each ID
                                     │
                                     ▼
                            List<Customer>
~~~

Redis command illustration to visualize the structures:

~~~redis
HGETALL customers:c-101
SMEMBERS customers:email:lan@example.test
SMEMBERS customers:status:ACTIVE
SMEMBERS customers:address.city:Hà Nội
~~~

In a standard mapping configuration, the `SMEMBERS` commands above show the set of IDs associated with the indexed value. **This is an observed example**, not a guarantee that every Redis Serializer/keyspace configuration produces byte-for-byte identical keys.

Redis Repository must also track which indexes an entity participates in so that old membership can be removed during updates or deletions. Auxiliary keys used for index management are internal mapper details; you should not build business logic directly on internal key names or modify them via Redis CLI.

### Why Use Redis Sets?

Sets allow storing **unique** IDs. When multiple customers have `status = ACTIVE`, a single Set records all matching IDs. For queries combining indexed values, set operations such as intersection and union provide the foundation for determining candidate IDs.

This is completely different from creating a unique `email → customer` key mapping. For example, two records with the same email can both belong to the same Set. **`@Indexed` is not a unique constraint.**

## 6. Creating and Updating Indexes Across the Entity Lifecycle

### 6.1. On Initial Save

Calling `repository.save(customer)` causes Spring Data Redis to store the Hash data and update the index sets corresponding to properties marked with `@Indexed`. As a result, supported repository query methods can find the entity by email, status, or city.

### 6.2. When an Indexed Value Changes

Suppose the email of `c-101` changes:

~~~java
Customer customer = repository.findById("c-101")
    .orElseThrow();

customer.setEmail("lan.new@example.test");
repository.save(customer);

// Expected results:
repository.findByEmail("lan@example.test");     // No longer contains c-101
repository.findByEmail("lan.new@example.test"); // Contains c-101
~~~

When changing data **through the Repository**, the mapping infrastructure is responsible for updating the membership of index sets. The proper usage is to modify the entity and save it back via the repository.

Do not directly modify the Hash while bypassing the mapping path:

~~~redis
HSET customers:c-101 email lan.other@example.test
~~~

The `HSET` command above changes a Hash field without automatically updating the secondary index Redis Sets managed by Spring Data Redis. In that case, a query for the old email may still return the ID, while the new email may not be found yet. A consistent write flow must unify how Hashes and indexes are updated.

### 6.3. When Deleting an Entity

~~~java
repository.deleteById("c-101");
~~~

The Redis Repository deletion path handles both entity data and related index metadata. If you manually delete the Hash via `DEL`, auxiliary sets may retain stale membership because the application bypassed the index management logic.

Saving/deleting an entity and its related index sets may involve multiple Redis commands. Do not assume the entire index update sequence is an atomic multi-key transaction unless you have specifically verified and designed the required consistency conditions.

### 6.4. When a Property Has a `null` Value

A property with no value has no concrete value to serve as an index key. For example:

~~~java
Customer customer = new Customer(
    "c-104",
    null,
    "PENDING",
    new Address("Huế", null)
);

repository.save(customer);
~~~

The application should not expect `findByEmail(null)` to work as a mechanism to find all records missing an email via a secondary index. If you need to query "no email yet", design your business data or an explicit indexable status property.

### 6.5. When Adding `@Indexed` to an Entity with Existing Data

Adding the annotation in source code does not automatically scan and create membership for all Hashes already saved from older versions. Existing records may not appear in queries using the new index.

When rolling out this feature on existing data, you must have a **backfill/reindex** strategy: read valid source records, pass the entities through the repository write path, or run a controlled reindexing process. Consider existing keys, TTL, concurrent updates, and rerunnability without corrupting data.

## 7. Integration Testing `@Indexed` with Real Redis

Simply seeing the annotation in code is not enough to prove queries work. A useful test should demonstrate three behaviors: **save and find**, **update value and refresh index**, and **delete and no longer find**.

Example dependency for a Spring Boot project with version management via BOM/plugin:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
}
~~~

Assume the `Customer` and `Address` classes along with the repository are declared as above. The test below uses Redis in Testcontainers. The test configuration class lets Spring Boot auto-configuration establish the Redis connection and enables repositories in the package containing `CustomerRepository`.

~~~java
package com.example.redis.customer;

import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.repository.configuration.EnableRedisRepositories;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = CustomerIndexIntegrationTest.TestApp.class)
@Testcontainers
class CustomerIndexIntegrationTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableRedisRepositories(basePackageClasses = CustomerRepository.class)
    static class TestApp {
    }

    @Container
    static final GenericContainer<?> REDIS =
        new GenericContainer<>(DockerImageName.parse("redis:7.2-alpine"))
            .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry properties) {
        properties.add("spring.data.redis.host", REDIS::getHost);
        properties.add("spring.data.redis.port",
            () -> REDIS.getMappedPort(6379));
    }

    @Autowired
    CustomerRepository repository;

    @Test
    void findByIndexedPropertyAndRefreshIndexAfterUpdate() {
        String id = "it-" + UUID.randomUUID();
        String originalEmail = id + "@example.test";
        String newEmail = id + ".new@example.test";

        try {
            Customer customer = new Customer(
                id,
                originalEmail,
                "ACTIVE",
                new Address("Huế", "Lê Lợi")
            );
            repository.save(customer);

            assertThat(ids(repository.findByEmail(originalEmail)))
                .contains(id);
            assertThat(ids(repository.findByAddress_City("Huế")))
                .contains(id);

            customer.setEmail(newEmail);
            repository.save(customer);

            assertThat(ids(repository.findByEmail(originalEmail)))
                .doesNotContain(id);
            assertThat(ids(repository.findByEmail(newEmail)))
                .contains(id);

            repository.deleteById(id);

            assertThat(ids(repository.findByEmail(newEmail)))
                .doesNotContain(id);
        } finally {
            repository.deleteById(id);
        }
    }

    private static List<String> ids(List<Customer> customers) {
        return customers.stream().map(Customer::getId).toList();
    }
}
~~~

Each run generates a unique ID and email, avoiding collisions between parallel test runs. The test uses the repository's write/delete paths to verify the exact index behavior owned by the framework. The machine running the integration test requires Docker or a compatible container runtime.

For applications with custom Redis or repository configurations, use the project's actual Spring configuration and ensure tests point to a containerized Redis instance. Do not run tests against production Redis.

## 8. Limitations of Secondary Indexes with `@Indexed`

### 8.1. Does Not Replace a General-Purpose Query Engine

`@Indexed` supports property-index lookups in the Redis Repository model. It does not turn Redis into a relational database and does not automatically add capabilities such as:

- Full-text search, relevance scoring, or fuzzy search.
- `LIKE '%abc%'` queries on arbitrary strings.
- Arbitrary `JOIN`s across multiple entity types.
- SQL-like sorting and pagination over large datasets by any arbitrary property.
- Complex query analysis or flexible multi-field aggregations.

If you need full-text search or rich document querying, evaluate a search engine or dedicated indexing/query capability suitable for your Redis deployment. **Redis Repository `@Indexed` and Redis Search/RediSearch are two different mechanisms**; you cannot assume that adding `@Indexed` creates a search index for Redis Search.

### 8.2. Indexes Do Not Guarantee Email Uniqueness

Two customers with the same email can both exist in the Redis Set:

~~~text
customers:email:shared@example.test → { "c-201", "c-202" }
~~~

A method returning `List<Customer>` makes sense when multiple entities may share the same value. If business logic requires emails to be unique, you need a **dedicated uniqueness constraint and write mechanism**, especially when multiple application instances save concurrently. Merely setting the return type to `Optional<Customer>` or adding `@Indexed` does not create a unique constraint.

### 8.3. Indexes Have Storage and Update Costs

For every annotated property, the system must maintain additional Sets and index management metadata. Indexes speed up certain lookups, but they come with costs:

| Aspect | Benefit | Cost/Trade-off |
| --- | --- | --- |
| Reading by property | Looks up ID group via Redis Set | May require loading many Hashes after fetching IDs |
| New writes | Data is immediately queryable by property | Must write the Hash and add membership to Sets |
| Updates | Queries reflect the new value via repository | Must remove old membership and add new membership |
| Deletions | No longer returns deleted records once index is cleaned | Must clean up related metadata/indexes |
| Redis memory | Avoids scanning all data during queries | Consumes memory for Sets and auxiliary keys |

Annotating too many fields can create a significant number of keys/Sets. For example, a property with millions of distinct values can generate very many small Sets; a common status such as `ACTIVE` can create a Set containing a huge number of IDs. Only index properties needed for actual business queries.

### 8.4. Values May Be Exposed via Index Key Names

In standard key naming conventions, property values become part of the index key name. If sensitive data such as email, personal identifier, or token is used as an indexed value, consider security policies, Redis access permissions, and logs/backups/key inspection. Do not directly index secrets such as access tokens just for query convenience. If exact lookup by a sensitive value is needed, design a normalized lookup key protected appropriately according to security requirements.

## 9. Indexes and TTL: What Happens When a Key Expires?

A Redis entity can have a time-to-live, for example:

~~~java
@RedisHash(value = "customers", timeToLive = 300)
public class Customer {
    // ...
}
~~~

`timeToLive = 300` in the example is 300 seconds. When the Redis Hash expires, the entity data can no longer be read. However, **cleaning up membership in secondary indexes is a separate related concern**.

Spring Data Redis has a mechanism to listen for **Redis keyspace expiration events** to handle expired entities and clean up corresponding index information. Receiving events depends on Redis configuration, whether the listener is running, and when the event occurs. Cases to watch out for:

- Keyspace notifications are disabled, or the Redis environment does not allow the application to enable them automatically.
- The application/lifecycle listener is not running when Redis emits the notification.
- The key is deleted directly outside the repository.
- The key expires before a listener starts listening.

Redis Pub/Sub keyspace notifications are not a durable queue that replays all missed events. Therefore, **do not assume every index Set is cleaned up instantaneously just because the Hash TTL expired**.

Example of what you might observe:

~~~text
GET/HGETALL customers:c-101  → key has expired or does not exist
SMEMBERS customers:status:ACTIVE → may still contain "c-101" if cleanup was missed
~~~

This can lead to orphaned membership and increased memory usage, even though loading the actual Hash does not find the entity. For high-TTL-churn data, check keyspace event configuration, how listeners start, support in managed Redis, and build index observation/cleanup strategies when appropriate.

TTL is not a property of the `@Indexed` annotation itself. Expiration policies, index cleanup, and query efficiency need to be designed as related yet distinct concerns.

## 10. Common Pitfalls When Using `@Indexed`

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `findByEmail` does not find saved data | Field is missing `@Indexed`, or old records have not been indexed yet | Verify the annotation and plan to reindex existing data |
| `findById` works, but `findByStatus` returns no results | ID lookup and secondary index are two different access paths | Check the `status` index and verify saving goes through the repository |
| Updated email via `HSET`, but query returns old results | Direct operations do not sync index Sets | Update via the repository or manage indexes explicitly |
| `findByEmail("LAN@...")` does not match lowercase email | Indexed values are not normalized according to that rule | Normalize data on both write and query |
| Two records share the same email | `@Indexed` does not enforce a unique constraint | Design a separate uniqueness enforcement mechanism |
| Added `@Indexed`, but old data does not show up | Annotation does not automatically backfill existing Hashes | Run a controlled reindexing process |
| Hash key expired, but index Set still holds the ID | Expiration event/cleanup was not received or processed | Check notification config, listener, and cleanup strategy |
| Substring query does not work | Secondary index is not full-text search | Use a different query model or search engine |
| Wrote JSON via `RedisTemplate` and expected repository to find it | Standard serializers do not create secondary indexes | Choose a consistent write path through the repository |
| Querying by a `@Reference` property like a JOIN | Spring Data Redis does not auto-JOIN references like SQL | Design queries/indexes based on actually mapped properties |

## 11. Designing Indexes for Query Needs

Suppose an application supports these use cases:

1. Find a customer by ID to open the detail page.
2. Find a customer by email during login.
3. List all customers with `ACTIVE` status.
4. Search customers by keyword across multiple text fields.

Corresponding choices:

| Use Case | Choice |
| --- | --- |
| By ID | `@Id` and `findById`, no secondary index needed |
| By exact email | `@Indexed` on normalized email property |
| By status | `@Indexed` on `status` if this query is truly needed and result size is manageable |
| Advanced text search | Evaluate dedicated search capabilities; `@Indexed` is not enough |

Before adding the annotation, consider whether lookup results might be too large. An index for `status=ACTIVE` quickly identifies the ID set, but if millions of entities are active, loading all results into a `List<Customer>` still consumes significant memory and time. You may need to reorganize data access, bound the result set, or build another read model suited to the scale.

Several helpful practices:

- **Unify the write path.** If the repository owns the Hash and indexes, other data-modification flows must respect the index update mechanism.
- **Normalize values with clear rules.** Email, region code, or status must be written and queried using the same convention.
- **Test after updates and deletions.** Indexes must reflect the full entity lifecycle, not just the initial save.
- **Plan for existing data.** Adding `@Indexed` on a live system usually requires backfilling.
- **Monitor TTL and index cleanup.** Do not treat lossy notifications as proof that data has been cleaned up.
- **Measure actual memory and latency costs.** Key count, Set size, and update frequency directly affect index choices.

## 12. Conclusion

`@Indexed` is how you declare **property-based secondary indexes** in Spring Data Redis Repositories. When saving a `@RedisHash`, the framework can maintain Redis Sets linking property values to entity IDs; supported repository query methods use that ID set to load objects.

To use it properly, clearly distinguish **ID lookup** from **secondary index**, place the Spring Data Redis annotation on properties that need querying, and keep write/delete paths consistent through the repository. Secondary indexes are useful for exact lookups, but they do not guarantee uniqueness, do not replace full-text search, and incur update, memory, and TTL expiration cleanup costs.
