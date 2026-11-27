# Counting Affected Rows and Verifying Update Conditions

## 1. Objectives

In Spring Data JPA, a bulk `UPDATE` or `DELETE` query can affect multiple Entities with a single statement. A Repository method can return the number of affected Entities so the Service knows how many records the operation matched. Combining this count with a clear `WHERE` condition verifies state before modifying data.

After this lesson, you will be able to:
- Obtain the number of affected records from JPQL bulk updates/deletes.
- Use `@Modifying` and transactions properly in Spring Data JPA.
- Design `WHERE` conditions to update only records in the expected state.
- Distinguish affected row counts from pre-update count queries.
- Use `@Version` and version conditions to detect concurrent updates in bulk DML.
- Handle the persistence context after bulk updates/deletes.
- Determine when to roll back if the actual count differs from the expected count.
- Test affected counts and update conditions against the database.

## 2. Bulk update/delete and affected counts

Bulk DML is a JPQL `UPDATE` or `DELETE` statement applied directly to a set of Entities matching a condition. Spring Data JPA marks Repository methods with `@Modifying` to execute data-modifying statements instead of normal read queries.

Example:

```java
@Modifying
@Query("update PurchaseOrder o set o.status = :newStatus where o.status = :oldStatus")
int changeStatus(OrderStatus oldStatus, OrderStatus newStatus);
```

The `int` return type receives the number of affected Entities according to the bulk query execution result. `0` means no Entity matched the entire `WHERE` condition; a positive number indicates Entities were updated.

For bulk delete, receiving the count works similarly:

```java
@Modifying
@Query("delete from PurchaseOrder o where o.status = :status")
int deleteByStatus(OrderStatus status);
```

There is no need to load each Entity into memory and call `save()` or `delete()` in a loop if the business operation is truly a simple bulk modification. Bulk DML generally reduces round-trips and avoids per-Entity dirty checking.

## 3. Meaning and limitations of the affected count

With JPQL, `executeUpdate()` returns the number of Entities updated or deleted. Spring Data converts that result to the integer return type of the `@Modifying` method.

| Result | Typical interpretation |
| ---: | --- |
| `0` | No Entity satisfied all `WHERE` conditions at the time the statement ran. |
| `1` | One Entity was affected. |
| `n > 1` | `n` Entities were affected by the bulk statement. |

For updates by primary key, the expected result is usually `1`. If you receive `0`, the record may not exist, the current status may have changed, the version may no longer match, or another condition may no longer hold. The number `0` alone does not tell you which exact cause occurred.

For conditional bulk updates, the affected count is the number of Entities the statement acted upon. Do not interpret this number as the count of field values guaranteed to have changed in the way business logic expects. With native SQL, update counts also depend on JDBC driver and database reporting rules; verify semantics on the engine in use.

Do not use the affected count to infer that per-Entity side effects ran. Bulk DML bypasses Entity lifecycle callbacks and does not invoke logic in setters or Services for each record.

## 4. Verifying update conditions with WHERE

To avoid overwriting newer state, place business conditions inside the `UPDATE` statement itself. For example, only transition orders from `PENDING` to `EXPIRED` if the expiration time has passed:

```jpql
update PurchaseOrder o
set o.status = :expiredStatus
where o.status = :pendingStatus
  and o.expiresAt < :cutoff
```

The `o.status = :pendingStatus` condition verifies the status before updating. The `o.expiresAt < :cutoff` condition verifies the expiration time. The database checks the conditions and updates in the same statement.

This is safer than reading the status first in Java and then running an update without a status condition. Between the read and the write, another transaction could change the data.

### 4.1. Do not rely on a prior count to confirm an update

You can write a `count` query before the operation to see how many orders currently match. However, the count and the update are two separate statements:

1. Transaction A counts 10 expired `PENDING` orders.
2. Transaction B changes the status of 3 orders.
3. Transaction A runs the update and only 7 orders still match the condition.

Therefore, a prior count is only suitable for previews or point-in-time reporting. It does not guarantee how many rows will be updated afterward. **The affected count returned by the UPDATE statement itself is the result to use to confirm how many Entities the operation affected.**

If business logic requires an exact count or all-or-nothing updates, compare the affected count within the same transaction and roll back when the condition is not met.

### 4.2. Conditions should be sufficiently strict

The `WHERE` clause should include every precondition that must hold at write time, for example:

- Record ID.
- Tenant or data scope the caller is permitted to modify.
- Allowed current status for the transition.
- Expected version if using optimistic concurrency.
- Time conditions or other business rules.

Do not check conditions only in the Controller or Service and omit them from the update statement. Checking at write time helps reduce race conditions.

## 5. Example model

The example uses Java 17+, Spring Boot 3.5.x, Spring Data JPA, and Hibernate versions managed by Spring Boot. An order has a status, an expiration timestamp, and a version.

### 5.1. OrderStatus enum

`src/main/java/com/example/orders/OrderStatus.java`:

```java
package com.example.orders;

public enum OrderStatus {
    PENDING,
    PAID,
    EXPIRED,
    CANCELLED
}
```

### 5.2. PurchaseOrder entity

`src/main/java/com/example/orders/PurchaseOrder.java`:

```java
package com.example.orders;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.time.Instant;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private OrderStatus status;

    @Column(name = "expires_at", nullable = false)
    private Instant expiresAt;

    @Version
    @Column(nullable = false)
    private long version;

    protected PurchaseOrder() {
        // JPA requires a no-arg constructor.
    }

    public PurchaseOrder(OrderStatus status, Instant expiresAt) {
        if (status == null || expiresAt == null) {
            throw new IllegalArgumentException("Status and expiresAt are required");
        }
        this.status = status;
        this.expiresAt = expiresAt;
    }

    public Long getId() {
        return id;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public Instant getExpiresAt() {
        return expiresAt;
    }

    public long getVersion() {
        return version;
    }
}
```

`@Version` allows JPA to enforce optimistic locking when updating Entities normally. However, bulk JPQL updates do not automatically perform version checking or version incrementing like dirty checking on a managed Entity. This lesson handles it explicitly.

## 6. Repository returning the affected count

`src/main/java/com/example/orders/PurchaseOrderRepository.java`:

```java
package com.example.orders;

import java.time.Instant;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface PurchaseOrderRepository extends JpaRepository<PurchaseOrder, Long> {
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
           update PurchaseOrder o
           set o.status = :expiredStatus,
               o.version = o.version + 1
           where o.status = :pendingStatus
             and o.expiresAt < :cutoff
           """)
    int expirePendingOrders(
            @Param("pendingStatus") OrderStatus pendingStatus,
            @Param("expiredStatus") OrderStatus expiredStatus,
            @Param("cutoff") Instant cutoff);

    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
           update PurchaseOrder o
           set o.status = :newStatus,
               o.version = o.version + 1
           where o.id = :id
             and o.status = :expectedStatus
             and o.version = :expectedVersion
           """)
    int updateStatusIfCurrent(
            @Param("id") Long id,
            @Param("expectedStatus") OrderStatus expectedStatus,
            @Param("expectedVersion") long expectedVersion,
            @Param("newStatus") OrderStatus newStatus);

    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
           delete from PurchaseOrder o
           where o.status = :status
             and o.expiresAt < :cutoff
           """)
    int deleteExpiredOrders(
            @Param("status") OrderStatus status,
            @Param("cutoff") Instant cutoff);

    long countByStatusAndExpiresAtBefore(OrderStatus status, Instant cutoff);
}
```

Points to note:

- `@Modifying` informs Spring Data that this is a data-modifying statement.
- The `int` return type receives the number of updated or deleted Entities.
- `flushAutomatically = true` requests flushing pending changes before running the bulk query.
- `clearAutomatically = true` requests clearing the persistence context after the query runs to avoid continuing to read managed Entities with stale state.
- `version = version + 1` is written explicitly because bulk DML does not auto-increment versions.

The `countByStatusAndExpiresAtBefore` method only serves counting/preview purposes. Do not use that count result in place of the update's affected count.

## 7. Calling the Repository inside a transaction

Bulk DML methods should execute inside a transaction. You can place the transaction boundary in the Service to encompass both the operation and the verification step:

`src/main/java/com/example/orders/OrderMaintenanceService.java`:

```java
package com.example.orders;

import java.time.Instant;
import java.util.Objects;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderMaintenanceService {
    private final PurchaseOrderRepository repository;

    public OrderMaintenanceService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public int expirePendingOrders(Instant cutoff) {
        Objects.requireNonNull(cutoff, "cutoff is required");
        return repository.expirePendingOrders(
                OrderStatus.PENDING, OrderStatus.EXPIRED, cutoff);
    }

    @Transactional
    public void markPaid(Long id, long expectedVersion) {
        int affected = repository.updateStatusIfCurrent(
                id, OrderStatus.PENDING, expectedVersion, OrderStatus.PAID);

        if (affected == 0) {
            throw new IllegalStateException(
                    "Order is missing or no longer matches the expected state");
        }
        if (affected != 1) {
            throw new IllegalStateException(
                    "Expected to update one order but affected " + affected);
        }
    }
}
```

In `markPaid`, the condition on ID and version must match exactly one Entity. If the result is `0`, the record may not exist, the status may have changed, or the version may be stale. If the result is other than `1`, the Service throws an error because the unique primary key assumption no longer holds.

Throwing a runtime exception inside a default transaction causes Spring to roll back the transaction. You can replace `IllegalStateException` with a custom business exception and map it to HTTP 404 or 409 according to your API contract. You cannot determine the exact reason for `0` from the affected count alone; if you need to distinguish missing from stale state, design an additional read step or an appropriate business result.

## 8. Confirming a conditional update

Suppose a client reads an order and receives:

```text
id = 42
status = PENDING
version = 3
```

When the client submits a payment request, the update statement uses three conditions:

```jpql
update PurchaseOrder o
set o.status = PAID,
    o.version = o.version + 1
where o.id = 42
  and o.status = PENDING
  and o.version = 3
```

If no transaction modified the order after the read, the statement affects one Entity and the version increments from 3 to 4. If another transaction updated the order and changed the version to 4, the `o.version = 3` condition is no longer true; the statement affects 0 Entities.

This is the compare-and-set pattern: the update succeeds only when the current state still equals the value the caller read. It suits status transitions, order confirmation, inventory reservations, or operations that must detect changed data.

**Note:** because this is a bulk update, Hibernate does not automatically throw an optimistic locking exception on version mismatch. The Service must check the affected count and handle a `0` result.

## 9. When an exact count or all-or-nothing is required

For a bulk operation, business logic might require updating an exact `expectedCount` of records. For instance, a processing batch must update all 50 orders:

```java
@Transactional
public int expireExactly(
        Instant cutoff, int expectedCount) {
    int affected = repository.expirePendingOrders(
            OrderStatus.PENDING, OrderStatus.EXPIRED, cutoff);

    if (affected != expectedCount) {
        throw new IllegalStateException(
                "Expected " + expectedCount + " updates but affected " + affected);
    }

    return affected;
}
```

If the exception is unchecked and not swallowed inside the transaction, the transaction rolls back the entire operation. Ensure the Service method actually runs through the Spring transaction proxy; calling a `@Transactional` method from another method on the same instance (self-invocation) does not activate the proxy in the usual way.

If business logic accepts partial updates, do not roll back merely because the count is lower than expected. Return the actual count and let the caller decide the next step.

Do not fetch `countBy...()` first and assume the update will have the same count. If all-or-nothing verification under concurrent conditions is needed, use a single conditional statement, the affected count, a transaction, and locking/isolation mechanisms appropriate for the requirement.

## 10. Bulk DML and @Version

With normal Entity updates:

```java
PurchaseOrder order = repository.findById(id).orElseThrow();
order.markPaid();
```

JPA/Hibernate tracks the managed Entity. On flush, the provider normally generates an UPDATE conditioned on the current version, increments the version, and detects optimistic locking conflicts.

Bulk JPQL works differently:

- Does not load individual Entities for dirty checking.
- Does not automatically check `@Version` like normal Entity updates.
- Does not automatically increment the version attribute unless the statement specifies it.
- Does not call `@PreUpdate`, `@PostUpdate`, or corresponding callbacks for each Entity.

If a bulk update affects Entities with `@Version`, define an explicit version policy. When concurrent updates must be detected, add the expected version to `WHERE` and increment the version in `SET`, as in `updateStatusIfCurrent` above.

For multi-row bulk updates, you can increment each row's version with `o.version = o.version + 1`. However, the statement still does not perform per-Entity input version checks. It only increments versions so other transactions holding stale versions detect conflicts on their next normal Entity update.

## 11. Persistence context after bulk update/delete

Bulk DML runs directly against the database, so Entities already loaded in the persistence context may retain old values.

Example:

1. The Service loads a `PurchaseOrder` with status `PENDING` into the persistence context.
2. The Repository runs a bulk update changing the status in the database to `EXPIRED`.
3. The Service continues reading the previously loaded object and still sees `PENDING` because the managed object was not automatically synced with the bulk statement.

Three common ways to handle this:

- `clearAutomatically = true`: Spring Data clears the entire persistence context after the modifying query runs.
- Call `EntityManager.clear()` after the bulk query when you want to control clear timing yourself.
- Call `EntityManager.refresh(entity)` for a specific Entity that needs resynchronizing, if the Entity is still managed and the usage fits.

Clearing the entire persistence context detaches all currently managed Entities, including Entities unrelated to the bulk query. Therefore, consider the transaction scope and operation ordering.

`flushAutomatically = true` synchronizes pending changes before the bulk query. Combining flush before and clear after avoids both skipping unflushed changes and reading stale state from the persistence context.

## 12. Bulk delete and deleted counts

Bulk delete also returns the number of deleted Entities:

```java
@Modifying(flushAutomatically = true, clearAutomatically = true)
@Query("delete from PurchaseOrder o where o.status = :status and o.expiresAt < :cutoff")
int deleteExpiredOrders(
        @Param("status") OrderStatus status,
        @Param("cutoff") Instant cutoff);
```

If the method returns `int`, the Service can record the number of deleted orders and enforce business limits. However, bulk delete bypasses per-Entity lifecycle callbacks and does not apply Entity-lifecycle cascade remove as when calling `EntityManager.remove()` on each object.

If the database has foreign keys, deletion may be rejected while child records still reference the parent, unless the schema has an appropriate `ON DELETE CASCADE`. Database cascade rules are a separate mechanism, not JPA's cascade remove.

Do not use bulk delete if business logic requires running per-Entity deletion logic, emitting domain events for each record, or performing JPA cascades. In those cases, load and delete Entities in batches or design a separate processing workflow.

## 13. Distinguishing JPQL bulk count from JDBC batching

Both concepts can appear in the same application, yet they mean different things:

| Mechanism | How it works | Count result |
| --- | --- | --- |
| JPQL bulk update/delete | A single statement acting directly on the set of Entities matching `WHERE`. | `executeUpdate()`/`@Modifying` method returns the number of affected Entities. |
| JDBC batching | Groups multiple individual INSERT/UPDATE/DELETE statements to send in batches. | JDBC driver returns update counts per statement or batch result; semantics depend on driver. |
| Entity-by-Entity update | Loads each Entity, modifies the object, and lets dirty checking write back. | No automatic total affected count from an update method; Service counts processed Entities itself if needed. |

Do not confuse `hibernate.jdbc.batch_size` with the number of rows affected by a single JPQL bulk update. JDBC batching optimizes sending multiple write statements; bulk DML uses a single conditional statement across multiple Entities.

## 14. Testing affected counts with H2

The example uses `spring-boot-starter-data-jpa`, H2, and `spring-boot-starter-test`. `@DataJpaTest` creates a test slice and transaction for each test.

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:bulkdb;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=true
```

`src/test/java/com/example/orders/PurchaseOrderBulkDmlTest.java`:

```java
package com.example.orders;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

@DataJpaTest
class PurchaseOrderBulkDmlTest {
    @Autowired
    private PurchaseOrderRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    private PurchaseOrder order(OrderStatus status, String expiresAt) {
        return new PurchaseOrder(status, Instant.parse(expiresAt));
    }

    @Test
    void returnsNumberOfOrdersUpdatedByBulkQuery() {
        PurchaseOrder first = entityManager.persist(order(
                OrderStatus.PENDING, "2026-01-01T00:00:00Z"));
        PurchaseOrder second = entityManager.persist(order(
                OrderStatus.PENDING, "2026-01-02T00:00:00Z"));
        PurchaseOrder future = entityManager.persist(order(
                OrderStatus.PENDING, "2026-02-01T00:00:00Z"));
        PurchaseOrder paid = entityManager.persist(order(
                OrderStatus.PAID, "2026-01-01T00:00:00Z"));
        entityManager.flush();

        Long firstId = first.getId();
        Long secondId = second.getId();
        Long futureId = future.getId();
        Long paidId = paid.getId();

        int affected = repository.expirePendingOrders(
                OrderStatus.PENDING,
                OrderStatus.EXPIRED,
                Instant.parse("2026-01-15T00:00:00Z"));

        assertThat(affected).isEqualTo(2);
        assertThat(entityManager.find(PurchaseOrder.class, firstId).getStatus())
                .isEqualTo(OrderStatus.EXPIRED);
        assertThat(entityManager.find(PurchaseOrder.class, secondId).getStatus())
                .isEqualTo(OrderStatus.EXPIRED);
        assertThat(entityManager.find(PurchaseOrder.class, futureId).getStatus())
                .isEqualTo(OrderStatus.PENDING);
        assertThat(entityManager.find(PurchaseOrder.class, paidId).getStatus())
                .isEqualTo(OrderStatus.PAID);
    }

    @Test
    void conditionalUpdateUsesExpectedStatusAndVersion() {
        PurchaseOrder order = entityManager.persist(order(
                OrderStatus.PENDING, "2026-02-01T00:00:00Z"));
        entityManager.flush();
        Long id = order.getId();
        long initialVersion = order.getVersion();
        entityManager.clear();

        int firstUpdate = repository.updateStatusIfCurrent(
                id, OrderStatus.PENDING, initialVersion, OrderStatus.PAID);
        int staleUpdate = repository.updateStatusIfCurrent(
                id, OrderStatus.PENDING, initialVersion, OrderStatus.CANCELLED);

        assertThat(firstUpdate).isEqualTo(1);
        assertThat(staleUpdate).isZero();

        PurchaseOrder reloaded = entityManager.find(PurchaseOrder.class, id);
        assertThat(reloaded.getStatus()).isEqualTo(OrderStatus.PAID);
        assertThat(reloaded.getVersion()).isEqualTo(initialVersion + 1);
    }

    @Test
    void returnsZeroWhenNoOrderMatchesTheUpdateCondition() {
        int affected = repository.expirePendingOrders(
                OrderStatus.PENDING,
                OrderStatus.EXPIRED,
                Instant.parse("2026-01-15T00:00:00Z"));

        assertThat(affected).isZero();
    }

    @Test
    void returnsNumberOfOrdersDeletedByBulkQuery() {
        PurchaseOrder expiredOne = entityManager.persist(order(
                OrderStatus.EXPIRED, "2026-01-01T00:00:00Z"));
        PurchaseOrder expiredTwo = entityManager.persist(order(
                OrderStatus.EXPIRED, "2026-01-02T00:00:00Z"));
        PurchaseOrder stillValid = entityManager.persist(order(
                OrderStatus.EXPIRED, "2026-02-01T00:00:00Z"));
        entityManager.flush();

        Long firstId = expiredOne.getId();
        Long secondId = expiredTwo.getId();
        Long validId = stillValid.getId();

        int deleted = repository.deleteExpiredOrders(
                OrderStatus.EXPIRED, Instant.parse("2026-01-15T00:00:00Z"));

        assertThat(deleted).isEqualTo(2);
        assertThat(entityManager.find(PurchaseOrder.class, firstId)).isNull();
        assertThat(entityManager.find(PurchaseOrder.class, secondId)).isNull();
        assertThat(entityManager.find(PurchaseOrder.class, validId)).isNotNull();
    }
}
```

The first test verifies that the update returns `2` and only changes orders matching both status and cutoff. The second test verifies that the first update affects one Entity, the version increments by one, and the update using the stale version returns `0`. The third test confirms that when no rows match, the count is `0`. The last test checks the number of Entities deleted by bulk delete.

Run the tests from the directory containing `pom.xml`:

```bash
mvn test
```

The expected outcome is Maven finishing with `BUILD SUCCESS` and all four tests passing. This is the expected output for the example, not a build log executed in this environment.

## 15. Common mistakes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `@Query` method throws an error on update | Missing `@Modifying`, or query is still a SELECT. | Add `@Modifying` for JPQL UPDATE/DELETE. |
| Affected count is 0 | No Entity matched all `WHERE` conditions. | Check ID, status, cutoff, version, and tenant scope; do not guess a single cause. |
| Pre-count was 5 but update only affected 4 | Data changed between statements or another transaction updated first. | Use the UPDATE's affected count; place protective conditions directly in the statement. |
| Already-loaded Entity still shows old status | Bulk DML does not sync managed objects. | Flush beforehand if needed and clear/refresh the persistence context after the query. |
| Version did not increment after bulk update | Bulk DML does not auto-apply version management like dirty checking. | Increment version explicitly in `SET` when policy requires it. |
| Failed to detect stale update via `@Version` | Bulk DML bypasses automatic optimistic locking. | Put the expected version in `WHERE`, increment version, and check affected count. |
| Callbacks or cascades did not run | Bulk DML bypasses each Entity's lifecycle. | Use Entity-by-Entity operations when callbacks or JPA cascades are needed. |
| Transaction did not roll back when count was wrong | Exception was caught and not rethrown, or code ran outside the desired transaction boundary. | Throw an unchecked exception inside the transaction or configure rollback explicitly. |
| Bulk delete rejected by foreign key | Child records still reference the parent Entity. | Delete child data per business workflow or design an intentional FK cascade. |
| Native SQL returns unexpected affected count | JDBC driver/database has specific update count reporting rules. | Test against the real engine/driver and document system semantics. |

## 16. Implementation principles

1. Use an `int` return type on JPQL bulk update/delete methods to receive the number of affected Entities.
2. Put key business preconditions into `WHERE`, such as ID, tenant, status, and version.
3. Use the statement's own affected count to confirm the result; a prior count is only a preview due to possible race conditions.
4. When updating a single Entity, treat `1` as success; `0` as condition mismatch; any number greater than `1` as a violation of the unique key assumption.
5. If an exact count or all-or-nothing guarantee is required, compare the count inside the transaction and roll back on mismatch.
6. Remember that bulk DML bypasses dirty checking, callbacks, Entity cascades, and automatic optimistic locking.
7. If using `@Version`, add the version condition in `WHERE` and increment version in `SET` when compare-and-set is needed.
8. Use `flushAutomatically` and `clearAutomatically` intentionally; clearing detaches every managed Entity in the persistence context.
9. Do not use bulk DML when business logic needs per-Entity processing or per-record side effects.
10. Test counts of 0, 1, multiple records, stale versions, and deletes.
11. Verify SQL and affected counts on the actual database if the application uses native queries or driver-dependent behavior.

## 17. Completion checklist

- [ ] Can explain JPQL bulk UPDATE/DELETE and the role of `@Modifying`.
- [ ] Can receive the affected Entity count using an `int` return type.
- [ ] Can explain the meaning of counts equal to 0, 1, or greater than 1.
- [ ] Can place status/time/scope conditions directly in the `WHERE` clause.
- [ ] Understand why a pre-update count does not guarantee the post-update affected count.
- [ ] Can use transactions and roll back when actual count fails requirements.
- [ ] Can distinguish bulk DML from normal Entity updates.
- [ ] Can handle `@Version` explicitly in bulk updates when optimistic concurrency is required.
- [ ] Can synchronize the persistence context with flush, clear, or refresh.
- [ ] Understand that bulk delete does not run Entity cascades and callbacks.
- [ ] Can test affected counts and update conditions using `@DataJpaTest`.

Once complete, you can use affected counts to verify bulk operations, enforce update conditions directly in the database, and safely handle cases with no matching records or concurrently modified data.
