# Indexing Nested and Referenced Properties in Spring Data Redis

In Spring Data Redis Repositories, Java entities are typically stored as Redis Hashes, while queries finding entities by property are supported through **secondary indexes**. This mechanism is especially important to understand accurately when the model contains relationships between objects:

- **Nested objects (embedded/nested object):** properties of the child object are stored inside the parent entity's Redis Hash, such as `person.address.city`. Spring Data Redis can index child properties.
- **Objects referenced via `@Reference`:** the parent entity only stores the Redis key address of the other entity, such as `person.employer` pointing to `companies:c-9`. Spring Data Redis **does not** follow the reference to create indexes from the target entity's properties.

This is an important design boundary: a Java path like `person.employer.name` looks similar to `person.address.city`, but their storage and indexing behavior are different.

## 1. What Is a Redis Repository Secondary Index?

Redis does not have SQL tables and does not automatically build B-trees for every field in a Hash. Spring Data Redis Repositories use Redis data structures, primarily **Sets**, to maintain a list of IDs sharing the same property value.

For example, two people living in Hanoi:

```text
people:p-100
  id             = p-100
  displayName    = Mai
  address.city   = HaNoi

people:p-101
  id             = p-101
  displayName    = Binh
  address.city   = HaNoi
```

If `address.city` is indexed, the repository infrastructure creates/maintains a Set conceptually:

```redis
SADD people:address.city:HaNoi p-100
SADD people:address.city:HaNoi p-101
```

When querying for people with `address.city = "HaNoi"`, Spring Data Redis can read the Set containing the IDs and then load the corresponding Hashes. The query does not need to scan all `people:*`. Key names are illustrated by default convention; choices around keyspace, mapping, and serializer can affect the actual representation.

| Component | Role |
|---|---|
| `people` | Keyspace of the `Person` entity |
| `people:p-100` | Redis Hash of one `Person` entity |
| `address.city` | Property path from parent entity to child property |
| `people:address.city:HaNoi` | Redis Set containing IDs matching the indexed value |
| `p-100` in Set | Entity ID, not a copy of the entire Hash |

Adding `@Indexed` takes effect on **writes through the repository infrastructure**; it does not make Redis automatically find all existing Hashes and build historical indexes.

## 2. Indexing Properties of Nested Objects

### 2.1. Declaring the Entity and Value Object

Suppose an application manages user profiles and contact addresses. `Address` is only part of a profile and does not exist independently with its own Redis key.

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("people")
public class Person {

    @Id
    private String id;
    private String displayName;
    private Address address;

    protected Person() {
    }

    public Person(String id, String displayName, Address address) {
        this.id = id;
        this.displayName = displayName;
        this.address = address;
    }

    public String getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }

    public Address getAddress() {
        return address;
    }

    public void changeAddress(Address address) {
        this.address = address;
    }
}
```

In `Address`, mark the **searchable field** with `@Indexed`:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.index.Indexed;

public class Address {

    @Indexed
    private String city;
    private String country;

    protected Address() {
    }

    public Address(String city, String country) {
        this.city = city;
        this.country = country;
    }

    public String getCity() {
        return city;
    }

    public String getCountry() {
        return country;
    }
}
```

Here, `Address` does not need `@RedisHash` or `@Id`: it is a nested object inside `Person`. The `@Indexed` annotation on `Address.city` enables the infrastructure to discover the **`address.city`** path when traversing `Person`'s structure.

Annotating `Address.city` does not automatically create a separate entity to query with an `AddressRepository`. Query results remain the `Person` instances owning that child object.

### 2.2. Repository with Queries on Nested Paths

```java
import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface PersonRepository extends CrudRepository<Person, String> {

    // Method name traverses Person.address.city.
    List<Person> findByAddressCity(String city);

    // Underscore _ explicitly marks the boundary of the nested path.
    List<Person> findByAddress_City(String city);
}
```

This is a **derived query**: Spring Data parses the method name, resolves the property path, and uses the declared secondary index to fetch IDs. When property names could be ambiguous—for example, if an entity has both `addressCity` and `address.city`—the underscore `_` explicitly clarifies that the query traverses `address` to `city`.

Only use one of the two method naming styles in real code if they mean the same thing; both are shown so learners can see how paths are expressed. In particular, the ability to parse property paths **does not mean** every relationship can be indexed: the limitation of `@Reference` is explained later.

### 2.3. Saving and Querying

```java
Person mai = new Person(
        "p-100",
        "Mai",
        new Address("HaNoi", "VietNam")
);

Person binh = new Person(
        "p-101",
        "Binh",
        new Address("HaNoi", "VietNam")
);

Person an = new Person(
        "p-102",
        "An",
        new Address("DaNang", "VietNam")
);

personRepository.save(mai);
personRepository.save(binh);
personRepository.save(an);

List<Person> inHaNoi = personRepository.findByAddress_City("HaNoi");
// Expected to contain Person p-100 and p-101, in no guaranteed order.
```

In Redis CLI, you can observe:

```redis
TYPE people:p-100
# hash

HGET people:p-100 address.city
# "HaNoi" (example output)

TYPE people:address.city:HaNoi
# set

SMEMBERS people:address.city:HaNoi
# p-100, p-101 (Sets do not guarantee order)
```

An entity with `address == null` or `address.city == null` does not contribute an element to the index Set for a city value. Redis Sets also do not directly represent an `IS NULL` query like a relational database.

## 3. Data Flow and Index Lifecycle

For data written through a Spring Data Redis Repository, the process can be visualized as:

```text
personRepository.save(person)
       |
       v
Read @RedisHash, @Id, and property metadata
       |
       +--> MappingRedisConverter
       |        |
       |        v
       |    Redis Hash people:p-100
       |    address.city = HaNoi
       |
       +--> Detect @Indexed on Address.city
                |
                v
            Update Redis Set
            people:address.city:HaNoi += p-100
```

When `save` is called again after changing the city, the repository updates the index structures to match the entity's state. Conceptually:

```redis
# Previous value:
SREM people:address.city:HaNoi p-100

# New value:
SADD people:address.city:Hue p-100
```

This is a logical diagram, not a guarantee of the exact internal command sequence a specific Spring Data version sends to Redis. The infrastructure also maintains index-tracking structures to support deletions and updates.

### A Proper Business Change

```java
Person person = personRepository.findById("p-100")
        .orElseThrow();

person.changeAddress(new Address("Hue", "VietNam"));
personRepository.save(person);

List<Person> inHue = personRepository.findByAddress_City("Hue");
```

Modifying a Java object in memory does not automatically write changes to Redis. You must save it back via the repository or use an update API that supports index maintenance. Running `HSET people:p-100 address.city Hue` manually updates the Hash, but **does not automatically update** repository-managed secondary indexes.

**Consequence:** You can end up with the Hash field showing the new value while derived queries still match the old value if the application alters data directly via Redis CLI or `RedisTemplate.opsForHash()`, bypassing the index maintenance mechanism.

## 4. Indexing Multiple Levels, Lists, and Maps

### 4.1. Multi-Level Nested Properties

With the structure:

```text
Person
  └── address
        └── geo
              └── regionCode
```

If `regionCode` is marked with `@Indexed` and the objects along the path are mappable embedded objects, the index name typically reflects the property path, such as:

```text
people:address.geo.regionCode:R1
```

You do not need to put `@Indexed` on every parent level. The annotation is placed on the target property to be indexed; the infrastructure resolves the path from the root entity down to that property.

### 4.2. Lists of Nested Objects

For example, a `Person` with multiple addresses:

```java
@RedisHash("people")
public class Person {
    @Id String id;
    List<Address> addresses;
}

public class Address {
    @Indexed String city;
}
```

Index configuration for list paths can use **programmatic indexing**, such as `addresses.city`. Spring Data Redis describes the conceptual key format as:

```text
people:addresses.city:HaNoi  -> Set of Person IDs having an address in HaNoi
```

Because one person can have multiple `Address`es, a single ID can belong to Sets for multiple cities. This has **exists-a-matching-element** semantics at the root object level, not paginated results per individual child address.

Distinguish clearly: being able to **create an index** on a collection property does not mean every kind of derived query or Query by Example automatically supports traversing collections. If complex collection querying is needed, consider designing custom indexes and ID retrieval paths.

### 4.3. Maps and Dynamic Keys

For example, `Map<String, String> attributes` containing:

```java
attributes.put("tier", "gold");
attributes.put("locale", "vi");
```

Spring Data Redis can configure indexes on a Map entry or a path inside Map values. The index representation might look like:

```text
people:attributes.tier:gold
people:attributes.locale:vi
```

Do not assume that placing `@Indexed` on the `Map` itself guarantees all dynamic keys are indexed for all query styles. With Maps and Lists, explicitly configure the property paths or custom indexes and verify the desired query mechanism against your specific API/version.

### 4.4. Programmatic Index Configuration Instead of Annotations

Spring Data Redis allows declaring indexes without modifying domain classes, via `IndexConfiguration` and `SimpleIndexDefinition`:

```java
import java.util.List;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.index.IndexConfiguration;
import org.springframework.data.redis.core.index.IndexDefinition;
import org.springframework.data.redis.core.index.SimpleIndexDefinition;
import org.springframework.data.redis.repository.configuration.EnableRedisRepositories;

@Configuration
@EnableRedisRepositories(indexConfiguration = PersonIndexConfiguration.class)
public class RedisRepositoryConfiguration {
}

class PersonIndexConfiguration extends IndexConfiguration {

    @Override
    protected Iterable<IndexDefinition> initialConfiguration() {
        return List.of(
                new SimpleIndexDefinition("people", "address.city"),
                new SimpleIndexDefinition("people", "addresses.city")
        );
    }
}
```

The example shows how to specify the `people` keyspace and property paths. If `@Indexed` is already present for the same path, there is no need to declare it twice just to create the same index. For Maps, Collections, and complex paths, programmatic configuration helps explicitly control which property paths the model actually needs to look up.

## 5. Referenced Properties with `@Reference` Are a Different Case

`@Reference` represents a **link to another Redis entity**, rather than embedding all properties of the target entity into the source entity's Hash.

Suppose each `Person` works at a `Company`:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("companies")
public class Company {

    @Id
    private String id;
    private String name;
    private String region;

    protected Company() {
    }

    public Company(String id, String name, String region) {
        this.id = id;
        this.name = name;
        this.region = region;
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getRegion() {
        return region;
    }
}
```

Source entity:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Reference;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("people")
public class Person {

    @Id
    private String id;
    private String displayName;

    @Reference
    private Company employer;

    protected Person() {
    }

    public Person(String id, String displayName, Company employer) {
        this.id = id;
        this.displayName = displayName;
        this.employer = employer;
    }
}
```

After `Company` has been saved, `Person` can store the **key address** of the company instead of copying `name` and `region` into the person's Hash:

```text
Redis Hash companies:c-9
    id      = c-9
    name    = Example Logistics
    region  = central

Redis Hash people:p-100
    id          = p-100
    displayName = Mai
    employer    = companies:c-9
```

When reading `Person`, Spring Data Redis can resolve the reference to reconstruct `employer` as a `Company`. However, when saving `Person`, Spring Data **does not automatically save changes inside `Company`**. The company must be saved via its own repository.

### What Is Not Automatically Supported

Suppose `Company` has:

```java
@Indexed
private String region;
```

This index can serve queries **on `Company`** by `region` if the Company is properly saved through the repository infrastructure. However, it **does not** become an index for `Person` on `employer.region`.

A method `PersonRepository.findByEmployerRegion("central")` is not supported as a query traversing `@Reference` merely because `Company.region` has `@Indexed`. Spring Data Redis does not perform a JOIN across referenced Redis keys when maintaining secondary indexes of a root entity.

**Rule:** *Indexes cannot be resolved on References.* This is a limitation stated directly in the Spring Data Redis documentation on secondary indexes and references.

| Relationship Type | Data Stored in Person's Hash | Can Auto-Index Child Properties? |
|---|---|---|
| `Address address` (embedded) | `address.city = HaNoi` | Yes, if `@Indexed`/IndexDefinition is configured properly |
| `@Reference Company employer` | `employer = companies:c-9` | No, cannot traverse `employer.region` or `employer.name` |
| `String employerId` with `@Indexed` | `employerId = c-9` | Yes, because this is a direct property of `Person` |

## 6. How to Support Queries by Referenced Entity

You cannot use an index on a target entity's property as an automatic JOIN. Instead, there are a few approaches depending on your needs.

### 6.1. Storing an Additional Denormalized ID on the Source Entity

If business logic needs to find all employees of a company by ID, add a **direct indexed field** to `Person`:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Reference;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("people")
public class Person {

    @Id
    private String id;
    private String displayName;

    @Reference
    private Company employer;

    @Indexed
    private String employerId;

    protected Person() {
    }

    public Person(String id, String displayName, Company employer) {
        this.id = id;
        this.displayName = displayName;
        assignEmployer(employer);
    }

    public void assignEmployer(Company employer) {
        if (employer == null || employer.getId() == null) {
            throw new IllegalArgumentException(
                    "Employer must be persisted and have an ID");
        }
        this.employer = employer;
        this.employerId = employer.getId();
    }
}
```

Repositories:

```java
import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface PersonRepository extends CrudRepository<Person, String> {
    List<Person> findByEmployerId(String employerId);
}

public interface CompanyRepository extends CrudRepository<Company, String> {
}
```

Save sequence:

```java
Company company = companyRepository.save(
        new Company("c-9", "Example Logistics", "central")
);

personRepository.save(new Person("p-100", "Mai", company));
personRepository.save(new Person("p-101", "Binh", company));

List<Person> employees = personRepository.findByEmployerId("c-9");
```

Conceptual Hash and index:

```text
people:p-100
  employer    = companies:c-9
  employerId  = c-9

people:p-101
  employer    = companies:c-9
  employerId  = c-9

people:employerId:c-9
  {p-100, p-101}
```

In this model, `employer` serves relationship navigation when loading the entity; `employerId` serves lookup via the secondary index. This is **intentional denormalization**, not two independent sources of truth: code must update both fields together when changing the company.

Renaming the company does not require changing `employerId` on `Person` because the ID remains stable. Conversely, when a `Person` moves from `c-9` to `c-10`, you must update both the reference and `employerId`, then call `personRepository.save(person)` to maintain the index.

### 6.2. When You Need to Query by a Company Property

Suppose you need "all Persons working at a Company with `region = central`". Two common approaches:

**Approach A — Two-step query:**

1. Store `Company.region` with `@Indexed` and use `CompanyRepository.findByRegion("central")` to find matching companies.
2. Take each company's ID and look up `PersonRepository.findByEmployerId(companyId)`.
3. Merge matching Person IDs/records and handle deduplication and pagination as needed.

```text
Company.region = central
        |
        v
Index companies:region:central
        |
        v
Company IDs [c-9, c-12]
        |
        +--> people:employerId:c-9  --+
        |                             +--> Person IDs
        +--> people:employerId:c-12 --+
```

This is how the application proactively "joins" at the service layer. When the number of companies or employees is large, consider the number of Redis reads and handle pagination instead of loading everything into memory.

**Approach B — Copying query-supporting values onto Person:**

```java
@Indexed
private String employerRegion;
```

When creating or changing company:

```java
person.employerRegion = company.getRegion();
personRepository.save(person);
```

You can then use `findByEmployerRegion("central")` on `PersonRepository`. This reduces the step of reading the company list, but increases **data synchronization** responsibility. When `Company.region` changes, you must update `employerRegion` across all related Persons; calling `companyRepository.save(company)` alone will **not** update Person records for you.

Choose Approach A when normalized data is preferred and the number of links is manageable; choose Approach B when frequent low-latency lookups are required and you accept a synchronization/eventual-consistency mechanism. Never let a copied property turn into a value that can be modified arbitrarily without rules.

### 6.3. When Are Self-Managed Indexes Needed?

For multi-dimensional queries or large relationships, you can maintain a separate Set, such as `company:employees:c-9`, and update it along with business logic. However, these Sets are **application-owned**. Spring Data Redis Repositories do not automatically manage the lifecycle of indexes outside their infrastructure. You must design the add, update, delete, TTL cleanup, index recovery, and partial-write failure handling paths.

If the requirement is essentially deep JOINs, text search, aggregations, or dynamic relational queries, evaluate whether Redis Repository secondary indexes are appropriate or if another query system should be used.

## 7. Behavior of Set-Based Queries

With two indexed properties, Spring Data Redis can combine Sets:

```java
List<Person> findByAddress_CityAndEmployerId(
        String city, String employerId);
```

Conceptually, this is an intersection of ID sets:

```redis
SINTER people:address.city:HaNoi people:employerId:c-9
```

If an `Or` condition is used, it can correspond to a union of Sets (`SUNION`). Method names supported by Spring Data do not turn Redis into an engine for arbitrary SQL expressions: this feature relies on existing indexes, primarily for exact matching. For example, `findByAddress_City("hanoi")` does not automatically match the stored value `"HaNoi"` because strings are case-sensitive.

For Query by Example, Spring Data Redis supports a subset of features, including exact matching on simple or nested indexed properties. Queries on associations, collections, and map-like properties are not supported in the same way as simple properties; do not assume QBE can traverse `@Reference`.

Key distinctions:

- **Ability to define a property path:** the framework recognizes the Java structure.
- **Ability to create a secondary index:** the infrastructure writes a Set containing IDs along supported paths.
- **Query expressiveness:** derived queries/QBE have specific limitations regarding data types, operators, and associations.

These three capabilities are related, but not identical.

## 8. Lifecycle Management and Index Consistency

### 8.1. Save and Delete via Repository

Redis Repository secondary indexes are updated when saving an entity and corresponding members are removed when an entity is deleted through the repository infrastructure. If you change `address.city` or `employerId`, save the entity via the repository so the index management mechanism can handle old and new states.

Operations requiring special care:

| Operation | Impact on Index |
|---|---|
| `personRepository.save(person)` | Repository infrastructure maintains `Person` indexes |
| `personRepository.deleteById(id)` | Repository infrastructure handles removing entity indexes |
| `HSET people:p-100 address.city Hue` | Modifies only the Hash; repository index risks drifting |
| `DEL people:p-100` via Redis CLI | Deletes Hash without running the repository's full index cleanup logic |
| `companyRepository.save(company)` | Updates `Company` index; does not auto-sync copied fields on `Person` |

Do not mix modifying indexed fields via Redis CLI, raw Hash templates, and Repositories in the same business flow without an explicit synchronization contract.

### 8.2. Data Saved Before `@Indexed` Existed

If millions of entities existed before you added `@Indexed` to `Address.city`, starting the new application version **does not automatically backfill all Redis Sets**. Entities saved afterward are indexed by the active configuration.

You need an explicit migration or rebuild plan:

1. Identify all root entities that need reindexing using a reliable traversal path.
2. Load entities and re-save them via the repository with the new index configuration, or use a dedicated controlled rebuild process.
3. Manage Redis load, large key counts, and concurrent updates to avoid rebuilding indexes from stale data.
4. Only switch query flows depending on the new index after backfill/synchronization completes.

For short-lived cache data that can be regenerated, clearing and rebuilding over the application lifecycle is sometimes simpler. Do not mass-delete business data just to add an index.

### 8.3. TTL and Expired Keys

When an entity has a TTL, Redis can automatically delete the Hash without any `repository.deleteById(...)` call. Spring Data Redis uses keyspace expiration notifications to help clean up leftover index references. **Redis Pub/Sub notifications are not persisted**: if the application is down or misses an event, the index Set may retain the ID of an expired Hash.

Therefore:

- Do not use `SMEMBERS` on an index Set as proof that all corresponding Hashes still exist.
- Pay attention to keyspace notifications configuration and listener lifecycle if entities have `@TimeToLive` or `@RedisHash(timeToLive = ...)`.
- Design a periodic mechanism to detect/clean orphaned entries or rebuild indexes if business logic requires high accuracy.
- Do not assume a TTL on the root entity will automatically expire individual members inside an index Set.

Indexes occasionally containing invalid IDs is an operational risk, especially when using raw Redis commands or losing expiration events. The entity retrieval layer must handle cases where an ID in an index no longer has a corresponding Hash.

### 8.4. Modifying an Entity Pointed to by `@Reference`

A reference relationship is a link between **two Redis keys**. Suppose `Person.employer` points to `companies:c-9`:

- Deleting `companies:c-9` does not guarantee all `Person` records are updated to clear the reference.
- Re-saving `Company` does not automatically update denormalized fields on `Person`.
- When loading `Person`, have a strategy to handle missing references suited to business logic and how the mapper resolves missing referenced objects.

Redis Repositories do not provide relational database-style foreign key constraints. If you need the invariant "Person always points to an existing Company", the service layer must design consistent write, delete, and recovery flows.

## 9. Performance and Limits

### 9.1. Size and Number of Secondary Indexes

Each distinct value of an indexed property can produce a separate Redis Set. For high-cardinality properties such as a unique per-user token, indexing can generate huge numbers of keys/Sets and increase memory overhead. On saves or deletions, the repository must also maintain related Sets.

Prioritize indexing properties that **actually appear in filter criteria** and provide clear value:

| Property | Consideration |
|---|---|
| `address.city` | Often useful if users filter by city |
| `employerId` | Useful for querying employees by company |
| `employerRegion` (denormalized) | Useful for repeated queries, but incurs sync overhead |
| Mostly unique session ID or token | May not need a secondary index if direct key lookup is already available |
| Every field of Address | Adds overhead with no benefit if business logic only filters by city |

### 9.2. Indexed Strings and Normalization

Values like `"HaNoi"`, `"hanoi"`, and `"Hà Nội"` are three distinct values if indexed verbatim. If business logic wants case-insensitive, accent-insensitive, or spelling-normalized matching, explicitly define normalization on both the write path and query path. A dedicated field like `normalizedCity` with `@Indexed` is usually clearer than silently assuming Redis performs natural-language matching.

### 9.3. Redis Cluster

The index Redis Set and the entity's Redis Hash can reside on different hash slots in a Cluster. Some multi-key operations such as `SINTER` or `SUNION` are constrained by hash slot rules. Do not assume the current Redis Repository and driver configuration smoothly handles all Set-combining derived queries on every cluster topology. Verify support in your Spring Data Redis version, Redis server, and driver; if the design requires complex cross-slot intersections/unions, consider key/hash-tag strategies or a dedicated query engine.

## 10. Common Pitfalls When Querying Nested and Referenced Properties

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `findByAddress_City("HaNoi")` returns no data | Target property not indexed, or legacy entities not re-saved | Check annotation/index config; prepare backfill if needed |
| `HGET` shows the new city, but query returns old data | Hash updated directly via `HSET` outside repository | Route updates through repository or index maintenance flow |
| Query `findByEmployerRegion(...)` does not work | `employer` is a `@Reference`; indexes do not traverse references | Two-step query or add `@Indexed employerRegion` on `Person` |
| Updated `Company.region`, but `Person` stays in old region index | Denormalized region value not updated | Re-sync affected `Person` records when `Company` changes region |
| Index Set contains a `Person` ID that fails to load | Root key expired via TTL or deleted raw; cleanup event may be lost | Check expiration events and index cleanup plan |
| `null` values not found by normal index queries | No index membership exists for null values | Model an explicit status value if needed by business logic |
| Queries by collection/map are rejected | Query capability differs from index definition capability | Design separate ID lookups or use supported queries |
| Searching `"hanoi"` does not match `"HaNoi"` | Index comparison is exact match | Normalize both stored data and query input |
| Index has too many tiny Sets | High-cardinality property or overly broad indexing | Review which search conditions are truly needed |

### Inspecting Data with Redis CLI

```redis
# Inspect an entity Hash
TYPE people:p-100
HGETALL people:p-100

# Inspect the index Set of an embedded property
TYPE people:address.city:HaNoi
SCARD people:address.city:HaNoi
SSCAN people:address.city:HaNoi 0

# Inspect the index Set of a denormalized key
SMEMBERS people:employerId:c-9

# Inspect the referenced company record
TYPE companies:c-9
HGETALL companies:c-9
```

In production, avoid using `KEYS people:*` on large keyspaces to inspect indexes. Use `SCAN` with pattern matching and direct reads on known keys. Illustrated key names must be cross-checked against your application's actual keyspace and serializer.

## 11. Practice Exercises

**Exercise 1 — Embedded index:** Create two `Person` instances with `Address.city = "HaNoi"` and one in `"Hue"`. Save via the repository, inspect the Redis Set `people:address.city:HaNoi` and the result of `findByAddress_City("HaNoi")`. Then change one person to `"Hue"` via `save` and observe how the Sets change.

**Exercise 2 — Distinguishing `@Reference`:** Create a `Company` with `region = "central"`, save a `Person` referencing that `Company`, and inspect the `employer` field in the Person's Hash. Explain why `@Indexed Company.region` does not create a `people:employer.region:central` Set.

**Exercise 3 — Denormalization:** Add `@Indexed employerId` and a `findByEmployerId` method. Save two `Person` entities for the same company, move one to another company, ensuring both `employer` and `employerId` are updated together.

**Exercise 4 — Consistency trade-offs:** If users want to filter `Person` by `Company.region`, compare the two-step query approach versus storing `employerRegion` on `Person` in terms of read count, lookup latency, update cost, and handling when `Company` changes region.

## 12. Key Design Principles to Remember

1. **Embedded properties** such as `address.city` are mapped into the parent entity's Hash and can be secondary-indexed by property path.
2. **Referenced properties** such as `employer.region` live in another entity's Hash. `@Reference` stores the reference key; Spring Data Redis does not auto-resolve references to build indexes for the source entity.
3. To look up root entities by a relationship, you can **store a direct lookup key** such as `@Indexed employerId` or organize a two-step query. When copying properties from another entity, you must manage consistency yourself.
4. Redis Repository secondary indexes use Redis Sets for ID lookups, not relational indexes or general JOINs. Creating indexes and supporting query syntax each have their own boundaries.
5. Maintain indexes through the repository, watch out for backfilling existing data, and clean up indexes when keys expire or data is modified outside the repository.

## References

- [Spring Data Redis — Secondary Indexes](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/indexes.html): `@Indexed`, nested indexes, Maps/Lists, and `IndexConfiguration`; limitations with references.
- [Spring Data Redis — Usage and Persisting References](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/usage.html): `@Reference` model, storing keys of referenced entities, requirement to save target entities separately.
- [Spring Data Redis — Redis-specific Query Methods](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/queries.html): derived queries based on index Sets and `And`/`Or` criteria.
- [Spring Data Redis — Query by Example](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/query-by-example.html): exact-match query support for simple/nested properties and limitations with associations/collections/maps.
- [Spring Data Redis — Time To Live](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html): expiration events and notes on cleaning up secondary indexes when entities expire.
