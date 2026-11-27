# JPA, Hibernate, and the Proxies, Enhancement, and Metadata That Must Be Verified

> **Chapter:** Application Integration  
> **Module:** `SPRING_BOOT_NATIVE_IMAGE`  
> **Objective:** Distinguish Spring AOP proxies from Hibernate lazy-loading proxies; understand entity bytecode enhancement; know how Spring Data JPA contributes `ManagedTypes` and `RuntimeHints`; verify dialects, repositories, resources, and drivers on the exact Hibernate/Spring Boot/GraalVM versions before releasing a native executable.

## 1. Why JPA/Hibernate Must Be Verified Separately

Spring Boot can bootstrap a JPA application on the JVM without requiring developers to manually declare every reflection class or method. Hibernate and Spring Data perform many dynamic operations during startup and data access:

- Discovering entities and mappings.
- Creating `EntityManagerFactory`, metamodels, and repository proxies.
- Creating proxies for lazy-loaded associations or collections.
- Loading mapping XML, dialects, JDBC drivers, and service providers.
- Using reflection to instantiate entities, converters, listeners, interceptors, or custom types.
- Optionally using bytecode enhancement to inject interception into entity classes.

With GraalVM Native Image, the compiler analyzes reachability at build time. Reflection, resources, serialization, and dynamic proxies must be discovered or declared via metadata before the executable is built. The classpath is also fixed at build time. Spring AOT generates initialization code, bytecode, and hints, yet each integration must still be verified according to how that library instantiates objects and accesses data. [Spring Boot — Introducing GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html)

An application can pass native compilation and still fail when:

- Hibernate initializes `EntityManagerFactory`.
- A lazy association is accessed for the first time.
- A repository method uses projections or custom queries.
- An entity listener or converter is loaded by class name.
- A mapping/resource is read only on a business branch not exercised in tests.
- A JDBC driver or dialect differs from the build environment.

Therefore, **bean proxies, Hibernate proxies, entity enhancement, AOT metadata, and database behavior** must be verified individually. They are related, yet not a single mechanism.

## 2. Distinguishing Four Mechanisms Often Grouped Together as Proxies or Enhancement

| Mechanism | Who Creates/Manages It? | Purpose | Where to Check? |
|---|---|---|---|
| Spring AOP proxy | Spring Framework | Applies transactions, caching, security, and aspects to Spring beans | Bean types, advisors, and AOT-generated proxies |
| Hibernate lazy proxy/collection wrapper | Hibernate ORM | Defers loading entity associations or collections | Entity mappings, persistence context, native runtime |
| Hibernate bytecode enhancement | Hibernate build plugin/enhancer | Injects interception into entities for lazy attribute loading, dirty tracking, or association management | Class bytecode after compile/enhance |
| Spring Data JPA AOT output | Spring Data and Spring AOT | Prepares `ManagedTypes`, repository metadata, accessor bytecode, query implementations, and runtime hints | AOT output and repository tests |

**Spring AOT generating proxies for Spring beans does not mean Hibernate entity proxies are already handled.** Spring AOP proxies typically wrap service/repository beans. Hibernate proxies represent an unloaded entity or an uninitialized collection. Bytecode enhancement modifies entity classes during the build. Meanwhile, Spring Data AOT prepares information and code for the persistence layer.

When an error appears, first identify which mechanism is actually failing. Adding a reflection hint for an entity will not fix a `LazyInitializationException`; enabling Hibernate enhancement will not automatically include XML resources or a JDBC driver in the native image.

## 3. How Hibernate Proxies and Lazy Loading Work

Hibernate manages an entity graph that can be large. If every entity read recursively loaded all associations, the application would waste memory and could trigger many database round trips. Hibernate uses lazy fetching to load associations only when needed.

Example:

```java
@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id")
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public Long getId() {
        return id;
    }

    public Customer getCustomer() {
        return customer;
    }

    public List<OrderLine> getLines() {
        return lines;
    }
}
```

When loading `PurchaseOrder`, Hibernate may not load `Customer` and the `OrderLine` elements yet. Instead, Hibernate provides a proxy or collection wrapper. When code accesses unloaded state, Hibernate uses the persistence context to fetch the data and continue the call.

```java
PurchaseOrder order = entityManager.find(PurchaseOrder.class, orderId);

// The association may still not be loaded.
boolean customerLoaded = entityManagerFactory
        .getPersistenceUnitUtil()
        .isLoaded(order, "customer");

// Calling customer data may trigger SQL.
String customerName = order.getCustomer().getName();
```

Collections can be checked as well:

```java
boolean linesLoaded = entityManagerFactory
        .getPersistenceUnitUtil()
        .isLoaded(order, "lines");
```

Hibernate also provides `Hibernate.isInitialized(...)` to check proxy/collection state via Hibernate's own API. [Hibernate ORM — Proxies and Lazy Fetching](https://docs.hibernate.org/stable/core/introduction/html_single/#proxies-and-lazy-fetching)

### 3.1. Proxies Can Only Load While the Persistence Context Is Active

Lazy proxies usually require an open persistence context/session to query the database. If the transaction and persistence context end before the association is accessed, Hibernate may throw `LazyInitializationException`.

Example:

```java
PurchaseOrder order = repository.findById(orderId).orElseThrow();

// The transaction ended and the persistence context is closed.
// The following lazy call may fail.
String customerName = order.getCustomer().getName();
```

This is a persistence context lifecycle issue, not a Native Image reachability metadata error. The native executable must still obey the same lazy-loading rules as the JVM.

The proper approach is to fetch the required data inside the transaction, map it to a DTO while the persistence context is open, and return the DTO over the API. Do not extend transactions indefinitely just so a serializer can traverse the entire entity graph.

### 3.2. Lazy Loading Can Cause N+1 Queries

Suppose a page displays 50 orders and each order needs the customer's name. If the initial query loads only orders and code subsequently calls `getCustomer()` one by one, Hibernate may emit one query per customer. That is the N+1 query problem.

Native Image does not eliminate this cost. Faster startup does not make database round trips disappear. Check SQL counts and fetch plans on the native runtime just as you would on the JVM.

Common ways to control fetching:

- JPQL/HQL `join fetch` when a specific set of associations is needed.
- JPA `EntityGraph` for use-case-specific fetch plans.
- DTO projections when only a few fields are needed.
- Batch fetching when appropriate for the data shape.
- Dedicated queries for screens or reports with large data graphs.

Repository example:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Override
    @EntityGraph(attributePaths = {"customer", "lines"})
    Optional<PurchaseOrder> findById(Long id);
}
```

Service mapping entity to DTO inside a transaction:

```java
@Service
public class PurchaseOrderQueryService {

    private final PurchaseOrderRepository repository;

    public PurchaseOrderQueryService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public PurchaseOrderView getDetails(Long id) {
        PurchaseOrder order = repository.findById(id)
                .orElseThrow();

        return new PurchaseOrderView(
                order.getId(),
                order.getCustomer().getName(),
                order.getLines().stream()
                        .map(line -> new OrderLineView(
                                line.getProductCode(),
                                line.getQuantity()))
                        .toList());
    }
}
```

Tests should verify that the fetch plan actually loads the expected associations without issuing unexpected queries. `@EntityGraph` is a hint to the JPA provider; inspect the SQL and loaded state on your actual Hibernate version.

## 4. Entity Proxies and Class Limitations

Hibernate typically uses bytecode proxying to represent unloaded entities. A `final` entity class or `final` method can restrict subclass proxy generation and interception. Polymorphic associations also introduce extra issues because the proxy may not know the concrete subtype at creation time.

Design principles:

- Follow entity class requirements for Jakarta Persistence and the Hibernate version in use.
- Do not declare entities as `final` if the mapping relies on class-based lazy proxies.
- Keep a no-arg constructor accessible as required by JPA, unless the bytecode enhancer and provider version specifically support otherwise.
- Do not assume `instanceof` or casting on a polymorphic proxy always behaves like an initialized entity.
- Use `PersistenceUnitUtil.isLoaded` or Hibernate APIs to check state rather than inferring from class names.
- Test `getReference`, `find`, lazy associations, and collections on the native executable.

Hibernate 6.2 deprecated the `@Proxy` annotation; do not rely on this legacy configuration as a general solution for native image. For `final` entity classes, Hibernate may not be able to generate proxy classes in the usual way. [Hibernate ORM User Guide — Entity Proxies](https://docs.hibernate.org/orm/6.6/userguide/html_single/#entity-proxy)

## 5. What Does Hibernate Bytecode Enhancement Solve?

Bytecode enhancement is a step that transforms entity class bytecode so Hibernate can inject interception into fields or methods. It is neither Spring AOT code generation nor GraalVM Native Image compilation.

Hibernate's bytecode enhancer supports key capabilities:

- **Attribute-level lazy fetching:** defers loading basic attributes annotated with `@Basic(fetch = LAZY)` and certain non-polymorphic lazy associations.
- **Interception-based dirty tracking:** records changes when fields are updated, instead of only comparing snapshots at flush time.
- **Association management:** helps synchronize certain operations on both ends of an association depending on enabled enhancer features.

Example of a potentially expensive basic attribute:

```java
@Entity
public class DocumentRecord {

    @Id
    @GeneratedValue
    private Long id;

    private String title;

    @Basic(fetch = FetchType.LAZY)
    @Lob
    private String fullText;

    protected DocumentRecord() {
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public String getFullText() {
        return fullText;
    }
}
```

Without bytecode enhancement, Hibernate may ignore the lazy-loading request on a basic attribute and load `fullText` together with the entity. When the class is properly enhanced, Hibernate can intercept field access to load the content later.

By default, Hibernate may load lazy fields belonging to the same fetch group in a single query when one field in the group is accessed. `@LazyGroup` allows splitting fields into independent loading groups when the use case requires it. [Hibernate ORM — Using the Bytecode Enhancer](https://docs.hibernate.org/stable/core/introduction/html_single/#using-the-bytecode-enhancer)

### 5.1. Enhancement Does Not Eliminate All Proxies

Interception can perform lazy loading for certain non-polymorphic associations without needing a separate proxy object. If an association is polymorphic and the target type has subclasses, Hibernate still needs a proxy to represent the unknown concrete type.

Therefore:

- Enabling the enhancer does not mean all lazy associations become proxy-free.
- Not enabling the enhancer does not mean Hibernate cannot lazy-load regular entity associations.
- Enhancement does not replace `RuntimeHints` or Hibernate/GraalVM metadata.
- Spring AOT does not automatically enable Hibernate enhancement for entity classes.

Identify which features truly require the enhancer before adding the plugin to the build. If you only use standard lazy associations, verify Hibernate native support and the proxy path; if you use lazy basic attributes, verify that bytecode enhancement actually ran.

### 5.2. Trade-Offs of Interception-Based Dirty Tracking

Interception-based dirty tracking can reduce the overhead of retaining and comparing snapshots. However, Hibernate notes that this approach can be less accurate than snapshot-based dirty checking in certain scenarios.

For example, the interceptor detects replacing an entire array:

```java
document.setImage(new byte[] {1, 2, 3});
```

But if code mutates an element inside an existing array directly:

```java
document.getImage()[0] = 9;
```

the interceptor may not observe the in-place modification inside the array. When enabling enhancement, inspect how the application updates collections, arrays, and mutable value types; do not assume all mutations are tracked identically.

## 6. Enabling Bytecode Enhancement in the Build

If the application needs lazy basic attributes or interception-based dirty tracking, enable the Hibernate enhancer at build time and verify that the plugin version matches Hibernate ORM.

### 6.1. Gradle

Example with Hibernate ORM 7.x:

```groovy
plugins {
    id "org.hibernate.orm" version "<hibernate-version>"
}

hibernate {
    enhancement {}
}
```

The `enhancement {}` block is required to enable enhancement. Do not write `hibernate { enhancement }` as a bare property reference; Gradle may interpret that as a getter and fail to configure enhancement. Hibernate explicitly highlights this distinction in its current documentation. [Hibernate ORM — Bytecode Enhancer](https://docs.hibernate.org/stable/core/introduction/html_single/#using-the-bytecode-enhancer)

Use a plugin version aligned with the `hibernate-core` resolved by the Spring Boot BOM, following the documentation for your Hibernate major version. If the plugin version does not match, the build may fail or the enhancer may apply behavior different from the runtime provider.

### 6.2. Maven

With Hibernate ORM 7.x, the Maven plugin was rewritten and uses new plugin coordinates:

```xml
<plugin>
    <groupId>org.hibernate.orm</groupId>
    <artifactId>hibernate-maven-plugin</artifactId>
    <version><!-- version matching Hibernate ORM --></version>
    <executions>
        <execution>
            <goals>
                <goal>enhance</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Hibernate 6.x uses different Maven plugin coordinates. Take the exact `groupId`, `artifactId`, and configuration from the documentation of the Hibernate version managed by Spring Boot; do not mix 6.x plugin configuration with Hibernate 7.x. [Hibernate ORM 7.0 Migration Guide — Maven Enhancement Plugin](https://docs.hibernate.org/orm/7.0/migration-guide/)

### 6.3. Verifying That Classes Were Enhanced

Do not rely solely on the build log. Verify that:

1. The enhancement task/goal actually runs after entities are compiled.
2. Output classes/JARs contain the enhanced bytecode.
3. Enhancement is applied to the source set and module containing the actual entities.
4. No packaging step overwrites them with unenhanced class files.
5. Runtime Hibernate uses the same major/minor line tested with the enhancer.

You can use `javap -p` to inspect the bytecode and added interfaces/methods, though internal member names can vary across versions. A more reliable behavioral check is testing lazy basic attributes and dirty tracking with the Hibernate runtime.

## 7. How Spring Data JPA AOT Prepares Entities and Repositories

Spring Data needs to know the set of managed domain types. On the JVM, an application can rely on classpath scanning at startup. In a native image, runtime classpath scanning cannot be used as flexibly as on the JVM, so Spring Data uses `ManagedTypes` to record entities/types discovered during AOT processing.

Spring Data documentation recommends annotating domain types with store-specific annotations like `@Entity` to support early entity scanning and ensure types are included in `ManagedTypes`. [Spring Data JPA — Ahead of Time Optimizations](https://docs.spring.io/spring-data/jpa/reference/jpa/aot.html)

Example:

```java
@Entity
@Table(name = "customer")
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    protected Customer() {
    }
}
```

If entities live outside the default scan package, configure the scan scope explicitly:

```java
@SpringBootApplication
@EntityScan(basePackageClasses = {
        Customer.class,
        PurchaseOrder.class
})
@EnableJpaRepositories(basePackageClasses = PurchaseOrderRepository.class)
public class PaymentApplication {
}
```

For configurations with multiple persistence units, specialized mappings, or entities provided by separate modules, inspect `PersistenceManagedTypes` and `PersistenceUnitInfo` used by the AOT collector. Spring Data JPA can use a `PersistenceManagedTypes` bean if present; if discovery is insufficient for the application, the documentation provides `spring.aot.jpa.repositories.use-entitymanager=true` to use `EntityManagerFactory` directly during metadata collection.

### 7.1. RuntimeHints Contributed by Spring Data

During AOT processing, Spring Data can contribute hints for:

- `ManagedTypes` and the discovered entity set.
- Reflection for entities, repository return types, and Spring Data annotations.
- Repository fragments.
- Querydsl `Q` classes.
- Auditing and certain other integrations.

Therefore, do not reflexively add broad reflection hints for all entities before checking the hints Spring Data already generates. Add `RuntimeHints` when custom types, converters, listeners, mappings, or dynamic access paths exist that the framework cannot infer.

### 7.2. AOT Repositories Do Not Mean Every Repository Has Generated Code

Spring Data JPA can generate AOT implementations for certain query methods known at build time, such as derived queries, annotated queries, and named queries. This feature shifts query parsing from runtime to build time.

However, not every repository method qualifies. Methods with implementation fragments, dynamic projections, certain custom collection types, or `ScrollPosition` may fall outside the supported scope of a specific version. AOT repositories are an internal implementation detail; application code should not directly reference generated classes. [Spring Data JPA — AOT Repositories and Limitations](https://docs.spring.io/spring-data/jpa/reference/jpa/aot.html)

## 8. Metadata to Verify in a Native Image

With JPA/Hibernate, metadata typically spans several groups:

| Group | Examples | What to Verify |
|---|---|---|
| Reflection | Entity constructors, fields, converters, listeners, custom types | Required members are retained for the exact operations used |
| Dynamic proxy | Hibernate entity/collection proxies, JDK proxies created by integrations | Proxy/interface sets and proxy creation mechanisms are compatible |
| Resource | `orm.xml`, mapping XML, SQL templates, or dynamically loaded config files | Resource patterns are included in the image |
| Service/provider | JDBC drivers, Hibernate `Integrator`, dialects, or providers loaded via service mechanisms | Providers are on the runtime classpath and recognized by Native Image |
| Serialization | Java serialization in custom types/caches/integrations | Type serialization metadata is sufficient |
| Repository AOT | Query metadata, generated repository fragments, type accessors | AOT output is built and included in the final artifact |

### 8.1. Reflection Hints

Spring Data JPA contributes hints for entities and repository types it detects. If the application has custom code using reflection to instantiate converters or listeners by class name, register those exact types/members via `RuntimeHintsRegistrar`.

Illustrative example for a dynamically loaded custom converter:

```java
public class PaymentRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.reflection().registerType(
                CurrencyCodeConverter.class,
                MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS);
    }
}
```

Registering the registrar:

```java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(PaymentRuntimeHints.class)
class PaymentNativeConfiguration {
}
```

This example is only needed when the converter is actually instantiated via a dynamic path that static analysis/AOT does not detect. If the converter is already declared in Spring/JPA configuration and the framework already generates hints for it, do not add duplicate registrations.

### 8.2. Resource Hints

If the application reads mapping XML or SQL files from paths obtained via properties, declare the corresponding resource patterns. For example:

```java
public class PaymentResourceHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.resources().registerPattern("META-INF/orm-custom.xml");
        hints.resources().registerPattern("sql/payment/*.sql");
    }
}
```

Registering a resource hint only ensures the file is packaged and readable inside the native image. It does not validate that the mapping XML is valid, entities are scanned properly, or SQL is compatible with the database. Test both resource lookup and Hibernate actually loading and using it.

For `META-INF/services` and providers loaded via `ServiceLoader`, verify the service-loading mechanism supported by GraalVM and actual dependencies. Do not assume every file in a JAR is included in the native executable merely because it is on the JVM classpath.

### 8.3. Hibernate Native Extension

Hibernate publishes the `hibernate-graalvm` module to assist compiling Hibernate ORM into GraalVM Native Image. Hibernate documentation currently describes this module as **experimental**. Therefore:

- Add the module only if required by the documentation of your Hibernate version and Spring Boot integration.
- Match the version with Hibernate ORM; do not add an arbitrary version.
- Verify the module is in the final native build dependency graph.
- Read release notes to understand supported scope and limitations.
- Do not treat this dependency as a guarantee that all custom types, proxies, dialects, or drivers will work.

[Hibernate ORM — Integration Modules](https://docs.hibernate.org/stable/orm/quickstart/html_single/)

## 9. Spring Boot, Spring Framework, and Hibernate Versions Must Be Aligned

Native compatibility depends on the version combination, not solely on the Hibernate version.

Spring Framework 6.2 requires Hibernate ORM 6.5 or later for GraalVM Native Image support. This is a requirement of the Spring Framework 6.2 line; do not infer it as the minimum or recommended version for all current Spring Boot lines. Hibernate ORM 6.5 has reached end-of-life, so do not use this baseline note as a reason to pin 6.5 for a new application today. [Spring Framework 6.x Upgrade Guide — Spring Framework 6.2](https://github.com/spring-projects/spring-framework/wiki/Upgrading-to-Spring-Framework-6.x)

Version selection process:

1. Choose a Spring Boot release compatible with your Java and GraalVM toolchain.
2. Use the Spring Boot BOM/dependency management to select compatible Spring Framework, Spring Data JPA, and Hibernate ORM versions.
3. Check the Hibernate ORM release compatibility matrix for that Spring Boot line.
4. If using Hibernate enhancer or `hibernate-graalvm`, pick the exact version matching Hibernate ORM.
5. Verify that the JDBC driver, dialect extensions, and other integration modules support native image.
6. Record all resolved versions in the build report.

Do not override `hibernate-core` independently to try to fix a native build before determining whether the issue is proxies, enhancement, service loading, or metadata. Upgrading a single dependency in isolation can create an untested Spring Data/Hibernate combination.

## 10. Dialects and Database Configuration in AOT

Spring Data JPA AOT may initialize an in-memory Hibernate instance to collect metadata without accessing a real database. The managed type set is determined by the AOT metadata collector. Some decisions such as the database dialect may be fixed in the AOT-processed application.

This matters when the build pipeline and runtime environment use different databases. If the build uses H2 while production uses PostgreSQL, do not assume a dialect detected at build time will automatically change based on the runtime JDBC URL.

When deterministic behavior is required, configure the dialect explicitly using the property appropriate for your Hibernate version:

```yaml
spring:
  jpa:
    database-platform: org.hibernate.dialect.PostgreSQLDialect
```

Use a dialect belonging to the Hibernate ORM managed by Spring Boot. If using a custom dialect, verify the dialect class and its metadata in the native executable.

Distinguish two phases:

- **AOT processing:** collects bean/entity/repository metadata; Spring Data JPA can use in-memory Hibernate and does not require a database connection.
- **Actual native application runtime:** creates the `DataSource`, connects to the database, runs DDL validation/migrations, and executes queries per runtime configuration.

If a build pipeline needs to connect to a database for a custom plugin or migration step, that is a separate pipeline step, not a default requirement of Spring Data JPA AOT.

## 11. Verifying JDBC Drivers, Dialects, and Mapping Resources

An application with complete entity metadata can still fail if the required JDBC driver or resources are absent from the native artifact.

Check the following:

- JDBC driver version is compatible with Java, GraalVM, and the database server.
- Driver is on the runtime classpath, not just the compile classpath.
- Driver has native-image reachability metadata or official configuration guidance.
- Custom dialects and type contributors have the required constructors/service providers.
- Mapping XML, `persistence.xml`, `orm.xml`, and dynamically loaded config files have appropriate resource hints.
- SQL migrations/resources are packaged properly in the JAR or container image.
- TLS providers, charsets, and native libraries the driver depends on are available in the image/runtime OS.
- Database URL, credentials, and pool configuration are provided at runtime per deployment environment.

Do not add reflection/resource hints for an entire driver package without an error or documentation requirement. Start with the dependency documentation and reachability metadata for that exact driver version; add custom hints only for unhandled parts.

## 12. Testing JPA/Hibernate on the JVM, AOT, and the Native Executable

A test that only verifies the Spring context starts is insufficient. You must execute queries, proxies, enhancement, and transactions on the actual native binary.

### 12.1. Unit and Integration Tests on the JVM

Verify:

- Entity mappings, identifier generation, relationship ownership, and cascades.
- Repository derived queries, `@Query`, projections, pagination, and sorting.
- Converters, entity listeners, callbacks, custom types, and auditing.
- Transaction rollback/commit and optimistic locking.
- `EntityGraph`/`join fetch` and SQL statement counts.
- Lazy associations and collections.
- Lazy basic attributes if enhancement is enabled.

These tests verify JPA/Hibernate logic, not that native metadata is complete.

### 12.2. Inspecting AOT Output

Run Spring AOT under your application's build profile. Verify:

- `ManagedTypes` contains all entities.
- Repository metadata/generated implementations appear for qualifying methods.
- Reflection hints include required custom types.
- Resource hints include dynamically loaded mappings/resources.
- Generated proxy bytecode and JDK proxy metadata match the Spring beans requiring proxies.
- Hibernate integration metadata is present in the native build inputs.

AOT output paths depend on the Spring Boot/build tool version. In common Spring Boot 3.x lines, Maven generates output under `target/spring-aot/main/`, while Gradle typically uses `build/generated/aotSources`, `build/generated/aotClasses`, and `build/generated/aotResources`. Rely on your exact plugin's log/task output rather than hard-coding paths across versions.

### 12.3. Native Integration Tests with a Real Database

Run the native executable connected to the same database type and JDBC driver used in production. You can use Testcontainers or a dedicated test database, as long as the test exercises the native binary rather than only the JVM.

Cases to include:

| Case | Action | What Must Be Proven |
|---|---|---|
| JPA bootstrap | Initialize `EntityManagerFactory` | Hibernate, dialect, and driver initialize properly |
| Persist/load | Save, flush, clear, reload entity | Entity metadata and constructors work |
| Lazy to-one | Load entity, check loaded state, access association in transaction | Hibernate proxy/interception works |
| Lazy collection | Access collection inside transaction | Collection wrapper and fetch path work |
| Detached access | Access lazy association after persistence context closes | Application handles `LazyInitializationException` properly |
| `EntityGraph` | Query with graph and inspect associations | Fetch plan and query are correct |
| Repository query | Run derived queries and `@Query` | Repository AOT/runtime works |
| Projection | Read interface/DTO projections | Constructor/accessor metadata is sufficient |
| Custom converter/listener | Save and load custom types | Reflection/instantiation path works |
| Mapping resource | Load XML/custom mappings | Resource is present and Hibernate uses it |
| Transaction | Commit/rollback and optimistic locking | Transaction integration works |
| Enhancement | Read lazy basic field and update mutable field | Entity bytecode is enhanced with proper semantics |

### 12.4. Testing Lazy Loading and Enhancement Using Loaded State

Integration test example:

```java
@Test
@Transactional
void loadsCustomerOnlyWhenRequested() {
    PurchaseOrder order = entityManager.find(
            PurchaseOrder.class, existingOrderId);

    PersistenceUnitUtil util = entityManagerFactory
            .getPersistenceUnitUtil();

    assertThat(util.isLoaded(order, "customer")).isFalse();

    String customerName = order.getCustomer().getName();

    assertThat(customerName).isNotBlank();
    assertThat(util.isLoaded(order, "customer")).isTrue();
}
```

Specific expectations depend on mappings, queries, and Hibernate version. If the test uses `join fetch` or an `EntityGraph`, the association is loaded upfront and the initial assertion must adjust to the fetch plan.

For lazy basic attributes, tests must confirm that the enhancer ran and the provider supports the use case. Never treat a single JVM test as proof that the native executable has sufficient metadata.

### 12.5. Checking SQL and Performance

Besides correctness, record:

- Query count per request.
- Queries emitted when accessing lazy associations.
- Query count before and after using `EntityGraph`/`join fetch`.
- Dirty tracking results after flush.
- `EntityManagerFactory` initialization time.
- Startup time, RSS, and memory under representative workloads.

Do not compare startup time alone. Native image may start faster, yet query plans, round-trip counts, or pool sizing still dominate most data API latency.

## 13. Common Errors and How to Diagnose Them

| Symptom | Possible Cause | What to Check |
|---|---|---|
| `EntityManagerFactory` fails to initialize in native | Incompatible Hibernate version, provider, driver, or metadata | Dependency tree, Hibernate logs, native metadata |
| `ClassNotFoundException` for entity/converter | Type missing from managed set or classpath | `@EntityScan`, `PersistenceManagedTypes`, dependency graph |
| `NoSuchMethodException` when instantiating entity | Constructor/metadata or enhancer mismatch with runtime expectations | Entity constructors, generated bytecode, reflection hints |
| Lazy association fails in native | Missing Hibernate proxy/interception path or metadata | Hibernate version, proxy support, transaction scope |
| `LazyInitializationException` | Persistence context closed before access | Transaction boundaries and DTO mapping |
| `ClassCastException`/unexpected proxy type | Assuming concrete class instead of proxy/interface | Entity inheritance, proxy strategy, polymorphic associations |
| Lazy basic field is always eagerly loaded | Bytecode enhancement did not run or `@Basic(fetch=LAZY)` unsupported in config | Gradle/Maven enhancer task, output classes, query logs |
| Dirty tracking misses changes | Mutable object modified in place instead of replacing reference | Enhancement mode and value update patterns |
| Repository method fails only in native | AOT repository unsupported for method pattern or missing hints | Spring Data version, query type, AOT output |
| Mapping XML not found | Resource not packaged or missing resource pattern | JAR contents and resource hints |
| Wrong dialect in production | Dialect decided/frozen during AOT build | Build-time properties and target database |
| Fails only with one JDBC driver | Driver version or reachability metadata mismatch | Driver compatibility and native-image documentation |

Do not solve every Hibernate error by adding `allDeclaredMethods` to an entire package. Identify whether the fault lies in Spring proxies, Hibernate proxies, enhancement, managed types, resources, service loading, or database integration.

## 14. Pre-Release Verification Workflow

1. **Resolve versions:** record Spring Boot, Spring Framework, Spring Data JPA, Hibernate ORM, Hibernate enhancer, JDBC driver, and GraalVM.
2. **Check compatibility:** use the BOM and compatibility matrix for the exact release; do not override Hibernate independently without a clear reason.
3. **Define the persistence model:** list entities, embeddables, converters, listeners, custom types, repositories, and mapping resources.
4. **Verify lazy behavior:** identify which associations use proxies, which fields require bytecode enhancement, and the fetch plan for each use case.
5. **Run the enhancer if needed:** confirm the plugin actually transforms entity bytecode and its version matches runtime Hibernate.
6. **Run Spring AOT:** verify `ManagedTypes`, repository metadata, and reflection/resource hints are generated.
7. **Inspect artifacts:** verify JDBC drivers, mapping XML, migration resources, and native metadata are in the native build inputs.
8. **Build native:** use the exact toolchain and configuration of the release pipeline.
9. **Run native integration tests:** exercise persist/load, lazy access, repository queries, converters, transactions, and migrations.
10. **Check SQL/performance:** confirm there are no unexpected N+1 queries and query counts are appropriate.
11. **Record baseline:** save versions, AOT settings, native build args, database/driver details, and test results for comparison during upgrades.

## 15. JPA/Hibernate Native Image Checklist

- [ ] Spring Boot, Spring Framework, Spring Data JPA, Hibernate, and GraalVM are in a supported version combination.
- [ ] Hibernate ORM is not overridden outside the BOM without checking compatibility.
- [ ] Entities are discovered in `ManagedTypes`/AOT output.
- [ ] `@EntityScan` or persistence unit configuration covers all entity packages.
- [ ] Converters, listeners, custom types, and entity callbacks are verified.
- [ ] Spring AOP proxies are distinguished from Hibernate lazy proxies.
- [ ] Entity classes meet the proxy/subclassing requirements of the mapping in use.
- [ ] Lazy associations are tested inside transactions and after persistence context closure.
- [ ] Fetch plans avoid N+1 queries and are verified on the native runtime.
- [ ] If using lazy basic attributes, the bytecode enhancer actually ran.
- [ ] Enhancement plugin version matches Hibernate ORM.
- [ ] Dirty tracking is tested with mutable values, arrays, and collections.
- [ ] Spring Data AOT repositories are relied upon only for supported method patterns.
- [ ] Custom reflection/resource hints are verified; broad hints duplicating framework hints are avoided.
- [ ] Mapping XML and dynamically loaded resources are present in the native image.
- [ ] JDBC driver and dialect are compatible with GraalVM/native runtime.
- [ ] Dialect/build-time settings match the target database.
- [ ] Hibernate native extension (if used) is checked for version and support status.
- [ ] Native executable has run integration tests with a real database or Testcontainers.
- [ ] SQL counts, transactions, lazy loading, and query semantics are verified.

## 16. Key Takeaways

In Spring Boot Native Image, JPA/Hibernate must be verified across multiple layers. Spring AOT prepares bean definitions, repository metadata, and runtime hints. Hibernate manages entity proxies, collection lazy loading, and bytecode enhancement. GraalVM requires metadata for dynamic access paths that static analysis cannot infer.

Clearly distinguish three mechanisms: **lazy-loading proxies**, **bytecode enhancement**, and **native image metadata**. Enhancement can support lazy basic attributes and dirty tracking, but it does not eliminate all proxies. Spring Data JPA contributes `ManagedTypes` and hints, yet does not replace tests for the JDBC driver, dialect, mapping resources, or Hibernate runtime. Final proof must come from integration tests running on the exact native executable with the database and dependency versions the application will ship with.

### References

- [Spring Boot — Introducing GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html)
- [Spring Framework — Ahead-of-Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html)
- [Spring Data JPA — Ahead of Time Optimizations](https://docs.spring.io/spring-data/jpa/reference/jpa/aot.html)
- [Spring Framework 6.x Upgrade Guide — Hibernate requirement for native image](https://github.com/spring-projects/spring-framework/wiki/Upgrading-to-Spring-Framework-6.x)
- [Hibernate ORM — Proxies and Lazy Fetching](https://docs.hibernate.org/stable/core/introduction/html_single/#proxies-and-lazy-fetching)
- [Hibernate ORM — Bytecode Enhancer](https://docs.hibernate.org/stable/core/introduction/html_single/#using-the-bytecode-enhancer)
- [Hibernate ORM — Entity Proxy User Guide](https://docs.hibernate.org/orm/6.6/userguide/html_single/#entity-proxy)
- [Hibernate ORM — Integration Modules](https://docs.hibernate.org/stable/orm/quickstart/html_single/)
- [GraalVM Native Image — Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/)

