# Transaction Resources at Listener Execution Time

## 1. Transaction Resources Are Bound to the Thread

Spring transaction management typically binds active resources to the current thread via `TransactionSynchronizationManager`. For example, `DataSourceTransactionManager` binds a `ConnectionHolder` for the `DataSource`; a JPA transaction manager can bind an `EntityManagerHolder` for the `EntityManagerFactory`. As a result, `JdbcTemplate` or `EntityManager` obtains the exact resource participating in the transaction without passing a connection through every method call.

This state is thread-scoped. A thread may have an active transaction, registered transaction synchronizations, and corresponding resource holders. When the transaction finishes, Spring invokes the synchronization callbacks before cleaning up the resources from the thread.

This directly affects `@TransactionalEventListener`: whichever phase a listener runs in, you must understand what state the transaction and resources are in at that phase. In particular, after commit or rollback, resources may still remain bound to the thread while callbacks run, even though the transaction outcome has already been decided.

## 2. Resources at Each Phase

`@TransactionalEventListener` supports four phases. Resource holders may remain bound throughout callback execution; what matters is what state the transaction is in and whether another commit will happen.

| Phase | Transaction state | Appropriate resource usage |
|---|---|---|
| `BEFORE_COMMIT` | Transaction is still active, not yet committed. | Can use JDBC/JPA to participate in the current transaction. Changes are committed or rolled back with the original transaction. |
| `AFTER_COMMIT` | Commit has succeeded; Spring may keep resources bound to the thread until callbacks finish and cleanup runs. | Can read committed data. If writing new data is needed, open an independent transaction such as `REQUIRES_NEW`. |
| `AFTER_ROLLBACK` | Transaction has rolled back; resources may still be bound in the callback before cleanup. | Do not write through the rolled-back transaction's resource expecting data to commit. Open a new transaction if processing outcomes must be saved. |
| `AFTER_COMPLETION` | Transaction has ended, whether committed or rolled back; resource cleanup happens after the callback. | Use for observation or cleanup. If database writes are needed, use a new transaction. |

`AFTER_COMMIT` is the default phase. A common point of confusion is that a still-bound resource does not mean the transaction can commit again. When a post-commit callback runs, the original transaction has already ended in terms of outcome. Write commands using the old resource may run on that connection, but there is no subsequent commit to persist the changes.

## 3. What Is TransactionSynchronizationManager Used to Inspect?

`TransactionSynchronizationManager` provides diagnostic methods for the state on the current thread:

| Method | Meaning |
|---|---|
| `isActualTransactionActive()` | Whether the current thread is marked as having an actual active transaction. |
| `isSynchronizationActive()` | Whether transaction synchronization is active for registering callbacks. |
| `hasResource(key)` | Whether a resource holder is bound to the key, such as a `DataSource`. |
| `getResource(key)` | Retrieves the resource holder bound to the key. Should only be used in infrastructure integration when holder lifecycle is understood. |
| `getResourceMap()` | Views resources currently bound on the thread; useful for diagnostics, but do not dump entire holder objects into application logs. |

Example checking a specific `DataSource`:

```java
boolean active = TransactionSynchronizationManager.isActualTransactionActive();
boolean synchronization = TransactionSynchronizationManager.isSynchronizationActive();
boolean bound = TransactionSynchronizationManager.hasResource(dataSource);

System.out.printf(
    "active=%s, synchronization=%s, dataSourceBound=%s%n",
    active, synchronization, bound
);
```

This is information for the thread calling this code. It is not global application state. `hasResource(dataSource)` also requires the exact key used by the transaction manager; passing a wrapper or a different `DataSource` instance can return `false` even when the application has an active transaction on the managed datasource.

Do not manually call `unbindResource`, `releaseConnection`, or close a connection managed by Spring. The transaction manager is responsible for binding, commit/rollback, and cleanup. Manually detaching holders or closing connections can corrupt the active transaction.

## 4. Runnable Example with Java 17

The example uses Spring Context, Spring JDBC, and H2. The service inserts an order and publishes an event inside `TransactionTemplate`. The listener observes transaction state and `DataSource` binding in `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION`. After the transaction ends, the program checks the state again on the calling thread.

### Directory Structure

```text
transaction-resource-lifecycle/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── App.java
```

### pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>transaction-resource-lifecycle</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring-framework.version>6.2.0</spring-framework.version>
        <h2.version>2.3.232</h2.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>${spring-framework.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>${spring-framework.version}</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>${h2.version}</version>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.App</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### src/main/java/demo/App.java

```java
package demo;

import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class App {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            var jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute("create table orders (id varchar(40) primary key)");

            var service = context.getBean(OrderService.class);
            service.create("ORD-COMMIT", false);
            service.create("ORD-ROLLBACK", true);

            printState("AFTER_TRANSACTION", context.getBean(DataSource.class));

            Integer count = jdbc.queryForObject(
                "select count(*) from orders", Integer.class
            );
            System.out.println("committed orders=" + count);
        }
    }

    static void printState(String label, DataSource dataSource) {
        System.out.printf(
            "%s active=%s synchronization=%s resourceBound=%s%n",
            label,
            TransactionSynchronizationManager.isActualTransactionActive(),
            TransactionSynchronizationManager.isSynchronizationActive(),
            TransactionSynchronizationManager.hasResource(dataSource)
        );
    }

    @Configuration
    static class AppConfig {

        @Bean
        DataSource dataSource() {
            var dataSource = new DriverManagerDataSource();
            dataSource.setDriverClassName("org.h2.Driver");
            dataSource.setUrl("jdbc:h2:mem:txresources;DB_CLOSE_DELAY=-1");
            dataSource.setUsername("sa");
            dataSource.setPassword("");
            return dataSource;
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        TransactionTemplate transactionTemplate(PlatformTransactionManager manager) {
            return new TransactionTemplate(manager);
        }

        @Bean
        OrderService orderService(
                JdbcTemplate jdbc,
                TransactionTemplate transaction,
                ApplicationEventPublisher publisher,
                DataSource dataSource) {
            return new OrderService(jdbc, transaction, publisher, dataSource);
        }

        @Bean
        ResourceListener resourceListener(DataSource dataSource) {
            return new ResourceListener(dataSource);
        }
    }

    static class OrderService {
        private final JdbcTemplate jdbc;
        private final TransactionTemplate transaction;
        private final ApplicationEventPublisher publisher;
        private final DataSource dataSource;

        OrderService(
                JdbcTemplate jdbc,
                TransactionTemplate transaction,
                ApplicationEventPublisher publisher,
                DataSource dataSource) {
            this.jdbc = jdbc;
            this.transaction = transaction;
            this.publisher = publisher;
            this.dataSource = dataSource;
        }

        void create(String id, boolean rollback) {
            transaction.execute(status -> {
                jdbc.update("insert into orders(id) values (?)", id);
                printState("INSIDE_TRANSACTION " + id, dataSource);
                publisher.publishEvent(new OrderChanged(id));
                if (rollback) {
                    status.setRollbackOnly();
                }
                return null;
            });
        }

    }

    static class ResourceListener {
        private final DataSource dataSource;

        ResourceListener(DataSource dataSource) {
            this.dataSource = dataSource;
        }

        private void inspect(String phase, OrderChanged event) {
            System.out.printf(
                "%s %s active=%s synchronization=%s resourceBound=%s%n",
                phase,
                event.orderId(),
                TransactionSynchronizationManager.isActualTransactionActive(),
                TransactionSynchronizationManager.isSynchronizationActive(),
                TransactionSynchronizationManager.hasResource(dataSource)
            );
        }

        @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
        public void beforeCommit(OrderChanged event) {
            inspect("BEFORE_COMMIT", event);
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void afterCommit(OrderChanged event) {
            inspect("AFTER_COMMIT", event);
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
        public void afterRollback(OrderChanged event) {
            inspect("AFTER_ROLLBACK", event);
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
        public void afterCompletion(OrderChanged event) {
            inspect("AFTER_COMPLETION", event);
        }
    }

    public record OrderChanged(String orderId) {
    }
}
```

In the example, `DataSource` is injected directly into `OrderService` and used as the key when checking `TransactionSynchronizationManager.hasResource(dataSource)`. Therefore, the check uses the exact datasource managed by `DataSourceTransactionManager`.

### Running the Program

Stand in the directory containing `pom.xml` and run:

```bash
mvn -q compile exec:java
```

In each callback phase, `resourceBound` can still be `true` because Spring only cleans up resources after completing synchronization callbacks. With `AFTER_COMMIT`, the transaction has committed even though the holder is still bound. After `TransactionTemplate.execute` returns, Spring has cleaned up and the thread's state returns to having no transaction.

## 5. Why Do Writes in AFTER_COMMIT Require a New Transaction?

Spring invokes `AFTER_COMMIT` after the original transaction's commit has completed, but before cleaning up resources from the thread. Therefore, a JDBC/JPA command inside the callback can find the bound connection/entity manager. The presence of the resource only indicates that the holder is still on the thread; it does not reopen the original transaction and does not create a subsequent commit.

If the listener needs to write new data, call a separate service using `PROPAGATION_REQUIRES_NEW`:

```java
@Service
public class AuditWriter {
    private final AuditRepository repository;

    public AuditWriter(AuditRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(String orderId) {
        repository.insert(orderId, "ORDER_CREATED");
    }
}

@Component
public class OrderListener {
    private final AuditWriter auditWriter;

    public OrderListener(AuditWriter auditWriter) {
        this.auditWriter = auditWriter;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(OrderChanged event) {
        auditWriter.record(event.orderId());
    }
}
```

The `AuditWriter` service is a separate bean so the call goes through Spring's transaction proxy. Do not call `this.record(...)` from the same object because self-invocation does not trigger the proxy. The new transaction can commit independently; if it fails, the original business transaction has still committed and errors must be handled according to a separate policy.

## 6. Resources Do Not Automatically Propagate to Asynchronous Threads

Spring transaction resources are normally stored in `ThreadLocal`. Therefore, when a listener runs via `@Async` on an executor, the worker thread does not inherit the resource holders or transaction synchronization of the event-publishing thread.

Do not grab a `ConnectionHolder`, `EntityManagerHolder`, or transaction context from the event-publishing thread and pass it to another thread. If async work needs database access, have the worker call a service that opens an appropriate transaction on the worker thread itself. For example, a `@Transactional` method in a separate bean will start a new transaction when called through the proxy.

```java
@Component
public class AsyncOrderListener {
    private final OrderReadService readService;

    public AsyncOrderListener(OrderReadService readService) {
        this.readService = readService;
    }

    @Async("applicationEventExecutor")
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void handle(OrderChanged event) {
        readService.loadCommittedOrder(event.orderId());
    }
}

@Service
public class OrderReadService {
    @Transactional(readOnly = true)
    public Order loadCommittedOrder(String orderId) {
        // Read using a transaction on the executor thread.
        return repository.findById(orderId).orElseThrow();
    }
}
```

In this example, the transaction-bound callback is triggered after commit; `@Async` moves listener execution to the executor. `OrderReadService` opens its own read transaction on the worker thread. Configuration for `@EnableAsync`, transaction management, and the executor must be enabled in the appropriate context.

## 7. `fallbackExecution` and the No-Transaction Case

By default, `@TransactionalEventListener` only registers when an event is published inside an active transaction. If there is no transaction, the listener is not invoked.

When `fallbackExecution = true` is enabled, the listener can run even when there is no transaction:

```java
@TransactionalEventListener(fallbackExecution = true)
public void handleWithoutTransaction(OrderChanged event) {
    // No transaction: runs immediately via fallback.
}
```

In the fallback case, there is no transaction resource holder from a publishing transaction to inspect or reuse. If the listener needs to write to the database, open a separate transaction as needed.

## 8. Common Pitfalls

| Symptom | Cause and Solution |
|---|---|
| `hasResource(dataSource)` returns `false` | Checking the wrong key/DataSource instance, callback not running on a thread with a transaction, or event published outside a transaction. |
| Resource still bound after commit | This is the behavior during the callback stage before cleanup. Do not infer that the original transaction can commit again. |
| Wrote to database in `AFTER_COMMIT` but data is not committed | Resource is still bound, but the original transaction has already completed. Use `REQUIRES_NEW` for new write operations. |
| Resource does not appear in an `@Async` listener | Transaction context bound to the event-publishing thread does not propagate to the executor. Open a separate transaction on the worker thread. |
| Listener manually unbinds or closes connection | Corrupts the resource lifecycle managed by the transaction manager. Let Spring handle cleanup. |
| Listener runs outside a transaction when using fallback | `fallbackExecution=true` allows immediate execution, so there is no resource from a source transaction. |
| Parent or child context has different states | Resources and synchronizations belong to a specific thread/context and transaction manager; identify the exact managed datasource/entity manager factory. |

## 9. Key Takeaways

- Spring typically binds JDBC/JPA resources to the current thread using `TransactionSynchronizationManager`.
- `BEFORE_COMMIT` runs while the transaction is still active; write operations participate in the original transaction.
- `AFTER_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION` can run while resources are still bound, before cleanup.
- A resource still bound after commit does not mean the original transaction can commit further changes.
- Use `REQUIRES_NEW` when a post-commit listener needs to write new data.
- Transaction resources do not automatically propagate to `@Async` threads; workers need their own transactions if accessing the database.
- Do not manually unbind or close resources managed by the Spring transaction manager.