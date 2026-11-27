# Batch Fetching, @BatchSize, and Hibernate-Specific Configuration

## 1. Objectives

Batch fetching is a Hibernate mechanism that reduces the number of SELECT statements when an application accesses multiple lazily loaded associations. Instead of issuing a separate SELECT for each entity proxy or each collection, Hibernate groups multiple uninitialized items together and loads them in a single query, typically using an `IN` condition.

This lesson focuses on:
- Why lazy loading can create the N+1 problem.
- How batch fetching works with entity proxies and collections.
- Using `@BatchSize` at the entity level and on collection attributes.
- Configuring a global default with `hibernate.default_batch_fetch_size` in Spring Boot.
- Distinguishing batch fetching on reads from JDBC batching on writes.
- Choosing between batch fetching, `JOIN FETCH`, `@EntityGraph`, and other loading strategies.
- Measuring SQL statement counts and testing batch fetching behavior.

After this lesson, you will be able to keep associations lazy, reduce database round-trips in suitable use cases, and choose a batch size based on real measurements.

## 2. The N+1 Problem When Using Lazy Loading

Suppose there are 20 orders, each linked to a customer. The `PurchaseOrder` entity uses `@ManyToOne(fetch = LAZY)` to avoid loading `Customer` immediately when querying orders.

If the application does the following:

```java
List<PurchaseOrder> orders = orderRepository.findAll();

for (PurchaseOrder order : orders) {
    System.out.println(order.getCustomer().getName());
}
```

The initial query fetches the order list. When `getCustomer().getName()` is called, Hibernate needs to initialize the `Customer` proxy. If each `Customer` is loaded with a separate SELECT, the total number of statements can be:

```text
1 SELECT fetching 20 orders
+ 20 SELECTs fetching 20 customers
= 21 SELECTs
```

This is the N+1 problem: one query fetches the root dataset, followed by N additional queries for related data. Lazy loading avoids loading unneeded data, but accessing each association in a loop can generate many queries.

Batch fetching reduces the number of supplementary queries by loading multiple proxies at once. With a batch size of 16 and 20 distinct `Customer`s, the example above typically requires:

```text
1 SELECT fetching orders
+ 1 SELECT fetching up to 16 customers
+ 1 SELECT fetching the remaining 4 customers
= 3 SELECTs
```

These query counts illustrate the case when proxies of the same type are pending in a single persistence context, no cache alters the outcome, and each order references a different `Customer`. Actual counts depend on data, access order, caching, and configuration.

## 3. How Does Batch Fetching Work?

Hibernate maintains a persistence context within a Session/transaction. When entities or collections are lazily loaded, Hibernate can track uninitialized proxies or collection wrappers.

When the application accesses one proxy/collection, Hibernate selects a group of pending objects of the same type and loads them in a single SELECT. For example, with the `Customer` entity:

```sql
select c.id, c.name
from customers c
where c.id in (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
```

For the `Customer.orders` collection, Hibernate can load collections for multiple `Customer`s in a single query:

```sql
select o.customer_id, o.id, o.order_number
from purchase_orders o
where o.customer_id in (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
```

The batch size is the maximum number of entity proxies or collection owners Hibernate attempts to load in one SELECT. If 20 items need loading and the batch size is 16, there will typically be one batch of 16 and one batch of 4.

Batch fetching does not combine all associations into a single query. It groups lazy loads into smaller chunks. It can also only batch eligible proxies/collections currently residing in the same persistence context; if each loop iteration opens a separate transaction/session or clears the persistence context repeatedly, batching opportunities decrease.

## 4. Using @BatchSize on an Entity

`@BatchSize` is a Hibernate-specific annotation in the package:

```java
import org.hibernate.annotations.BatchSize;
```

Place the annotation at the entity level to specify how many proxies of that entity can be loaded together:

```java
@Entity
@Table(name = "customers")
@BatchSize(size = 16)
public class Customer {
    // Entity fields
}
```

When multiple lazy associations point to `Customer` and `Customer` proxies are pending in the Session, Hibernate can initialize up to 16 proxies in the same SELECT.

Relationship example:

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;
}
```

The annotation on `Customer` applies to batch loading `Customer` instances. It is useful when querying many `PurchaseOrder`s and reading `order.getCustomer()` sequentially.

### 4.1. @BatchSize Does Not Change Fetch Type

`@BatchSize` does not convert `LAZY` into `EAGER`, nor does it force Hibernate to load `Customer` immediately when querying `PurchaseOrder`. It only affects how Hibernate executes loading when a lazy proxy is initialized.

Thus, the application can still keep the mapping:

```java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;
```

and let Hibernate batch proxy initializations when needed.

## 5. Using @BatchSize on a Collection

Batch fetching also applies to lazy collections. Place `@BatchSize` directly on the collection attribute to limit how many collections of the same role are loaded in one SELECT.

```java
@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
    @BatchSize(size = 16)
    private List<PurchaseOrder> orders = new ArrayList<>();
}
```

When the application loads a list of `Customer`s and calls `customer.getOrders()` for multiple customers, Hibernate can load the `orders` collection for up to 16 `Customer`s in a single query.

Difference between the two annotation placements:

| @BatchSize Placement | What Is Batched | Example Use Case |
| --- | --- | --- |
| On the `Customer` entity class | Uninitialized `Customer` proxies/instances. | Many `PurchaseOrder`s referencing different `Customer`s. |
| On the `Customer.orders` attribute | Uninitialized `orders` collections across multiple `Customer`s. | Loading a list of `Customer`s and reading each customer's orders. |

For a collection, the batch size is the number of collection owners loaded together, not the maximum number of `PurchaseOrder` elements inside a single collection.

## 6. Global Default Configuration in Spring Boot

If you want to apply a default batch size to lazy associations across the entire application, configure the Hibernate property:

`src/main/resources/application.properties`:

```properties
spring.jpa.properties.hibernate.default_batch_fetch_size=16
```

With YAML:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        default_batch_fetch_size: 16
```

This is a Hibernate configuration setting, not a standard JPA property. Spring Boot forwards properties under `spring.jpa.properties.*` to Hibernate.

`hibernate.default_batch_fetch_size` is the global default for batch fetching. You can still place `@BatchSize(size = n)` on a specific entity or collection when you want a custom size for that mapping. Keep configurations explicit and verify behavior on the Hibernate version your application uses.

### 6.1. Choosing a Batch Size

There is no single right number for every application. Values like 16, 32, or 64 are often used as starting points for measurement, while considering:

- The number of associations typically accessed in a use case.
- Database bind parameter limits and `IN`-clause handling.
- Row size and total returned data volume.
- Application memory, network, and latency between the app and database.
- The actual number of proxies/collections present in a persistence context.

A large batch size reduces round-trips but produces queries with more parameters and returns more data at once. A small batch size increases supplementary queries. Measure on a realistic workload rather than simply picking the largest number.

## 7. Distinguishing Batch Fetching from JDBC Batching

Both features include the word "batch", but they solve two different problems:

| Mechanism | Purpose | Config/Annotation | Database Action |
| --- | --- | --- | --- |
| Batch fetching | Reduce SELECTs when loading lazy entities/collections. | `@BatchSize`, `hibernate.default_batch_fetch_size`. | One SELECT loads multiple entities or collection owners, typically using `IN`. |
| JDBC batching | Reduce round-trips for INSERT/UPDATE/DELETE writes. | `hibernate.jdbc.batch_size` and related DML settings. | Driver sends multiple write statements in a batch. |

JDBC batching configuration example:

```properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
```

This property does not enable batch fetching. If your goal is to reduce N+1 when reading lazy associations, configure `@BatchSize` or `hibernate.default_batch_fetch_size`.

## 8. Complete Example Model

The example uses Java 17+, Spring Boot 3.5.x, Spring Data JPA, and Hibernate versions managed by Spring Boot. The model has `Customer` and `PurchaseOrder` with a bidirectional relationship:

- One `Customer` has many `PurchaseOrder`s.
- Each `PurchaseOrder` belongs to one `Customer`.
- Both sides load lazily when reading associations.

### 8.1. Customer Entity

`src/main/java/com/example/orders/Customer.java`:

```java
package com.example.orders;

import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import java.util.ArrayList;
import java.util.List;
import org.hibernate.annotations.BatchSize;

@Entity
@Table(name = "customers")
@BatchSize(size = 16)
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    @OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
    @BatchSize(size = 16)
    private List<PurchaseOrder> orders = new ArrayList<>();

    protected Customer() {
        // JPA requires a no-arg constructor.
    }

    public Customer(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Customer name is required");
        }
        this.name = name.trim();
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public List<PurchaseOrder> getOrders() {
        return orders;
    }

    public void addOrder(PurchaseOrder order) {
        orders.add(order);
        order.setCustomer(this);
    }
}
```

`@BatchSize` on the class applies to `Customer` proxies; the annotation on `orders` applies to the `orders` collection across multiple `Customer`s.

### 8.2. PurchaseOrder Entity

`src/main/java/com/example/orders/PurchaseOrder.java`:

```java
package com.example.orders;

import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String orderNumber;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    protected PurchaseOrder() {
        // JPA requires a no-arg constructor.
    }

    public PurchaseOrder(String orderNumber, Customer customer) {
        if (orderNumber == null || orderNumber.isBlank()) {
            throw new IllegalArgumentException("Order number is required");
        }
        if (customer == null) {
            throw new IllegalArgumentException("Customer is required");
        }
        this.orderNumber = orderNumber.trim();
        this.customer = customer;
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public Customer getCustomer() {
        return customer;
    }

    void setCustomer(Customer customer) {
        this.customer = customer;
    }
}
```

The constructor sets the owning side `PurchaseOrder.customer`. The `Customer.addOrder()` method keeps both sides synchronized in memory when building the relationship from `Customer`.

### 8.3. Repositories

`src/main/java/com/example/orders/CustomerRepository.java`:

```java
package com.example.orders;

import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository extends JpaRepository<Customer, Long> {
}
```

`src/main/java/com/example/orders/PurchaseOrderRepository.java`:

```java
package com.example.orders;

import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository extends JpaRepository<PurchaseOrder, Long> {
}
```

## 9. Observing SQL During Batch Fetching

In `application.properties`, you can enable SQL logging and Hibernate statistics in development or test environments:

```properties
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true
spring.jpa.properties.hibernate.generate_statistics=true
spring.jpa.properties.hibernate.default_batch_fetch_size=16
```

Or use loggers:

```properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Bind logging can print sensitive parameter values; enable it only in development/test environments and manage logs appropriately.

With 20 orders referencing 20 customers, the SQL typically looks like:

```sql
-- Query 1: fetch orders
select o.id, o.order_number, o.customer_id
from purchase_orders o;

-- Query 2: initialize a batch of Customer proxies
select c.id, c.name
from customers c
where c.id in (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);

-- Query 3: load the remaining Customers
select c.id, c.name
from customers c
where c.id in (?, ?, ?, ?);
```

Actual SQL generated by Hibernate and the dialect may vary in aliases, columns, placeholder counts, and grouping. What to verify is that SELECT counts drop by batch groups and association data remains accurate.

## 10. Testing Query Counts with Hibernate Statistics

Functional tests verifying data accuracy alone are not enough to prove batch fetching is active. You can use Hibernate `Statistics` to measure prepared statement counts within an operation block.

The test below creates 20 `Customer`s, each with one `PurchaseOrder`. After flushing and clearing the persistence context, the test verifies:

1. One SELECT fetching all `PurchaseOrder`s.
2. Two SELECTs loading 20 `Customer` proxies with batch size 16.

### 10.1. Test Configuration

Example using H2 in `src/test/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:batchdb;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.properties.hibernate.generate_statistics=true
spring.jpa.properties.hibernate.default_batch_fetch_size=16
```

### 10.2. Integration Test

`src/test/java/com/example/orders/BatchFetchingTest.java`:

```java
package com.example.orders;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.ArrayList;
import java.util.List;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.Sort;
import jakarta.persistence.EntityManager;

@DataJpaTest
class BatchFetchingTest {
    @Autowired
    private EntityManager entityManager;

    @Autowired
    private CustomerRepository customerRepository;

    @Autowired
    private PurchaseOrderRepository orderRepository;

    private Statistics statistics() {
        SessionFactory sessionFactory = entityManager
                .getEntityManagerFactory()
                .unwrap(SessionFactory.class);
        return sessionFactory.getStatistics();
    }

    private void seedTwentyCustomersAndOrders() {
        for (int i = 1; i <= 20; i++) {
            Customer customer = new Customer("Customer " + i);
            entityManager.persist(customer);
            entityManager.persist(new PurchaseOrder("ORD-" + i, customer));
        }
        entityManager.flush();
        entityManager.clear();
    }

    @Test
    void batchesLazyCustomerProxies() {
        seedTwentyCustomersAndOrders();
        Statistics stats = statistics();
        stats.clear();

        List<PurchaseOrder> orders = orderRepository.findAll(Sort.by("id").ascending());
        List<String> customerNames = orders.stream()
                .map(order -> order.getCustomer().getName())
                .toList();

        assertThat(customerNames).hasSize(20);
        assertThat(stats.getPrepareStatementCount()).isEqualTo(3);
    }

    @Test
    void batchesLazyCollectionsForMultipleCustomers() {
        seedTwentyCustomersAndOrders();
        Statistics stats = statistics();
        stats.clear();

        List<Customer> customers = customerRepository.findAll(Sort.by("id").ascending());
        List<Integer> orderCounts = customers.stream()
                .map(customer -> customer.getOrders().size())
                .toList();

        assertThat(orderCounts).hasSize(20);
        assertThat(orderCounts).containsOnly(1);
        assertThat(stats.getPrepareStatementCount()).isEqualTo(3);
    }
}
```

The first test checks batching of `Customer` entity proxies. The second test checks batching of the `Customer.orders` collection. With 20 items and a batch size of 16, each test expects one root query plus two association queries, totaling three prepared statements.

Exact statement counts can vary if configuration, Hibernate version, caching, query setup, or seeding changes. If a test in a real project reports a different number, inspect SQL logs and statistics to identify which queries are counted; do not tweak assertions just to force a test to pass.

Run:

```bash
mvn test
```

The expected result is `BUILD SUCCESS` with both tests passing under the example's mapping/configuration. This is the expected outcome, not a build log executed in this environment.

## 11. When to Use BatchSize, JOIN FETCH, or EntityGraph?

Batch fetching is not the best option for every query. Choose a strategy based on association counts and the shape of data to return.

| Strategy | When Appropriate | Trade-offs to Consider |
| --- | --- | --- |
| Batch fetching | Reading many lazy entities/collections in one persistence context where actual association counts vary by data. | Still issues supplementary SELECTs per batch. |
| `JOIN FETCH` | A specific query definitely needs the association and joined row count is controlled. | Joining collections can multiply rows, duplicate roots, and complicate pagination. |
| `@EntityGraph` | Want to declare a fetch plan per repository method or use case. | Provider decides execution; inspect actual SQL. |
| `@Fetch(FetchMode.SUBSELECT)` | A root query loads many owners and needs collections of the same role initialized via one subselect query. | Hibernate-specific strategy; may load collections for the entire owner group in the root query. |
| DTO projection | Only specific fields are needed without an entity graph. | Requires designing projections/queries; avoids hydrating unused associations. |

`JOIN FETCH` example:

```java
@Query("""
       select o
       from PurchaseOrder o
       join fetch o.customer
       order by o.id
       """)
List<PurchaseOrder> findAllWithCustomer();
```

`@EntityGraph` example:

```java
@EntityGraph(attributePaths = "customer")
List<PurchaseOrder> findByOrderNumberStartingWith(String prefix);
```

For queries returning `Page` and `@OneToMany` collections, avoid directly fetch-joining collections with pagination unless you understand row multiplication and Hibernate's handling. Batch fetching, DTO projections, or a two-step strategy are usually easier to control.

## 12. Limitations and Influencing Factors

Batch fetching has several limitations to understand:

- Batch size is an upper bound, not a guarantee that every SELECT always uses that exact placeholder count.
- Only eligible pending proxies/collections within the same persistence context can be batched.
- Associations must be accessed while the Session is still open; batch fetching does not prevent `LazyInitializationException` after the persistence context closes.
- Second-level caching can satisfy some entities without querying the database, resulting in fewer SELECTs than expected.
- If associations hold massive data or huge collections, batch fetching can produce large result sets; consider child pagination or projections.
- Databases impose bind parameter limits; batch size must fit your engine and query size.
- If code opens a new transaction per record or clears the Session inside a loop, proxies no longer share a batch queue.

Batch fetching reduces round-trips, but does not automatically reduce total bytes fetched. Consider entity size, association counts, and real use-case needs.

## 13. Common Mistakes

| Symptom | Cause | Solution |
| --- | --- | --- |
| Still seeing many SELECTs after adding `@BatchSize` | Association is not lazy, proxies are in different Sessions, or annotation is on the wrong entity/collection role. | Check fetch type, annotation placement, persistence context, and SQL logs. |
| `@BatchSize` not recognized | Wrong package import or incompatible Hibernate dependency. | Use `org.hibernate.annotations.BatchSize` and the Hibernate version managed by Spring Boot. |
| Confusing JDBC batch with fetch batch | Using `hibernate.jdbc.batch_size` expecting fewer lazy SELECTs. | Use `hibernate.default_batch_fetch_size` or `@BatchSize` for reads. |
| Batch query has too many bind parameters | Batch size set too high for the database or wide queries. | Lower batch size and re-measure on the target engine. |
| Lazy loading error after leaving transaction | Association accessed after Session closed. | Load data inside the transaction, map to DTO, or use an appropriate fetch plan. |
| Unstable test query counts | Caching, seed data, Hibernate version, or persistence context altering the batch queue. | Clear persistence context and statistics at the right point; inspect SQL instead of guessing. |
| Collection fetch multiplies rows | Using join fetch on collections with many elements. | Use batch fetching, DTOs, an appropriate EntityGraph, or two-step queries. |
| Expecting a single SELECT | Confusing batch fetching with JOIN FETCH. | Understand batch size is the max per batch; multiple batches still issue multiple SELECTs. |

## 14. Process for Applying and Measuring Performance

1. Identify the use case generating N+1 via SQL logs, APM, or Hibernate statistics.
2. Check which associations are lazy and accessed inside loops.
3. If lazy loading should be retained, try `@BatchSize` on the corresponding entity proxy or collection role.
4. If many mappings share a value, configure `hibernate.default_batch_fetch_size`.
5. Re-run the exact use case with representative data; compare SELECT counts, row counts, and latency.
6. Test different batch sizes, such as 16, 32, and 64, according to database limits and workload.
7. Compare against `JOIN FETCH`, `EntityGraph`, or DTO projections if the use case always needs the same association.
8. Test edge cases: empty associations, many owners, duplicate proxy references, and large data pages.
9. Keep SQL logs/measurement evidence in development or test environments; avoid logging sensitive bind parameters in production.

## 15. Completion Checklist

- [ ] Can explain the N+1 problem when accessing lazy associations.
- [ ] Can describe how Hibernate batches entity proxies into a SELECT with `IN`.
- [ ] Can use `@BatchSize` at the entity level to batch-fetch proxies.
- [ ] Can use `@BatchSize` on collections to batch-fetch multiple collection owners.
- [ ] Can configure `spring.jpa.properties.hibernate.default_batch_fetch_size`.
- [ ] Can distinguish fetch batching from `hibernate.jdbc.batch_size`.
- [ ] Understands batch fetching does not change `LAZY` to `EAGER`.
- [ ] Can choose between batch fetching, `JOIN FETCH`, `EntityGraph`, and DTO projections.
- [ ] Can enable Hibernate statistics and observe prepared statement counts.
- [ ] Can write integration tests for batching entity proxies and collections.
- [ ] Chooses batch sizes based on measured data and database limits.

Once completed, you can apply Hibernate batch fetching to reduce N+1 in a controlled manner, configure batch sizes at the right scope, and confirm effectiveness with SQL logs and Hibernate statistics.