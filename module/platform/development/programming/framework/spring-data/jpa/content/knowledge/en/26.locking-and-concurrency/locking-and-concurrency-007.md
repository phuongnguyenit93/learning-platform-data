# Locking Relationships and Protection Scope Boundaries

In JPA, locking an entity does not mean locking the entire object graph that the entity references. The protection scope depends on the **lock type**, the **owning side of the relationship**, the **location of foreign keys or join tables**, and the **lock scope** applied by the persistence provider.

When using Spring Data JPA, we typically place a lock mode on a repository method with **@Lock**. For pessimistic locking, Jakarta Persistence also allows choosing **NORMAL** or **EXTENDED** scope via the **jakarta.persistence.lock.scope** property.

Two questions must be distinguished:

- **Lock mode**: what kind of protection is the transaction requesting, such as a locked read or an exclusive write?
- **Lock scope**: when locking an entity with a pessimistic lock, does the scope extend to the join tables or collection tables of relationships owned by that entity?

These two settings work together, but neither replaces the other.

## 1. Lock types in JPA

JPA supports optimistic locking and pessimistic locking. They resolve concurrency conflicts in different ways.

### 1.1. Optimistic locking

Optimistic locking typically uses a version field annotated with **@Version**:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class Inventory {

    @Id
    private Long id;

    private int availableQuantity;

    @Version
    private long version;

    protected Inventory() {
    }

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        if (availableQuantity < quantity) {
            throw new IllegalStateException("insufficient inventory");
        }
        availableQuantity -= quantity;
    }
}
~~~

When updating the entity, JPA uses the current version value in the UPDATE condition. Conceptually, the statement looks like:

~~~sql
UPDATE inventory
   SET available_quantity = ?, version = version + 1
 WHERE id = ?
   AND version = ?;
~~~

If another transaction has already updated the record and incremented the version, the current transaction's UPDATE no longer matches the old version. The provider detects the conflict and throws **OptimisticLockException** or the corresponding translated Spring exception.

Optimistic locking does not hold row locks during reads and business processing. It detects conflicts when checking the version, typically during flush or commit. This approach fits when conflicts are infrequent and transactions are relatively short.

### 1.2. Pessimistic locking

Pessimistic locking asks the database to protect the record as soon as the transaction acquires the lock. JPA defines the commonly used modes:

| Lock mode | Meaning |
|---|---|
| **PESSIMISTIC_READ** | Requests a lock allowing concurrent reads while preventing other transactions from updating or deleting the locked entity |
| **PESSIMISTIC_WRITE** | Requests an exclusive lock so other transactions cannot update or delete the entity until the lock-holding transaction finishes |
| **PESSIMISTIC_FORCE_INCREMENT** | Pessimistic write lock that forces an increment of the version on an entity with a @Version field |
| **OPTIMISTIC** | Requests a version check using the optimistic locking mechanism |
| **OPTIMISTIC_FORCE_INCREMENT** | Optimistic check that forces a version increment |

With pessimistic modes, the lock is held until the transaction commits or rolls back. A repository method returning an entity does not mean the lock is released as soon as that method finishes if it is participating in a broader transaction.

The legacy **READ** and **WRITE** names in LockModeType are aliases for optimistic modes. When reading or writing code, prefer **OPTIMISTIC** and **OPTIMISTIC_FORCE_INCREMENT** to avoid confusing them with **PESSIMISTIC_READ** and **PESSIMISTIC_WRITE**.

## 2. Using @Lock in Spring Data JPA

Spring Data JPA lets you attach a lock mode directly to a query method with **@Lock**:

~~~java
import jakarta.persistence.LockModeType;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface InventoryRepository
        extends JpaRepository<Inventory, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select i from Inventory i where i.id = :id")
    Optional<Inventory> findForUpdate(@Param("id") Long id);
}
~~~

When **findForUpdate** is called, Spring Data JPA instructs the provider to execute the query with **PESSIMISTIC_WRITE** mode. The provider translates that request into a locking mechanism appropriate for the underlying database.

### 2.1. Locks must reside inside a transaction

Lock modes other than **NONE** require an active transaction, and the EntityManager must join that transaction. If a lock is requested without a transaction, JPA may throw **TransactionRequiredException**.

Place transaction boundaries on the service coordinating reading, validation, and updating:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {

    private final InventoryRepository inventories;

    public InventoryService(InventoryRepository inventories) {
        this.inventories = inventories;
    }

    @Transactional
    public void reserve(Long id, int quantity) {
        Inventory inventory = inventories.findForUpdate(id)
            .orElseThrow(() -> new IllegalArgumentException("inventory not found"));

        inventory.reserve(quantity);
    }
}
~~~

In the example, the lock-acquiring query, quantity check, and entity mutation all sit within one transaction. The lock is held until the transaction completes. Annotating only a repository method with a lock and calling it outside a transaction can cause the operation to fail.

Do not hold locks while making HTTP calls, waiting for users, or running unnecessary slow work. The longer the transaction, the longer other transactions must wait and the higher the deadlock risk.

## 3. Entity relationships and the owning side

To understand how far a lock protects relationships, you must first identify the **owning side**. In JPA, the owning side of a relationship is the side that controls the foreign key or join table mapping. The side with **mappedBy** is the inverse side.

Example of a purchase order with a customer, tags, and order lines:

~~~java
@Entity
public class PurchaseOrder {

    @Id
    private Long id;

    // FK customer_id resides in the purchase_order table.
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private Customer customer;

    // PurchaseOrder owns the join table purchase_order_tag.
    @ManyToMany
    @JoinTable(
        name = "purchase_order_tag",
        joinColumns = @JoinColumn(name = "order_id"),
        inverseJoinColumns = @JoinColumn(name = "tag_id")
    )
    private Set<OrderTag> tags = new HashSet<>();

    // FK order_id resides in the order_line table.
    // OrderLine is the owning side because PurchaseOrder uses mappedBy.
    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines = new ArrayList<>();
}
~~~

In the mapping above:

- **ManyToOne customer**: the purchase_order table contains the customer_id column. PurchaseOrder is the owning side of this relationship.
- **ManyToMany tags**: PurchaseOrder declares @JoinTable, making it the owning side of the purchase_order_tag table.
- **OneToMany lines**: PurchaseOrder declares mappedBy = "order". The foreign key order_id resides in the order_line table and is managed by OrderLine.

Simply having a getter returning a collection on an entity does not mean that entity owns the rows in the relationship table. Inspect the mapping and actual foreign key placement to determine lock scope.

## 4. Pessimistic lock scope: NORMAL and EXTENDED

Jakarta Persistence defines the **jakarta.persistence.lock.scope** property for pessimistic locks. The default enum value is **PessimisticLockScope.NORMAL**; **PessimisticLockScope.EXTENDED** extends lock scope to certain relationship tables owned by the entity.

### 4.1. NORMAL — default scope

With **NORMAL**, the provider must lock rows belonging to the primary table and any secondary tables mapping non-collection state of the entity. With joined inheritance, corresponding rows in superclass tables also belong to the scope.

Relationships where the locked entity holds the foreign key are also protected alongside the entity's state. However, that **does not lock the state of the referenced entity**.

For example, locking PurchaseOrder:

- The purchase_order row is locked, including the customer_id column on that row.
- The referenced Customer row is not automatically locked.
- Relationships using join tables and element collections are not included in lock expansion by default.
- For OneToMany mappedBy, the foreign key resides in the OrderLine table; locking PurchaseOrder does not automatically lock OrderLine rows.

NORMAL is suitable when the business invariant only needs to protect the root entity's state and relationship columns stored directly on that entity's row.

### 4.2. EXTENDED — extending to relationship tables owned by the entity

With **PessimisticLockScope.EXTENDED**, the provider retains the entire NORMAL scope and additionally extends to:

- Rows in join tables of relationships owned by the entity.
- Rows in collection tables of element collections belonging to the entity.

For PurchaseOrder in the example above:

- The purchase_order row remains locked.
- Existing relationship rows in purchase_order_tag are included in the lock scope because PurchaseOrder owns the join table.
- Customer and OrderTag rows are not automatically locked.
- OrderLine rows are not automatically locked just because PurchaseOrder has a lines collection with mappedBy; the foreign key lives in the OrderLine table and the relationship is not owned by PurchaseOrder.

**EXTENDED does not mean locking every entity in the object graph.** It extends scope to applicable join table and collection table rows; the state of referenced entities still needs explicit locking if required by business logic.

### 4.3. Scope comparison table

| Data component of PurchaseOrder | NORMAL | EXTENDED |
|---|---|---|
| purchase_order row | Yes | Yes |
| Secondary tables of PurchaseOrder | Yes | Yes |
| customer_id column on purchase_order | Part of locked row | Part of locked row |
| Referenced Customer row | Not automatic | Not automatic |
| purchase_order_tag rows owned by PurchaseOrder | Does not extend to join table | Yes |
| Referenced OrderTag row | Not automatic | Not automatic |
| Collection table rows of @ElementCollection | No | Yes |
| order_line rows with mappedBy on PurchaseOrder | Not automatic | Not automatic |

### 4.4. EXTENDED can still experience phantoms

When locking a relationship or element collection with EXTENDED, the provider usually locks only the rows currently present in the join table or collection table. New rows can still be inserted into the query range while the transaction is running. This phenomenon is called a **phantom**.

Therefore, EXTENDED is not equivalent to completely locking the entire collection or guaranteeing nobody can add new members. If an invariant requires protecting additions/removals to a relationship as well, design additional mechanisms as needed, such as explicitly locking child entities, updating an aggregate root version under a consistent convention, database constraints, or an appropriate isolation level.

## 5. Setting lock scope via query hint

Spring Data JPA lets you attach JPA query hints to repository methods using **@QueryHints**. To request EXTENDED, use the exact Jakarta Persistence property name:

~~~java
import jakarta.persistence.LockModeType;
import jakarta.persistence.QueryHint;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.jpa.repository.QueryHints;
import org.springframework.data.repository.query.Param;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @QueryHints(
        @QueryHint(
            name = "jakarta.persistence.lock.scope",
            value = "EXTENDED"
        )
    )
    @Query("select o from PurchaseOrder o where o.id = :id")
    Optional<PurchaseOrder> findForUpdateWithExtendedScope(
        @Param("id") Long id
    );
}
~~~

There are two independent configurations here:

- **@Lock(PESSIMISTIC_WRITE)** requests a pessimistic write lock on the queried entity.
- **jakarta.persistence.lock.scope = EXTENDED** extends the lock scope to the entity's join tables and collection tables per JPA rules.

If the query hint is omitted, the provider uses the default NORMAL scope. Setting EXTENDED alone without requesting a pessimistic lock does not create a lock; it only adjusts the scope of a pessimistic lock.

You can also declare a lock timeout using a query hint:

~~~java
@QueryHints({
    @QueryHint(
        name = "jakarta.persistence.lock.scope",
        value = "EXTENDED"
    ),
    @QueryHint(
        name = "jakarta.persistence.lock.timeout",
        value = "3000"
    )
})
~~~

The value **3000** represents 3,000 milliseconds per the lock timeout hint convention. Enforcement and interpretation still depend on the JPA provider, JDBC driver, and database. Test on your target deployed database; a query hint does not guarantee every system will abort waiting for a lock at that exact moment.

For applications using older JPA under the **javax.persistence** namespace, the corresponding property name is **javax.persistence.lock.scope** and imports must match the version namespace in use. Do not mix javax and jakarta in the same application.

## 6. Lock scope is not data fetch scope

Lock scope and fetch plan solve two different problems:

- **FetchType.LAZY/EAGER**, JOIN FETCH, and EntityGraph determine which relationship data is loaded.
- **LockModeType** and lock scope determine which rows need to be protected by locks.

Fetching an association does not automatically mean all related entities are locked as the application intends. Likewise, setting EXTENDED does not ask the provider to load every association into memory.

If the business logic needs to lock both PurchaseOrder and Customer, explicitly request a lock on Customer in the same transaction, or design a query whose lock mode applies to the entities needing protection. Do not infer that locking the root automatically propagates to every referenced entity.

## 7. Choosing a protection strategy by business invariant

Define what must remain true throughout the transaction before choosing a lock mode and scope.

| Invariant | Commonly suitable strategy |
|---|---|
| Prevent two transactions from updating the same inventory row concurrently | PESSIMISTIC_WRITE on Inventory or `@Version` with retry handling |
| Prevent modifying the status of an order currently being processed | PESSIMISTIC_WRITE on PurchaseOrder |
| Need to protect existing join table rows of an owned relationship | PESSIMISTIC lock with EXTENDED scope |
| Need to protect the state of a referenced Customer | Lock Customer explicitly within the same transaction |
| Need to protect OrderLine rows where the FK resides in the child table | Lock the necessary OrderLines or design aggregate rules/constraints |
| Prevent two records from having the same business code | UNIQUE constraint in the database; locks do not replace constraints |
| Conflicts are rare and want detection on write | `@Version` and optimistic locking |

Do not use pessimistic locks to replace constraints. For instance, checking "order code does not exist yet" and then inserting can still suffer a race condition if two transactions run concurrently. A UNIQUE constraint is the ultimate safeguard in the database.

## 8. Timeouts, lock failures, and deadlocks

Pessimistic locking can force a transaction to wait for another transaction to release a lock. Common errors:

- **PessimisticLockException**: lock acquisition failure causing the transaction to roll back.
- **LockTimeoutException**: lock acquisition timed out and only the statement is rolled back per the JPA provider's classification.
- **TransactionRequiredException**: requesting a lock mode other than NONE when no transaction is active.
- **Deadlock**: two or more transactions hold different locks and wait on each other.

Ways to reduce risk:

1. Keep transactions short and avoid calling external services while holding locks.
2. Lock multiple entities in a consistent order across processing flows.
3. Lock only the entities and relationships needed for the invariant.
4. Set a lock timeout matching SLAs and verify database support.
5. For retryable deadlock or timeout errors, retry in a new transaction; do not reuse a rolled-back transaction.
6. Monitor lock wait times, deadlock counts, and queries holding locks for long durations.

JPA does not prescribe the exact SQL statement or database mechanism a provider must use to acquire locks. The provider or database may lock more rows than the application requested. Therefore, inspect the actual SQL and behavior of your deployed database.

## 9. Complete example: locking an order along with relationship scope

Suppose an order approval workflow must ensure no other transaction concurrently modifies the order or its existing tag associations in the join table. The repository can declare:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @QueryHints(
        @QueryHint(
            name = "jakarta.persistence.lock.scope",
            value = "EXTENDED"
        )
    )
    @Query("select o from PurchaseOrder o where o.id = :id")
    Optional<PurchaseOrder> findForApproval(@Param("id") Long id);
}
~~~

The service coordinates the entire business operation inside a transaction:

~~~java
@Service
public class PurchaseOrderService {

    private final PurchaseOrderRepository orders;

    public PurchaseOrderService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public void approve(Long orderId) {
        PurchaseOrder order = orders.findForApproval(orderId)
            .orElseThrow(() ->
                new IllegalArgumentException("order not found")
            );

        if (order.isApproved()) {
            return;
        }

        order.approve();
    }
}
~~~

In this case, the transaction requests a write lock on PurchaseOrder and EXTENDED scope for join tables/collection tables belonging to the order. Customer, OrderTag, and OrderLine entities are not automatically locked just because they are referenced or present in the object graph. If the approval workflow must protect the state of one of those entities, add explicit locking for it.

The code above is an integration example within a Spring Boot application configured with JPA, a datasource, entity mappings, and a transaction manager; imports, status enums, and domain methods depend on your actual domain.

## 10. Testing lock scope

Test using two independent transactions against a database matching production. A test calling a single repository method inside a single transaction does not prove a second transaction is actually blocked.

Test scenario:

1. Transaction A calls the repository method with PESSIMISTIC_WRITE and keeps the transaction open.
2. Transaction B attempts to update or delete the same entity; verify the operation must wait or fails on lock timeout.
3. Transaction A commits or rolls back.
4. Verify Transaction B can proceed once the lock is released.
5. Repeat with an association using a join table and EXTENDED to verify the linked rows.
6. Try modifying the referenced Customer or OrderTag row to confirm that entity is not automatically in the lock scope.
7. Try inserting a new link while transaction A holds the lock to test for possible phantoms.
8. Test the OneToMany mappedBy case, where the FK resides in the child table.

When writing concurrency tests, use latches/barriers or explicit synchronization to control when transactions A and B execute. Avoid arbitrary sleeps because tests can become flaky on CI. You can set a short lock timeout in tests to verify lock wait behavior, while verifying whether the database and driver support that hint.

## 11. Common misconceptions

| Misconception | Reality |
|---|---|
| Locking PurchaseOrder also locks Customer | NORMAL locks the PurchaseOrder row; Customer state is not automatically locked |
| EXTENDED locks every entity in the object graph | EXTENDED extends to join tables and collection tables owned by the entity, not automatically to referenced entities |
| EXTENDED prevents all collection membership changes | Existing join/collection table rows are locked, but phantoms can still occur |
| OneToMany mappedBy is always locked when locking parent | FK is in the child table; child entities must be locked if required by business rules |
| `@Lock` creates a transaction automatically | Lock modes other than NONE require an active transaction |
| Lock scope decides which associations are fetched | Fetch plans and lock scope are two separate mechanisms |
| PESSIMISTIC_WRITE protects all business rules | It protects locked rows; UNIQUE, FK, and CHECK constraints still belong in the database |
| Provider always locks strictly the selected row | Database/provider may lock additional rows depending on implementation |
| You can keep using a transaction after deadlock/lock failure | The transaction may have rolled back; retrying requires a new transaction |

## 12. Implementation checklist

- [ ] Identified the business invariant and the entities requiring locks.
- [ ] Identified the owning side, mappedBy, foreign key placement, and join tables.
- [ ] Selected the lock mode: optimistic or an appropriate PESSIMISTIC_* mode.
- [ ] If using pessimistic locking, repository methods are called within an active transaction.
- [ ] EXTENDED is used only when join tables/collection tables owned by the entity need locking.
- [ ] Referenced entities are locked explicitly if business logic must protect their state.
- [ ] Phantoms and database constraints have been evaluated for integrity rules.
- [ ] Timeout, deadlock, and retry in a new transaction have been verified.
- [ ] Integration tests use two independent transactions on an appropriate database.
- [ ] Inspected actual SQL and lock scope from the JPA provider/database.

## 13. Key takeaways

**@Lock** specifies the query's lock mode; **jakarta.persistence.lock.scope** specifies the scope of a pessimistic lock. **NORMAL** protects the entity's row and related state tables per JPA rules. **EXTENDED** adds join table rows for associations owned by the entity and collection table rows, but does not automatically lock referenced entities and does not eliminate phantoms.

To protect business logic properly, start from foreign key placement and the owning side, identify which rows actually participate in the invariant, and lock inside short transactions. Use versions or database constraints for rules that row locks and lock scope cannot guarantee.

## References

- [Jakarta Persistence 3.2 — Locking and concurrency](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html)
- [Jakarta Persistence API — PessimisticLockScope](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/pessimisticlockscope)
- [Spring Data JPA — Locking](https://docs.spring.io/spring-data/jpa/reference/jpa/locking.html)
- [Spring Data JPA — Query methods and query hints](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)