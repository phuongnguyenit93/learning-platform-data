# Natural IDs and Hibernate-Specific Lookup Capabilities

A natural key (or natural ID) is one or more business attributes that uniquely identify a record, such as a book's ISBN, a country code, a SKU, or an email address within a tenant. A primary key is typically a system-managed technical identifier, such as an auto-generated `Long`.

Hibernate supports marking natural IDs with `@NaturalId`, looking up entities with `Session.byNaturalId()` or `Session.bySimpleNaturalId()`, and caching the natural-ID-to-primary-key mapping via `@NaturalIdCache`. These are Hibernate-specific utilities, not part of the standard JPA API. They are useful when an application frequently looks up entities by a business key and wants to express that key explicitly in the mapping.

## 1. Primary Keys and Natural Keys

The two kinds of keys serve different purposes:

| Criterion | Primary Key (Surrogate Key) | Natural Key |
|---|---|---|
| Meaning | Technical identifier | Business-meaningful identifier |
| Example | `customer.id = 8124` | `tenantId = 7, email = "a@example.com"` |
| Stability | Typically immutable | May be immutable or change per business rules |
| Usage in relationships | Typically the FK of other tables | Typically used for lookups or integrations |
| Value generation | Sequence, identity, UUID, or application | Derived from business data |
| Uniqueness scope | Per table/entity | May be system-wide or scoped to a context |

A common pattern is using a surrogate primary key for internal relationships while declaring a natural ID for the business key. This keeps foreign keys in related tables stable even if a business attribute such as email or display code changes.

Not every attribute that appears unique today makes a good natural ID. A good key should have clear uniqueness rules, consistently normalized values, and rare changes. Phone numbers, emails, usernames, or partner-issued codes may change or be reassigned; evaluate business policy before choosing one.

## 2. Guaranteeing Uniqueness in the Database

`@NaturalId` describes the business key to Hibernate, yet the database still needs unique constraints to protect data against concurrent requests, SQL scripts, and other applications.

Example where email is unique only within a tenant:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

import org.hibernate.annotations.NaturalId;

@Entity
@Table(
    name = "customer",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_customer_tenant_email",
        columnNames = {"tenant_id", "email_normalized"}
    )
)
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @NaturalId
    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @NaturalId
    @Column(name = "email_normalized", nullable = false, length = 254)
    private String emailNormalized;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    protected Customer() {
    }

    public Customer(Long tenantId, String emailNormalized, String displayName) {
        this.tenantId = tenantId;
        this.emailNormalized = emailNormalized;
        this.displayName = displayName;
    }

    public Long getId() {
        return id;
    }

    public Long getTenantId() {
        return tenantId;
    }

    public String getEmailNormalized() {
        return emailNormalized;
    }

    public String getDisplayName() {
        return displayName;
    }
}
```

In this example, the natural ID is the combination of `tenantId` and `emailNormalized`, not email alone. Two customers in different tenants can share the same email if business rules allow it.

For production migrations, create unique constraints via Flyway or Liquibase and check for existing duplicates before applying them. `@UniqueConstraint` describes schema metadata to schema-generation tools; it does not clean up existing duplicates or replace controlled migrations.

### 2.1. Normalizing values before persisting and querying

Normalization rules must be identical at both write time and lookup time. For example, if business rules treat emails as case-insensitive, the application can store a normalized value in `email_normalized`. Avoid lowercasing only in queries while storing raw data without following the same rule.

Clarify:

- Should leading/trailing whitespace be trimmed?
- Is matching case-sensitive or case-insensitive?
- Which Unicode normalization form applies if allowed?
- How are hyphens, spaces, or separator characters in codes handled?
- Is the key globally unique or unique only per tenant/organization?

For case-insensitive requirements, you can use a normalized column or a functional unique index depending on the database. Database and application rules must align. In particular, do not blindly lowercase every part of an email if business rules or upstream systems require preserving case; define semantics upfront.

Do not rely on an `existsByEmail(...)` check to guarantee uniqueness. Two transactions can both see "does not exist" and both insert. A database unique constraint is the final safeguard; the application should handle constraint violations appropriately.

## 3. Marking Natural IDs with @NaturalId

`@NaturalId` is a Hibernate-specific annotation in `org.hibernate.annotations`. It can be placed on a single property or multiple properties to form a composite natural key.

By default, a natural ID is treated as immutable (`mutable = false`). This suits product codes, country codes, or identifiers guaranteed not to change by business rules.

```java
@NaturalId
@Column(nullable = false, unique = true)
private String sku;
```

If the business key is allowed to change, declare it explicitly:

```java
@NaturalId(mutable = true)
@Column(nullable = false)
private String emailNormalized;
```

For a composite key, annotate each participating property with `@NaturalId`. Together those properties identify a single entity. Ensure the database unique constraint reflects the exact same set of columns.

`@NaturalId` does not turn a property into `@Id`, does not generate primary keys, and does not replace foreign keys. An entity can still use a surrogate key as its `@Id`.

## 4. Retrieving via the Hibernate Session API

JPA's `EntityManager.find()` looks up entities by primary key. To look up by natural ID, Hibernate provides a specialized API on `Session`.

### 4.1. Single-property natural ID

If an entity has a single natural ID property, use `bySimpleNaturalId()`. To keep this example independent of `Customer` in section 2 (which has a composite natural ID), we use a `Product` entity with SKU as a single natural ID:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

import org.hibernate.annotations.NaturalId;

@Entity
@Table(
    name = "product",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_product_sku",
        columnNames = "sku"
    )
)
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @NaturalId
    @Column(nullable = false, length = 64)
    private String sku;

    protected Product() {
    }

    public Product(String sku) {
        this.sku = sku;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }
}
```

Lookup via Hibernate Session:

```java
import java.util.Optional;

import jakarta.persistence.EntityManager;

import org.hibernate.Session;
import org.springframework.stereotype.Repository;

@Repository
public class ProductLookup {

    private final EntityManager entityManager;

    public ProductLookup(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    public Optional<Product> findBySku(String sku) {
        Session session = entityManager.unwrap(Session.class);

        Product product = session
                .bySimpleNaturalId(Product.class)
                .load(sku);

        return Optional.ofNullable(product);
    }
}
```

`load()` returns the entity if found and `null` otherwise. The code wraps the result in `Optional` so the repository API avoids returning `null` to callers. `bySimpleNaturalId()` fits here because `Product` has only one property marked `@NaturalId`.

### 4.2. Multi-property natural ID

For composite natural IDs, use `byNaturalId()` and supply each property using the entity's mapped Java property name:

```java
public Optional<Customer> findByTenantAndEmail(
        Long tenantId,
        String normalizedEmail) {

    Session session = entityManager.unwrap(Session.class);

    Customer customer = session
            .byNaturalId(Customer.class)
            .using("tenantId", tenantId)
            .using("emailNormalized", normalizedEmail)
            .load();

    return Optional.ofNullable(customer);
}
```

Names passed to `using()` are Hibernate-mapped Java property names—such as `emailNormalized`—not database column names like `email_normalized`.

### 4.3. Using inside a service transaction

Perform lookups inside an appropriate transactional/service method so the Hibernate Session lifecycle is clear:

```java
@Service
public class CustomerQueryService {

    private final CustomerLookup customerLookup;

    public CustomerQueryService(CustomerLookup customerLookup) {
        this.customerLookup = customerLookup;
    }

    @Transactional(readOnly = true)
    public CustomerResponse getCustomer(
            Long tenantId,
            String normalizedEmail) {

        Customer customer = customerLookup
                .findByTenantAndEmail(tenantId, normalizedEmail)
                .orElseThrow(() -> new CustomerNotFoundException());

        return new CustomerResponse(
                customer.getId(),
                customer.getDisplayName()
        );
    }
}
```

This example assumes `CustomerResponse` and `CustomerNotFoundException` exist in the application. Mapping to a DTO inside the transaction prevents the response from depending on whether a serializer accesses lazy relationships after the Session closes.

Do not adopt Hibernate's API merely to query by a single field. Spring Data JPA can generate derived query methods or `@Query` queries; choose the specialized API when you want natural-ID semantics, natural-ID caching, or related Hibernate features.

## 5. Natural IDs and the First-Level Cache

Within a Hibernate Session, Hibernate maintains a persistence context (first-level cache) and corresponding natural-ID cross-reference metadata. When looking up the same natural ID multiple times within the same Session, Hibernate can locate the already-managed entity without re-running the database query.

This means query counts within one Session can differ from query counts across multiple Sessions. The first-level cache exists only for the persistence context's lifespan; once the transaction or request completes and the Session closes, that state is not a shared long-lived cache.

Distinguish clearly:

- **Persistence context/L1:** manages entity instances within a single Session.
- **Natural-id cross-reference:** maps natural IDs to entity identifiers within a Session.
- **Natural ID cache:** shared cache mapping natural IDs to primary keys across Sessions when configured.
- **Entity second-level cache:** caches entity state by primary key.
- **Query cache:** caches query results using Hibernate's separate mechanism.

These cache layers solve different problems. Enabling one does not automatically enable the others.

## 6. Caching Natural IDs with @NaturalIdCache

Hibernate supports `@NaturalIdCache` to cache the natural-ID-to-primary-key mapping across Sessions. This helps when an application repeatedly looks up the same business key across many Sessions.

Example:

```java
import org.hibernate.annotations.Cache;
import org.hibernate.annotations.CacheConcurrencyStrategy;
import org.hibernate.annotations.NaturalIdCache;

@Entity
@Cache(
    usage = CacheConcurrencyStrategy.READ_WRITE,
    region = "customer-entity"
)
@NaturalIdCache(region = "customer-natural-id")
public class Customer {
    // @Id and @NaturalId properties
}
```

The second-level cache must be enabled and a cache provider compatible with your Hibernate version must be configured. Example Hibernate properties:

```properties
spring.jpa.properties.hibernate.cache.use_second_level_cache=true
spring.jpa.properties.hibernate.cache.region.factory_class=jcache
```

Configuring `jcache` requires Hibernate's JCache integration module and a JCache provider such as Ehcache or another provider. The `customer-natural-id` region must be configured with appropriate capacity limits and eviction/expiration policies per your provider. Region names in annotations must match cache configuration if the provider requires explicit declarations.

The natural ID cache stores only the mapping from business key to primary key; it does not necessarily store full entity state. After a successful natural-ID lookup, Hibernate may then load entity state from the entity L2 cache or the database. Thus, the natural ID cache and entity cache are distinct regions serving different purposes.

### 6.1. When should natural IDs be cached?

Suitable when:

- The application frequently fetches entities by a stable natural ID.
- Reads far outnumber updates.
- The natural key has clear uniqueness rules.
- A cache provider with bounded size and controlled eviction is configured.
- The system has an appropriate invalidation strategy when data changes.

Do not automatically cache every natural ID. If keys change frequently or multiple external applications require immediate freshness, cache synchronization costs may outweigh benefits.

### 6.2. Monitoring cache effectiveness

You can enable Hibernate statistics in test or controlled observation environments:

```properties
spring.jpa.properties.hibernate.generate_statistics=true
```

Monitor natural-id cache hits, misses, puts, entity cache hits/misses, SQL counts, and query latency. When evaluating, open fresh Sessions to distinguish the shared cache from the first-level cache within a single Session.

Do not conclude the cache is working well merely because a second lookup in the same transaction issues no SQL. That may just be the persistence context at work.

## 7. Mutable Natural IDs

A natural ID should generally be immutable. However, some attributes such as email or username can change under business rules. For those cases, declare `@NaturalId(mutable = true)` and update the managed entity inside a transaction.

```java
@NaturalId(mutable = true)
@Column(name = "email_normalized", nullable = false)
private String emailNormalized;

public void changeEmail(String newNormalizedEmail) {
    this.emailNormalized = newNormalizedEmail;
}
```

When updated, Hibernate must synchronize the Session's natural-id cross-reference and the natural-id cache so lookups by old or new keys do not return wrong results. Updating via the managed entity lifecycle lets Hibernate observe the change.

With mutable natural IDs, certain lookups may require Hibernate to synchronize pending Session changes before querying. Hibernate provides an option to disable synchronization for a specific lookup, though this should be used only when you are certain the Session holds no unsynchronized natural-ID changes. Disabling synchronization at the wrong time can return results that fail to reflect current persistence-context state.

If business rules allow, keeping natural keys immutable is far simpler for caching, synchronization, and integrations. If mutation is unavoidable, test lookups by old values, new values, flush/clear behavior, and post-commit caching thoroughly.

### 7.1. Avoid updating natural IDs via direct SQL

Direct UPDATE statements or bulk JPQL bypass the entity lifecycle. Hibernate is unaware of natural IDs modified outside the Session. After such updates, the persistence context may retain stale state and the natural-id cache may require invalidation.

If direct SQL updates are necessary:

1. Execute inside a controlled transaction.
2. Identify affected entities and natural-id cache regions.
3. Flush any pending JPA changes that must be preserved before running bulk SQL.
4. Clear or refresh persistence contexts holding affected entities.
5. Evict affected natural-id caches and entity caches after the transaction commits.
6. Test lookups using both old and new keys.

Hibernate provides a dedicated cache API to evict natural ID data; for example:

```java
SessionFactory sessionFactory =
        entityManagerFactory.unwrap(SessionFactory.class);

sessionFactory.getCache().evictNaturalIdData(Customer.class);
```

This is a Hibernate-specific API. In multi-node applications, evicting on one JVM synchronizes across the cluster only if the cache provider is properly configured for invalidation or replication.

## 8. Spring Data JPA Portable Alternatives

`@NaturalId`, `@NaturalIdCache`, `Session.byNaturalId()`, and `Session.bySimpleNaturalId()` are Hibernate features. If the application wants to remain portable across JPA providers, use Spring Data JPA query methods:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByTenantIdAndEmailNormalized(
            Long tenantId,
            String emailNormalized
    );
}
```

Or use JPQL:

```java
@Query("""
    select c
    from Customer c
    where c.tenantId = :tenantId
      and c.emailNormalized = :email
    """)
Optional<Customer> findByBusinessKey(
        @Param("tenantId") Long tenantId,
        @Param("email") String email
);
```

These approaches are more portable because they use Spring Data/JPA query abstractions, though they do not automatically provide a natural-id cache or all Hibernate-specific semantics. A database unique constraint remains mandatory in all cases.

You can choose according to these criteria:

| Need | Choice |
|---|---|
| Need code minimally coupled to Hibernate | Spring Data derived query or JPQL |
| Want to declare natural IDs directly in Hibernate mapping | `@NaturalId` |
| Want lookup by a single natural ID property | `bySimpleNaturalId()` |
| Want lookup by multiple natural ID properties | `byNaturalId().using(...)` |
| Want to cache natural ID mappings | `@NaturalIdCache` with an L2 cache provider |
| Need uniqueness guarantees under concurrent inserts | Database unique constraint/index |

## 9. equals() and hashCode() When Using Natural IDs

Do not blindly include every `@NaturalId` field in `equals()` and `hashCode()` without considering the entity lifecycle.

Points to weigh:

- A natural ID may be mutable, causing hash codes to change after an object is placed in a `HashSet` or used as a `HashMap` key.
- A newly instantiated entity may not yet have all natural ID values populated.
- Hibernate proxies can affect class/field access if `equals` is implemented carelessly.
- A natural ID may be unique only within a tenant; omitting the tenant from `equals` would treat two distinct entities as equal.

If using natural IDs for equality, choose only immutable, non-null fields that form a globally unique key under entity semantics. For mutable entities or tenant-scoped keys, implement and test carefully. A common alternative is equality based on a stable identifier or following your project's established `equals`/`hashCode` convention.

`@NaturalId` does not automatically generate `equals()` or `hashCode()` implementations.

## 10. Common Pitfalls and Resolutions

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Lookup returns multiple results or inserts duplicate keys | Database lacks a properly scoped unique constraint | Add a unique constraint/index and clean up duplicates |
| Tenant-scoped lookup returns wrong data or nothing | Missing tenant in composite natural ID | Annotate all key properties and pass all of them via `using()` |
| `bySimpleNaturalId()` is rejected or unsuitable | Natural ID spans multiple properties | Use `byNaturalId()` |
| Natural ID changed, yet old/new lookups behave unexpectedly | Mapping is still immutable or cache/session is unsynchronized | Mark mutable if needed, update managed entities, and test flush/cache |
| SQL still runs even though natural ID cache is enabled | Entity state is absent from L2 cache or cache missed | Distinguish natural-id cache from entity cache and inspect statistics |
| Stale cache data after bulk SQL | Bulk/native SQL bypassed Hibernate synchronization | Clear/refresh persistence context and evict affected caches after commit |
| Second test lookup runs zero SQL, yet production stays slow | Test measured L1 within one Session | Measure across fresh Sessions, verify L2, and monitor SQL |
| Pre-check fails to prevent duplicates under concurrent load | Two transactions checked simultaneously before inserting | Rely on unique constraints as the final guard and handle violations |

## 11. Testing Natural IDs

Write integration tests against a real database or Testcontainers when verifying unique constraints, collations, and transaction behavior of the target engine.

Scenarios to cover:

1. Create an entity with a valid natural ID and look it up via `bySimpleNaturalId()`.
2. Look up a composite natural ID with all properties supplied.
3. Look up a nonexistent key and verify `null`/empty per the API wrapper.
4. Attempt to insert two entities with duplicate natural IDs and confirm the database unique constraint rejects the second.
5. Update a mutable natural ID, flush, and look up by the new value.
6. After updating, verify looking up by the old key no longer returns that entity.
7. Open a new Session to verify the natural-id cache and entity cache.
8. Update via native SQL in a test, run invalidation, and verify caches do not return stale data.
9. Verify tenant isolation when natural IDs are unique only per tenant.

When testing caching, separate three cases: repeated lookup within the same Session, lookup in a fresh Session with L2 cache, and lookup after cache eviction. This pinpoints exactly which layer serves the data.

## 12. Design Checklist

- [ ] Natural ID reflects a genuinely unique and stable business key.
- [ ] Uniqueness scope is defined: system-wide or per tenant/organization.
- [ ] Values are normalized consistently before saving and querying.
- [ ] Database has a unique constraint/index covering the exact natural ID properties.
- [ ] Surrogate primary keys remain used where appropriate for internal relationships.
- [ ] `@NaturalId` is used for immutable properties; `mutable = true` only when business rules require it.
- [ ] `bySimpleNaturalId()` is used for single properties and `byNaturalId().using(...)` for composite keys.
- [ ] Property names in `using()` match mapped Java properties.
- [ ] `@NaturalIdCache` is enabled only when benefits are measurable and the cache provider has bounded capacity.
- [ ] Natural-id cache is distinguished from entity L2 cache, L1 cache, and query cache.
- [ ] An invalidation strategy exists for native SQL/bulk updates and multi-node deployments.
- [ ] Impact on `equals`/`hashCode` has been evaluated if natural IDs can change.
- [ ] Integration tests cover duplicates, mutable natural IDs, tenant scoping, and caching.

Natural IDs let Hibernate understand and retrieve entities by business keys explicitly. Keep unique constraints in the database, pick stable keys, and allow mutability only when strictly necessary. Hibernate lookup APIs and natural-id caching can optimize frequent lookups, while Spring Data derived queries and JPQL remain suitable when preserving portability across JPA providers.