# Handling Missing References and Provider Lazy-Loading Limitations in Spring Data JPA

In JPA, a relationship property can point to an entity that does not exist in the database, or it can be a reference whose state has not been fully loaded yet. These two situations are often confused:

- **Missing reference:** a foreign key holds a value with no corresponding row in the referenced table, or the application requests an ID that does not exist in the database.
- **Unloaded (lazy) reference:** the target entity may exist, but the JPA provider only holds a proxy/indirection and loads state when the application accesses properties.

Understanding the difference helps you choose between `findById` and `getReferenceById`, handle errors at the right moment, avoid `LazyInitializationException`, and control SQL query counts. Lazy loading behavior also depends on the provider and deployment configuration, so test with the exact Hibernate or EclipseLink setup your application actually uses.

## 1. Distinguishing Non-Existent IDs, Null Foreign Keys, and Orphaned Foreign Keys

Suppose an `Order` entity references `Customer`:

~~~java
@Entity
@Table(name = "orders")
public class Order {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private Customer customer;
}
~~~

There are three distinct states:

1. `customer_id IS NULL`: the order has no customer. If the relationship is optional, the `customer` property can be `null`.
2. `customer_id = 25` and the `customers` table has ID 25: valid reference. The entity may be loaded eagerly or lazily.
3. `customer_id = 25` but the `customers` table does not have ID 25: this is an orphaned foreign key (broken/orphan reference).

If the database has foreign key constraints enabled and data is written through constraint-enforcing paths, the third case is blocked by the database. Orphaned data usually appears when legacy tables lack FKs, constraints were previously disabled, data was imported directly, or another system wrote data without enforcing referential integrity.

Do not use the phrase "does not exist" for all three states. `null` may be valid per business rules; an orphaned foreign key is a data integrity error; a non-existent ID passed by a user is an application-layer scenario to handle.

## 2. How Do findById and getReferenceById Differ?

Spring Data JPA provides two ways to retrieve an entity by ID for different purposes.

### 2.1. findById — Checking Existence and Retrieving Data

~~~java
Optional<Customer> optional = customerRepository.findById(customerId);

if (optional.isEmpty()) {
    throw new CustomerNotFoundException(customerId);
}

Customer customer = optional.get();
~~~

`findById` returns `Optional<T>`. If no record exists, the result is `Optional.empty()`. This is the right choice when an ID comes from a request or user and the application must clearly report that the object does not exist.

Service example:

~~~java
@Service
public class OrderService {

    private final CustomerRepository customers;
    private final OrderRepository orders;

    public OrderService(
            CustomerRepository customers,
            OrderRepository orders) {
        this.customers = customers;
        this.orders = orders;
    }

    @Transactional
    public Long createOrder(Long customerId) {
        Customer customer = customers.findById(customerId)
                .orElseThrow(() ->
                        new CustomerNotFoundException(customerId));

        Order order = new Order(customer);
        return orders.save(order).getId();
    }
}
~~~

In this example, the service verifies the customer exists before creating the order. If this is an HTTP API, the business exception can be mapped to HTTP 404 via an exception handler.

### 2.2. getReferenceById — Obtaining a Reference Without Reading State Yet

~~~java
Customer customer =
        customerRepository.getReferenceById(customerId);
~~~

`getReferenceById` returns a JPA reference to the entity with that ID. The provider may return a proxy or an enhanced object without querying the full entity state. This is useful when you only need to assign a relationship to an entity known to exist.

Example:

~~~java
@Transactional
public Long createOrderUsingReference(Long customerId) {
    Customer customer =
            customers.getReferenceById(customerId);

    Order order = new Order(customer);
    return orders.save(order).getId();
}
~~~

If the provider supports proxies, the application can create an order using the customer ID without loading the customer's name, email, or other attributes. However, `getReferenceById` **is not an ID existence check method**.

Per the JPA contract, an error for a non-existent reference may be detected when the reference's state is accessed. Some providers may reject an invalid ID immediately when creating the reference. Spring Data JPA also notes that when the exception is thrown depends on the provider.

### 2.3. Quick Comparison

| Criterion | findById(id) | getReferenceById(id) |
|---|---|---|
| Return value | `Optional<T>` | Reference `T` |
| Purpose | Look up and handle missing record cases | Reference an entity assumed to exist |
| Can read state immediately? | Yes, the found entity is returned | Not necessarily; may be a proxy/uninitialized |
| Non-existent ID | Returns `Optional.empty()` | May fail immediately or when the reference is initialized |
| Use to validate request ID? | Suitable | Not suitable |
| Use to assign FK when ID is known valid? | Possible, but loads entity | Can avoid loading entity state |

`getReferenceById` was introduced in Spring Data JPA 2.7. The older APIs `getOne` and `getById` are deprecated in newer Spring Data JPA versions; when using a version with `getReferenceById`, prefer this method name.

### 2.4. Do Not Use existsById Followed by getReferenceById to Check

The following pattern is usually unnecessary:

~~~java
if (!customers.existsById(customerId)) {
    throw new CustomerNotFoundException(customerId);
}

Customer customer = customers.getReferenceById(customerId);
~~~

It can cause two database round-trips and still leaves a time window between check and use where data could change (race condition). If you need data or a 404 response, call `findById` once. If you only need a reference and the database guarantees the FK, use `getReferenceById` and let constraints protect integrity on write.

## 3. Handling Missing References Properly

### 3.1. Using Foreign Keys to Protect Data

Database design should include an FK constraint for required relationships:

~~~sql
alter table orders
add constraint fk_orders_customer
foreign key (customer_id)
references customers(id);
~~~

If every order must have a customer, the column can be declared `NOT NULL`:

~~~sql
customer_id bigint not null
~~~

`NOT NULL` and FK constraints solve two different problems:

- `NOT NULL` forbids empty foreign key values.
- FK ensures the foreign key value points to a real row.

In the entity, this can be expressed as:

~~~java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "customer_id", nullable = false)
private Customer customer;
~~~

`optional = false` indicates the relationship cannot be null in the JPA model; `nullable = false` helps describe the column during schema generation. Actual database constraints still need to be created and maintained via migrations. Annotations do not automatically alter an existing schema if the project does not use the corresponding schema generation mechanism.

### 3.2. Validating IDs from Requests

When a user sends `customerId`, you typically need to validate it before running business logic:

~~~java
@Transactional
public Long createOrder(CreateOrderRequest request) {
    Customer customer = customerRepository.findById(request.customerId())
            .orElseThrow(() ->
                    new CustomerNotFoundException(request.customerId()));

    Order order = new Order(customer);
    return orderRepository.save(order).getId();
}
~~~

This approach lets you return a clear business error and does not depend on when the provider initializes a proxy.

Do not catch `EntityNotFoundException` as a replacement for all validation steps. That exception typically reflects a requested JPA reference whose corresponding state could not be found; it is not the best way to express every request validation failure.

### 3.3. Assigning References When the ID Is Already Trusted

If an ID comes from a validated internal workflow or a managed entity, `getReferenceById` can be used to assign the relationship:

~~~java
@Transactional
public void assignCustomer(Long orderId, Long customerId) {
    Order order = orderRepository.findById(orderId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));

    Customer customer = customerRepository.getReferenceById(customerId);
    order.setCustomer(customer);
}
~~~

If you only assign the relationship without reading the customer's properties, Hibernate can use the proxy's ID when writing the FK. If the ID does not exist and the database has an FK, the INSERT/UPDATE fails when the constraint is checked, typically at flush or commit. The provider may also detect it earlier if the reference is initialized.

Clearly define where database errors are caught and translated into appropriate business errors. Do not treat obtaining a proxy as proof that the ID is valid.

### 3.4. Handling Legacy Data with Orphaned Foreign Keys

If a legacy system lacks FKs and contains values referencing deleted rows, prioritize:

1. Auditing and finding foreign keys without target rows.
2. Defining business rules: clear the link, restore parent data, or map to a fallback state.
3. Cleaning the data.
4. Adding FKs once data is valid.
5. Keeping integration tests to prevent orphaned data from reappearing.

You can find orphaned data with SQL:

~~~sql
select o.id, o.customer_id
from orders o
left join customers c on c.id = o.customer_id
where o.customer_id is not null
  and c.id is null;
~~~

This query is just an example for the `orders.customer_id` relationship. Adjust table names, columns, and conditions to match your actual schema.

### 3.5. Hibernate's @NotFound for Data Without FKs

Hibernate provides its own `@NotFound` annotation to handle relationships where the database does not guarantee a physical foreign key:

~~~java
import org.hibernate.annotations.NotFound;
import org.hibernate.annotations.NotFoundAction;

@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "legacy_customer_id")
@NotFound(action = NotFoundAction.IGNORE)
private Customer customer;
~~~

Two options:

- `NotFoundAction.EXCEPTION` (default): Hibernate throws an error when it detects a foreign key pointing to a non-existent row; modern Hibernate uses `FetchNotFoundException` for this case.
- `NotFoundAction.IGNORE`: Hibernate treats the invalid association as `null`.

There is an important consequence: `@ManyToOne` and `@OneToOne` relationships with `@NotFound` are always loaded eagerly by Hibernate, even if the relationship annotation specifies `fetch = FetchType.LAZY`. Hibernate needs to check the reference state to apply the policy when the target row does not exist.

`@NotFound` is a Hibernate-specific feature, not a standard Jakarta Persistence annotation. Do not use it as a substitute for FKs in new schemas. With `IGNORE`, the underlying data still contains orphaned foreign keys; the mapping merely changes how the application sees the relationship.

## 4. How Does Lazy Loading Work?

Lazy loading defers reading related data until the application needs to access it. Example:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "customer_id")
private Customer customer;

@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLine> lines = new ArrayList<>();
~~~

When loading an `Order`, the provider may read only the order's data. `customer` and `lines` are represented by a proxy or indirection object; when code accesses the relationship, the provider issues additional queries.

### 4.1. Jakarta Persistence Rules

In Jakarta Persistence 3.1, the key defaults are:

| Mapping | Default Fetch |
|---|---|
| `@ManyToOne` | `FetchType.EAGER` |
| `@OneToOne` | `FetchType.EAGER` |
| `@OneToMany` | `FetchType.LAZY` |
| `@ManyToMany` | `FetchType.LAZY` |
| `@ElementCollection` | `FetchType.LAZY` |
| `@Basic` | `FetchType.EAGER` |

`FetchType.EAGER` is a requirement for the provider: data must be loaded eagerly. `FetchType.LAZY` is only a hint; the provider is allowed to load data earlier than requested by the application. Thus, `fetch = FetchType.LAZY` is not a guarantee that no SQL runs before a getter is called.

For ToOne relationships, explicitly declare `LAZY` if business logic does not always need the related entity:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;

@OneToOne(fetch = FetchType.LAZY)
private Invoice invoice;
~~~

Then proactively request fetching needed relationships in each query. This reduces unnecessary data loading caused by ToOne's `EAGER` default.

### 4.2. LAZY Is Not Synonymous with JOIN

`LAZY` describes when data is loaded, not which SQL form the provider must use. The provider may:

- Load the root entity and then load the relationship with a separate SELECT when the proxy is initialized.
- Group multiple references into a batch query.
- Use bytecode enhancement or indirection to track unloaded properties.
- Load eagerly early if required by mapping, query, or provider.

Similarly, `EAGER` does not guarantee the provider will generate a single SQL JOIN. A query returning multiple entities with eager relationships without an appropriate fetch join can still issue separate SELECTs.

Therefore, observe actual SQL and design per-use-case fetch plans rather than deducing SQL query counts solely from annotations.

## 5. Lazy-Loading Limitations by JPA Provider

JPA defines the common contract, while the mechanism implementing lazy loading depends on the provider. Two common providers with different mechanisms are Hibernate and EclipseLink.

### 5.1. Hibernate

Hibernate typically uses:

- **Proxies for ToOne relationships:** a placeholder object holding the target entity's ID; when unloaded state is accessed, the proxy is initialized via SQL.
- **Persistent collection wrappers for ToMany:** collections managed by Hibernate that can load elements when iterated or accessed.
- **Bytecode enhancement:** supports lazy attribute loading and certain relationship cases requiring finer-grained attribute state tracking.

Practical limitations:

1. **Entities must be proxyable when using traditional subclass proxies.** Final classes or final methods can restrict proxy generation; bytecode enhancement uses a different mechanism but requires appropriate build/runtime configuration.
2. **Inverse One-to-One relationships can be hard to keep lazy.** The provider needs to know whether a record exists on the other side to distinguish null from a proxy; some mappings may require an eager query. Enhancement and mapping configuration affect how this is handled.
3. **Accessing a proxy after Session closes fails.** Hibernate typically throws `LazyInitializationException` when data needs to be loaded without an active persistence context.
4. **`@NotFound` forces ToOne to be eager.** This is an important exception when a system must tolerate orphaned foreign keys.
5. **N+1 queries can still happen.** A query fetching many orders followed by reading `order.getCustomer().getName()` for each can trigger an extra SELECT per customer.

Hibernate can mitigate N+1 using batch fetching. Example:

~~~java
import org.hibernate.annotations.BatchSize;

@Entity
@BatchSize(size = 32)
public class Customer {
    // entity fields
}
~~~

Or global configuration:

~~~properties
spring.jpa.properties.hibernate.default_batch_fetch_size=32
~~~

When multiple proxies or collections need initialization, Hibernate can batch the IDs into a single query. This is a Hibernate-specific feature; batch sizes should be measured against real workloads rather than set arbitrarily high.

### 5.2. EclipseLink

EclipseLink uses an *indirection* mechanism to defer loading relationships. For ToMany collections, the provider can use transparent indirection so the application works with the collection normally while data is loaded on demand.

For ToOne relationships (`@OneToOne` and `@ManyToOne`), lazy loading capability depends on weaving:

- **Dynamic weaving:** EclipseLink transforms bytecode as classes are loaded. In Java SE, this typically requires an agent or an integrated environment allowing weaving.
- **Static weaving:** bytecode is processed prior to runtime, useful when an agent cannot be attached at JVM startup.
- If weaving is disabled or unavailable, lazy ToOne may not behave as expected and the relationship may be loaded eagerly.

EclipseLink provides the `eclipselink.weaving.lazy` property to enable/disable lazy ToOne weaving; this property only takes effect when weaving is properly configured (`true` or `static`).

Persistence unit configuration example:

~~~xml
<property name="eclipselink.weaving" value="true"/>
<property name="eclipselink.weaving.lazy" value="true"/>
~~~

In Java SE environments, verify the actual runtime setup and agent/static weaving configuration. Do not copy these settings into Hibernate, as they are EclipseLink-specific properties.

### 5.3. Practical Comparison

| Aspect | Portable JPA | Hibernate | EclipseLink |
|---|---|---|---|
| Is LAZY an absolute guarantee? | No, only a hint | Can use proxies/enhancement, still subject to mapping and fetch plan | Can use indirection/weaving; depends on configuration |
| Lazy ToOne | Provider may load eagerly | Typically uses proxies or enhancement | Java SE requires weaving for lazy ToOne |
| Lazy ToMany | Defaults to LAZY | Persistent collection wrapper | Transparent indirection |
| Access after persistence context closes | Loading not guaranteed; error depends on provider | Typically `LazyInitializationException` | Provider may throw indirection/detached errors |
| Handling orphaned FKs via dedicated annotation | No equivalent standard annotation | `@NotFound`; ToOne becomes eager | Requires custom strategy, no Hibernate annotation |
| Batch fetching | No single standardized annotation | Has `@BatchSize` and batch settings | Has its own batch/indirection mechanisms |

Do not conclude which provider has "better lazy loading" solely from a feature table. Outcomes depend on mappings, provider versions, bytecode enhancement/weaving, transaction boundaries, databases, and query styles. Test on the exact provider packaged in your application.

## 6. Lazy Loading and Persistence Context Lifecycle

A proxy can only load data while the provider still has an active persistence context/session. If the entity is detached or the `EntityManager` is closed, accessing an uninitialized lazy property can fail.

Error-prone example:

~~~java
public Order getOrder(Long id) {
    return orderRepository.findById(id).orElseThrow();
}

// EntityManager/transaction is already closed when the caller runs:
String customerName = getOrder(10L).getCustomer().getName();
~~~

In this example, the service returns an entity outside the transaction. If `customer` has not been loaded yet, the caller may no longer be able to initialize the proxy.

### 6.1. Loading Necessary Data Inside the Transaction

A safe approach is building a DTO inside the service while the transaction is still open:

~~~java
public record OrderSummary(
        Long id,
        String customerName) {
}

@Service
public class OrderQueryService {

    private final OrderRepository orders;

    public OrderQueryService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(readOnly = true)
    public OrderSummary getSummary(Long id) {
        Order order = orders.findById(id)
                .orElseThrow(() -> new OrderNotFoundException(id));

        String customerName = order.getCustomer().getName();

        return new OrderSummary(order.getId(), customerName);
    }
}
~~~

The service reads the required attributes while the persistence context is open and returns data already converted into a DTO. Controllers/serializers do not have to initialize proxies.

### 6.2. Open Session in View Does Not Replace a Fetch Plan

In web applications, Open Session in View (OSIV) can keep the persistence context open while rendering the response. This sometimes masks cases where a service returns entities without having loaded enough data.

If a serializer accesses lazy relationships, SQL can be triggered while generating JSON. The consequence is hidden database queries in the presentation layer, prone to N+1 queries and unpredictable latency.

You can explicitly disable OSIV:

~~~properties
spring.jpa.open-in-view=false
~~~

When disabled, services must load needed attributes inside transactions and map them to DTOs. This keeps data access boundaries clearer. If a project keeps OSIV enabled, avoid relying on it to load relationships haphazardly inside serializers.

## 7. Choosing a Fetch Plan per Use Case

You do not need to change every relationship to EAGER to avoid lazy errors. Keep sensible mappings and select what to load per query.

### 7.1. EntityGraph

Spring Data JPA supports `@EntityGraph` to specify relationships to load for a repository method:

~~~java
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    @EntityGraph(attributePaths = "customer")
    Optional<Order> findWithCustomerById(Long id);
}
~~~

When calling this method, the query requests loading `customer` along with the order. `EntityGraph` can be declared on the method or reference a named entity graph on the entity.

`EntityGraph` keeps the fetch plan close to the query/use case. It does not force the provider to use a single SQL shape; the provider chooses a loading strategy matching the mapping and its capabilities.

### 7.2. JOIN FETCH

With JPQL, you can explicitly request a fetch join:

~~~java
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    @Query("""
           select o
           from Order o
           left join fetch o.customer
           where o.id = :id
           """)
    Optional<Order> findWithCustomer(@Param("id") Long id);
}
~~~

`LEFT JOIN FETCH` preserves the order even when the customer relationship is optional and has no value. If the relationship is mandatory, `JOIN FETCH` can be used.

Fetch join fits when a specific query needs a relationship. Do not mechanically add multiple collection fetch joins, because joining multiple collections can multiply result rows and load excessive data.

### 7.3. DTO Projections

If a screen needs only a few fields, projections can be more efficient than loading the entire entity graph:

~~~java
public record OrderRow(
        Long orderId,
        String customerName) {
}

@Query("""
       select new com.example.store.OrderRow(
           o.id,
           c.name
       )
       from Order o
       join o.customer c
       where o.status = :status
       """)
List<OrderRow> findRowsByStatus(
        @Param("status") OrderStatus status);
~~~

This is an example of a DTO projection using a JPQL constructor expression. The package name and constructor must match the actual DTO. The result contains only the needed columns, independent of a serializer initializing lazy relationships.

### 7.4. Be Careful When Paginating Collection Fetch Joins

Fetch-joining a ToOne relationship is usually more predictable than fetch-joining a ToMany collection. When combining a collection fetch join with `Pageable`, one order with multiple lines can appear as multiple SQL rows. That makes root-entity pagination complex.

Common approaches:

- Paginate root entity IDs first, then query to fetch related data for that ID set.
- Use DTO projections to retrieve only the needed data.
- Split the count query and content query.
- Check SQL logs and Hibernate warnings about paginating collection fetches.

Do not assume `Pageable` combined with a collection fetch join always produces accurate and efficient SQL pagination.

## 8. N+1 Queries and Diagnostics

Suppose a query loads 50 orders:

~~~java
List<Order> orders = orderRepository.findAll();

for (Order order : orders) {
    System.out.println(order.getCustomer().getName());
}
~~~

If each `customer` is a separate uninitialized proxy, Hibernate may execute:

- 1 SELECT to load the list of orders.
- Up to 50 SELECTs to load customers.

That is the N+1 problem. The actual SQL count may be lower if the persistence context or cache already holds the entity, or the provider uses batch fetching; do not rely on that assumption during design.

Solutions:

1. Use `EntityGraph` or fetch join if the use case always needs the customer.
2. Use DTO projections if only order ID and customer name are needed.
3. With Hibernate, consider `@BatchSize` or `hibernate.default_batch_fetch_size` when accessing many proxies/collections.
4. Use `PersistenceUnitUtil.isLoaded(entity, "customer")` to check whether an attribute has been loaded via the standard JPA API.
5. Enable SQL logging in test environments and measure query counts, execution time, and returned data.

Do not switch all relationships to EAGER to cure N+1. EAGER can cause other queries to load extra data or still generate N+1 through secondary SELECTs.

## 9. Testing Missing References

### 9.1. findById Returning Empty

This behavior can be tested directly and reliably:

~~~java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository customers;

    @Test
    void returnsEmptyWhenCustomerDoesNotExist() {
        assertThat(customers.findById(999999L)).isEmpty();
    }
}
~~~

The test database must be initialized in a state without the tested ID. If the test uses fixture data, choose an ID guaranteed not to exist in the fixtures.

### 9.2. Testing getReference with a Non-Existent ID

`EntityManager.getReference` and Spring Data `getReferenceById` can defer checking until the reference is initialized. The provider is also permitted to detect the error earlier.

Illustrative example:

~~~java
@Test
void missingReferenceFailsWhenProviderChecksIt() {
    assertThatThrownBy(() -> {
        Customer reference =
                entityManager.getReference(Customer.class, 999999L);

        reference.getName();
    }).isInstanceOf(EntityNotFoundException.class);
}
~~~

This is a common expectation across JPA providers, but exact timing and exception types must be verified against your project's provider/version. When using a Spring repository proxy, exceptions thrown immediately inside a repository call may also pass through Spring's exception translation. Write tests according to the exception contract your application exposes, rather than relying on a single proxy initialization moment.

### 9.3. Testing Lazy Loading and Detached Entities

You can check whether an attribute is loaded using the JPA API:

~~~java
PersistenceUnitUtil util =
        entityManagerFactory.getPersistenceUnitUtil();

Order order = entityManager.find(Order.class, orderId);

boolean loaded =
        util.isLoaded(order, "customer");
~~~

The result depends on the query's fetch plan and the provider. If you want to verify a query does not load `customer` immediately, inspect both loaded status and SQL logs; a provider is allowed to load eagerly even if the mapping requests LAZY.

For tests after closing the persistence context, confirm the association is uninitialized before detaching/closing. Then access the association to observe the provider's exception. Hibernate typically throws `LazyInitializationException`; do not assume every provider uses the exact same exception class.

## 10. Application Handling Checklist

- [ ] Distinguish null FKs, orphaned FKs, and non-existent request IDs.
- [ ] Use `findById` when you need to confirm a record and return a clear business error.
- [ ] Use `getReferenceById` when you only need a reference to an already-trusted ID.
- [ ] Have physical foreign keys for relationships requiring data integrity.
- [ ] Do not use `existsById` followed by `getReferenceById` as a double check.
- [ ] Understand `FetchType.LAZY` is a hint and `FetchType.EAGER` is a requirement in JPA.
- [ ] Check provider/version and proxy, enhancement, or weaving configuration.
- [ ] Do not access unloaded associations after the persistence context closes.
- [ ] Choose `EntityGraph`, fetch join, or DTO projection per use case.
- [ ] Measure SQL to catch N+1 and unintended eager queries.
- [ ] Only use `@NotFound` when you genuinely must support legacy data without FKs and accept Hibernate's eager side effect.
- [ ] Have tests for non-existent IDs, valid FKs, lazy associations, and fetch-plan queries.

## 11. References

- [Jakarta Persistence 3.1 Specification](https://jakarta.ee/specifications/persistence/3.1/jakarta-persistence-spec-3.1.pdf) — defines `FetchType`, `EntityManager.getReference`, associations, and persistence context lifecycle.
- [Spring Data JPA — JpaRepository Javadoc](https://docs.spring.io/spring-data/jpa/docs/current/api/org/springframework/data/jpa/repository/JpaRepository.html) — `findById`, `getReferenceById`, and repository APIs.
- [Hibernate ORM 6.2 User Guide](https://docs.hibernate.org/orm/6.2/userguide/html_single/) — proxies, lazy fetching, `@NotFound`, and batch fetching.
- [EclipseLink 4.0 — Understanding EclipseLink](https://eclipse.dev/eclipselink/documentation/4.0/concepts/concepts.html) — indirection and weaving.
- [EclipseLink 4.0 — JPA Extensions Reference](https://eclipse.dev/eclipselink/documentation/4.0/jpa/extensions/jpa-extensions.html) — the `eclipselink.weaving.lazy` property.

The core point is determining clearly whether the application needs an existence check or only a reference, then choosing a fetch plan aligned with transactions and the provider. Using FKs to protect data integrity, loading associations within service boundaries, and testing with the exact provider avoids late reference failures, post-detach lazy loading errors, and N+1 queries.