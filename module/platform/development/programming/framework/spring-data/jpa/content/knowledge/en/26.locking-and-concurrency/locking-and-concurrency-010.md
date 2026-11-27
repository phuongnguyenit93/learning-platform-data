# Concurrency Testing for Inventory, Balances, and Reservations

## Objectives

In multi-user applications, two requests can read the same state and then both write results. Without appropriate protection, inventory can go negative, accounts can overdraw their balance, or the same seat can be booked twice. These bugs are race conditions: the outcome depends on the interleaving order of transactions.

Concurrency testing must prove that **data invariants** hold true when multiple transactions contend for the same resource. This article builds testing approaches for three scenarios:

- **Inventory:** multiple orders purchasing the same SKU; available quantity must never become negative and total sold quantity must not exceed initial stock.
- **Balances:** multiple concurrent money transfers; accounts must never go negative and total money across accounts must be conserved.
- **Reservations:** multiple requests booking the same seat; at most one reservation is recorded for a given event and seat.

The three scenarios require different protection mechanisms: atomic conditional updates in the database, pessimistic locks when reading and updating multiple rows, and unique constraints for resources that can be booked only once. Tests must run across multiple threads with independent transactions and verify the final state in the database.

## 1. Why sequential tests miss race conditions

Suppose inventory has 1 item left. Two requests both buy one item. If the code reads and then writes in two steps:

```java
InventoryItem item = repository.findById(id).orElseThrow();
if (item.getAvailable() > 0) {
    item.setAvailable(item.getAvailable() - 1);
    repository.save(item);
}
```

In a sequential run, the first request reduces stock from 1 to 0. The second request reads 0 and is rejected. A single-threaded test passes.

Yet two transactions can interleave as follows:

```text
Transaction A                 Transaction B
---------------------------   ---------------------------
SELECT available -> 1
                              SELECT available -> 1
available = 0
                              available = 0
UPDATE available = 0
                              UPDATE available = 0
COMMIT                        COMMIT
```

Both requests can report purchase success even though only one item remained. This is a lost update and overselling. Sequential testing cannot produce this interleaving.

With balances, two withdrawal requests can both read a stale balance and overwrite results. With reservations, two requests can both see the seat unbooked and both insert a reservation. Therefore, tests need multiple threads and separate transactions, followed by verifying invariants in the database.

## 2. Defining invariants before writing tests

Do not start with the question "which thread should win?". Execution order across threads is not guaranteed. Start with the data conditions that must always hold true.

| Domain | Invariant to preserve | What tests should verify |
| --- | --- | --- |
| Inventory | `available >= 0` | Successful purchases do not exceed initial quantity; final remaining stock is accurate. |
| Balances | `balance >= 0` and total money conserved during internal transfers | No negative account; total debits equal total credits; failed transactions leave balances unchanged. |
| Seat booking | One `(eventId, seatNumber)` has at most one reservation | Out of multiple requests for the same seat, only one commits and the database has exactly one row. |
| Capacity-based booking | `remaining >= 0` | Successful bookings do not exceed capacity; decrementing capacity and inserting the reservation occur in the same transaction. |

Invariants should be protected in the database, not just in Java. Pre-checking with `existsBy...` or reading a balance before deciding is insufficient against race conditions because another transaction can write right after that check.

## 3. Choosing protection mechanisms by contention type

### Inventory: a single conditional UPDATE

For inventory counters, a clean and safe approach is an atomic conditional update:

```sql
update inventory_items
set available = available - :quantity
where id = :id
  and available >= :quantity;
```

The database performs the check and the decrement in a single statement. Each request receives the updated row count:

- `1`: stock deduction succeeded.
- `0`: no matching item or insufficient stock.

There is no gap between SELECT and UPDATE for another request to sneak in with the same stale value. Validate `quantity > 0` in the service and add a database CHECK constraint `available >= 0` as a final layer of invariant protection.

### Balances: pessimistic or optimistic locking

Money transfers usually must read balances, validate conditions, and update two accounts in the same transaction. Two common strategies:

- **Pessimistic locking:** acquire `PESSIMISTIC_WRITE` on the account rows before checking balance and writing. Other transactions must wait until the locks are released.
- **Optimistic locking:** add `@Version`; if a transaction writes against an old version, one transaction is rejected with an optimistic locking error. The application can retry the entire use case in a new transaction if allowed by business logic.

For transfers between two accounts, when using pessimistic locks, always lock in the same ID order (for example, lower ID first, higher ID second). This reduces deadlock risk when two transfers run in opposite directions.

Debit and credit must sit in one transaction. If debit succeeds while credit fails, the transaction must roll back both.

### Seat booking: unique constraint

For a specific seat in an event, place a unique constraint on the `(event_id, seat_number)` pair. Two transactions can try inserting simultaneously, but the database permits only one row to exist.

```sql
alter table reservations
add constraint uk_event_seat unique (event_id, seat_number);
```

The application may pre-check to show friendly messages, yet the unique constraint is the final guarantee when two requests arrive concurrently. On constraint violation, Spring typically translates the persistence error into `DataIntegrityViolationException`.

For capacity-based booking rather than individual seats, use a conditional UPDATE with `remaining > 0` to decrement capacity. If a reservation record must be created, decrementing capacity and inserting the reservation must occur in the same transaction so capacity is never deducted without creating the booking.

## 4. Transaction and thread boundaries in tests

Each competing operation must run in an independent transaction. A practical approach is invoking a Spring service bean with a `@Transactional` method from worker threads. The transaction interceptor opens a separate transaction for each call.

Test classes should not put `@Transactional` on this kind of test:

- The test's transaction runs on the test thread and does not automatically propagate to worker threads.
- Uncommitted setup data may not be visible to worker transactions.
- Final assertions might read uncommitted data or roll back when the test finishes.

Keep the test non-transactional, use `saveAndFlush` or committed setup transactions, invoke the service from multiple threads, wait for all Futures to complete, and then read the final state via repositories.

Do not share an `EntityManager`, Hibernate `Session`, or managed entities across threads. EntityManager is not thread-safe. Each worker calls services/repositories through Spring proxies to receive a persistence context bound to its own transaction.

## 5. Creating controlled concurrency

Use `ExecutorService` to spawn workers and `CountDownLatch` as a starting gate:

1. Create a thread pool sized to the number of workers.
2. Each worker signals readiness via `ready.countDown()`.
3. Workers wait on `start.await()`.
4. The test waits until all workers are ready and calls `start.countDown()` once.
5. Collect results via `Future.get()` with a timeout.
6. Shut down the executor in `finally`.

Do not use `Thread.sleep()` to "hope" two transactions collide. Sleeps depend on machine speed and make tests flaky. A start gate makes workers start together and creates intentional contention.

For a specific race condition requiring exact synchronization between read and write steps, you can use `CyclicBarrier` or `CountDownLatch` in the test harness to pause two transactions right after reading. Never put barriers in production services. The optimistic locking section later explains how to control this interleaving.

## 6. Designing the inventory test

Suppose initial stock is 10 and 20 concurrent requests arrive, each buying one unit. Valid outcome:

- Exactly 10 requests succeed.
- The remaining 10 requests are rejected as out of stock.
- Final stock equals 0.
- At no point does the database store `available < 0`.

The test should check both the count of successful requests and re-read the stock value from the database. Do not check only exceptions or return values in individual threads, because bugs can reside in committed state.

### Why use row count?

A conditional UPDATE returns the number of rows actually updated. This is the direct signal for the service to decide success or out-of-stock. If using `findById`, checking in Java, and calling `save`, two transactions can both pass the check before either writes.

## 7. Designing the transfer test

Suppose account A has 100 and account B has 100. 20 concurrent requests transfer 10 from A to B.

Valid outcome:

- Exactly 10 transfers succeed.
- A has balance 0; B has balance 200.
- Total money remains 200.
- No negative account balance.
- The 10 rejected transfers leave balances unchanged.

This test creates contention on the same two rows. Pessimistic locking ensures each transaction checks the balance after acquiring locks. Consistent lock ordering prevents opposite-direction transfers from locking A/B in two different orders.

With optimistic locking, an equivalent test must make two transactions read the same version before either writes. One transaction commits; the other must receive an optimistic lock error. If the application retries, retries must re-run the entire use case in a new transaction with bounded attempts.

## 8. Designing the seat reservation test

Two workers simultaneously book `eventId=77`, `seatNumber=A-10`. The database has a unique constraint on that pair.

Valid outcome:

- One request commits successfully.
- One request receives a duplicate key/constraint error.
- `countByEventIdAndSeatNumber(77, "A-10")` equals 1.

Do not rely on both requests calling `existsBy...` before inserting. Both can see it missing at the same time. Pre-checking only helps with early user feedback; the unique constraint resolves contention.

If the API supports retries when a client misses a response, add an idempotency key with a unique constraint. When the same request is resent, the system returns the processed request's result rather than creating a new booking.

## 9. Complete example with Java 17+, Spring Boot, and H2

The example uses three different strategies in the same application:

- Inventory: conditional atomic UPDATE.
- Account: two `PESSIMISTIC_WRITE` locks ordered by ID.
- Reservation: unique constraint on event and seat.

The integration test runs 20 concurrent workers for inventory and balances, and two workers for the same seat. Each service method is invoked through a Spring bean so every call receives its own transaction.

### Project structure

```text
concurrency-tests/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/concurrency/
    │   │   ├── ConcurrencyApplication.java
    │   │   ├── InventoryItem.java
    │   │   ├── Account.java
    │   │   ├── Reservation.java
    │   │   ├── InventoryRepository.java
    │   │   ├── AccountRepository.java
    │   │   ├── ReservationRepository.java
    │   │   ├── InventoryService.java
    │   │   ├── AccountTransferService.java
    │   │   └── ReservationService.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/concurrency/ConcurrencyIntegrationTest.java
```

### `pom.xml`

```xml
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
    <artifactId>concurrency-tests</artifactId>
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
```

### `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:concurrency;DB_CLOSE_DELAY=-1;LOCK_TIMEOUT=30000
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=30
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
logging.level.org.hibernate.SQL=DEBUG
```

`LOCK_TIMEOUT` and the connection pool are sized generously so test workers can wait on one another during contention. Suitable production values must be based on the real database, latency, and connection limits.

### `ConcurrencyApplication.java`

```java
package com.example.concurrency;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ConcurrencyApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConcurrencyApplication.class, args);
    }
}
```

### `InventoryItem.java`

```java
package com.example.concurrency;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.Check;

@Entity
@Table(name = "inventory_items")
@Check(constraints = "available >= 0")
public class InventoryItem {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 60)
    private String sku;

    @Column(nullable = false)
    private int available;

    protected InventoryItem() {
    }

    public InventoryItem(String sku, int available) {
        this.sku = sku;
        this.available = available;
    }

    public Long getId() {
        return id;
    }

    public int getAvailable() {
        return available;
    }
}
```

`@Check` generates a CHECK constraint via Hibernate schema generation. For production, manage constraints with migrations such as Flyway or Liquibase so the schema is controlled and deployed consistently.

### `Account.java`

```java
package com.example.concurrency;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import org.hibernate.annotations.Check;

@Entity
@Table(name = "accounts")
@Check(constraints = "balance >= 0")
public class Account {
    @Id
    private Long id;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal balance;

    protected Account() {
    }

    public Account(Long id, BigDecimal balance) {
        this.id = id;
        this.balance = balance;
    }

    public Long getId() {
        return id;
    }

    public BigDecimal getBalance() {
        return balance;
    }

    public void debit(BigDecimal amount) {
        balance = balance.subtract(amount);
    }

    public void credit(BigDecimal amount) {
        balance = balance.add(amount);
    }
}
```

Account IDs are pre-assigned so the example focuses on ordered locking of two rows. Real systems can use auto-generated IDs; the principle of locking in a consistent order remains the same.

### `Reservation.java`

```java
package com.example.concurrency;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

@Entity
@Table(
    name = "reservations",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_reservation_event_seat",
        columnNames = {"event_id", "seat_number"}
    )
)
public class Reservation {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "event_id", nullable = false)
    private Long eventId;

    @Column(name = "seat_number", nullable = false, length = 20)
    private String seatNumber;

    protected Reservation() {
    }

    public Reservation(Long eventId, String seatNumber) {
        this.eventId = eventId;
        this.seatNumber = seatNumber;
    }
}
```

A unique constraint guarantees a seat can be booked only once. If reservations have a CANCELLED status and seats may be rebooked after cancellation, the design needs a conditional/partial unique index by status if supported by the database, or a dedicated seat inventory row to lock and transition state.

### `InventoryRepository.java`

```java
package com.example.concurrency;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface InventoryRepository extends JpaRepository<InventoryItem, Long> {
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("update InventoryItem i "
         + "set i.available = i.available - :quantity "
         + "where i.id = :id and i.available >= :quantity")
    int decreaseIfAvailable(
            @Param("id") Long id,
            @Param("quantity") int quantity
    );
}
```

Bulk updates bypass managed entity state in the persistence context. `clearAutomatically = true` clears the persistence context after the query to avoid using stale entities; if the fragment/service manages other entities, consider the clear scope and flush before running bulk updates.

### `AccountRepository.java`

```java
package com.example.concurrency;

import java.util.Optional;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface AccountRepository extends JpaRepository<Account, Long> {
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select a from Account a where a.id = :id")
    Optional<Account> findForUpdateById(@Param("id") Long id);
}
```

`PESSIMISTIC_WRITE` asks the database to lock the read row so other transactions cannot update that row concurrently in the same manner. The lock is held until the transaction commits or rolls back.

### `ReservationRepository.java`

```java
package com.example.concurrency;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ReservationRepository extends JpaRepository<Reservation, Long> {
    long countByEventIdAndSeatNumber(Long eventId, String seatNumber);
}
```

### `InventoryService.java`

```java
package com.example.concurrency;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {
    private final InventoryRepository repository;

    public InventoryService(InventoryRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void purchase(Long itemId, int quantity) {
        if (itemId == null || quantity <= 0) {
            throw new IllegalArgumentException("itemId and positive quantity are required");
        }

        int changed = repository.decreaseIfAvailable(itemId, quantity);
        if (changed != 1) {
            throw new OutOfStockException("Item not found or insufficient stock");
        }
    }

    public static class OutOfStockException extends RuntimeException {
        public OutOfStockException(String message) {
            super(message);
        }
    }
}
```

The service does not read stock before updating. The database checks `available >= quantity` and deducts in a single statement. If no row was updated, the service reports out-of-stock or item not found.

### `AccountTransferService.java`

```java
package com.example.concurrency;

import java.math.BigDecimal;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AccountTransferService {
    private final AccountRepository repository;

    public AccountTransferService(AccountRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void transfer(Long fromId, Long toId, BigDecimal amount) {
        if (fromId == null || toId == null || amount == null
                || amount.signum() <= 0 || fromId.equals(toId)) {
            throw new IllegalArgumentException("Invalid transfer request");
        }

        // Every transfer locks the lower ID first to reduce deadlock risk.
        Long firstId = Math.min(fromId, toId);
        Long secondId = Math.max(fromId, toId);

        Account first = repository.findForUpdateById(firstId)
                .orElseThrow(() -> new IllegalArgumentException("Account not found: " + firstId));
        Account second = repository.findForUpdateById(secondId)
                .orElseThrow(() -> new IllegalArgumentException("Account not found: " + secondId));

        Account source = fromId.equals(firstId) ? first : second;
        Account target = fromId.equals(firstId) ? second : first;

        if (source.getBalance().compareTo(amount) < 0) {
            throw new InsufficientFundsException("Insufficient balance");
        }

        source.debit(amount);
        target.credit(amount);
    }

    public static class InsufficientFundsException extends RuntimeException {
        public InsufficientFundsException(String message) {
            super(message);
        }
    }
}
```

There is no need to call `save()` for the two accounts already managed in the transaction; dirty checking persists changes on flush/commit. If crediting or committing fails, the transaction rolls back both debit and credit.

### `ReservationService.java`

```java
package com.example.concurrency;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ReservationService {
    private final ReservationRepository repository;

    public ReservationService(ReservationRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void reserve(Long eventId, String seatNumber) {
        if (eventId == null || seatNumber == null || seatNumber.isBlank()) {
            throw new IllegalArgumentException("eventId and seatNumber are required");
        }

        // Flush inside the service so the unique-key violation is raised here.
        repository.saveAndFlush(new Reservation(eventId, seatNumber));
    }
}
```

No Java locks or `synchronized` blocks are needed to enforce uniqueness across multiple application instances. The unique constraint operates in the database and protects even when requests hit different servers.

### `ConcurrencyIntegrationTest.java`

```java
package com.example.concurrency;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataIntegrityViolationException;

@SpringBootTest
class ConcurrencyIntegrationTest {
    @Autowired
    private InventoryRepository inventoryRepository;

    @Autowired
    private InventoryService inventoryService;

    @Autowired
    private AccountRepository accountRepository;

    @Autowired
    private AccountTransferService transferService;

    @Autowired
    private ReservationRepository reservationRepository;

    @Autowired
    private ReservationService reservationService;

    @BeforeEach
    void cleanDatabase() {
        reservationRepository.deleteAllInBatch();
        inventoryRepository.deleteAllInBatch();
        accountRepository.deleteAllInBatch();
    }

    @Test
    void concurrentPurchasesNeverOversell() throws Exception {
        InventoryItem item = inventoryRepository.saveAndFlush(
                new InventoryItem("SKU-1", 10));

        List<Boolean> outcomes = runConcurrently(20, () -> {
            try {
                inventoryService.purchase(item.getId(), 1);
                return true;
            } catch (InventoryService.OutOfStockException expected) {
                return false;
            }
        });

        long successful = outcomes.stream().filter(Boolean::booleanValue).count();
        assertThat(successful).isEqualTo(10L);
        assertThat(inventoryRepository.findById(item.getId())
                .orElseThrow().getAvailable()).isZero();
    }

    @Test
    void concurrentTransfersCannotOverspendOrCreateMoney() throws Exception {
        accountRepository.saveAllAndFlush(List.of(
                new Account(1L, new BigDecimal("100.00")),
                new Account(2L, new BigDecimal("100.00"))
        ));

        List<Boolean> outcomes = runConcurrently(20, () -> {
            try {
                transferService.transfer(1L, 2L, new BigDecimal("10.00"));
                return true;
            } catch (AccountTransferService.InsufficientFundsException expected) {
                return false;
            }
        });

        long successful = outcomes.stream().filter(Boolean::booleanValue).count();
        assertThat(successful).isEqualTo(10L);

        BigDecimal balanceA = accountRepository.findById(1L)
                .orElseThrow().getBalance();
        BigDecimal balanceB = accountRepository.findById(2L)
                .orElseThrow().getBalance();

        assertThat(balanceA).isEqualByComparingTo("0.00");
        assertThat(balanceB).isEqualByComparingTo("200.00");
        assertThat(balanceA.add(balanceB)).isEqualByComparingTo("200.00");
    }

    @Test
    void theSameSeatCanBeReservedOnlyOnce() throws Exception {
        List<Boolean> outcomes = runConcurrently(2, () -> {
            try {
                reservationService.reserve(77L, "A-10");
                return true;
            } catch (DataIntegrityViolationException expected) {
                return false;
            }
        });

        long successful = outcomes.stream().filter(Boolean::booleanValue).count();
        assertThat(successful).isEqualTo(1L);
        assertThat(reservationRepository.countByEventIdAndSeatNumber(77L, "A-10"))
                .isEqualTo(1L);
    }

    private static <T> List<T> runConcurrently(
            int workerCount, Callable<T> action) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(workerCount);
        CountDownLatch ready = new CountDownLatch(workerCount);
        CountDownLatch start = new CountDownLatch(1);

        try {
            List<Future<T>> futures = new ArrayList<>();
            for (int i = 0; i < workerCount; i++) {
                futures.add(executor.submit(() -> {
                    ready.countDown();
                    if (!start.await(10, TimeUnit.SECONDS)) {
                        throw new TimeoutException("Workers did not receive start signal");
                    }
                    return action.call();
                }));
            }

            assertThat(ready.await(10, TimeUnit.SECONDS)).isTrue();
            start.countDown();

            List<T> results = new ArrayList<>();
            for (Future<T> future : futures) {
                results.add(future.get(60, TimeUnit.SECONDS));
            }
            return results;
        } finally {
            start.countDown();
            executor.shutdownNow();
            assertThat(executor.awaitTermination(10, TimeUnit.SECONDS)).isTrue();
        }
    }
}
```

The test class has no `@Transactional`. Initial data is persisted via `saveAndFlush`, and workers call service beans. Each service call receives an independent Spring transaction; `Future.get()` waits for transactions to complete before the test reads the final state.

### Running tests

```bash
mvn test
```

The test suite contains three tests:

```text
concurrentPurchasesNeverOversell
  20 requests, 10 succeeded, final stock = 0

concurrentTransfersCannotOverspendOrCreateMoney
  20 transfer requests of 10, 10 succeeded, A = 0.00, B = 200.00

theSameSeatCanBeReservedOnlyOnce
  2 requests for same seat, 1 succeeded, reservation count = 1
```

Maven prints test counts, failures, and errors in Surefire's format. The lines above describe expected assertions, not logs run inside this documentation environment.

## 10. Optimistic locking and how to test conflicts

If data has low contention and you want to avoid holding row locks during processing, you can use optimistic locking with `@Version`:

```java
@Entity
public class Wallet {
    @Id
    private Long id;

    private BigDecimal balance;

    @Version
    private long version;
}
```

When a transaction reads Wallet version 4, Hibernate updates with a condition similar to:

```sql
update wallets
set balance = ?, version = 5
where id = ? and version = 4;
```

If another transaction has already updated the version to 5, the old UPDATE matches zero rows and the provider reports an optimistic locking conflict. Spring typically translates this into `ObjectOptimisticLockingFailureException` or a subtype of `OptimisticLockingFailureException`.

To test conflicts in a controlled way:

1. Open two independent transactions on two threads.
2. Have each transaction read the same Wallet and the same version.
3. Use a `CyclicBarrier` in the test to wait until both have finished reading.
4. Have both update and flush.
5. Verify that one transaction commits and the other receives an optimistic locking exception.
6. Re-read the database and verify only one change was written.

Barriers belong only in the test harness to force intentional interleaving. Do not place barriers or sleeps in production services.

If retrying optimistic conflicts, retry the entire business operation in a fresh transaction. Do not catch the error and keep using a transaction marked rollback-only. Retries must be bounded, use appropriate backoff, and apply only when the operation has idempotent semantics or duplicate protection.

## 11. Testing deadlocks and lock ordering

A deadlock can happen when:

- Transaction A locks account 1 then waits for account 2.
- Transaction B locks account 2 then waits for account 1.

The way to reduce risk is locking rows in the same global order, such as ascending ID. Both transfer directions lock the lower account ID first, then the higher ID.

In advanced tests, run many bidirectional transfers and set timeouts on Futures. After all transactions finish, verify total money is unchanged and no balance is negative. If the database detects a deadlock, one transaction may be aborted; the application needs to handle the error appropriately and may retry in a fresh transaction with bounds.

You cannot prove an application will never deadlock with a single test. Inspect execution plans, access orders across multiple tables, indexes, and lock timeouts on the production database.

## 12. Common mistakes when writing concurrency tests

1. **Sequential tests:** create no contention and can miss race conditions. Use multiple worker threads.
2. **Using `Thread.sleep()` for coordination:** depends on machine speed and does not guarantee interleaving. Use latches or barriers.
3. **One shared transaction for all workers:** does not simulate independent requests. Call transactional services through Spring proxies from each thread.
4. **Placing `@Transactional` on the test:** workers do not join the test transaction; uncommitted setup data may be invisible.
5. **Sharing EntityManager or Session:** these objects are not thread-safe. Each thread must use its own transaction/persistence context.
6. **Checking only responses:** re-read the database to verify invariants after all Futures complete.
7. **Checking only `existsBy...` before inserting:** two transactions can still pass the check simultaneously. Use a unique constraint.
8. **Reading then writing counters in Java:** use an atomic conditional UPDATE or appropriate locks.
9. **Locking multiple rows without ordering:** easily causes deadlocks. Lock in a consistent order.
10. **Catching constraint errors and continuing the transaction:** the transaction may already be rollback-only. Handle errors outside the failed transaction.
11. **Using H2 to conclude production behavior:** H2 is useful for fast tests, yet lock, isolation, SQL, and constraint behavior can differ from PostgreSQL, MySQL, SQL Server, or Oracle.
12. **Testing only once:** race conditions can be rare. Run repeatedly in CI, increase contention in a controlled way, and keep invariant-based assertions.
13. **Not testing retries/idempotency:** clients or message brokers can resend requests. Use idempotency keys/unique constraints if business rules require it.
14. **Omitting timeouts:** tests can hang on deadlocks or stuck workers. Set timeouts for latches, Futures, and the test runner.

## 13. Running tests on a production-like database

Concurrency depends heavily on the database engine, isolation level, lock implementation, indexes, and connection pool. H2 cannot replace integration tests on the production engine.

For production systems using PostgreSQL, MySQL, or SQL Server, add Testcontainers to run the same database type in CI:

- Use the same database major version as the deployed environment.
- Apply real migrations instead of relying solely on `ddl-auto=create-drop`.
- Re-run inventory, transfer, reservation, and deadlock tests.
- Verify lock timeouts, deadlock exceptions, and transaction isolation.
- Confirm CHECK/UNIQUE constraints are created properly and required indexes exist.
- Check that the connection pool is large enough for test concurrency without exceeding database limits.

The H2 example above illustrates test structure and JPA mechanics. Final outcomes must be confirmed on the target database before being treated as proof of production behavior.

## 14. Pre-release checklist

- [ ] Defined invariants for inventory, balances, and reservations.
- [ ] Inventory uses a conditional UPDATE or equivalent lock; has CHECK `available >= 0`.
- [ ] Transfers run in a single transaction; lock in consistent order or use `@Version`.
- [ ] Has a CHECK constraint preventing negative balances if business rules require it.
- [ ] Seats/booking slots have appropriate unique constraints.
- [ ] Decrementing capacity and creating the reservation happen in the same transaction.
- [ ] Each test worker uses an independent transaction and does not share EntityManager.
- [ ] Tests generate contention via an executor and latch/barrier, without sleeps.
- [ ] Tests verify both success counts and final database state.
- [ ] Timeouts exist for workers, Futures, and the test runner.
- [ ] Tests cover rollbacks, optimistic conflicts, deadlocks, and retries if the application uses those mechanisms.
- [ ] Integration tests run on the same database type as production.

## 15. Practical guidelines

- Design invariants before designing tests.
- Let the database protect data with conditional updates, row locks, CHECK, and UNIQUE constraints.
- Use optimistic locking for low contention and conflict detection; use pessimistic locking when read-modify-write operations must be serialized.
- Lock multiple rows in the same order to reduce deadlocks.
- Keep all steps of a business operation atomic within the same transaction.
- Spawn separate worker threads and invoke transactional services through Spring proxies.
- Synchronize starting points with latches/barriers; do not rely on sleeps.
- Re-read the database after all transactions finish and verify invariants.
- Run tests on the target database because H2 does not emulate every production locking behavior.

Key takeaway: **Concurrency tests must spawn multiple independent transactions contending for a resource and verify invariants after commit. Inventory needs atomic conditional updates, balances need locking or versioning inside a transaction, and reservations need unique constraints. Multi-threaded tests are only meaningful when the final state in the database remains valid.**