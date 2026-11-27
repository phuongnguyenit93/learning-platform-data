# LazyInitializationException and Accessing Outside PersistenceContext

## Objectives

LazyInitializationException is a common error occurring when an application accesses a lazy entity attribute after Hibernate no longer has a Session/JPA PersistenceContext available to load that data. The error typically appears when a service returns an entity outside the transaction and a controller, mapper, serializer, or another thread reads the association.

The proper solution starts by identifying what data the use case needs and loading it within an appropriate persistence boundary. Common options include:

- Opening the transaction in the service and converting entities into DTOs before the transaction ends.
- Using JOIN FETCH or `@EntityGraph` to define a query fetch plan.
- Using DTO/interface projections to retrieve only the required data.
- Explicitly initializing an association with Hibernate.initialize() while inside the persistence context.
- Disabling Open Session in View (OSIV) if you want to catch database access outside the service early.

This lesson explains the persistence context lifecycle, lazy proxies and collections, error-inducing scenarios, distinguishing detached entities from managed entities, OSIV's impact, and runnable Java 17+ examples with Spring Boot 3.4.5, Spring Data JPA, and H2.

## 1. What is PersistenceContext?

JPA EntityManager manages a persistence context. The persistence context is a workspace tracking managed entities, their dirty state, and entity identity within a unit of work.

In Hibernate, the persistence context is backed by a Session. When an entity is loaded in a persistence context, Hibernate can:

- Track property changes and automatically flush them at transaction commit.
- Maintain a single instance for a given entity identity within the context.
- Load lazy associations when accessed if the Session is still open.
- Use snapshots/versions to perform dirty checking and optimistic locking.

An entity can be in the following states:

| State | Meaning |
| --- | --- |
| Transient | New Java object, not managed by a persistence context and usually has no corresponding row in the database. |
| Managed/Persistent | Entity currently managed by a persistence context; changes can be written to the database via dirty checking. |
| Detached | Entity that was previously managed but no longer belongs to the current persistence context. |
| Removed | Entity marked for deletion in the persistence context; the DELETE statement is synchronized on flush/commit. |

When the transaction ends and its persistence context closes or the entity becomes detached, Hibernate can no longer automatically query the database to load lazy associations for that entity.

### Transaction and PersistenceContext Are Related, Not Strictly Synonymous

In Spring, `@Transactional` usually creates or joins a transaction and binds an EntityManager/persistence context to the current execution thread. When the transactional method finishes, the transaction commits/rolls back and the transaction-scoped persistence context is typically closed or released.

OSIV can keep the EntityManager open across the entire HTTP request even after the service transaction has finished. Hence, "the transaction has ended" and "the EntityManager is definitely closed" are not always the exact same moment. Still, service design should explicitly determine what data to read rather than relying on a request-scoped persistence context.

## 2. How Do Lazy Loading and Proxies Work?

Lazy loading defers fetching an association until the application actually accesses it. Hibernate typically uses a proxy for to-one associations and a persistent collection wrapper for to-many associations.

Example:

~~~java
@Entity
public class PurchaseOrder {
    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderItem> items;
}
~~~

When querying PurchaseOrder, Hibernate may load only the row in purchase_orders. customer is represented by a proxy; items is represented by an uninitialized collection wrapper.

When calling:

~~~java
order.getCustomer().getName();
order.getItems().size();
~~~

Hibernate needs to run additional SQL to load customer or items. If the Session is still open, the lazy query can execute. If the entity is detached or the Session is closed, Hibernate cannot execute the query and may throw LazyInitializationException.

### Lazy Does Not Mean Never Loaded

Lazy only defers loading until needed. It does not guarantee the association will never be loaded. Calling a getter, iterating a collection, calling size(), contains(), or serializing the object can trigger queries.

### Default Fetch Types

Per JPA, `@ManyToOne` and `@OneToOne` default to EAGER, while `@OneToMany` and `@ManyToMany` default to LAZY. Explicitly declare `fetch = FetchType.LAZY` on to-one associations to avoid automatic loading beyond what is needed; then select a fetch plan per query/use case.

Do not switch every association to EAGER to avoid LazyInitializationException. EAGER can load unnecessary data, produce large joins, or trigger secondary selects and N+1 queries.

## 3. When Does LazyInitializationException Occur?

The error typically happens when an uninitialized lazy attribute is accessed after the persistence context is no longer active.

Typical scenarios:

1. **Service returns an entity to a controller:** the service transaction ends, and the controller reads order.getCustomer().getName().
2. **JSON serialization:** the controller returns an entity; Jackson traverses getters and touches lazy associations after the service has returned.
3. **Mapping to DTOs too late:** the service returns an entity, and a mapper runs outside the transaction and reads lazy collections.
4. **Async or executors:** an entity is passed to another thread; the original thread's persistence context is not propagated.
5. **Messages/events:** an entity is held and its associations are accessed after the message-handling transaction finishes.
6. **Detached entity:** code calls entityManager.detach() or clear(), then reads an unloaded association.
7. **Closed Session:** code retains an entity across request/job boundaries and accesses it after the Session has closed.

Error example:

~~~java
@Service
public class OrderService {
    @Transactional(readOnly = true)
    public PurchaseOrder findById(Long id) {
        return repository.findById(id).orElseThrow();
    }
}

// Controller calls after the service transaction ends.
PurchaseOrder order = orderService.findById(id);
String customerName = order.getCustomer().getName();
~~~

If customer has not been initialized, the last line can throw LazyInitializationException.

The key points when debugging are identifying which association was not loaded, what state the entity is in, and where the persistence context ended. The stack trace usually pinpoints the accessed getter/proxy/collection; SQL logs and PersistenceUnitUtil.isLoaded() help confirm state.

## 4. How to Check Whether Entities and Associations Are Loaded

JPA provides PersistenceUnitUtil.isLoaded:

~~~java
PersistenceUnitUtil util = entityManagerFactory.getPersistenceUnitUtil();

boolean entityLoaded = util.isLoaded(order);
boolean customerLoaded = util.isLoaded(order, "customer");
boolean itemsLoaded = util.isLoaded(order, "items");
~~~

In Hibernate, you can check directly:

~~~java
boolean initialized = Hibernate.isInitialized(order.getItems());
~~~

This is a useful diagnostic tool in tests or debugging. Do not use isLoaded checks to replace fetch plan design: if the caller definitely needs the customer name and item count, the query should load that exact data.

## 5. Preferred Solution: Convert to DTOs Inside the Transaction

A clean design is for the service to read the entity, extract all needed data while the transaction is still open, and return a DTO containing no lazy proxies.

~~~java
public record OrderSummary(
        Long id,
        String status,
        String customerName,
        int itemCount
) {
}

@Transactional(readOnly = true)
public List<OrderSummary> findSummaries(String status) {
    return repository.findByStatus(status).stream()
            .map(order -> new OrderSummary(
                    order.getId(),
                    order.getStatus(),
                    order.getCustomer().getName(),
                    order.getItems().size()
            ))
            .toList();
}
~~~

The mapper executes inside the transactional method, allowing Hibernate to load the associations. When the method returns, the caller only holds Java values copied into the DTO.

Benefits:

- The API does not depend on the entity graph or lazy proxies.
- Prevents Jackson from accidentally hitting the database during serialization.
- Clearly controls which fields are exposed externally.
- Easy to test, version responses, and enforce field-level authorization.
- Can reduce read volume using appropriate query projections.

DTOs must hold only the required values and should not retain entities or Hibernate collections inside the DTO.

## 6. Using @EntityGraph to Declare a Fetch Plan

`@EntityGraph` lets a repository method specify associations to fetch for a particular query:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @EntityGraph(attributePaths = {"customer", "items"})
    List<PurchaseOrder> findByStatusOrderByIdAsc(String status);
}
~~~

When the service calls this method, Spring Data instructs the JPA provider to load customer and items according to the entity graph. The service can then map to DTOs immediately inside the transaction.

EntityGraph is useful when:

- One use case needs extra associations while other use cases do not.
- You want to keep repository methods readable instead of writing JPQL fetch joins.
- You want to define fetch plans via named graphs or attributePaths.

EntityGraph is not a guarantee that the SQL will always be a single JOIN statement. The provider may select an appropriate loading strategy given the mapping. Inspect SQL and statement counts when optimizing performance.

## 7. Using JOIN FETCH

JPQL JOIN FETCH loads associations within the same query:

~~~java
@Query("select distinct o from PurchaseOrder o "
     + "join fetch o.customer "
     + "left join fetch o.items "
     + "where o.status = :status")
List<PurchaseOrder> findWithDetails(@Param("status") String status);
~~~

- join fetch on customer requires a matching customer.
- left join fetch on items preserves orders that have no items.
- distinct expresses the intent to return each root entity once; Hibernate 6 also deduplicates root entities in fetch join results.

Fetch join fits when a use case always needs that association. Do not fetch every association in every query.

### Collection Fetch Joins and Pagination

Do not carelessly combine to-many collection fetch joins with Pageable. An order with multiple items duplicates SQL rows; paginating over joined results may not align with root entity counts. Hibernate may log a warning or paginate in memory depending on configuration/version.

For paginated lists, safer options include:

1. Query the page of IDs/root entities first, with a stable sort.
2. Run a second query to load the graph for the IDs on that page using `IN (:ids)`.
3. Use a DTO projection to select only the columns needed for display.
4. Use `@EntityGraph` for to-one associations and handle collections in a separate query when needed.

Fetch joining multiple collections simultaneously can also cause a large Cartesian product or trigger MultipleBagFetchException depending on mapping types. Inspect cardinality and SQL rather than looking only at Java row counts.

## 8. Using DTO/Interface Projections to Avoid Loading the Entity Graph

If a screen only needs a few fields, projections can query the needed data directly:

~~~java
public interface OrderListView {
    Long getId();
    String getStatus();
    String getCustomerName();
}
~~~

JPQL constructor projection:

~~~java
public record OrderListItem(Long id, String status, String customerName) {
}

@Query("select new com.example.orders.OrderListItem("
     + "o.id, o.status, c.name) "
     + "from PurchaseOrder o join o.customer c "
     + "where o.status = :status")
List<OrderListItem> findOrderItems(@Param("status") String status);
~~~

Projections avoid instantiating the PurchaseOrder entity along with its entire association graph. This is often an efficient choice for read models, list tables, and search APIs.

With DTO projections, verify the fully qualified class name, constructor argument order, and return types. With interface projections, query aliases must match accessor names.

## 9. Explicit Initialization with Hibernate.initialize

In some use cases, you can proactively initialize associations while the Session is still open:

~~~java
@Transactional(readOnly = true)
public PurchaseOrder loadWithItems(Long id) {
    PurchaseOrder order = repository.findById(id).orElseThrow();
    Hibernate.initialize(order.getItems());
    Hibernate.initialize(order.getCustomer());
    return order;
}
~~~

Hibernate.initialize() is a Hibernate-specific API, not a portable JPA API. It is helpful when initializing a specific association within a narrow code block.

However, calling Hibernate.initialize() inside a loop over hundreds of entities can cause N+1 queries. Prefer EntityGraph, fetch join, or projections when the required data is known upfront.

Hibernate.initialize() cannot succeed on a detached proxy without an active Session. It must execute while the persistence context is still open.

## 10. Open Session in View (OSIV)

OSIV is a mechanism that keeps the EntityManager/Session open throughout the HTTP request lifecycle. In Spring Boot web applications, OSIV may be enabled by default depending on configuration; explicitly configure it so behavior does not depend on environment defaults:

~~~properties
spring.jpa.open-in-view=false
~~~

When OSIV is enabled, controllers or JSON serializers can access lazy associations after the service transaction ends because the EntityManager remains open for the request. This may make the error disappear, yet introduces risks:

- SQL runs in the controller layer or during response serialization.
- N+1 queries are harder to detect because queries originate outside the service.
- Endpoint latency becomes difficult to tie back to repository methods.
- Database access can happen at unexpected times.
- The web layer inadvertently depends on the entity graph and persistence.

OSIV does not mean a database transaction stays open for the entire request. It primarily keeps the persistence context/EntityManager open; database transactions usually span only transactional methods. Even so, lazy loading outside the service still issues SQL and acquires connections.

For APIs needing strict control over data access, disabling OSIV and mapping DTOs inside the transaction is more predictable. If keeping OSIV enabled, still define explicit fetch plans and do not rely on serializers to load data.

## 11. Detached Entities, Merge, and Clear

Once the persistence context closes, loaded entities become detached. Reading already-loaded scalar fields usually still works; reading uninitialized lazy associations can throw LazyInitializationException.

### merge Is Not a Way to Load Lazy Associations

EntityManager.merge(detachedEntity) copies detached state onto a managed instance and returns that managed instance:

~~~java
PurchaseOrder managed = entityManager.merge(detached);
~~~

The original detached object remains detached. Use the return value of merge() if you actually need to merge.

merge() is not a general way to load all lazy associations and does not guarantee the graph is initialized. If you need the data, re-query with an appropriate fetch plan.

### clear and detach

entityManager.detach(entity) detaches one specific entity; entityManager.clear() detaches all entities in the persistence context. Afterward, uninitialized lazy associations cannot automatically load via the old context.

Before clearing, flush any changes you intend to keep. If clearing to avoid first-level cache skewing measurements or to synchronize bulk DML, remember that all managed entities lose their managed state.

## 12. Async, Threads, and Message Boundaries

Spring transactions and EntityManagers are typically bound to the current thread. Do not pass entities with lazy associations to `@Async`, executors, schedulers, or message consumers expecting the original thread's persistence context to be shared.

Appropriate approaches:

- Pass IDs or command DTOs across thread/message boundaries.
- In the worker thread, open a new transaction and re-query the needed data.
- Or map to a complete DTO before dispatching to another thread.

Example:

~~~java
@Async
public CompletableFuture<Void> processOrder(Long orderId) {
    workerService.processInNewTransaction(orderId);
    return CompletableFuture.completedFuture(null);
}

@Transactional
public void processInNewTransaction(Long orderId) {
    PurchaseOrder order = repository.findWithDetails(orderId);
    // Work with loaded state inside this transaction.
}
~~~

The two methods should live in separate Spring beans so calls pass through the proxy. Do not rely on self-invocation to activate `@Async` or `@Transactional`.

## 13. Runnable Example with Java 17+, Spring Boot 3.4.5, Spring Data JPA, and H2

The example creates an order with a customer and two items. The first service returns an entity with uninitialized lazy associations; accessing them after the transaction ends throws LazyInitializationException. The second service uses `@EntityGraph` and maps to DTOs inside the transaction, so the caller needs no persistence context.

### Project Structure

~~~text
lazy-loading-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/lazyloading/
    │   │   ├── LazyLoadingApplication.java
    │   │   ├── Customer.java
    │   │   ├── PurchaseOrder.java
    │   │   ├── OrderItem.java
    │   │   ├── OrderSummary.java
    │   │   ├── CustomerRepository.java
    │   │   ├── PurchaseOrderRepository.java
    │   │   └── OrderService.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/lazyloading/OrderServiceIntegrationTest.java
~~~

### pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>lazy-loading-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### src/main/resources/application.properties

~~~properties
spring.datasource.url=jdbc:h2:mem:lazyloading;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=false
logging.level.org.hibernate.SQL=DEBUG
~~~

`open-in-view=false` helps the example clearly expose the service transaction boundary. The SQL logger is enabled to observe queries; you can turn it off after studying.

### Customer.java

~~~java
package com.example.lazyloading;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    protected Customer() {
    }

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

### PurchaseOrder.java

~~~java
package com.example.lazyloading;

import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 30)
    private String status;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @OneToMany(mappedBy = "order", cascade = CascadeType.ALL, orphanRemoval = true)
    private List<OrderItem> items = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String status, Customer customer) {
        this.status = status;
        this.customer = customer;
    }

    public void addItem(OrderItem item) {
        items.add(item);
        item.setOrder(this);
    }

    public Long getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }

    public Customer getCustomer() {
        return customer;
    }

    public List<OrderItem> getItems() {
        return items;
    }
}
~~~

### OrderItem.java

~~~java
package com.example.lazyloading;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "order_items")
public class OrderItem {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String productName;

    @Column(nullable = false)
    private int quantity;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    protected OrderItem() {
    }

    public OrderItem(String productName, int quantity) {
        this.productName = productName;
        this.quantity = quantity;
    }

    void setOrder(PurchaseOrder order) {
        this.order = order;
    }
}
~~~

### OrderSummary.java

~~~java
package com.example.lazyloading;

public record OrderSummary(
        Long id,
        String status,
        String customerName,
        int itemCount
) {
}
~~~

### CustomerRepository.java

~~~java
package com.example.lazyloading;

import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository extends JpaRepository<Customer, Long> {
}
~~~

### PurchaseOrderRepository.java

~~~java
package com.example.lazyloading;

import java.util.List;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository extends JpaRepository<PurchaseOrder, Long> {
    @EntityGraph(attributePaths = {"customer", "items"})
    List<PurchaseOrder> findByStatusOrderByIdAsc(String status);
}
~~~

findById inherited from JpaRepository declares no fetch graph, so associations remain lazy per the mapping. findByStatusOrderByIdAsc requests loading customer and items for the summary creation use case.

### OrderService.java

~~~java
package com.example.lazyloading;

import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final CustomerRepository customerRepository;
    private final PurchaseOrderRepository repository;

    public OrderService(
            CustomerRepository customerRepository,
            PurchaseOrderRepository repository) {
        this.customerRepository = customerRepository;
        this.repository = repository;
    }

    @Transactional
    public Long createDemoOrder() {
        Customer customer = customerRepository.saveAndFlush(new Customer("Acme"));

        PurchaseOrder order = new PurchaseOrder("NEW", customer);
        order.addItem(new OrderItem("Keyboard", 1));
        order.addItem(new OrderItem("Mouse", 2));

        return repository.saveAndFlush(order).getId();
    }

    @Transactional(readOnly = true)
    public PurchaseOrder loadWithoutFetching(Long id) {
        return repository.findById(id).orElseThrow();
    }

    @Transactional(readOnly = true)
    public List<OrderSummary> findSummaries(String status) {
        return repository.findByStatusOrderByIdAsc(status).stream()
                .map(order -> new OrderSummary(
                        order.getId(),
                        order.getStatus(),
                        order.getCustomer().getName(),
                        order.getItems().size()
                ))
                .toList();
    }
}
~~~

loadWithoutFetching returns the entity after the transaction ends; the caller receives a detached entity with uninitialized associations. findSummaries uses EntityGraph and maps to DTOs while the transaction is still open.

### LazyLoadingApplication.java

~~~java
package com.example.lazyloading;

import java.util.List;
import org.hibernate.LazyInitializationException;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class LazyLoadingApplication {
    public static void main(String[] args) {
        SpringApplication.run(LazyLoadingApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(OrderService orderService) {
        return args -> {
            Long orderId = orderService.createDemoOrder();
            PurchaseOrder detached = orderService.loadWithoutFetching(orderId);

            try {
                detached.getCustomer().getName();
            } catch (LazyInitializationException expected) {
                System.out.println("Detached customer access: LazyInitializationException");
            }

            try {
                detached.getItems().size();
            } catch (LazyInitializationException expected) {
                System.out.println("Detached items access: LazyInitializationException");
            }

            List<OrderSummary> summaries = orderService.findSummaries("NEW");
            for (OrderSummary summary : summaries) {
                System.out.println("DTO: order=" + summary.id()
                        + ", status=" + summary.status()
                        + ", customer=" + summary.customerName()
                        + ", itemCount=" + summary.itemCount());
            }
        };
    }
}
~~~

### Running the Application

~~~bash
mvn spring-boot:run
~~~

Expected stdout on a fresh H2 database:

~~~text
Detached customer access: LazyInitializationException
Detached items access: LazyInitializationException
DTO: order=1, status=NEW, customer=Acme, itemCount=2
~~~

The first generated ID is 1 in the example's fresh database. The first two lines demonstrate accessing uninitialized associations after the transaction. The last line shows the service loading the required graph and returning DTOs independent of the persistence context.

## 14. Integration Test for the Error and Fix

Tests should not wrap the entire test method in a transaction if you want to prove the entity is detached after the service returns. `@SpringBootTest` does not automatically start a transaction around test methods; keep the test without `@Transactional` to observe the real boundary.

~~~java
package com.example.lazyloading;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import org.hibernate.LazyInitializationException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class OrderServiceIntegrationTest {
    @Autowired
    private CustomerRepository customerRepository;

    @Autowired
    private PurchaseOrderRepository orderRepository;

    @Autowired
    private OrderService orderService;

    private Long orderId;

    @BeforeEach
    void setUp() {
        orderRepository.deleteAll();
        customerRepository.deleteAll();

        Customer customer = customerRepository.saveAndFlush(new Customer("Test Customer"));
        PurchaseOrder order = new PurchaseOrder("NEW", customer);
        order.addItem(new OrderItem("Keyboard", 1));
        order.addItem(new OrderItem("Mouse", 2));
        orderId = orderRepository.saveAndFlush(order).getId();
    }

    @Test
    void lazyAssociationsCannotBeLoadedAfterServiceTransactionEnds() {
        PurchaseOrder detached = orderService.loadWithoutFetching(orderId);

        assertThatThrownBy(() -> detached.getCustomer().getName())
                .isInstanceOf(LazyInitializationException.class);
        assertThatThrownBy(() -> detached.getItems().size())
                .isInstanceOf(LazyInitializationException.class);
    }

    @Test
    void entityGraphAllowsDtoMappingInsideTransaction() {
        List<OrderSummary> summaries = orderService.findSummaries("NEW");

        assertThat(summaries).hasSize(1);
        assertThat(summaries.get(0).customerName()).isEqualTo("Test Customer");
        assertThat(summaries.get(0).itemCount()).isEqualTo(2);
    }
}
~~~

Run tests:

~~~bash
mvn test
~~~

The first test confirms both the to-one proxy and to-many collection remain uninitialized when the service returns the entity. The second test confirms EntityGraph lets the service map DTOs inside the transaction without accessing lazy associations in the caller.

## 15. Approaches to Avoid

### Setting EAGER on Every Association

EAGER can make queries load far more data than needed and trigger secondary selects. Fetch plans should be decided per use case.

### Enabling OSIV Just to Mask Errors

OSIV allows lazy loading to keep running in controllers/serializers, hiding that the service returned incomplete data. If using OSIV, still monitor SQL and avoid arbitrary association access.

### Enabling hibernate.enable_lazy_load_no_trans

This Hibernate option attempts to load lazy associations outside transactions using temporary Sessions in certain cases. It can spawn many small transactions/connections, obscure persistence boundaries, and lead to N+1 queries. Do not use it as a default application design.

### Calling merge() to "Reopen" the Entity

merge() does not make the original detached object managed and does not automatically guarantee the entire lazy graph is loaded. If you need data, re-query with EntityGraph/fetch join or projection.

### Returning Entities Directly to JSON Serializers

Serializers can invoke getters and trigger lazy loading. API responses should be DTOs/projections with a well-defined structure.

### Initializing Collections Inside a Loop

Reading lazy collections one by one across hundreds of entities can cause N+1 queries. Use an appropriate fetch plan or batch fetching and measure query counts.

## 16. Common Mistakes and How to Diagnose Them

1. **Accessing associations after the service returns an entity:** map DTOs inside the transaction or load associations via EntityGraph/fetch join.
2. **Jackson triggering LazyInitializationException:** do not serialize entities directly; return DTOs.
3. **Putting `@Transactional` only on the controller:** the transaction is too broad and blurs business boundaries; place it on service use cases.
4. **Calling transactional methods via self-invocation:** the call bypasses the Spring proxy; move the method to another bean or use the appropriate transaction API.
5. **Passing entities to async threads:** the persistence context is not thread-safe and does not propagate automatically; pass IDs/DTOs and re-query in a new transaction.
6. **Using merge() but continuing to read the old object:** use the managed instance returned by merge(), or re-query with a fetch plan.
7. **Collection fetch join with Pageable:** can multiply rows and paginate inaccurately/expensively; paginate IDs first and then fetch the graph.
8. **Putting EAGER on all relationships:** loads excessive data; select fetch plans per query.
9. **Enabling OSIV without inspecting SQL:** lazy queries can fire during serialization and cause N+1.
10. **Calling Hibernate.initialize() outside a Session:** cannot initialize a detached proxy; call while the transaction is open.
11. **Clearing the persistence context with unflushed changes:** changes may not be synchronized; flush before clearing if you want to keep them.
12. **Confusing loaded scalar fields with loaded associations:** an entity may allow reading scalar fields while still holding uninitialized lazy proxies/collections.

## 17. Checklist When Investigating LazyInitializationException

- [ ] Identify the exact association or collection causing the error from the stack trace.
- [ ] Check whether the entity is still managed and where the persistence context ended.
- [ ] Check `PersistenceUnitUtil.isLoaded(entity, "association")` when needed.
- [ ] Determine whether the caller actually needs that association's data.
- [ ] If needed, load via `@EntityGraph`, JOIN FETCH, projection, or a separate query.
- [ ] Map to DTOs inside the service transaction before returning data outward.
- [ ] Check whether controllers, serializers, mappers, async tasks, or message consumers access entities after the transaction.
- [ ] Set `spring.jpa.open-in-view` explicitly and do not rely on OSIV to hide errors.
- [ ] Check N+1 queries and SQL statement counts after modifying the fetch plan.
- [ ] Do not enable EAGER globally or enable_lazy_load_no_trans just to make the error disappear.
- [ ] Test services with real transactions and keep test methods non-transactional when verifying detached behavior.

## 18. Best-Practice Principles

- Understand the persistence context as the boundary managing entities and lazy loading.
- Treat LazyInitializationException as a signal that code is reading data outside the appropriate persistence boundary.
- Place transactions at the service layer and complete required data reads inside the transaction.
- Prefer DTOs/projections for data crossing API, async, or messaging boundaries.
- Use `@EntityGraph` or JOIN FETCH to load associations per use case.
- Use projections when only specific fields are needed and an entity graph is unnecessary.
- Only use Hibernate.initialize() for targeted associations while the Session is open; avoid loops causing N+1.
- Disable OSIV if you want strict enforcement of database access inside services; even with OSIV enabled, control fetch plans.
- Do not treat EAGER, merge, or lazy-load-no-trans as general-purpose solutions.
- Test detached behavior, DTO mapping, and SQL statement counts.

Core takeaway: **LazyInitializationException occurs when Hibernate needs to load a lazy association but the persistence context is no longer available. Identify what data the use case needs, load it within the transaction using EntityGraph/fetch join/projection, and return complete DTOs. This keeps database access inside service boundaries and avoids relying on serializers or OSIV.**
