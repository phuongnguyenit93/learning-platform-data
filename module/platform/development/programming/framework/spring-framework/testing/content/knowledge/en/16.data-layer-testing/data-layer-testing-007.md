# Testing Entity Lifecycle Callbacks

Entity lifecycle callbacks are methods invoked by Jakarta Persistence at defined points while an entity is being persisted, updated, removed, or loaded from the database. Testing callbacks verifies that rules tied to the data lifecycle—such as setting default statuses, normalizing fields, or recording creation and update timestamps—are actually executed by the JPA provider when the application interacts with the persistence context.

In Spring, these tests typically use Spring Boot Test with `@DataJpaTest` and `TestEntityManager`, or use `EntityManager` inside a regular JPA test context. The key is letting the JPA provider execute the operations and crossing the appropriate `flush`, `clear`, and `find` boundaries. Calling callback methods directly does not test entity lifecycle behavior.

## 1. JPA Lifecycle Callbacks

Jakarta Persistence defines seven primary callback types:

| Callback | When It Runs | Typical Test Cases |
| --- | --- | --- |
| `@PrePersist` | Before a new entity is inserted | Setting default values, normalizing data before insert |
| `@PostPersist` | After the insert statement is executed | Verifying post-insert behavior or generated values |
| `@PreUpdate` | Before the update statement is executed | Updating derived fields before writing data |
| `@PostUpdate` | After the update statement is executed | Verifying post-update behavior |
| `@PreRemove` | Before an entity is removed | Checking rules prior to deletion |
| `@PostRemove` | After the delete statement is executed | Verifying post-delete behavior |
| `@PostLoad` | After entity state is loaded | Initializing transient state or validating data after load |

Callbacks can be declared directly on the entity or inside a listener class registered with `@EntityListeners`. For callbacks placed on the entity, the method returns `void`, takes no parameters, and is non-static. Example:

```java
@Entity
public class Account {
    @Id
    @GeneratedValue
    private Long id;

    private String status;

    @PrePersist
    private void initializeStatus() {
        if (status == null) {
            status = "NEW";
        }
    }
}
```

With an entity listener, the callback method accepts the entity as a parameter:

```java
public class AccountListener {
    @PrePersist
    public void beforePersist(Account account) {
        if (account.getStatus() == null) {
            account.setStatus("NEW");
        }
    }
}
```

```java
@Entity
@EntityListeners(AccountListener.class)
public class Account {
    // Entity fields and getters/setters
}
```

`@PreUpdate` does not mean it runs every time a setter is called. This callback runs when JPA prepares to write an entity change during flush. If the entity has not changed, the provider usually does not issue an update statement and `@PreUpdate` does not run. Likewise, `@PostUpdate` is tied to an update actually being executed.

## 2. Understanding Execution Boundaries

Operations like `persist`, modifying a managed entity, and `remove` typically only change state in the persistence context or schedule SQL operations. The JPA provider synchronizes those changes with the database on flush. Therefore, tests must flush explicitly at the point they want to verify.

```mermaid
flowchart TD
    A[New entity] --> B[@PrePersist]
    B --> C[INSERT on flush]
    C --> D[@PostPersist]
    E[Managed and modified entity] --> F[@PreUpdate]
    F --> G[UPDATE on flush]
    G --> H[@PostUpdate]
    I[Entity marked for removal] --> J[@PreRemove]
    J --> K[DELETE on flush]
    K --> L[@PostRemove]
    M[SELECT and load entity] --> N[@PostLoad]
```

Several points to distinguish when writing assertions:

- `flush()` asks the provider to synchronize the persistence context with the database within the current transaction. Flush is not synonymous with commit.
- `clear()` removes managed entities from the persistence context. Afterward, `find()` must reload the entity, letting the test inspect persisted data instead of re-reading the old in-memory object.
- Post-insert, post-update, or post-delete callbacks may have executed even if the transaction later rolls back. Thus, `@PostPersist` does not prove data was durably committed.
- `@PostLoad` is only meaningfully tested when the entity is actually reloaded. Calling `find()` for an entity still managed in the context may return the existing persistence context instance without triggering a new load.
- Depending on the primary key generation strategy, the timing of ID assignment can vary. Do not write `@PrePersist` assuming an auto-generated ID is always available.

## 3. Preparing the Test Environment in Spring

`@DataJpaTest` is a suitable choice when testing entities, mappings, repositories, and JPA callbacks in Spring Boot. This annotation creates a test slice for the JPA layer, configures the necessary persistence components, and normally runs each test in a transaction that rolls back after completion.

```java
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.beans.factory.annotation.Autowired;

@DataJpaTest
class AccountLifecycleTest {
    @Autowired
    private TestEntityManager entityManager;
}
```

`TestEntityManager` provides convenient operations such as `persistAndFlush`, `flush`, `clear`, `remove`, and `find`. Without Spring Boot, you can configure a test context with Spring Test, inject `EntityManager` via `@PersistenceContext`, and perform the same JPA operations.

A test slice may use an embedded database such as H2 if its dependency is present in the project. This is fast and useful for mapping checks, but if the application depends on SQL syntax, data types, constraints, or behaviors specific to PostgreSQL, MySQL, or another DBMS, also run integration tests against the exact target DBMS, for example via Testcontainers.

The examples below use `jakarta.persistence`, suitable for Spring Boot 3 and later. Spring Boot 2 or legacy JPA projects may need to adjust imports to `javax.persistence` according to their version.

## 4. Example Entity with Callbacks

The `Customer` example sets a default status and normalizes the name before insert, re-normalizes the name before update, and records executed callbacks via transient fields to demonstrate testing.

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.PostLoad;
import jakarta.persistence.PostPersist;
import jakarta.persistence.PostRemove;
import jakarta.persistence.PostUpdate;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreRemove;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import jakarta.persistence.Transient;

import java.util.Locale;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false)
    private String normalizedName;

    @Column(nullable = false)
    private String status;

    @Transient
    private boolean loaded;

    @Transient
    private boolean postPersistCalled;

    @Transient
    private boolean postUpdateCalled;

    @Transient
    private boolean preRemoveCalled;

    @Transient
    private boolean postRemoveCalled;

    protected Customer() {
    }

    public Customer(String name) {
        this.name = name;
    }

    @PrePersist
    private void beforePersist() {
        if (status == null) {
            status = "NEW";
        }
        normalizedName = normalize(name);
    }

    @PostPersist
    private void afterPersist() {
        postPersistCalled = true;
    }

    @PreUpdate
    private void beforeUpdate() {
        normalizedName = normalize(name);
    }

    @PostUpdate
    private void afterUpdate() {
        postUpdateCalled = true;
    }

    @PreRemove
    private void beforeRemove() {
        preRemoveCalled = true;
    }

    @PostRemove
    private void afterRemove() {
        postRemoveCalled = true;
    }

    @PostLoad
    private void afterLoad() {
        loaded = true;
    }

    private static String normalize(String value) {
        return value == null ? null : value.trim().toLowerCase(Locale.ROOT);
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getNormalizedName() {
        return normalizedName;
    }

    public String getStatus() {
        return status;
    }

    public boolean isLoaded() {
        return loaded;
    }

    public boolean isPostPersistCalled() {
        return postPersistCalled;
    }

    public boolean isPostUpdateCalled() {
        return postUpdateCalled;
    }

    public boolean isPreRemoveCalled() {
        return preRemoveCalled;
    }

    public boolean isPostRemoveCalled() {
        return postRemoveCalled;
    }
}
```

The `@Transient` flags are solely for test illustration and are not persisted to the table. In real applications, prefer asserting observable business effects, such as default values or normalized fields. Avoid adding test flags into production entities just to count callback invocations.

## 5. Testing Callbacks on Insert and Load

The first test confirms `@PrePersist` sets values before insert and `@PostPersist` ran after insert. Then the test clears the persistence context and reloads the entity to verify `@PostLoad`.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class CustomerLifecycleTest {
    @Autowired
    private TestEntityManager entityManager;

    @Test
    void appliesPersistAndLoadCallbacks() {
        Customer customer = new Customer("  An Nguyen  ");

        entityManager.persistAndFlush(customer);

        Long id = customer.getId();
        assertThat(customer.getStatus()).isEqualTo("NEW");
        assertThat(customer.getNormalizedName()).isEqualTo("an nguyen");
        assertThat(customer.isPostPersistCalled()).isTrue();

        entityManager.clear();

        Customer reloaded = entityManager.find(Customer.class, id);

        assertThat(reloaded).isNotNull();
        assertThat(reloaded.getNormalizedName()).isEqualTo("an nguyen");
        assertThat(reloaded.isLoaded()).isTrue();
    }
}
```

`persistAndFlush` makes clear when the insert executes, allowing the test to verify insert-related callbacks. `clear()` is essential for testing load: skipping this step allows `find()` to return the instance already sitting in the persistence context, failing to prove `@PostLoad` ran.

## 6. Testing Callbacks on Update

To test `@PreUpdate`, first save the entity, then modify a field so the entity becomes dirty and flush. The test should also re-read data after `clear()` to verify the value was written to the database.

```java
@Test
void normalizesNameBeforeUpdate() {
    Customer customer = new Customer("Lan");
    entityManager.persistAndFlush(customer);

    Long id = customer.getId();
    customer.setName("  BINH  ");

    entityManager.flush();

    assertThat(customer.getNormalizedName()).isEqualTo("binh");
    assertThat(customer.isPostUpdateCalled()).isTrue();

    entityManager.clear();

    Customer reloaded = entityManager.find(Customer.class, id);
    assertThat(reloaded.getName()).isEqualTo("  BINH  ");
    assertThat(reloaded.getNormalizedName()).isEqualTo("binh");
}
```

If a test only calls `setName()` and checks immediately, it only confirms the setter works; it has not confirmed JPA invoked `@PreUpdate`. Without flushing, the callback may not have run yet. Without clearing and reloading, the test may simply read the value off the managed object. Both steps ensure the test verifies actual data-layer behavior.

## 7. Testing Callbacks on Remove

For deletion, call `remove()` and flush so the provider executes the delete. You can verify pre- and post-delete callbacks on the removed instance, then confirm the record is absent upon reloading.

```java
@Test
void runsRemoveCallbacksAndDeletesTheRow() {
    Customer customer = new Customer("Mai");
    entityManager.persistAndFlush(customer);
    Long id = customer.getId();

    entityManager.remove(customer);
    entityManager.flush();

    assertThat(customer.isPreRemoveCalled()).isTrue();
    assertThat(customer.isPostRemoveCalled()).isTrue();

    entityManager.clear();
    assertThat(entityManager.find(Customer.class, id)).isNull();
}
```

Checking both callbacks and query results separates two questions: whether the callbacks were invoked, and whether the deletion was actually synchronized to the database. If the application uses cascade remove, create related data in the test to verify the exact cascade path the application uses.

## 8. Testing Entity Listeners and Spring Data Auditing

When callback logic lives in a listener class, tests should still trigger operations via `EntityManager` or a repository. This confirms the listener is attached to the entity and the JPA provider invokes it at the right time. If the listener uses a Spring-managed dependency, check the project's JPA/Spring integration config; injection support depends on provider configuration and platform version.

Spring Data JPA auditing is a common use case for callback listeners. `AuditingEntityListener` handles annotations such as `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy`, and `@LastModifiedBy`. Auditing setup typically requires `@EnableJpaAuditing` and registering the listener on the entity:

```java
@Entity
@EntityListeners(AuditingEntityListener.class)
public class OrderRecord {
    @Id
    @GeneratedValue
    private Long id;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant updatedAt;
}
```

In a `@DataJpaTest` slice, make sure the configuration enabling auditing is included in the test context, such as through an imported test configuration. After persisting and flushing, inspect `createdAt`; after modifying the entity and flushing, inspect `updatedAt`. For time testing, configure a controllable time source if the project supports `DateTimeProvider` or `Clock`. Avoid using `Thread.sleep()` to wait for timestamps to change, as that makes tests slow and flaky.

## 9. Common Testing Mistakes

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `@PreUpdate` does not run | Entity unchanged, detached, or not flushed | Modify a persistent field on a managed entity and call `flush()` |
| `@PostLoad` does not run on `find()` | Entity is already in the persistence context | Call `clear()` before reloading |
| Callback value is right on the object yet uncertain if saved | Inspecting only the managed instance | Flush, clear, then re-query |
| `@PostPersist` ran yet record is gone after test | Test transaction rolled back | Distinguish post-SQL callback from transaction commit |
| Delete test still finds the record | Not flushed or reading stale state in persistence context | Flush, clear, then `find()` again |
| Time test passes intermittently | Using system time with overly tight comparisons | Use a controllable clock or assertions with reasonable tolerance |
| Test passes on H2 yet fails in production | Dialect, data type, or DBMS behavior differences | Run integration tests with the same production database type |

Another pitfall is putting too much logic inside callbacks. JPA callbacks execute during persistence context management, so keep them short and focused on the entity's own state. Avoid running queries through `EntityManager`, making network calls, sending emails, or mutating other entities inside callbacks. Actions depending on commit should be handled via appropriate application-layer mechanisms, such as post-commit transactional events or a transactional outbox.

If a callback throws an exception, the persistence operation can fail and the transaction may be marked for rollback. When this is a business behavior to guarantee, write a test that triggers the exact JPA operation and asserts the exception at the `flush()` boundary; do not invoke the callback method directly to simulate the error.

## 10. Principles for Writing Reliable Tests

1. Use real entities and a real JPA provider in the test context so callbacks run through the actual lifecycle.
2. Clearly identify which operation is being tested: insert, update, remove, or load.
3. Use `persistAndFlush()` or `flush()` to trigger synchronization when testing write callbacks.
4. Use `clear()` then `find()` to verify persisted state and trigger a fresh load.
5. Verify observable business outcomes; check flags or invocation counts only when that is genuinely the test's goal.
6. Remember `@DataJpaTest` transactions usually roll back after the test. A callback running does not mean the transaction committed.
7. Use a database close to the deployment environment when logic depends on DBMS-specific behavior.

A solid callback test demonstrates the behavioral chain from the persistence operation, through the callback, to the entity state or reloaded data. When tests explicitly control flushing and the persistence context, callback bugs surface at the right data layer and are much easier to pinpoint.
