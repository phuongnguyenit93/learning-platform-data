# Do Not Pass an EntityManager or ORM Session to Another Execution Thread

## 1. Main Idea: A Thread Boundary Is Also a Persistence Context Boundary

In a concurrent Spring application, one thread may be executing `@Transactional`, holding a **persistence context**, and using a JPA `EntityManager` or Hibernate `Session`. If that method dispatches work to `@Async` or a `TaskExecutor`, **do not pass the active EntityManager/Session instance itself to the new worker** to keep querying or updating data.

Why: a real provider-created `EntityManager`, or a real Hibernate `Session`, is a **stateful, non-thread-safe** component. It tracks managed entities, dirty-checking state, flushes, lazy loading, and transactions. Spring manages imperative transactions via resources bound to the **current thread**; when handing work off to a worker, the caller's transaction and persistence context **do not follow along automatically**.

**Recommended design:** pass only **IDs, immutable values, or materialized DTOs** across the async boundary. On the worker, invoke a **Spring-managed service/repository bean** with its own transaction; let Spring obtain the appropriate EntityManager from **the worker's** persistence context, read/write data, and **return a DTO** — never an EntityManager, Session, or lazy collection.

~~~text
DO NOT

request thread                          async worker thread
  @Transactional
  Real EntityManager / Real Session ────────► em.find(), em.flush()
  persistence context A                         cross-using A: unsafe
  transaction A                                  transaction A does not auto-propagate


DO

request thread                          async worker thread
  save entity and commit
  get orderId (Long) ─────────────────────────► @Transactional(readOnly = true)
                                               worker's EntityManager
                                               em.find(Order.class, orderId)
                                               DTO snapshot
                  ◄──────────────────────────── CompletableFuture<DTO>
~~~

Here "real EntityManager" means the provider-created object managing a persistence context. There is an **important exception regarding reference types**: Spring's default `@PersistenceContext` typically injects a **shared EntityManager proxy** into a singleton repository. That proxy **can be used from multiple threads** because it routes calls to the EntityManager appropriate for the currently active transaction/thread. That **does not** make the **underlying EntityManager/Session** thread-safe; nor is it a reason to pass an EM/Session reference across task APIs. Section 3 explains this explicitly so the article's advice is not misread.

## 2. EntityManager, Session, EntityManagerFactory, and Persistence Context

| Component | Role | Concurrency rule |
| --- | --- | --- |
| `EntityManagerFactory` (JPA) | Factory and metadata for a persistence unit | Designed to be shared, usually a singleton bean; creates EntityManagers per unit of work |
| `SessionFactory` (Hibernate) | Hibernate factory and configuration/mappings | Normally shared across threads; opens a separate Session per unit of work |
| Real `EntityManager` | API operating on a specific persistence context | **Not thread-safe**; never use concurrently or forward across worker threads |
| Real `Session` | Stateful Hibernate API, typically implementing EntityManager | **Not thread-safe**; never share across threads/units of work |
| Spring `TRANSACTION`-type `@PersistenceContext` | Proxy reference routing calls to the current transaction's EntityManager | Proxy injected into a singleton DAO can be used by different threads; **does not share the underlying context** |
| Managed JPA entity | Data tracked by a persistence context | Not automatically thread-safe; do not let multiple threads use the same managed entity |
| Immutable DTO/record | Data snapshot detached from any ORM persistence context | Suitable to pass across threads if all fields are genuinely immutable/thread-safe |

`EntityManagerFactory` and `EntityManager` must not be equated: sharing the factory is normal, whereas the context holding the first-level cache and entity change state belongs to a single unit of work. Likewise, a shareable `SessionFactory` does not mean a `Session` opened by it is shareable.

A **persistence context** manages the entity lifecycle (`new` -> managed -> detached/removed) alongside its identity map, change tracking, and flushing. It is not a structure built for multiple workers mutating it at once. If two tasks need to operate on the same DB record, they should **have separate EntityManagers** and use transactions/locking/versioning to synchronize at the database, rather than trying to "share one Session to save overhead".

### 2.1. Why "Not Thread-Safe" Is a Serious Constraint

A Session/EntityManager can hold:

- An identity map / first-level cache tracking entity instances by database identifier.
- Pending changes to flush and an action queue.
- Transaction state, connections, or coordination with a transaction manager.
- Lazy-loading proxies, collection wrappers, and internal persistence state.
- Query context, flush mode state, and cache hints.
- Resources that must be closed when the transaction/unit of work finishes.

If two threads mutate or flush the same context concurrently, behavior is undefined: races, corrupted dirty tracking, inconsistent data, random exceptions, or broken connection lifecycles. Even if both tasks only call `find()`, execution can still mutate internal caches and state. **Do not treat read-only access as proof that a real Session can be used concurrently.**

A Hibernate `Session` typically needs a relatively short lifetime scoped to a unit of work. Never place a real Session in a singleton field, HTTP session, static field, or executor task and keep it alive across transactions.

## 3. Subtle Point: @PersistenceContext in Spring Is a Shared Proxy, Not a Real Session

In a Spring singleton repository:

~~~java
@Repository
public class OrderRepository {

    @PersistenceContext
    private EntityManager em;

    @Transactional(readOnly = true)
    public OrderSummary findSummary(Long id) {
        Order order = em.find(Order.class, id);
        return new OrderSummary(order.getId(), order.getStatus());
    }
}
~~~

This is an **illustrative code snippet** requiring `Order`, `OrderSummary`, and imports. `OrderSummary` should be an immutable DTO. With the default `PersistenceContextType.TRANSACTION`, Spring normally injects a **shared transactional EntityManager proxy** into `em`, not a fixed provider Session shared across every call.

This proxy resolves **the EntityManager bound to the active transaction**; when no transaction is active, in some cases it creates a per-operation EntityManager. When two different threads call the same repository bean, the proxy picks a context per invocation's transaction/thread rather than sharing one real persistence context. Hence the singleton repository pattern with `@PersistenceContext` is **supported by Spring** and does not contradict the title.

**What you must not do:**

- Call `em.unwrap(org.hibernate.Session.class)` inside a transaction and hold/pass that **real Session** to an executor.
- Manually call `emf.createEntityManager()` and share that instance between the request thread and a worker.
- Pass a persistence context as a parameter `worker.doWork(em, ...)` assuming the transaction will tag along.
- Use `@PersistenceContext(type = PersistenceContextType.EXTENDED)` inside a concurrently accessed singleton bean; an extended context is not a thread-safe shared transactional proxy like above.

**What is allowed:** injecting a repository with a `@PersistenceContext` proxy into Spring-managed services so each method is invoked with **its own proper transaction**. This pattern shares **the same proxy reference** without **sharing a single real underlying EntityManager**.

### 3.1. A Shared Proxy Is Not a "Free Pass" to Skip Transactions

Even though the shared proxy picks an EntityManager automatically, it **does not copy the caller's transaction** to the worker. On a worker with no active transaction, some read operations may execute via a per-operation EntityManager; writes or lazy loading outside managed scope generally lack a valid contract. The safer design is calling a `@Transactional` service/repository on the thread executing the work.

The distinction to remember:

~~~text
Field in a singleton repository:
  @PersistenceContext EntityManager em
             |
             +-- proxy reference (usable from multiple threads)
                      |
                      +-- thread A / transaction A -> EntityManager A
                      |
                      +-- thread B / transaction B -> EntityManager B

Not:
  singleton repo -> single real EntityManager -> all threads
~~~

Spring documentation emphasizes that `@PersistenceContext` defaults to `TRANSACTION` and warns that `EXTENDED` is a different mechanism unsuitable for concurrently accessed singletons. That distinction matters far more than merely reading the field type `EntityManager`.

## 4. @Transactional Does Not Propagate to a New Thread

An imperative `@Transactional` managed by `PlatformTransactionManager` normally binds transactions/resources to a thread via mechanisms like `TransactionSynchronizationManager`. When calling `@Async`, `Executor.execute(...)`, `CompletableFuture.supplyAsync(...)`, or spawning a new `Thread`, code runs on a **different thread**, so it **does not automatically inherit**:

- The caller's JPA transaction and persistence context.
- The JDBC connection bound by the transaction manager.
- The Hibernate `Session` of the caller's transaction.
- Other `ThreadLocal` values such as MDC/security/request context, unless proper propagation is explicitly configured.

Anti-pattern example:

~~~java
@Service
public class OrderCoordinator {
    private final EntityManagerFactory emf;
    private final Executor executor;

    // Constructor injection is not shown in this illustrative snippet.

    @Transactional
    public void unsafe(Long id) {
        EntityManager em = emf.createEntityManager();
        executor.execute(() -> em.find(Order.class, id));
        // No proper ownership, close, transaction, or
        // access synchronization protocol for this EntityManager.
    }
}
~~~

This is an **intentionally broken snippet**, not runnable code; constructor, `Order`, and imports are omitted. `createEntityManager()` returns a real application-managed EntityManager. The task is sent to another thread while the resource retains an unclear lifecycle; if the caller uses or closes `em` while the worker runs, concurrent access and lifecycle races occur as well. **Never treat this instance as a valid payload for an executor.**

An even clearer broken example:

~~~java
@Transactional
public void wrong(Long id) {
    Session session = entityManager.unwrap(Session.class);
    executor.execute(() -> session.find(Order.class, id));
}
~~~

This snippet needs `entityManager`, `executor`, `Order`, and Hibernate imports. `unwrap(Session.class)` can expose **the real Session bound to the caller's transaction**. By the time the lambda runs, the caller transaction may have committed/closed, or two threads may touch the non-thread-safe Session at once. Do not try to fix this by calling `session.flush()` on the worker or enlarging the pool.

### 4.1. An @Async Call May Start Before Commit

~~~text
request thread                                worker thread
  @Transactional save(order)
  submit async(order.id) --------------------> findById(id)
  not yet committed                            may not see the row
  commit
~~~

When the worker has its own transaction, it does not automatically see **uncommitted** data from the caller's transaction. Visibility depends on isolation, commit timing, database, locks, and operations. You can hit "record not found" or block on a lock even when repositories and EntityManagers are properly managed. This is a **data publication timing** issue, distinct from EntityManager thread-safety.

For work that **must run after commit**, see Section 10 on `@TransactionalEventListener(phase = AFTER_COMMIT)` and transactional outboxes.

## 5. Not Just EntityManager: Managed Entities and Lazy Proxies Are Also Dangerous Across Threads

A common "workaround" avoids passing `EntityManager`, yet passes a whole **managed entity** or a **Hibernate lazy collection/proxy** to the worker:

~~~java
@Transactional
public void start(Long orderId) {
    PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
    asyncWorker.process(order); // Passing a managed entity as payload is not recommended
}
~~~

This is an illustrative snippet with undeclared beans/types. Entities can contain mutable fields, `@OneToMany(fetch = LAZY)`, and references to provider state. Once the caller's transaction ends, the worker may receive a **detached** entity, hit `LazyInitializationException` when touching an unloaded lazy association, or read inconsistent data from sharing a mutable object.

**Detached does not mean immutable or thread-safe.** A detached POJO can still be mutated by two threads concurrently. A Hibernate lazy proxy may also need a now-closed Session, so "waiting until the worker uses it" does not automatically reattach it.

Payloads you should not carry across the boundary:

| Payload | Risk |
| --- | --- |
| Provider `EntityManager` or Hibernate `Session` | Non-thread-safe; lifecycle/transaction does not follow the worker |
| Managed entity with mutable state | Bound to persistence context, mutable, and subject to caller dirty checking |
| Lazy proxy / `PersistentCollection` | Needs a session to initialize; session may be closed or on another thread |
| `Query`, `TypedQuery`, `StoredProcedureQuery` | Usually tied to an EntityManager/persistence context, not a transport payload |
| Open JPA `Stream`/cursor | DB/connection resource tied to the original context's lifecycle |
| `EntityTransaction`, JDBC `Connection`, Hibernate transaction | Stateful resources; do not make a transaction "migrate" across threads |
| Primitive / ID / immutable record holding materialized data | Suitable when holding no ORM references and carrying clear semantics |

If fields from associations are needed, query them **inside the worker's transaction** or **materialize them into a DTO** within a transaction with proper access before passing; never ship an uninitialized collection proxy expecting the worker to load it.

### 5.1. Use an Immutable DTO as the Data Boundary

Java 17 record:

~~~java
public record OrderEvent(Long orderId, String requestedBy, long version) {}
~~~

This is a value object type, not an ORM entity. Its components are final and it carries no persistence context. **Note:** records are only shallowly immutable; if a component is a `List`, array, or mutable object, the inner data can still mutate. With `Long`, `String`, and `long` in this example, the payload is a clean passable snapshot.

Do not rely on `EntityManager.detach(entity)` as a cure-all: detaching only changes management state in the persistence context; it neither makes mutable objects immutable nor resolves unloaded lazy associations.

## 6. Safe Pattern: Pass the ID and Load Inside the Worker's Transaction

**Three-step rule:**

1. Caller persists or determines the ID **according to a commit contract**.
2. Caller sends the **ID/immutable command** via `@Async` or an executor — never an EM, Session, or managed entity.
3. Worker **opens its own transaction** via a Spring service/repository, loads through the worker bean's `@PersistenceContext` proxy, and returns a DTO snapshot.

Layered pattern:

~~~java
@Service
public class OrderWriter {
    @Transactional
    public Long create(OrderRequest request) {
        // Persist entity then return ID; transaction commits when
        // the call through the Spring proxy completes normally.
        return orderRepository.saveAndGetId(request);
    }
}

@Service
public class AsyncLookup {
    private final OrderReader orderReader;

    public AsyncLookup(OrderReader orderReader) {
        this.orderReader = orderReader;
    }

    @Async("dbExecutor")
    public CompletableFuture<OrderDto> loadAsync(Long id) {
        OrderDto dto = orderReader.readDto(id);
        return CompletableFuture.completedFuture(dto);
    }
}

@Service
public class OrderReader {
    @PersistenceContext
    private EntityManager em;

    @Transactional(readOnly = true)
    public OrderDto readDto(Long id) {
        Order entity = em.find(Order.class, id);
        return OrderDto.of(entity); // copy data, do not return the entity
    }
}
~~~

This is **illustrative code**; `OrderRequest`, `OrderDto`, `Order`, `orderRepository`, and bean configs are omitted. The crucial part is that `AsyncLookup` calls **another bean `OrderReader` through a Spring proxy**, so `@Transactional(readOnly = true)` opens a transaction **on the worker thread**. `@Async` is likewise invoked through a bean proxy from the caller, not `this.loadAsync(...)`.

Another option is placing both `@Async` and `@Transactional` on a worker method called through a proper proxy, though splitting into **async dispatcher + transactional reader** keeps the two boundaries explicit and less dependent on advice ordering.

### 6.1. readOnly Does Not Automatically Make Entities or Threads Safe

`@Transactional(readOnly = true)` is a transaction hint/attribute that Spring/providers may optimize depending on configuration; it does **not** make the underlying EntityManager thread-safe. You must still confine the context to the worker and never return managed entities to another thread.

### 6.2. When the Worker Must Update Data

The worker can invoke:

~~~java
@Transactional
public void markProcessed(Long id) {
    Order entity = em.find(Order.class, id);
    if (entity == null) {
        throw new IllegalArgumentException("Order not found: " + id);
    }
    entity.setProcessed(true);
}
~~~

This is an illustrative method inside a repository/service with a managed EM. The worker's own transaction performs dirty checking and flushing; the caller's transaction does not wrap this update. If multiple workers update the same row concurrently, use `@Version` optimistic locking, database constraints, or proper locking to prevent lost updates. Never share entity objects across worker threads to "synchronize" the database.

## 7. Complete Example: Java 17 + Spring Framework 6.1 + Hibernate + H2

The following example is a **plain Spring Framework command-line application** needing no Spring Boot, web server, or external database. It demonstrates:

- `OrderWriter.create(...)` executes `@Transactional` on the caller and **completes the transaction before returning**.
- The caller passes only a `Long id` to the worker.
- `AsyncOrderLookup.loadAsync(id)` runs via Spring `@Async("dbExecutor")`.
- The worker calls `OrderReader.read(id)`, **another bean** with `@Transactional(readOnly = true)`; this transaction forms on the worker.
- `@PersistenceContext` injects a **shared proxy** into the singleton `OrderReader`, without sharing the real provider EntityManager between the two transactions.
- The result is an immutable `OrderView` (record), not a managed entity or Session.

**Environment:** JDK 17+, Gradle 8.5+, Spring Framework 6.1.14, Hibernate ORM 6.4.10.Final, Jakarta Persistence 3.1, H2 2.2.224.

### 7.1. File Structure

~~~text
orm-thread-boundary/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/
    ├── JpaThreadDemo.java
    ├── PurchaseOrder.java
    ├── OrderView.java
    ├── OrderWriter.java
    ├── OrderReader.java
    └── AsyncOrderLookup.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'orm-thread-boundary'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.14'
    implementation 'org.springframework:spring-orm:6.1.14'
    implementation 'jakarta.persistence:jakarta.persistence-api:3.1.0'
    implementation 'org.hibernate.orm:hibernate-core:6.4.10.Final'
    runtimeOnly 'com.h2database:h2:2.2.224'
    runtimeOnly 'org.slf4j:slf4j-simple:2.0.16'
}

application {
    mainClass = 'demo.JpaThreadDemo'
}
~~~

This demo pins specific versions for learning purposes; real projects must check **BOM/version compatibility** and security patches per their dependency management process.

### 7.2. src/main/java/demo/PurchaseOrder.java

~~~java
package demo;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String reference;

    protected PurchaseOrder() {
        // Constructor for JPA.
    }

    public PurchaseOrder(String reference) {
        this.reference = reference;
    }

    public Long getId() {
        return id;
    }

    public String getReference() {
        return reference;
    }
}
~~~

The entity is managed by Hibernate **inside each thread's transaction**. It is not sent directly into a `CompletableFuture`. `@GeneratedValue(IDENTITY)` lets H2 generate primary keys for the demo. Complex mappings with lazy relationships are omitted here to focus on the concurrency boundary.

### 7.3. src/main/java/demo/OrderView.java

~~~java
package demo;

public record OrderView(
        Long id,
        String reference,
        String workerThread,
        boolean transactionActive) {
}
~~~

This DTO is a Java record composed of safely shareable values. `workerThread` merely shows which thread ran the query; production code normally returns required data/metadata rather than using thread names as business keys.

### 7.4. src/main/java/demo/OrderWriter.java

~~~java
package demo;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.transaction.annotation.Transactional;

public class OrderWriter {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public Long create(String reference) {
        PurchaseOrder order = new PurchaseOrder(reference);
        em.persist(order);
        em.flush();
        return order.getId();
    }
}
~~~

In the demo, `OrderWriter` is a Spring bean created by the configuration below. `create` is invoked **through a proxy**, and the Spring transaction interceptor completes commit before the caller proceeds after a normal return. `em` is a shared injected proxy, not a provider Session that can be carried to another thread.

`em.flush()` in the demo ensures JPA flushes before returning the ID, though **flush is not commit**. The transaction is finalized by Spring when the proxied method call ends successfully.

### 7.5. src/main/java/demo/OrderReader.java

~~~java
package demo;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class OrderReader {

    @PersistenceContext
    private EntityManager em;

    @Transactional(readOnly = true)
    public OrderView read(Long id) {
        PurchaseOrder order = em.find(PurchaseOrder.class, id);
        if (order == null) {
            throw new IllegalArgumentException("Missing order: " + id);
        }

        // Create snapshot while still inside the worker's transaction.
        return new OrderView(
                order.getId(),
                order.getReference(),
                Thread.currentThread().getName(),
                TransactionSynchronizationManager
                        .isActualTransactionActive());
    }
}
~~~

`OrderReader.read` is invoked from another bean, so the transaction interceptor establishes a read-only boundary **right on the worker thread**. It queries the entity and copies its fields into a DTO; the entity never leaves the persistence context across the thread boundary.

### 7.6. src/main/java/demo/AsyncOrderLookup.java

~~~java
package demo;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;

public class AsyncOrderLookup {
    private final OrderReader reader;

    public AsyncOrderLookup(OrderReader reader) {
        this.reader = reader;
    }

    @Async("dbExecutor")
    public CompletableFuture<OrderView> loadAsync(Long id) {
        // Only the ID travels from caller to worker.
        OrderView view = reader.read(id);

        // The @Async body is running on the worker;
        // Spring proxy provides the result future to the caller.
        return CompletableFuture.completedFuture(view);
    }
}
~~~

`AsyncOrderLookup` receives only `Long id` and a reference to the Spring-managed `OrderReader`. No `EntityManager`, `Session`, `Query`, or JPA entity appears in the async parameters. `loadAsync` returns a completed `CompletableFuture` from **inside the worker**; Spring's proxy returns a handle for the caller to track the background work.

### 7.7. src/main/java/demo/JpaThreadDemo.java

~~~java
package demo;

import java.util.Properties;
import java.util.concurrent.TimeUnit;

import javax.sql.DataSource;
import jakarta.persistence.EntityManagerFactory;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.orm.jpa.JpaTransactionManager;
import org.springframework.orm.jpa.LocalContainerEntityManagerFactoryBean;
import org.springframework.orm.jpa.vendor.HibernateJpaVendorAdapter;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

public final class JpaThreadDemo {

    public static void main(String[] args) throws Exception {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            // Spring proxy call: caller transaction commits before returning.
            Long id = context.getBean(OrderWriter.class)
                    .create("ORDER-42");

            // Pass only ID; worker creates its own transaction via OrderReader.
            OrderView view = context.getBean(AsyncOrderLookup.class)
                    .loadAsync(id)
                    .get(5, TimeUnit.SECONDS);

            System.out.println("id preserved: " +
                    id.equals(view.id()));
            System.out.println("field loaded: " +
                    "ORDER-42".equals(view.reference()));
            System.out.println("worker pool used: " +
                    view.workerThread().startsWith("db-worker-"));
            System.out.println("worker transaction active: " +
                    view.transactionActive());
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    @EnableAsync
    public static class Config {

        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:orm_thread_demo;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public LocalContainerEntityManagerFactoryBean
                entityManagerFactory(DataSource dataSource) {

            var factory = new LocalContainerEntityManagerFactoryBean();
            factory.setDataSource(dataSource);
            factory.setPackagesToScan("demo");
            factory.setJpaVendorAdapter(new HibernateJpaVendorAdapter());

            Properties props = new Properties();
            props.setProperty("hibernate.hbm2ddl.auto", "create-drop");
            props.setProperty("hibernate.show_sql", "false");
            factory.setJpaProperties(props);
            return factory;
        }

        @Bean
        public PlatformTransactionManager
                transactionManager(EntityManagerFactory emf) {
            return new JpaTransactionManager(emf);
        }

        @Bean("dbExecutor")
        public ThreadPoolTaskExecutor dbExecutor() {
            var executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(2);
            executor.setMaxPoolSize(2);
            executor.setQueueCapacity(8);
            executor.setThreadNamePrefix("db-worker-");
            return executor;
        }

        @Bean
        public OrderWriter orderWriter() {
            return new OrderWriter();
        }

        @Bean
        public OrderReader orderReader() {
            return new OrderReader();
        }

        @Bean
        public AsyncOrderLookup asyncOrderLookup(OrderReader reader) {
            return new AsyncOrderLookup(reader);
        }
    }
}
~~~

**Configuration explanation:** `LocalContainerEntityManagerFactoryBean` builds the `EntityManagerFactory` for Hibernate, `JpaTransactionManager` provides thread-bound JPA transactions, and `@EnableTransactionManagement` activates transaction proxies. `@EnableAsync` activates async proxies. H2 is an in-memory database; `create-drop` is **for demo use only** and must not be used in production because it can destroy schemas/data.

`OrderWriter`, `OrderReader`, and `AsyncOrderLookup` are registered via `@Bean`. Objects returned by `@Bean` methods are post-processed by Spring as normal beans, unlike manually instantiated objects outside the container. When `OrderReader` is injected into `AsyncOrderLookup`, the reference carries the transaction proxy to intercept `read`.

### 7.8. Running and Results

In the `orm-thread-boundary` directory, with Java 17+ and a compatible Gradle version:

~~~bash
gradle run
~~~

If the project already has a Gradle Wrapper, run `./gradlew run` on Linux/macOS or `gradlew.bat run` on Windows.

**Four lines printed by the program itself, assuming H2/Hibernate startup succeeds and the task finishes before timeout:**

~~~text
id preserved: true
field loaded: true
worker pool used: true
worker transaction active: true
~~~

Hibernate/SLF4J/Gradle libraries may print extra INFO/WARN lines during context startup/shutdown; those are separate from the four lines above. The demo asserts booleans instead of printing a specific ID or worker number so it does not depend on thread ordering or database-generated keys.

**Why is this design sound?**

1. The caller obtains `OrderWriter` from the context and calls `create` through its transaction proxy; on normal return, Spring commits the transaction.
2. Only `Long id` is sent to `AsyncOrderLookup` — no EntityManager, Hibernate Session, or managed entity.
3. `@Async` is applied via a Spring proxy, so the dispatcher runs on `db-worker-`.
4. The dispatcher invokes `OrderReader.read(id)` through its injected bean reference; `@Transactional(readOnly = true)` activates on the worker.
5. The shared EM proxy inside `OrderReader` delegates to an underlying EntityManager for the worker transaction.
6. `OrderView` is a snapshot built **inside** the transaction; the caller's Future carries plain DTO data.
7. The context closes after the future completes, letting Spring manage the lifecycle of the entity manager factory and executor.

**Key takeaway:** the example does not try to manually create an EntityManager on the caller and pass it into a thread pool. It passes **data** to another thread and lets Spring's infrastructure manage a fresh persistence context where the work actually runs.

## 8. When You Must Use EntityManagerFactory Manually in a Worker

Not every program uses declarative `@Transactional`. A worker running outside Spring can take a **shared factory** and create its **own EntityManager right inside the worker**, with its own transaction and lifecycle.

Illustrative JPA `RESOURCE_LOCAL` pattern:

~~~java
CompletableFuture<Summary> future = CompletableFuture.supplyAsync(
        () -> {
            EntityManager workerEm = emf.createEntityManager();
            EntityTransaction tx = workerEm.getTransaction();
            try {
                tx.begin();

                Order entity = workerEm.find(Order.class, orderId);
                Summary result = new Summary(
                        entity.getId(), entity.getStatus());

                tx.commit();
                return result;
            } catch (RuntimeException ex) {
                if (tx.isActive()) {
                    tx.rollback();
                }
                throw ex;
            } finally {
                workerEm.close();
            }
        },
        executor);
~~~

This is an **illustrative snippet** requiring `emf`, `executor`, `orderId`, `Summary`, and `Order`. It is valid only when using **application-managed resource-local transactions**; JTA/container-managed transactions require their corresponding protocol and management rather than calling `getTransaction()` directly.

What is right here: **the factory is shareable**; the worker calls `createEntityManager()`, begins a transaction, copies a DTO, commits/rolls back, and closes within **the same unit of work**. Never leak `workerEm` outside the lambda, store it in a singleton field, or return it in a Future.

In a Spring application that already has `JpaTransactionManager`/`@PersistenceContext`, prefer the **Spring-managed repository + @Transactional** approach from Sections 6–7; managing EntityManagers/transactions manually is error-prone on cleanup and can drift from the application's transaction manager.

## 9. Return a DTO, Not a Lazy Object or Query Stream

An async method may look safe because it does not pass `EntityManager`, yet **returning an entity or lazy collection through a Future** still causes trouble:

~~~java
@Async("dbExecutor")
public CompletableFuture<PurchaseOrder> findAsync(Long id) {
    PurchaseOrder entity = em.find(PurchaseOrder.class, id);
    return CompletableFuture.completedFuture(entity);
}
~~~

This is an **anti-pattern snippet** requiring beans/transactions/imports. If the entity is loaded in the worker, the Future hands the entity to the caller **after the worker's transaction may already have ended**, leaving lazy fields uninitialized or allowing uncontrolled mutation. An entity does not become immutable simply by becoming detached.

**Better approach:**

~~~java
@Transactional(readOnly = true)
public OrderDetailsDto getDetails(Long id) {
    PurchaseOrder order = em.find(PurchaseOrder.class, id);

    // Extract required values while the persistence context is still valid.
    return new OrderDetailsDto(
            order.getId(),
            order.getReference(),
            resolveItemNames(order));
}
~~~

This snippet requires its own DTO and `resolveItemNames`. If `resolveItemNames` reads a lazy association, explicitly fetch/map it inside the transaction. A record containing a `List<String>` should copy it with `List.copyOf(...)` if an immutable snapshot is needed, rather than returning a raw `PersistentCollection`.

You can use **JPQL constructor projections**, Spring Data projections, entity graphs, or appropriate `JOIN FETCH` clauses to load only needed fields. Yet the core question is not "how to fetch every association"; it is **do not pass persistence contexts or Sessions across threads**.

## 10. When Work Must Run After Commit: TransactionalEventListener and Outbox

For work spawned inside a caller transaction, using `@Async` alone does not ensure the worker runs after commit.

### 10.1. Publishing an Event Containing the ID and Processing After Commit

A pattern suitable for work **that can be handled in memory**:

~~~java
public record OrderCommittedEvent(Long orderId) {}

// Inside a Spring-managed service:
@Transactional
public void createAndNotify(OrderRequest request) {
    Long id = saveOrder(request);
    applicationEventPublisher.publishEvent(new OrderCommittedEvent(id));
}

// Inside another listener bean:
@Component
public class OrderCommittedListener {
    private final AsyncOrderLookup worker;

    public OrderCommittedListener(AsyncOrderLookup worker) {
        this.worker = worker;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onCommitted(OrderCommittedEvent event) {
        worker.loadAsync(event.orderId());
    }
}
~~~

These are **illustrative snippets**, not a standalone program: request types, persistence methods, imports, and Future handling are needed. `@TransactionalEventListener(AFTER_COMMIT)` ties event delivery to the **successful commit** of the originating transaction; the post-commit listener sends the ID to the async worker. The worker opens its own transaction when reading.

Understand the limitations:

- A normal transactional event listener expects the event to be published while an active transaction exists; if there is no transaction, the listener may **not be invoked** by default unless `fallbackExecution` is configured.
- With a synchronous listener running right after commit, **old transaction resources may temporarily remain bound** while the callback runs. If the listener intends to write to the DB, open an appropriate independent transaction boundary (often `REQUIRES_NEW` on the same post-commit thread) or dispatch to a worker with its own transaction.
- Do not indiscriminately push all transactional event registration onto an arbitrary **async event multicaster**: registering the listener with the transaction must occur inside the originating transaction context per Spring's contract.
- **In-memory events can be lost** if the process crashes right after commit before the worker runs. It does not automatically guarantee at-least-once delivery.

### 10.2. Transactional Outbox for Work That Must Be Durable

If sending an email, updating an external system, or processing a financial transaction **must not be lost on crash/restart**, consider a **transactional outbox**:

~~~text
Caller transaction:
  INSERT purchase_order
  INSERT outbox_event (orderId, eventType, status=PENDING)
  COMMIT both

Background worker:
  CLAIM outbox_event
  READ order by ID in its own transaction
  EXECUTE side effect with idempotency key
  UPDATE outbox status / retry metadata
~~~

An outbox keeps job metadata **in the same transaction** as the business change. It eliminates the notification loss gap between commit and in-memory dispatch, though it **does not automatically provide exactly-once side effects**; the worker still needs a retry budget, leasing/claiming, idempotency/deduplication, and status tracking.

Never put an EntityManager or managed entity into an outbox payload; store **the ID and required serializable data**. If you need the exact snapshot at commit time, persist those values in the event payload / outbox table per contract rather than expecting an async worker to read historical values later.

## 11. Data Changes Between Submission and Worker Read

Even when using IDs/DTOs and separate transactions properly, the worker **does not automatically read the same snapshot** the caller just saw.

Example:

~~~text
T1: Order status = NEW; caller submits async(id=7)
T2: Another transaction changes status to APPROVED and commits
T3: Worker starts, opens transaction, find(id=7) -> APPROVED
~~~

This is not an EntityManager race, but a **business race between independent transactions**. If you need the exact state at event creation time, carry an **immutable snapshot/version** in the event or store it in the outbox.

Some strategies:

- **Optimistic locking with `@Version`** for concurrent updates; handle `OptimisticLockException` / matching Spring exceptions and retry boundedly if the operation is idempotent.
- **Conditional updates** at the DB when state/version still matches.
- **Idempotency keys** to prevent duplicate side effects on retry.
- **Define processing order** (by aggregate ID) when messages have dependencies.
- **READ COMMITTED/SNAPSHOT/REPEATABLE READ** according to database needs; never assume a separate transaction always sees the same snapshot as the caller.
- **Record sufficient fields** in the payload when business logic needs point-in-time consistency at the event moment.

Avoid trying to solve versioning issues by having two threads share a persistence context. That only introduces new concurrency hazards and still does not replace database concurrency control.

## 12. Why Does Open EntityManager in View Not Fix the Async Boundary?

In some Spring MVC apps, Open EntityManager in View (OEIV) binds an EntityManager to the **request processing duration** to support lazy access in the view layer. However, OEIV **does not grant permission** to use the underlying EM/Session from another worker and does not make the context thread-safe.

Using OEIV to "keep the Session open longer" also brings risks:

- Increases how long request-bound resources are held.
- Easily triggers lazy queries during view rendering/serialization, making N+1 issues hard to control.
- Does not ensure an async worker has the same transaction, isolation, or persistence context.
- Can mislead teams because an endpoint returning an entity works in one path yet breaks when executed outside a request.

**Never turn on OEIV as a patch for `LazyInitializationException` caused by passing entities/lazy proxies to a worker.** The fix is to query/materialize inside the worker's own transaction or return a properly prepared DTO.

## 13. Spring @Async, @Transactional, and Proxy Boundaries

For annotated methods to be intercepted properly, you need:

1. `@EnableAsync` and `@EnableTransactionManagement` active in the **right ApplicationContext**.
2. Beans managed by Spring (via `@Component`/`@Service`/`@Repository` or `@Bean`).
3. In default proxy mode, calls passing **through the proxy**, without `this.method()` for methods needing advice.
4. The executor properly selected and still accepting tasks.
5. The right transaction manager for the JPA datasource/persistence unit.

An anti-pattern:

~~~java
@Service
public class BadService {
    @Transactional
    public void process(Long id) {
        this.doAsync(id); // Does not pass through the async proxy.
    }

    @Async
    public void doAsync(Long id) {
        // May run synchronously inside the caller's transaction,
        // misleading readers about thread safety.
    }
}
~~~

This snippet omits imports; it deliberately demonstrates self-invocation. Here, an EM is not shared across two threads; **the bug is that @Async was never applied**. The danger is that once refactored so the call truly runs asynchronously, a design that silently depended on the caller's transaction immediately breaks because the worker does not inherit it. You must fix **both data handoff and transaction boundaries**.

In the Section 7 demo, the two proxy boundaries are separated:

~~~text
Caller -> OrderWriter.create()      [@Transactional on caller]
        | returns Long id after commit
        v
Caller -> AsyncOrderLookup.loadAsync(id)  [@Async -> executor]
        |
        v
Worker -> OrderReader.read(id)       [@Transactional on worker]
        |
        v
Worker EntityManager -> OrderView
~~~

This architecture is easy to explain, test, and observe. One method can carry both `@Async` and `@Transactional` when interceptors are configured properly, yet you should not treat the two annotations as a tool for forwarding the old transaction to a new thread.

### 13.1. Do Not Manually Propagate TransactionSynchronizationManager

Never copy entries from `TransactionSynchronizationManager.getResourceMap()` or thread-local transaction internals and bind them to a worker to "share" the same transaction/context. Resources like Connections and EntityManagers are not designed to be distributed arbitrarily across workers; doing so can break lifecycle management, locking, and transaction manager cleanup.

Having a context-propagation library for MDC/tracing **does not mean** you should propagate **transactions**. Trace/correlation IDs carry request metadata; EntityManagers and JDBC connections are stateful resources bound to a unit of work.

## 14. Overload, Exceptions, and Cancellation Still Require Design

Proper thread confinement does not guarantee an async job always succeeds.

### 14.1. Bounded Executors and Connection Pools

A `ThreadPoolTaskExecutor` has:

- `corePoolSize` / `maxPoolSize`: caps the number of workers.
- `queueCapacity`: queued tasks, impacting latency.
- `RejectedExecutionHandler`: behavior under saturation or shutdown.
- `threadNamePrefix`: aids log and thread-dump reading.

If the DB connection pool has only a few connections while the executor allows too many querying workers, they will contend for connections, queue wait rises, and timeouts can happen. Tuning the executor must go hand in hand with **DataSource pool size, DB capacity, query latency, and service-level objectives**, not simply raising max threads.

For example, `DiscardPolicy` or `DiscardOldestPolicy` can silently drop tasks; incomplete Futures leave callers waiting indefinitely. For mandatory work, use **signaled rejection**, backpressure/rate limiting, or durable job persistence. Never record a status as "processed" merely because `@Async` returned a Future.

### 14.2. Exceptions Do Not Leave a Persistence Context Reusable

When a Hibernate Session encounters a severe error, the transaction must roll back and the Session/context should normally be discarded; catching an exception is not enough to safely continue operations on the same Session. Let Spring's transaction interceptor finalize/roll back per contract, or manage rollback/close cleanly in manual code.

`LazyInitializationException`, `TransactionRequiredException`, `OptimisticLockException`, `DataAccessException`, and `ExecutionException` carry different meanings. With Futures, `get()` can throw `ExecutionException` and `join()` can throw `CompletionException`; inspect the cause to find the root error rather than blaming the executor right away.

### 14.3. Cancellation and Database Side Effects

`Future.cancel(true)` only **attempts to request worker interruption** if the implementation supports it. It does not guarantee a JDBC query stops immediately, a DB transaction rolls back, an email is unsent, or an external payment is reversed. Per the JDK, `CompletableFuture.cancel(true)` does not even use `mayInterruptIfRunning` to control background computation.

Use query timeouts, transaction timeouts, and explicit cancellation policies; test against your actual driver and database. Never close an EntityManager **from the caller thread** trying to interrupt a worker using it. The worker and transaction manager own cleanup for the worker's context.

## 15. Testing the ORM + Async Boundary Under Control

A reliable integration test should run a **Spring ApplicationContext**, datasource, and real transaction manager (or a test profile with a DB close to production). Do not instantiate beans with `new` and expect `@Async`/`@Transactional` to take effect.

Suggested checks:

1. **Thread:** the async method runs on a thread with the executor prefix, distinct from the caller.
2. **Transaction on worker:** `TransactionSynchronizationManager.isActualTransactionActive()` is true inside the transactional method called through a proxy.
3. **No EM/Session passed:** async signatures accept only IDs/immutable DTOs/commands — no `EntityManager`, `Session`, `Query`, or managed entities.
4. **Commit visibility:** dispatching after the writer transaction commits reads the row; when dispatching before commit, test the failure/race case under real isolation.
5. **Lazy associations:** DTOs are materialized inside the transaction; accessing the DTO outside needs no Session.
6. **Rollback:** when the writer transaction rolls back, post-commit listeners do not dispatch such jobs.
7. **Multiple workers:** run concurrently and verify each worker has its own transaction boundary with no shared real EM.
8. **Optimistic locking:** concurrent updates report version conflicts rather than silently overwriting.
9. **Timeouts/rejections:** Future/HTTP/job status reports errors cleanly and cleans up without hanging forever.
10. **Crash/restart:** where durability is needed, outbox/job store retains pending tasks and workers can retry.
11. **Context propagation:** trace IDs travel via a safe mechanism without copying transaction resources.
12. **Connection pool:** load-test with realistic concurrency and queues to avoid starvation from an undersized DB pool.

### 15.1. Tests Can Use Latches to Verify Isolation

If you need to prove two workers overlap in execution, use a `CountDownLatch` to ensure both have entered their transactions and pause at a checkpoint before releasing them. Measure active threads and transactions per worker; **never share a single Session just to "test concurrent reads"**. Two separate EntityManagers are the exact behavior to verify.

Avoid tests asserting only that execution finishes faster than an arbitrary duration: JVM warmup, H2 memory mode, executor scheduling, and CI load make timings fluctuate. Asserting threads, transactions, and DTO output yields far more reliable signals.

## 16. Common Mistakes and Fixes

| Anti-pattern | Risk | Replace with |
| --- | --- | --- |
| Passing a real `EntityManager` into `@Async` | Shared non-thread-safe context, broken lifecycle | Pass ID; load inside the worker's transaction |
| Passing `session = em.unwrap(Session.class)` | Worker touches the caller's Hibernate Session | Do not unwrap for handoff; use a repository on the worker |
| Creating an external `EntityManager` shared across tasks | Unsafe races, flush/cache/lifecycle bugs | Create a separate EM per worker/unit of work and close it |
| Holding `@PersistenceContext(EXTENDED)` in a singleton | Extended context is not thread-safe | Use the default transaction-scoped proxy |
| Assuming a singleton `@PersistenceContext` field is one real Session | Confusing the shared proxy with the underlying context | Understand per-transaction delegation |
| Passing a managed entity into an async task | Data races and broken lazy access | ID/immutable DTO materialized inside the right transaction |
| Returning `PersistentCollection`/JPA Stream via Future | Session/connection tied to old lifecycle | Map to a DTO/list snapshot before returning |
| `@Async` reading rows before writer commits | Missing data or lock blocking | After-commit dispatch / outbox depending on durability |
| Putting `@Transactional` on caller expecting worker to inherit | Transactions are thread-bound | Worker opens its own transaction via proxy |
| Calling `this.asyncMethod()` inside the same bean | Bypasses the default async proxy | Extract a collaborating bean or call through a proper proxy |
| Copying transaction thread-locals to workers | Unsafe sharing of stateful JDBC/JPA resources | Propagate plain metadata, not transactions |
| Enabling OEIV to dodge lazy errors in workers | Does not solve thread confinement | Fetch/materialize inside the right transaction |
| Setting `readOnly=true` and sharing a real EM | Read-only does not make an EM thread-safe | Separate context per worker |
| Calling `Future.cancel(true)` assuming DB rolled back | Cancellation is best-effort | Transaction/query timeouts, verify outcome |
| Dispatching async and returning 202 Accepted as durable proof | Jobs can vanish on crash or rejection | Job store/outbox with explicit status |
| Too many workers compared to DB connections | Pool exhaustion and latency spikes | Bounded concurrency and DB pool sizing |

## 17. Code Review Checklist

- [ ] No real `EntityManager`, real `Session`, `Query`, `EntityTransaction`, or Hibernate collection proxy is passed to another worker.
- [ ] **Spring's `@PersistenceContext` shared proxy** is clearly distinguished from a **real provider EntityManager**.
- [ ] `PersistenceContextType.EXTENDED` is not placed on a concurrently accessed singleton.
- [ ] No managed JPA entity crosses an async boundary; IDs/immutable DTOs/commands with clear semantics are used instead.
- [ ] Every database operation on a worker runs in its own transaction managed via a Spring service/repository proxy.
- [ ] `@EnableAsync` and `@EnableTransactionManagement` live in the right context, with no self-invocation of advised methods.
- [ ] Nothing relies on the caller's transaction/ThreadLocal after switching threads.
- [ ] A **post-commit** rule exists whenever the worker must read newly written data.
- [ ] For critical tasks, an outbox/job store persists work to survive crashes/restarts.
- [ ] DTOs are fully materialized; no lazy associations, JPA Streams, or provider handles leak out.
- [ ] Optimistic locking/idempotency handles workers updating the same record.
- [ ] Executor and DB connection pool are sized together; rejection is signaled when needed.
- [ ] Futures/CompletableFutures are monitored for errors, timeouts, and cancellation; background failures are not swallowed.
- [ ] Real integration tests verify threads, transactions, commit visibility, rollbacks, and DTO reloading.
- [ ] `em.close()` is never called on a Spring-managed shared proxy; the framework manages its lifecycle.
- [ ] Manual EntityManagers (if genuinely needed) are created, used, and closed strictly within the owning thread's unit of work.
- [ ] Tracing carries correlation IDs, while transaction resources are never copied across threads.

## 18. Self-Check Questions

1. **Why shouldn't a Hibernate `Session` be passed into `CompletableFuture.supplyAsync`?** Because a real Session is stateful and not thread-safe; units of work and transactions do not migrate automatically.
2. **Can `EntityManagerFactory` be a singleton used by multiple workers?** Yes. The factory is shareable while each worker needs its own context/transaction.
3. **Is a `@PersistenceContext` field in a singleton Spring repository always a single provider EntityManager?** No. By default it is normally a shared proxy delegating per transaction.
4. **Does sharing the shared proxy reference mean sharing the persistence context?** No; the proxy itself selects an underlying EM per transaction/operation.
5. **Why is `@PersistenceContext(type=EXTENDED)` different?** It creates a long-lived extended persistence context unsuitable for concurrent singleton access.
6. **Can a managed entity be passed to a worker instead of an EM?** It should not. Entities can be mutable/lazy, tied to an old context, and not automatically thread-safe.
7. **If a worker needs order data, what should it receive?** An ID or immutable command/DTO, then load via a worker repository/transaction.
8. **Does `@Transactional` on the caller follow an `@Async` worker?** Not for imperative thread-bound transactions.
9. **Why can dispatching async before commit yield "not found"?** The worker runs in its own transaction and cannot see uncommitted data under the DB's isolation level.
10. **When should you use `@TransactionalEventListener(AFTER_COMMIT)`?** When you want to dispatch work only after the originating transaction commits successfully and accept in-memory delivery limits.
11. **When is an outbox needed?** When tasks/events must survive crashes with retries and durable status tracking.
12. **Does `@Transactional(readOnly=true)` make a real EntityManager thread-safe?** No.
13. **If caller and worker update the same row using separate EMs, how do you handle conflicts?** Locking/versioning, constraints, controlled retries, and idempotency.
14. **Does OEIV allow a worker to use the request's session?** No; it does not make a Session thread-safe.
15. **Does `Future.cancel(true)` guarantee the Session closes and the transaction rolls back?** No. Cancellation is best-effort; transactions, drivers, and lifecycle control the outcome.
16. **If a worker outside Spring needs database access, how should EM be managed?** Use a shared EntityManagerFactory, create an EntityManager **on the worker**, manage its transaction, and close it in the same unit of work.
17. **What is a more effective testing approach than pure timing assertions?** Checking thread names, active worker transactions, DTO accuracy, post-commit visibility, and concurrency via latches.
18. **What is safely "shared" in a Spring repository using `@PersistenceContext`?** The shared proxy reference — **not a single real underlying persistence context**.

**Conclusion:** Do not pass **a real EntityManager/Session or managed ORM objects** to another thread to reuse a transaction or persistence context. In Spring, pass **IDs or immutable data** and let **the worker have its own transaction/persistence context**. The default `@PersistenceContext` in a singleton repository is a shared proxy capable of routing by transaction; it is **not** an exception allowing you to share a real Hibernate Session. At the same time, manage commit timing, lazy data, overload, durability, and concurrent updates.

### Official References

- [Jakarta Persistence 3.1 — Persistence Context, EntityManager, and Thread Safety](https://jakarta.ee/specifications/persistence/3.1/jakarta-persistence-spec-3.1.html)
- [Spring Framework — JPA: EntityManagerFactory, @PersistenceContext, and EXTENDED](https://docs.spring.io/spring-framework/reference/data-access/orm/jpa.html)
- [Spring Framework 6.1 — SharedEntityManagerCreator](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/orm/jpa/SharedEntityManagerCreator.html)
- [Spring Framework — Declarative Transactions and Thread-bound Context](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Hibernate ORM — Session Javadoc](https://docs.jboss.org/hibernate/orm/6.4/javadocs/org/hibernate/Session.html)
- [Hibernate ORM — Transactions and Session-per-application Anti-pattern](https://docs.jboss.org/hibernate/orm/6.4/userguide/html_single/Hibernate_User_Guide.html#transactions-basics)
