# Second-Level Cache and Provider-Specific Configuration

The JPA second-level cache (L2 cache) stores entity state at a broader scope than a single `EntityManager`. As a result, multiple persistence contexts within the same application can reuse previously read data without querying the database every time.

JPA defines basic APIs and annotations to mark an entity as cacheable, while actual storage, synchronization strategies, expiration, and multi-node capabilities depend on the JPA provider and cache provider. Hibernate and EclipseLink have different configuration mechanisms. Therefore, you need to identify the provider in use before applying configuration.

## 1. Distinguishing first-level cache and second-level cache

JPA has a persistence context, often referred to as the first-level cache (L1). This is where entities currently managed within an `EntityManager` are tracked.

| Characteristic | First-level cache (L1) | Second-level cache (L2) |
|---|---|---|
| Scope | One persistence context / `EntityManager` | Shared across persistence contexts of the same persistence unit or `SessionFactory` |
| Lifecycle | Bound to the persistence context | Governed by the cache provider and application configuration |
| Default | Always present in the persistence context | Provider-dependent; Hibernate does not cache entities unless configured/marked |
| Contents | Managed entity instances and change-tracking state | Entity/collection data state in the provider's cache format |
| Goal | Avoid repeated loads of an entity within a single unit of work | Reuse data across units of work |

For example, within a transaction, calling `find(Product.class, 10L)` twice usually returns the same managed instance from L1. When the transaction ends, the persistence context closes. Another request creating a new `EntityManager` will not use the old L1; if the `Product` entity is eligible and L2 is enabled, the provider can retrieve the state from L2 instead of the database.

The L2 cache is not a database replica with full transactions and locking like a database. It is a performance optimization layer. Data can become stale if updated by another application or by SQL that does not notify the cache provider.

## 2. When should you use L2 cache?

L2 cache is most useful for data that is:

- Read frequently.
- Rarely changed or has clear update rules.
- Shareable across multiple requests and multiple persistence contexts.
- Significantly more expensive to read from the database compared to cache lookup cost.
- Bounded in size with an appropriate expiration policy.

Common examples include product catalogs, currencies, countries, rarely changing business configurations, reference tables, or shared metadata.

You should not cache every entity. Frequently changing order data, account balances, inventory, or state with strict consistency requirements may not be suitable for a shared cache without a carefully designed synchronization strategy. A cache does not replace optimistic locking, transaction isolation, or database integrity constraints.

You also need to distinguish the L2 entity cache from the query cache. The L2 entity cache typically looks up entity state by identifier. The query cache stores query results or sets of identifiers according to the provider's mechanism. Enabling L2 does not mean the query cache is automatically enabled.

## 3. Standard JPA annotations and provider-specific annotations

JPA provides `@Cacheable` to mark an entity as eligible to participate in the shared cache:

```java
import jakarta.persistence.Cacheable;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
@Cacheable
public class Country {

    @Id
    private String code;

    private String name;
}
```

This annotation is standard JPA, but it does not select a cache provider, nor does it configure TTL, capacity limits, or concurrency policies. The persistence unit's `shared-cache-mode` setting determines which entities are eligible for caching. The `ENABLE_SELECTIVE` value is an explicit choice under which only entities marked with `@Cacheable` are eligible.

Hibernate has its own annotation `org.hibernate.annotations.Cache` to specify the region and concurrency strategy. EclipseLink has its own annotation `org.eclipse.persistence.annotations.Cache` with options such as cache type, size, expiry, and isolation. These provider-specific annotations are not portable across providers.

When writing an application that might switch providers, prefer standard JPA APIs for shared parts, and keep provider-specific configuration in dedicated, intentional locations.

## 4. Configuring Hibernate with JCache and Ehcache 3

Spring Boot typically uses Hibernate as the default JPA provider when an application includes `spring-boot-starter-data-jpa`. Hibernate does not ship its own cache backend with capacity bounds, expiry, and replication; a suitable provider must be integrated.

A common approach is to use JCache (JSR-107) as the integration layer and Ehcache 3 as the cache provider.

### 4.1. Adding dependencies

Maven example:

```xml
<dependencies>
    <dependency>
        <groupId>org.hibernate.orm</groupId>
        <artifactId>hibernate-jcache</artifactId>
        <version>${hibernate.version}</version>
    </dependency>

    <dependency>
        <groupId>org.ehcache</groupId>
        <artifactId>ehcache</artifactId>
        <version>${ehcache.version}</version>
    </dependency>
</dependencies>
```

Version placeholders must be declared in the project's dependency management. `hibernate-jcache` must match the version of `hibernate-core` managed by Spring Boot. Ehcache must have a compatible JCache module and the JCache API on the classpath. Do not independently upgrade Hibernate to a version different from the Spring Boot BOM without checking compatibility.

### 4.2. Spring Boot configuration

In `application.properties`:

```properties
spring.jpa.properties.hibernate.cache.region.factory_class=jcache
spring.jpa.properties.hibernate.cache.use_second_level_cache=true
spring.jpa.properties.hibernate.javax.cache.provider=org.ehcache.jsr107.EhcacheCachingProvider
spring.jpa.properties.hibernate.javax.cache.uri=/ehcache.xml
spring.jpa.properties.jakarta.persistence.sharedCache.mode=ENABLE_SELECTIVE
spring.jpa.properties.hibernate.javax.cache.missing_cache_strategy=fail
```

In this example, `ehcache.xml` is placed at the classpath root. `jcache` selects Hibernate's JCache `RegionFactory`; the provider property explicitly specifies Ehcache when multiple JCache implementations exist on the classpath. The configuration key prefix `hibernate.javax.cache.*` is still used by Hibernate for JCache integration, even when the application's entities use Jakarta Persistence.

The `missing_cache_strategy=fail` strategy causes the application to fail if Hibernate requests a region that has not been configured. This helps detect missing regions at startup instead of silently creating a default cache without proper bounds. If you choose another strategy, check whether auto-created caches have bounds and eviction.

### 4.3. Defining regions in Ehcache

The cache alias name must match the region name Hibernate will use. For example, an entity assigned to region `catalog-countries`:

```java
import jakarta.persistence.Cacheable;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

import org.hibernate.annotations.Cache;
import org.hibernate.annotations.CacheConcurrencyStrategy;

@Entity
@Cacheable
@Cache(
    usage = CacheConcurrencyStrategy.READ_ONLY,
    region = "catalog-countries"
)
public class Country {

    @Id
    private String code;

    private String name;
}
```

Create `src/main/resources/ehcache.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<config xmlns="http://www.ehcache.org/v3"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:schemaLocation="http://www.ehcache.org/v3
        http://www.ehcache.org/schema/ehcache-core.xsd">

    <cache alias="catalog-countries">
        <key-type>java.lang.Object</key-type>
        <value-type>java.lang.Object</value-type>
        <expiry>
            <ttl unit="minutes">30</ttl>
        </expiry>
        <resources>
            <heap unit="entries">5000</heap>
        </resources>
    </cache>
</config>
```

The `catalog-countries` region has a limit of 5,000 entries on the heap and a 30-minute TTL. This is an example local cache configuration; choose size, TTL, and tiers based on actual data volume, memory, and update frequency. Unbounded default configurations should not be used in production.

If an entity uses the default region named after its class instead of declaring `region`, the Ehcache alias must match that default region name. If collections are also cached, a region must be defined for the corresponding collection role. Hibernate typically warns when it has to create an undeclared region; configure all used regions explicitly.

### 4.4. Choosing a concurrency strategy for Hibernate

`@Cache` requires selecting an appropriate concurrency strategy:

| Strategy | Use case | Trade-offs |
|---|---|---|
| `READ_ONLY` | Immutable entities or reference data that is not modified | Simple, efficient; updating a cacheable entity under this strategy is not appropriate |
| `NONSTRICT_READ_WRITE` | Rarely updated data where concurrent updates are uncommon | No locking; there can be a window where stale data is read |
| `READ_WRITE` | Data that is updated, though not overly frequently | Uses soft locks to reduce the chance of reading/writing stale entries; does not provide serializable isolation |
| `TRANSACTIONAL` | Cache provider supports transactions and strict synchronization is required | Requires a compatible backend and transaction integration; cannot be enabled by annotation alone |

Choose the strategy based on how data is read and updated. For immutable reference data, `READ_ONLY` is usually suitable. For frequently changing entities, carefully evaluate whether caching benefits outweigh synchronization costs.

## 5. Configuring other providers: Infinispan and EclipseLink

### 5.1. Hibernate with Infinispan

Infinispan can be used as a cache backend, especially when a distributed cache across multiple nodes is needed. Hibernate requires an Infinispan integration module compatible with the Hibernate version in use.

Hibernate configuration takes the form:

```properties
spring.jpa.properties.hibernate.cache.region.factory_class=infinispan
spring.jpa.properties.hibernate.cache.infinispan.cfg=org/infinispan/hibernate/cache/commons/builder/infinispan-configs.xml
```

The configuration path above is a sample configuration provided by the corresponding integration module. For real environments, use an Infinispan configuration designed for your system's topology, replication/distribution, persistence, and security. Do not just change `region.factory_class` and assume nodes already synchronize caches properly.

### 5.2. EclipseLink shared cache

EclipseLink has a shared cache scoped to the persistence unit and provides its own configuration via `@Cache` or persistence properties. Unlike Hibernate, EclipseLink's shared cache is often enabled by default for entities according to provider configuration.

Example:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

import org.eclipse.persistence.annotations.Cache;
import org.eclipse.persistence.annotations.CacheType;
import org.eclipse.persistence.config.CacheIsolationType;

@Entity
@Cache(
    type = CacheType.SOFT_WEAK,
    size = 1000,
    expiry = 600000,
    isolation = CacheIsolationType.SHARED
)
public class Product {

    @Id
    private Long id;

    private String name;
}
```

In this example, EclipseLink uses cache type `SOFT_WEAK`, a target size limit of 1,000 objects, and an expiry of 600,000 milliseconds (10 minutes). `SHARED` allows entity data to be used in the persistence unit's shared cache.

Main isolation levels:

- `SHARED`: entities and data are stored in the `EntityManagerFactory`/`ServerSession` shared cache.
- `PROTECTED`: state is stored in the shared cache, but entity instances are not shared directly across clients.
- `ISOLATED`: the entity is not placed in the shared cache; data belongs only to the persistence context. This is how to exclude an entity from the L2 cache.

The annotation and enum names in this example are EclipseLink extensions. Do not use them in entities if the application runs on Hibernate.

## 6. Query cache differs from entity L2 cache

Hibernate also has a query cache, but it is a separate feature and is disabled by default. The query cache stores query results using Hibernate's mechanism, typically a set of identifiers and related metadata to determine whether the result is still valid.

You can enable the query cache:

```properties
spring.jpa.properties.hibernate.cache.use_query_cache=true
```

Then, the query needs to be marked cacheable using Hibernate's hint, for example:

```java
@Query("select c from Country c where c.active = true")
@QueryHints(
    @QueryHint(name = "org.hibernate.cacheable", value = "true")
)
List<Country> findActiveCountriesCached();
```

The query cache does not replace the entity cache. If a query result contains entities whose entity state is not in the L2 cache, Hibernate may still need to read the entities from the database. Consider query frequency, result size, and how data changes before enabling the query cache.

Queries that depend on the current time, current user, or constantly changing parameters usually do not achieve a good cache hit rate. Do not enable caching for every repository query.

## 7. Cache invalidation, stale data, and updates outside Hibernate

The L2 cache can become stale in the following situations:

- Another application updates the same table.
- A DBA runs SQL directly.
- A batch job uses JDBC/native SQL that bypasses Hibernate's synchronization mechanism.
- One node in a cluster updates data, but another node's cache does not receive invalidation.
- The TTL is too long relative to how often data changes.

With Hibernate, you can evict an entity or region via the cache API:

```java
@Autowired
private EntityManagerFactory entityManagerFactory;

public void evictCountry(String code) {
    entityManagerFactory.getCache().evict(Country.class, code);
}
```

JPA provides `Cache.evict()` and its overloads to remove an entity, an identifier, or the entire cache. Hibernate also has its own API on `SessionFactory.getCache()` to evict entities, collections, or entire regions.

Eviction is a cache removal operation, not a database rollback. When updating outside Hibernate, determine the appropriate timing and scope of invalidation. If it must happen after a transaction, evict after the transaction commits to avoid reloading stale values into the cache while the transaction is still in progress.

For multi-node applications, eviction on one node is only cluster-wide if the provider supports it and the corresponding coordination/invalidation is configured. Local Ehcache inside each JVM does not automatically share caches with other JVMs. You can use a distributed provider, an invalidation messaging mechanism, or a short TTL depending on requirements.

Do not treat TTL as the sole solution for all data. TTL bounds entry age, but does not guarantee fresh data immediately after an important update. For data requiring consistency, consider not caching it or using a guaranteed synchronization mechanism.

## 8. Cache modes and standard JPA APIs

JPA can control reading from and writing to the shared cache via cache retrieve/store modes. For example, a query can be instructed to bypass the cache or avoid storing results in the cache:

```java
List<Country> countries = entityManager
        .createQuery(
                "select c from Country c",
                Country.class
        )
        .setHint("jakarta.persistence.cache.retrieveMode", CacheRetrieveMode.BYPASS)
        .setHint("jakarta.persistence.cache.storeMode", CacheStoreMode.BYPASS)
        .getResultList();
```

Common modes:

- `USE`: allows using the cache according to default configuration.
- `BYPASS`: bypasses the cache for the corresponding operation.
- `REFRESH`: requests refreshing cached data from the database when the store mode is applied.

Standard JPA APIs and hints can make code less provider-dependent, but how the provider executes them and their limitations must still be verified against the implementation.

## 9. Measuring effectiveness and common pitfalls

Enabling caching does not guarantee performance will improve. Monitor hits, misses, puts, evictions, region size, query execution times, and memory.

| Symptom | Possible cause | Resolution |
|---|---|---|
| No cache hits | Entity not marked cacheable, L2 not enabled, or provider not configured | Check annotations, shared cache mode, `RegionFactory`, and startup logs |
| Cache region auto-created unbounded | Region not declared in provider configuration | Declare regions explicitly and set TTL/size/eviction |
| Stale data after running external SQL | Cache was not notified by provider | Evict region/entry after commit or use a coordination mechanism |
| High cache hits but database still queried | Entity state not cacheable or query cache only caches identifier lists | Mark entities properly and evaluate query cache separately |
| Memory grows continuously | Unbounded region or caching too many entities/collections | Set capacity limits, TTL, and cache only appropriate data |
| Entity update fails under `READ_ONLY` | Data configured as immutable while code still modifies it | Choose an appropriate strategy or exclude entity from cache |
| Multiple nodes see different data | Local cache, replication/invalidation not configured | Choose a distributed provider or explicit synchronization mechanism |

When profiling, compare the same workload under cold-cache and warm-cache states. Measure p95/p99 latency, database call counts, memory footprint, and eviction overhead. Do not rely on a single query run alone.

## 10. Testing the cache

An integration test should verify both cache behavior and consistency:

1. Create a cacheable entity and commit the transaction.
2. Open a new `EntityManager` or transaction, read the entity by ID, and observe L2 cache statistics.
3. Read it again in another persistence context to verify L2 reuse.
4. Update the entity via JPA and verify the cache reflects the new value according to the concurrency strategy.
5. Perform an update outside Hibernate in the test environment, evict the cache as designed, and verify the next read fetches fresh data.
6. Test TTL, eviction, and provider capacity limits.

Do not test L2 cache solely by reading an entity twice in the same `EntityManager`: the second read may only prove that L1 is working. Use a new persistence context and enable provider statistics or inspect SQL to distinguish L1 hits, L2 hits, and database access.

For distributed caches, test across two application instances to verify invalidation/replication. Single-JVM tests do not prove the cache behaves properly on a cluster.

## 11. Provider selection and configuration checklist

- [ ] Identified the actual JPA provider running: Hibernate, EclipseLink, or another provider.
- [ ] Distinguished L1, L2 entity/collection cache, and query cache.
- [ ] Only caching entities with high read rates and suitable update policies.
- [ ] Using standard JPA `@Cacheable` and provider-specific annotations/configuration when a specific strategy/region is needed.
- [ ] Hibernate has a compatible `RegionFactory` and cache provider; integration module version matches Hibernate core.
- [ ] Regions have appropriate capacity limits, TTL, and eviction; no unbounded default caches in production.
- [ ] Concurrency strategy chosen based on immutability and update frequency.
- [ ] Defined invalidation approach for native SQL, JDBC, external applications, or multiple nodes.
- [ ] Query cache evaluated separately, not enabled indiscriminately.
- [ ] Have hit/miss/eviction metrics, SQL counts, and memory stats to prove benefit.
- [ ] Have integration tests using new persistence contexts and verifying data after invalidation.

L2 cache can reduce database reads when multiple requests access infrequently changing data. However, it introduces a stateful layer outside the database, so provider configuration, concurrency strategy, region bounds, and invalidation all matter. Start with a few reference entities with clear behavior, measure effectiveness with realistic workloads, and only then expand to other regions.

## References

- [Hibernate ORM 7 – Caching and JCache/Ehcache configuration](https://docs.hibernate.org/orm/7.2/introduction/html_single/)
- [Hibernate ORM User Guide – Caching](https://docs.hibernate.org/orm/7.0/userguide/html_single/)
- [EclipseLink 4 – JPA Extensions Reference, @Cache](https://eclipse.dev/eclipselink/documentation/4.0/jpa/extensions/jpa-extensions.html)
- [Ehcache 3 – XML configuration](https://www.ehcache.org/documentation/3.10/xml.html)
