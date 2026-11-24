# Never Infer Full Business Success from a Newly Generated Key Alone

An `INSERT` can return a new primary key (`id`) very early, right as the statement is processed by the database. **A generated key is identifying metadata of a write operation; by itself it does not prove the transaction committed, all business rules are satisfied, or external systems have completed their work.** This is a boundary that must be kept clear when using Spring JDBC, `JdbcTemplate`, `KeyHolder`, or any data-persistence API that returns an ID.

## 1. Typical scenario

Suppose an application receives a request to order two books. The expected processing flow:

1. `INSERT purchase_order` with status `PENDING`; the database generates `order_id = 501`.
2. Decrement inventory using `UPDATE inventory ... WHERE available >= 2`.
3. Write related records and confirm the business state.
4. Commit the database transaction; steps requiring external systems (payment, notifications...) have their own workflows.

If inventory is insufficient at step 2, the `UPDATE` affects **0 rows** and the service throws an exception to roll back. The application **already saw** key 501, yet the newly inserted order record may no longer exist after rollback. An ID allocation mechanism like sequence/identity can still consume the value 501, creating a gap in the ID sequence. Never rely on gaps or ID continuity to judge whether a transaction succeeded or failed.

Example of a wrong message: “Order 501 paid successfully” as soon as `KeyHolder.getKey()` returns 501. The accurate statement at that point is only “The insert statement returned a temporary ID for use within the flow”. The final state must be decided after verifying the appropriate business conditions and the outcome of the transaction/integration stages.

## 2. Distinguishing five levels of evidence

| Observable signal | What can be concluded | What **cannot** yet be concluded |
| --- | --- | --- |
| `KeyHolder` contains a new key | The JDBC driver returned the generated column value per statement configuration | Commit succeeded; order is valid; payment succeeded |
| `JdbcTemplate.update(...)` returns `1` | That single statement reported affecting one row | All other statements succeeded; transaction committed |
| Reading the record inside the same transaction | The current transaction sees data written by itself | The transaction is durable for other transactions |
| Transaction commits successfully | Changes belonging to **that database transaction** were accepted, per DB guarantees | Payment APIs, brokers, emails, and independent transactions succeeded |
| Business state is verified | The criteria corresponding to that state have been completed and recorded | Future steps not yet executed will also succeed |

A system can successfully create a `PENDING` resource, yet **not** have completed the order in `PAID` or `DELIVERED` state. “Order creation succeeded” and “payment succeeded” are two distinct propositions, even when sharing the same `order_id`.

## 3. What does Spring JDBC actually return?

Example method inserting one row and retrieving its ID with `JdbcTemplate`:

```java
// Method inside a class that already has JdbcTemplate jdbc.
long insertPendingOrder(JdbcTemplate jdbc, String sku, int quantity) {
    KeyHolder holder = new GeneratedKeyHolder();

    int affected = jdbc.update(connection -> {
        PreparedStatement statement = connection.prepareStatement(
            "INSERT INTO purchase_order (sku, quantity, status) VALUES (?, ?, ?)",
            new String[] { "ID" }
        );
        statement.setString(1, sku);
        statement.setInt(2, quantity);
        statement.setString(3, "PENDING");
        return statement;
    }, holder);

    if (affected != 1) {
        throw new IllegalStateException("INSERT_NOT_ONE_ROW");
    }

    Number generated = holder.getKey();
    if (generated == null) {
        throw new IllegalStateException("GENERATED_KEY_MISSING");
    }

    return generated.longValue();
}
```

Here:

- `connection.prepareStatement(sql, new String[] {"ID"})` asks the JDBC driver to return the generated key column. Column specification and support depend on the driver/database.
- `JdbcTemplate.update(PreparedStatementCreator, KeyHolder)` returns the **number of affected rows** and populates driver-supplied keys into `KeyHolder`. Those are two technical facts about the `INSERT` statement.
- `GeneratedKeyHolder.getKey()` is appropriate when expecting **a single numeric key**. If multiple columns or multiple rows are returned, you must work with `getKeys()` or `getKeyList()` per the actual structure; do not assume `getKey()` is always valid.
- Missing keys, non-numeric keys, `affected != 1`, or `DataAccessException` must be handled per the write operation's contract. **Do not** promote `affected == 1 && id != null` into `businessSuccess = true`.
- Other APIs such as `SimpleJdbcInsert.executeAndReturnKey(...)` do not alter transaction semantics or business criteria either: obtaining an ID is still only one signal in the workflow.

If this method runs inside `@Transactional`, obtaining the ID happens **before transaction commit time**. A subsequent failing operation or a constraint checked at commit can still cause the entire transaction to fail.

## 4. Runnable Java 17+ example: having an ID and still rolling back

To observe the difference accurately, this example uses Spring JDBC, `TransactionTemplate`, and an in-memory H2 database. The example business case is **reserving stock** for an order; it does not simulate payment or shipping.

Create `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.2.12'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'GeneratedKeyDemo'
}
```

Create `src/main/java/GeneratedKeyDemo.java`:

```java
import java.sql.PreparedStatement;
import java.util.Objects;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.transaction.support.TransactionTemplate;

public class GeneratedKeyDemo {
    public static void main(String[] args) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl("jdbc:h2:mem:key_demo;DB_CLOSE_DELAY=-1");
        dataSource.setUsername("sa");
        dataSource.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        TransactionTemplate transaction = new TransactionTemplate(
            new DataSourceTransactionManager(dataSource)
        );

        jdbc.execute(
            "CREATE TABLE inventory (" +
            "sku VARCHAR(32) PRIMARY KEY, available INT NOT NULL)"
        );
        jdbc.execute(
            "CREATE TABLE purchase_order (" +
            "id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, " +
            "sku VARCHAR(32) NOT NULL, quantity INT NOT NULL, " +
            "status VARCHAR(16) NOT NULL)"
        );
        jdbc.update(
            "INSERT INTO inventory (sku, available) VALUES (?, ?)",
            "BOOK", 1
        );

        try {
            reserve(jdbc, transaction, "BOOK", 2);
        } catch (IllegalStateException exception) {
            System.out.println("Request failed: " + exception.getMessage());
        }
        System.out.println(
            "Orders after rollback: " +
            jdbc.queryForObject("SELECT COUNT(*) FROM purchase_order", Integer.class)
        );

        long committedId = reserve(jdbc, transaction, "BOOK", 1);
        System.out.println("Reservation committed: " + (committedId > 0));
        System.out.println(
            "Orders after commit: " +
            jdbc.queryForObject("SELECT COUNT(*) FROM purchase_order", Integer.class)
        );
        System.out.println(
            "Remaining inventory: " +
            jdbc.queryForObject(
                "SELECT available FROM inventory WHERE sku = ?",
                Integer.class, "BOOK"
            )
        );
    }

    private static long reserve(
        JdbcTemplate jdbc,
        TransactionTemplate transaction,
        String sku,
        int quantity
    ) {
        Long id = transaction.execute(status -> {
            KeyHolder holder = new GeneratedKeyHolder();

            int inserted = jdbc.update(connection -> {
                PreparedStatement statement = connection.prepareStatement(
                    "INSERT INTO purchase_order (sku, quantity, status) " +
                    "VALUES (?, ?, ?)",
                    new String[] { "ID" }
                );
                statement.setString(1, sku);
                statement.setInt(2, quantity);
                statement.setString(3, "PENDING");
                return statement;
            }, holder);

            if (inserted != 1) {
                throw new IllegalStateException("INSERT_NOT_ONE_ROW");
            }
            Number rawKey = holder.getKey();
            if (rawKey == null) {
                throw new IllegalStateException("GENERATED_KEY_MISSING");
            }
            long orderId = rawKey.longValue();
            System.out.println("Generated key obtained: " + (orderId > 0));

            int reserved = jdbc.update(
                "UPDATE inventory SET available = available - ? " +
                "WHERE sku = ? AND available >= ?",
                quantity, sku, quantity
            );
            if (reserved != 1) {
                throw new IllegalStateException("OUT_OF_STOCK");
            }

            int marked = jdbc.update(
                "UPDATE purchase_order SET status = ? WHERE id = ?",
                "RESERVED", orderId
            );
            if (marked != 1) {
                throw new IllegalStateException("STATE_UPDATE_FAILED");
            }
            return orderId;
        });

        return Objects.requireNonNull(id);
    }
}
```

With JDK 17+ and Gradle installed (or the project's Gradle Wrapper), run `gradle run` (or `./gradlew run`). Excluding Gradle logs, the **program's stdout** is:

```text
Generated key obtained: true
Request failed: OUT_OF_STOCK
Orders after rollback: 0
Generated key obtained: true
Reservation committed: true
Orders after commit: 1
Remaining inventory: 0
```

Explanation in exact order:

1. The first request creates a `purchase_order` row with status `PENDING` and receives an ID. Next, the statement deducting two items returns `0` because stock only has one. The `OUT_OF_STOCK` exception causes `TransactionTemplate` to roll back the insert as well: counting orders from outside the transaction yields `0`.
2. The second request inserts the order, deducts one item, and updates status to `RESERVED` in the **same transaction**. When `transaction.execute(...)` returns in this example, the commit is complete because no outer transaction surrounds it. Only then is “Reservation committed” printed.
3. We do not compare the IDs of the two inserts, because the key allocator can leave gaps after rollback. What is verified is the **actually existing row count and status/stock**, not the ID value or sequence order.
4. The example uses `DriverManagerDataSource` purely for run-time simplicity; real applications typically use a connection pool configured and managed per deployment environment.

Core lesson of the code: **A log line “Generated key obtained: true” can be immediately followed by a rollback with zero orders saved.**

## 5. Where should transaction boundaries be placed?

For a group of data operations **on the same database**, choose a transaction boundary encompassing the steps that must succeed or fail together: inserting the order, checking/deducting stock, inserting order items, writing outbox rows, updating status... Never invoke them as disconnected auto-commit operations and then declare success based solely on the first ID.

Example with a Spring service:

```java
@Service
public class OrderApplicationService {
    private final OrderRepository orders;
    private final InventoryRepository inventory;

    public OrderApplicationService(
        OrderRepository orders,
        InventoryRepository inventory
    ) {
        this.orders = orders;
        this.inventory = inventory;
    }

    @Transactional
    public long reserveOrder(PlaceOrder command) {
        long id = orders.insertPending(command); // Key obtained, still uncommitted.

        boolean reserved = inventory.tryReserve(
            command.sku(), command.quantity()
        );
        if (!reserved) {
            throw new IllegalStateException("OUT_OF_STOCK");
        }

        orders.markReserved(id);
        return id; // Spring still has to complete the transaction in the proxy.
    }
}
```

This is **service structure illustrative code**, depending on the application's `OrderRepository`, `InventoryRepository`, and `PlaceOrder` classes; the H2 demo above is the standalone program.

Points to avoid confusing:

- Under default proxy mode, `@Transactional` only applies to calls going **through the Spring proxy**. One method on the same object directly calling another `@Transactional` method (`this.method()`) does not trigger transaction advice for that internal call.
- By default, `@Transactional` typically rolls back when `RuntimeException` or `Error` escapes the method; checked exceptions may require `rollbackFor` or custom rollback rules. **Catching an exception and silently returning success** can accidentally allow an invalid state to commit.
- Under default `REQUIRED` propagation, if a service participates in an **outer transaction**, when the service method returns there is still no guarantee the outer transaction has committed. Only the layer owning the outermost transaction boundary can conclude the commit result for that entire unit of work.
- Commit itself can still raise errors (e.g., deferred constraints or connection failures); never treat an ID obtained before commit as proof of a successful commit.
- Standard JDBC transactions **do not automatically encompass** HTTP APIs, payment gateways, emails, or message brokers. Only declare an external step completed when you have matching evidence per that step's contract.

## 6. Designing business results based on invariants and states

Name results according to what has genuinely been completed, for example:

| State | Minimum condition to publish |
| --- | --- |
| `PENDING` | Request was validly recorded per the order-creation contract; subsequent steps are pending |
| `RESERVED` | Inventory was reserved per business rules and successfully recorded in the relevant transaction |
| `PAID` | Valid payment confirmation was reconciled with the order and status updated properly |
| `COMPLETED` | All completion criteria defined by the product have been verified, potentially including shipping/post-checks |

There is no universal rule that “having an ID means state is `COMPLETED`”. A newly created record may be a pending request, a transaction awaiting verification, or an accepted task.

Example API contract response:

```json
{
  "orderId": 501,
  "status": "PENDING_PAYMENT",
  "message": "Order created; payment not yet confirmed"
}
```

This is a **state representation** example, not a promise that ID 501 exists after an uncommitted transaction. APIs should build success responses only after the required transaction boundary has been resolved, and separate resource creation state from workflow completion state. HTTP `201 Created` can be appropriate for a created resource; it does not implicitly mean `PAID`. For asynchronous processing, `202 Accepted` can be used when the API only accepts the request without completing processing yet.

If the system supports request retries, you need an **idempotency key/unique constraint** and an existing-state check to avoid creating two orders for one request; generating a new ID per call does not solve business duplication.

## 7. Boundaries with events and external systems

Suppose stock reservation committed, but an `OrderReserved` event needs to be sent to another system. Three common options exist:

- Emit the event **before commit**: consumers may process an order that ends up rolled back.
- Emit the event **after commit**: avoids publishing events for rolled-back transactions, yet the process can crash after commit and before sending; hence “committed” still does not guarantee event delivery.
- Write a **transactional outbox** in the same transaction as the order and have a publisher read/send from the outbox: reduces the risk of losing events between commit and publish. Consumers should still be idempotent because duplicates can occur.

Spring supports `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` to run a listener when commit succeeds; that is a **phase hook**, not a durable delivery guarantee to a message broker. Choose outbox, retries, and reconciliation according to actual reliability requirements. Multi-system workflows typically need state orchestration, retries, compensation, or sagas; you cannot infer “full business success” from a local `INSERT` result.

## 8. Proper verification with tests and logs

A valuable test suite verifies the **final post-transaction state**, rather than merely asserting `id != null`:

1. **Sufficient stock:** transaction returns successfully; exactly one order exists with state `RESERVED`, and stock decreased accurately.
2. **Insufficient stock:** a generated key was obtained inside the transaction, yet the service throws `OUT_OF_STOCK`; after rollback no new order exists and stock is unchanged.
3. **Error after `INSERT`:** inserting order items/outbox fails; all data in the same transaction rolls back per configuration. Verify using an independent verification connection/transaction.
4. **Error on commit:** caller receives a transaction error; do not send completion notifications just because an ID was logged earlier.
5. **External integration timeout:** maintain a reconcilable intermediate state; do not mark `PAID` merely because `order_id` was generated.
6. **Repeated requests:** idempotency constraints protect against creating duplicate business transactions.

Logging should include **correlation/request ID**, generated entity ID, phase, affected row count, transaction outcome when observable, and business state. For instance, two log lines `orderId=501 created` and `orderId=501 transaction rolled back` describe what can actually happen; do not draw conclusions from the first log alone.

## 9. Misconceptions to eliminate

- **“`getKey() != null` means the database saved it permanently.”** False: the key can appear before commit and the transaction can roll back.
- **“`update() == 1` means the entire workflow succeeded.”** False: that is the row count of **one statement**.
- **“I `SELECT`ed the order in the same transaction, so it must have committed.”** False: reads inside a transaction can observe its own uncommitted writes.
- **“Non-contiguous IDs mean lost data.”** Not necessarily: sequences/identities, rollbacks, caches, and concurrency can all leave gaps.
- **“Having `@Transactional` means external APIs and message brokers roll back too.”** False: a DB transaction does not create a distributed transaction across those systems.
- **“When a `@Transactional` method returns an ID, commit is always finished.”** False when participating in an unfinished outer transaction; moreover, the call must actually go through the proxy for advice to apply.
- **“An `AFTER_COMMIT` listener guarantees events can never be lost.”** False: phase listeners do not replace an outbox/redelivery guarantee.

## 10. Immediate design rules

Before returning “success”, identify success **of which operation**. Check: (a) SQL statements and row counts, (b) generated key has the right type and is used in the right place, (c) all transaction invariants hold, (d) the transaction actually finished with the expected outcome at its owning boundary, (e) published business state matches evidence, and (f) integration steps have their own confirmation/recovery mechanisms. Never use an ID to substitute for any verification step.

**Remember:** `generated key` answers **“how is this data row identified?”**, whereas **“did the entire business process succeed?”** must be answered by transaction outcomes, business invariants, state, and evidence from the involved systems.

### References

- [Spring Framework – JdbcTemplate API, update with KeyHolder](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html)
- [Spring Framework – Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework – Transaction propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework – Transaction-bound events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
