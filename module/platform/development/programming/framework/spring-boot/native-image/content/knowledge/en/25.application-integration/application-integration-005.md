# Spring Data Repositories and Data Model Type Information

## 1. Why Repositories and Domain Types Must Be Reviewed for Native Builds

Spring Data helps Spring Boot applications access data through repository interfaces, domain models, and abstractions such as `CrudRepository`, `JpaRepository`, or `MongoRepository`. On the JVM, Spring Data and persistence providers may rely on metadata, reflection, proxies, and introspection mechanisms to create repository implementations, map entities, invoke constructors, read/write properties, or convert data types.

GraalVM Native Image analyzes the reachable set of classes at build time. Dynamic access paths used by the framework or persistence provider must be adequately described by Spring AOT, Spring Data AOT, or dependency reachability metadata. Therefore, a repository that works on the JVM does not by itself prove that all queries, entity mappings, and projections work in the native executable.

In the **SPRING_BOOT_NATIVE_IMAGE** module, three interconnected parts must be understood:

- **Repository metadata:** repository interfaces, domain types, identifier types, query methods, and repository configuration.
- **Domain model type information:** constructors, properties, identifiers, associations, projections, generic types, and conversion metadata.
- **Persistence integration:** JPA/Hibernate, Spring Data JDBC, MongoDB, or other Spring Data modules, each with its own mapping rules and runtime requirements.

This lesson focuses on declaring models/repositories clearly, leveraging built-in AOT support, identifying remaining dynamic access paths, and testing them on the native executable.

## 2. Repository Interfaces Describe the Data Access Contract

Spring Data JPA example:

```java
public interface OrderRepository
        extends JpaRepository<Order, UUID> {

    Optional<Order> findByOrderNumber(String orderNumber);

    List<Order> findByStatusAndCreatedAtAfter(
            OrderStatus status, Instant createdAfter);
}
```

The interface declares:

- Domain type: `Order`.
- Identifier type: `UUID`.
- CRUD operations inherited from `JpaRepository`.
- Query methods parsed by Spring Data from method names.

Spring Data generates the repository implementation/proxy using the repository infrastructure. Applications typically inject the interface into a service:

```java
@Service
class OrderQueryService {

    private final OrderRepository orders;

    OrderQueryService(OrderRepository orders) {
        this.orders = orders;
    }

    Optional<Order> find(String number) {
        return orders.findByOrderNumber(number);
    }
}
```

Do not write manual implementations for repositories solely to make a native build pass. First verify that the Spring Boot/Spring Data versions and persistence module in use have corresponding AOT/native support. The framework may already supply the necessary contributions and metadata.

## 3. What Information Do Repository Generic Types Carry?

Spring Data repositories typically declare domain and identifier types via generic parameters:

```java
JpaRepository<Order, UUID>
```

The two parameters mean:

- `Order`: the entity/domain object type that the repository reads and writes.
- `UUID`: the entity's identifier type.

Spring Data uses this information to determine mapping metadata, CRUD operations, and identifier conversions. Using raw types or overly complex generic wrappers makes it harder for the framework to infer the required type information.

Declare concrete repositories:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
```

Avoid raw repositories:

```java
@SuppressWarnings("rawtypes")
interface GenericRepository extends JpaRepository {
}
```

Raw types lose compile-time information, reduce type safety, and make inferring domain/ID types harder. When building a generic base repository for multiple aggregates, keep the generic signature clear and verify repository scanning/AOT in your Spring Data version.

## 4. Domain Models and Constructors Used to Instantiate Entities

Spring Data must instantiate objects when reading data. Depending on the persistence module and mapping strategy, the framework may use constructors, persistence constructors, property accessors, or provider-specific mechanisms.

JPA entity example:

```java
@Entity
@Table(name = "orders")
public class Order {

    @Id
    private UUID id;

    @Column(nullable = false, unique = true)
    private String orderNumber;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    protected Order() {
        // Constructor for JPA per the entity model requirements
    }

    public Order(String orderNumber, OrderStatus status) {
        this.id = UUID.randomUUID();
        this.orderNumber = orderNumber;
        this.status = status;
    }

    public UUID getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public OrderStatus getStatus() {
        return status;
    }
}
```

With JPA, entities must satisfy Jakarta Persistence requirements regarding constructors and entity classes; details also depend on the mapping access strategy. Do not assume every Spring Data module instantiates objects using the same rules as JPA.

With Spring Data JDBC or MongoDB, Spring Data mapping infrastructure can use an appropriate constructor, including an annotated constructor. Follow the rules of the module in use rather than copying JPA entities across modules.

## 5. Persistence Constructors and @PersistenceCreator

Spring Data Commons provides `@PersistenceCreator` to explicitly designate which constructor or factory method should be used when materializing an object from stored data when multiple candidates exist.

Immutable model example:

```java
public class Customer {

    private final Long id;
    private final String email;
    private final String displayName;

    @PersistenceCreator
    public Customer(
            Long id,
            String email,
            String displayName) {
        this.id = id;
        this.email = email;
        this.displayName = displayName;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getDisplayName() {
        return displayName;
    }
}
```

This annotation belongs to the `org.springframework.data.annotation` package. It helps Spring Data determine constructor mapping. It is not a `RuntimeHints` declaration and does not automatically register the constructor for arbitrary reflection/JNI use cases.

For JPA entities, satisfy the JPA provider's requirements first; do not use `@PersistenceCreator` to replace a required no-arg constructor if the provider mandates one. For JDBC/MongoDB mapping, persistence creators play a more central role in Spring Data's materialization process.

## 6. Property Names and Access Strategies

Spring Data mapping must know how to associate columns/document fields with domain object properties. Example:

```java
@Table("customers")
public class CustomerRecord {

    @Id
    private Long id;

    @Column("email_address")
    private String email;

    // constructor/accessors
}
```

With Spring Data JDBC, mapping annotations and naming strategies determine how properties correspond to columns. With JPA, `@Column`, `@Access`, and annotation placement on fields/properties affect the access strategy. With MongoDB, `@Field` and the mapping context determine document field names.

Do not mix annotations across modules without understanding their semantics. `jakarta.persistence.Column` and `org.springframework.data.relational.core.mapping.Column` are two different annotations intended for different persistence models.

In Native Image, the framework needs sufficient type/property metadata for mapping. Spring Data AOT and provider integrations handle most standard cases; custom accessors or reflection-based property discovery should be tested specifically.

## 7. Query Derivation and Declared Queries

Spring Data can derive queries from method names:

```java
List<Order> findByStatusAndCreatedAtAfter(
        OrderStatus status, Instant time);
```

Or declared queries:

```java
@Query("""
       select o from Order o
       where o.customerId = :customerId
       order by o.createdAt desc
       """)
List<Order> findRecentByCustomer(
        @Param("customerId") UUID customerId);
```

Query derivation is parsed from repository method metadata. Query annotations are processed by the corresponding Spring Data module. Native compatibility also depends on the query parser, persistence provider, mapping metadata, and type conversion.

If a query references a wrong property name, the issue is typically a query/model mismatch rather than Native Image. Before adding hints, run repository integration tests on the JVM and verify that the generated query is valid.

## 8. Projections and DTO Queries

Spring Data projections can use interfaces or classes/records to return a subset of data:

```java
public interface OrderSummary {
    UUID getId();
    String getOrderNumber();
    OrderStatus getStatus();
}
```

Interface projections may be implemented via proxies or mapping mechanisms depending on the module/query. DTO projections can use constructors:

```java
public record OrderSummaryDto(
        UUID id,
        String orderNumber,
        OrderStatus status) {
}
```

When using projections in native, test the exact production path. If an interface projection creates a proxy, confirm that Spring Data AOT/the provider handled proxy metadata. If a DTO projection requires constructor mapping, verify constructor and parameter metadata in the way the framework actually uses it.

Do not assume every interface projection requires manually registering JDK proxy hints. Spring Data may supply the appropriate metadata automatically; add hints only when there is evidence of a gap and identify the exact interface combination.

## 9. Associations and Nested Types

Entities may contain associations or nested objects:

```java
@Entity
class OrderLine {

    @Id
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Order order;

    private String sku;
    private int quantity;
}
```

With JPA, associations can use provider proxies/lazy loading. Native compatibility requires reviewing the Hibernate version, enhancement/proxy strategy, entity metadata, and how the application accesses associations.

With Spring Data JDBC, aggregate references have different semantics than JPA associations; JDBC does not use lazy-loading proxies like Hibernate in the same way. With MongoDB, nested document mapping follows yet another set of rules.

When investigating native issues, identify the exact module and provider. A Hibernate lazy-proxy error should not be treated by applying guidance meant for Spring Data JDBC.

## 10. Spring Data AOT and Repository Infrastructure

Spring Data and Spring Boot provide AOT support to prepare metadata needed for repositories and mapping. The level of support depends on the Spring Boot, Spring Data module, provider, and version.

In the AOT pipeline, the framework can analyze repository configuration and contribute metadata/generated initialization for supported components. This reduces reliance on dynamic scanning/discovery when the native process runs.

Verify in the project:

- Are repository interfaces discovered by repository scanning?
- Is the right Spring Data module enabled?
- Are domain types and identifier types unambiguous?
- Are query methods parsed/validated?
- Is entity mapping metadata prepared properly?
- Does the provider version support Native Image?
- Do custom converters, projections, or repository fragments need extra metadata?

Do not assume that because application AOT succeeded, every repository has been verified. You must execute real queries and mappings on the native executable.

## 11. Repository Fragments and Custom Implementations

Spring Data allows adding repository fragments:

```java
public interface OrderSearch {
    List<Order> search(OrderCriteria criteria);
}

class OrderSearchImpl implements OrderSearch {

    @Override
    public List<Order> search(OrderCriteria criteria) {
        // Custom implementation
        return List.of();
    }
}

public interface OrderRepository
        extends JpaRepository<Order, UUID>, OrderSearch {
}
```

Custom fragments are application code and may contain custom dynamic logic. If the implementation uses reflection, resources, proxies, or external libraries, the corresponding native requirements still need to be checked.

Follow the naming/registration convention required by your Spring Data version. If a fragment is not detected, check repository configuration and naming/scanning first; do not immediately conclude hints are missing.

## 12. Custom Converters and Type Conversion

Spring Data mapping can use converters to translate types between the domain model and store representation. Spring Data MongoDB example:

```java
@WritingConverter
class MoneyWriteConverter
        implements Converter<Money, Document> {

    @Override
    public Document convert(Money source) {
        return new Document()
                .append("amount", source.amount())
                .append("currency", source.currency());
    }
}
```

This example is illustrative; source/target types and registration depend on the store module. Converters are usually beans or registered through the module's custom conversions.

In native, test converters bidirectionally if the application reads and writes data. If a converter uses reflection to read fields, load classes by name, or instantiate objects dynamically, identify the necessary metadata. Pure converters calling known accessors/constructors are generally easier to analyze.

Do not use converters just to mask mapping annotation errors. Keep domain types and store types clear, and test old/new data as well as null semantics.

## 13. Identifier Types and Custom ID Conversion

Identifiers can be `Long`, `UUID`, `String`, or a value object type. Example:

```java
public record OrderId(UUID value) {
}
```

If a repository uses a value object as an ID, determine whether the Spring Data module/provider supports mapping/conversion directly or requires a converter. The ID type must be compatible with the store representation and query parameter binding.

Test these cases:

- Creating a new entity and generating an ID.
- Reading an entity by ID.
- Query methods accepting an ID.
- Serializing/deserializing the ID over APIs.
- Mapping the ID between domain and database.
- Null/invalid IDs and conversion failures.

Native Image does not change the semantics of `UUID` or `Long`, but custom converters/type metadata may flow through framework infrastructure. Test on native if the ID relies on constructors/reflection or custom conversion.

## 14. Repository Bootstrap and Profiles

Repository scanning can be configured via `@EnableJpaRepositories`, `@EnableJdbcRepositories`, or Spring Boot auto-configuration. Profiles/conditions can determine which repository infrastructure, `DataSource`, and provider beans are created.

Example:

```java
@Configuration(proxyBeanMethods = false)
@EnableJpaRepositories(
        basePackageClasses = OrderRepository.class)
class JpaRepositoryConfiguration {
}
```

When using explicit repository configuration, ensure packages/types are included in the AOT `ApplicationContext`. If the application uses multiple store modules simultaneously, explicitly configure which repository belongs to which module to avoid ambiguity.

Structural properties/profiles used to determine repository infrastructure must be fixed when Spring AOT analyzes the context. Runtime URLs/credentials can vary as long as the bean graph remains stable and the datasource/client supports runtime configuration.

## 15. Reflection Hints: Add Only When Not Already Covered by the Framework

If a custom mapping path uses reflection outside default support, you can register `RuntimeHints` for known types/members:

```java
final class DomainMappingHints
        implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.reflection().registerType(
                ExternalPayload.class,
                MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS,
                MemberCategory.INVOKE_PUBLIC_METHODS
        );
    }
}
```

Attach the registrar:

```java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(DomainMappingHints.class)
class DomainNativeConfiguration {
}
```

This is an example for a custom reflection path. Do not blindly add hints for every JPA entity or repository merely because they are domain types. Spring Data, Spring Framework, and the persistence provider may already contribute metadata.

When hints are needed, register the exact constructors/methods/fields accessed. Verify with `RuntimeHintsPredicates`, then confirm AOT collected the registrar and the native runtime actually exercises that mapping path.

## 16. Testing Repositories on the JVM First

Start with repository integration tests on the JVM to confirm queries and mappings are correct:

```java
@DataJpaTest
class OrderRepositoryTest {

    @Autowired
    OrderRepository orders;

    @Test
    void findsOrderByNumber() {
        Order order = new Order(
                "ORD-1001", OrderStatus.CREATED);

        orders.save(order);

        assertThat(orders.findByOrderNumber("ORD-1001"))
                .isPresent()
                .get()
                .extracting(Order::getStatus)
                .isEqualTo(OrderStatus.CREATED);
    }
}
```

This test verifies the repository and mapping against the configured test database/provider. Add fixtures for query derivation, custom queries, projections, associations, ID conversion, and converters if used by the application.

JVM tests separate business/query errors from Native Image errors. If tests already fail on the JVM, fix mapping/queries before investigating hints.

## 17. Native Integration Tests for Repositories and Models

After JVM tests pass, select high-risk native scenarios:

- Initializing `ApplicationContext` and repository proxies.
- Persisting an entity and reading it back.
- Derived query methods and annotated queries.
- DTO/interface projections.
- Bidirectional custom converters.
- Constructor mapping for immutable models.
- Associations/lazy access if using JPA.
- Value object identifiers.
- Repository fragments/custom implementations.

You can run the native test task if supported by the plugin, or start the native application and invoke black-box endpoints. Use a compatible database/container and the same schema/fixtures as JVM tests.

Do not merely verify that repository beans exist. Invoke real methods and assert read/write results. A passing context startup does not prove entity materialization or query execution works.

## 18. Diagnosing Repository/Model Errors on Native

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Repository bean not created | Incorrect scan/configuration/profile | Check repository scanning and AOT inputs |
| Query method fails at startup | Wrong derived query/property name | Check domain properties and query parser on JVM |
| Entity fails to materialize | Incompatible constructor/property mapping | Check persistence constructor and mapping strategy |
| Projection fails on native | Missing proxy/constructor/type metadata or query returns wrong shape | Check projection implementation and native path |
| Custom converter does not run | Converter not registered with the right store module | Check custom conversions/configuration |
| Lazy association fails | Provider proxy/enhancement issue or access outside transaction | Check Hibernate/provider version and transaction boundary |
| JVM passes, native misses member | Reflection path not covered by metadata | Check provider metadata, hints, and native trace |
| Wrong ID conversion | Inconsistent converter/type mapping | Test store representation and query parameters |
| Native fails to connect to database | Driver/library/URL/credentials/runtime environment issue | Check JDBC driver, ABI, config, and container |

Do not assume every native repository error is missing reflection. Bad queries, transaction boundaries, schema mismatches, missing drivers, or unavailable datasources can also cause failures.

## 19. Evidence Matrix for Spring Data Integration

To track what has been verified, build a table tailored to the actual module:

| Capability | JVM Test | AOT/Build | Native Runtime |
|---|---|---|---|
| Repository discovery | Context/repository test | AOT processing | Repository bean created |
| Derived query | Repository test | Native build | Execute query and assert result |
| Entity constructor mapping | Persist/read test | AOT/native metadata | Materialize entity |
| Projection | Projection test | Native build | Query projection |
| Custom converter | Read/write test | Native build | Convert bidirectionally |
| Association/lazy loading | Provider integration test | Native build | Access within transaction |
| Custom repository fragment | Fragment test | AOT processing | Invoke implementation |
| ID conversion | CRUD/query test | Native build | Save/find by domain ID |

Mark `N/A` if the module does not use a capability. The table must accurately reflect the Spring Data module: do not put JPA lazy loading into a JDBC project lacking a corresponding mechanism.

## 20. Hands-On Exercise: Verifying OrderRepository on Native

**Context:** Spring Boot using Spring Data JPA, entity `Order`, `UUID` ID, query method by order number, `OrderSummary` projection, and a converter for an `OrderId` value object.

**Step 1 — Declare the domain model.** Create the entity with clear mappings, a JPA-compliant constructor, and required accessors.

**Step 2 — Declare the repository.** Use `JpaRepository<Order, UUID>`, adding the required query methods and custom queries.

**Step 3 — Add projection/converter.** Create the DTO/interface projection and ID converter if required by the module; register the converter via the proper mechanism.

**Step 4 — Write JVM repository tests.** Test save/find, query derivation, projection, ID conversion, and transaction behavior.

**Step 5 — Run Spring AOT.** Fix profiles, datasource/provider, and structural properties; confirm repository configuration is processed.

**Step 6 — Build native.** Use compatible Spring Boot/Native Build Tools versions; add `RuntimeHints` only if missing custom access is identified.

**Step 7 — Run native integration.** Using the same database schema and fixtures, invoke the repository methods and verify entities/projections materialize properly.

**Step 8 — Run container tests.** Supply the database endpoint, test credentials, and proper network; verify repository behavior on the target runtime image.

Completion criteria: repository is discovered; queries/mappings pass on the JVM; AOT/native build succeeds; the native executable performs the selected CRUD/query/projection/conversion operations; results are verified in a runtime environment equivalent to deployment.

## 21. Conclusion

Spring Data repositories and domain models supply critical metadata so Spring Data can determine how to create repositories, query stores, materialize entities, convert identifiers, and construct projections. In Spring Boot Native Image, keep generic types, constructors, property mappings, and repository configuration explicit; leverage official AOT/native support from Spring Data and the persistence provider before adding custom hints.

Test layer by layer: JVM repository tests to confirm queries/mappings, Spring AOT to confirm context/repository configuration is processed, and native integration to verify CRUD/queries/projections/converters actually work. Always distinguish the requirements of JPA, JDBC, and MongoDB; one mapping or proxy model does not apply uniformly across all Spring Data modules.
