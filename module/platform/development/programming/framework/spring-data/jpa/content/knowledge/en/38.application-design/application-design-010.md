# Avoiding Oversized Repositories, Arbitrary Generic CRUD, and Redundant save() Calls

A repository is the boundary between the domain model and data storage. A well-designed repository exposes data operations meaningful to an aggregate or use case; it should not become a dumping ground for every query in the application or a blanket CRUD wrapper ignoring domain rules.

In Spring Data JPA, `JpaRepository` provides many convenient operations. However, stuffing every query into a single interface, inheriting full CRUD for every entity, or calling `save()` after every mutation can obscure the design and introduce subtle bugs.

This lesson focuses on three decisions:

- Keep Repositories cohesive with clear responsibilities.
- Use generic CRUD only when behavior is genuinely shared while preserving domain boundaries.
- Understand `persist`, `merge`, transactions, and dirty checking to know when `save()` is actually needed.

## 1. What Should a Repository Be Responsible For?

A repository provides a way to retrieve and store aggregates in the domain model. It hides query and persistence mechanics so services or domain logic work with entities, value objects, and business behavior.

For example, with orders:

- `PurchaseOrderRepository` finds and saves the `PurchaseOrder` aggregate.
- Operations like adding order lines, confirming an order, or cancelling an order should go through the aggregate's behavior and the corresponding service.
- The repository can query orders by order number, status, or search criteria.
- The repository should not send emails, call payment gateways, decide refund policies, or orchestrate the entire checkout workflow.

In aggregate-based design, repositories are usually defined per aggregate root. Child entities are accessed through the aggregate root when invariants and aggregate lifecycles must be protected. If an entity has an independent lifecycle or a distinct querying need, a separate repository can be considered; the decision should follow business boundaries.

A repository with clear responsibilities typically exhibits these traits:

- Methods serve the same aggregate or a cohesive group of related data queries.
- Method names describe query criteria or data-retrieval intent.
- It contains no use-case orchestration logic that belongs in a service.
- It does not let callers arbitrarily mutate data while bypassing domain invariants.

## 2. Signs a Repository Is Growing Too Large

There is no fixed method-count limit for a repository. An interface with many methods can still be reasonable if all of them serve the same aggregate and a unified data-access responsibility. Problems arise when the interface turns into a collection of unrelated queries and behaviors.

Warning signs:

1. Groups of methods serving unrelated use cases—for instance, order management, accounting reports, payment reconciliation, and inventory management all crammed into one interface.
2. Readers struggle to find the right method due to near-duplicate names or multiple overloads with unclear differences.
3. The repository contains conditional logic, invokes other repositories, or executes multi-step business workflows.
4. Changing one use case forces unrelated callers to change because the interface exposes too many details.
5. The interface accumulates many queries tailored to one UI screen or report, letting presentation needs dictate the aggregate API.
6. Methods carry vastly different query responsibilities that cannot be summarized under a shared domain concept.

Example of an unfocused interface:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    List<PurchaseOrder> findByStatus(OrderStatus status);

    BigDecimal sumRevenueByMonth(int year, int month);

    List<PurchaseOrder> findOrdersWithUnmatchedPayments();

    List<PurchaseOrder> findOrdersWaitingForInventory();

    List<OrderExportRow> exportOrders(LocalDate from, LocalDate to);

    // Many ad-hoc queries for unrelated use cases...
}
~~~

Not every method above is inherently wrong inside an order repository. The question is whether they share the same responsibility and data model. Summary reports or exports often fit better in a dedicated query service or read model; reconciliation may belong to the payments module; inventory queries may belong to the inventory module.

Do not split a repository merely by line count or method count. Split when there is a clear responsibility boundary and distinct API consumers.

## 3. Organizing Repositories by Responsibility

### 3.1. Keep the Aggregate Root Repository Focused

The primary repository should hold core operations and lookups tied to the `PurchaseOrder` aggregate.

~~~java
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    Optional<PurchaseOrder> findByOrderNumber(String orderNumber);

    boolean existsByOrderNumber(String orderNumber);
}
~~~

Method names clearly state what data is fetched. Actions such as `confirm()`, `cancel()`, or `addLine()` belong on the aggregate or are orchestrated by the service, rather than creating a repository method for every state transition.

### 3.2. Extract Read Queries for Reporting

When a report needs dedicated projections or aggregations, create a specialized query repository or read service. It can query the same database and tables while serving a different read model than the aggregate repository.

~~~java
public record MonthlyRevenue(
        int year,
        int month,
        BigDecimal total) {
}

public interface OrderReportingRepository {
    List<MonthlyRevenue> summarizeRevenue(int year);
}
~~~

An implementation class can use `EntityManager`, JPQL, the Criteria API, or native SQL to compute report data. Reporting services depend on this component, leaving `PurchaseOrderRepository` focused on aggregate operations.

You do not have to create a separate repository for every small projection. If a query serves a simple operation and fits within the aggregate's responsibility, keeping it in the existing repository is reasonable.

### 3.3. Use Repository Fragments for Custom Query Groups

Spring Data JPA supports composing fragments into a repository. This is useful when a group of data-access operations requires a custom implementation, such as dynamic search queries.

~~~java
public interface PurchaseOrderSearch {
    Page<PurchaseOrder> search(
            OrderSearchCriteria criteria,
            Pageable pageable);
}
~~~

The main repository combines the fragment:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long>,
                PurchaseOrderSearch {

    Optional<PurchaseOrder> findByOrderNumber(String orderNumber);
}
~~~

An implementation class following naming conventions, such as `PurchaseOrderSearchImpl`, houses the custom query logic. Place the class in a package scanned by Spring Data repository scanning and follow the configured repository implementation postfix.

Fragments divide implementations by responsibility while presenting a unified external repository API. If two query groups belong to different bounded contexts or independent read models, consider separating them into distinct beans instead of merging everything into one interface.

## 4. Generic CRUD: When Helpful, When Risky?

Generic repositories or generic services are often introduced to reduce boilerplate. For example, a `BasicRepository<T, ID>` or `BaseService<T, ID>` offering save, find-by-ID, find-all, and delete-by-ID for every entity.

Reuse helps when behavior is truly identical. Yet arbitrary generic CRUD easily overlooks differences in lifecycles and rules across aggregates.

Common risks:

- Exposing delete-by-ID on entities whose business rules require status checks first.
- Allowing direct persistence of child entities, bypassing aggregate root behavior.
- Exposing unbounded find-all queries on large tables, causing uncontrolled data loads.
- Producing a lowest-common-denominator API unable to express domain-specific queries or invariants.
- Cramming entity-specific branches into a generic service, turning it into a hard-to-maintain dispatcher.

A uniform contract may look consistent yet fail to reflect each data type's rules. For instance, a customer might still have active contracts; an order might already be paid; an order line may only be modified via `PurchaseOrder`. A generic CRUD operation cannot enforce those rules on its own.

### 4.1. Reuse Only Truly Common Contracts

If a project has a genuinely identical minimal set of persistence operations, Spring Data allows defining a base repository annotated with `@NoRepositoryBean`. This annotation tells Spring Data not to instantiate a repository bean directly for the intermediate interface.

~~~java
import java.util.Optional;
import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.repository.Repository;

@NoRepositoryBean
public interface BasicRepository<T, ID>
        extends Repository<T, ID> {

    Optional<T> findById(ID id);

    <S extends T> S save(S entity);
}
~~~

Concrete repositories opt into that minimal contract:

~~~java
public interface CustomerRepository
        extends BasicRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);
}
~~~

This avoids generating a generic CRUD service automatically. Each concrete repository still defines the queries it needs, and services remain responsible for use cases. If full `JpaRepository` capabilities are needed, extend it on the specific repository; do not force every entity to expose all operations solely because of a base interface.

### 4.2. Do Not Use Generics to Obscure Domain Behavior

Actions like approve, cancel, publish, archive, or settle carry business meaning. Express them with explicitly named methods on the aggregate or service.

~~~java
@Service
public class PurchaseOrderService {

    private final PurchaseOrderRepository repository;

    public PurchaseOrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void cancelOrder(Long orderId) {
        PurchaseOrder order = repository.findById(orderId)
                .orElseThrow(() ->
                        new EntityNotFoundException("Order not found"));

        order.cancel();
    }
}
~~~

`PurchaseOrder.cancel()` validates state and protects invariants. The service loads the aggregate inside a transaction and calls the domain method. A generic CRUD operation cannot substitute for that business decision.

## 5. Understanding save() Properly in Spring Data JPA

`JpaRepository.save()` is a convenience API in Spring Data JPA. In the default implementation, Spring Data determines whether an entity is new and chooses either `persist()` or `merge()`:

- Entity detected as new: calls `EntityManager.persist(entity)`.
- Entity detected as existing: calls `EntityManager.merge(entity)`.

Newness detection typically checks a non-primitive version property if present, or the ID; entities can customize this strategy via `Persistable.isNew()`. Do not infer newness solely from whether an ID is null if the project uses assigned IDs or custom `isNew` logic.

### 5.1. Persist and Merge Differ

**persist(entity):**

- Registers a new entity in the persistence context.
- The passed entity instance becomes managed.
- `INSERT` is typically emitted at flush time, unless the provider requires immediate insertion, such as with certain ID generation strategies.

**merge(entity):**

- Copies state from the input entity onto a managed instance.
- Returns that managed instance.
- The passed input entity does not itself become managed.
- For detached entities, use the instance returned by `save()`/`merge()` if further changes occur within the persistence context.

Example:

~~~java
PurchaseOrder detached = receiveFromAnotherLayer();

PurchaseOrder managed = repository.save(detached);

// When merge is used, `managed` is the managed instance.
// Do not assume `detached` was reattached to the persistence context.
managed.changeDeliveryAddress("Hanoi");
~~~

Merge does not mean an `UPDATE` statement runs immediately. SQL execution is decided at flush time and depends on actual state, dirty checking, and mappings.

Similarly, never submit a detached entity with only a few fields populated and merge it as a partial update. Unpopulated attributes can overwrite existing state with nulls or defaults. For business updates, the safer approach is loading the entity inside a transaction and updating only the intended fields.

## 6. When Is Calling save() Again Unnecessary?

An entity loaded within an active transaction is usually managed. When attributes of a managed entity change, Hibernate tracks the modifications and issues SQL upon flush or commit. This mechanism is called **dirty checking**.

Example:

~~~java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void changeCustomerName(Long id, String newName) {
        Customer customer = repository.findById(id)
                .orElseThrow(() ->
                        new EntityNotFoundException("Customer not found"));

        customer.changeName(newName);

        // No need to call repository.save(customer)
        // because customer is managed in this transaction.
    }
}
~~~

In this example, the transaction opens before the repository finds the `Customer`. The entity is managed inside the persistence context. When `customer.changeName()` alters state, dirty checking detects the change and flush emits the required `UPDATE`.

Calling `repository.save(customer)` right afterward is usually redundant from a JPA perspective when the entity remains managed. It can mislead readers into believing `save()` is mandatory to persist every mutation. Use `save()` when persisting new entities or intentionally merging detached entities.

### 6.1. save() Remains Appropriate for New Entities

~~~java
@Transactional
public Long createCustomer(String email, String name) {
    Customer customer = new Customer(email, name);
    Customer saved = repository.save(customer);
    return saved.getId();
}
~~~

Here `save()` is appropriate because `customer` is a new entity requiring persistence. Capturing the returned reference is also consistent with Spring Data's contract.

### 6.2. saveAndFlush() Does Not Mean Commit

`saveAndFlush()` saves the entity via the repository and forces `EntityManager` to flush the persistence context. Flushing synchronizes pending changes with the database, yet the transaction continues and can still roll back afterward.

Flush deliberately when:

- You need to detect constraint violations at a specific point, such as in tests.
- The database must receive changes before a subsequent query or operation that depends on flushed SQL.
- You need explicit control over when persistence context synchronization occurs.

Avoid calling `saveAndFlush()` habitually after every entity. Flushing too often degrades performance and undermines the batching benefits of grouping operations inside one transaction.

## 7. Transaction Boundaries Determine Managed State

Dirty checking applies only to entities managed in an active persistence context. If a service method lacks an active transaction, or the entity is detached, Java object mutations are not persisted automatically to the database.

A typical flow:

1. The service opens a transaction.
2. The repository loads the aggregate.
3. The service invokes domain methods to mutate state.
4. On transaction flush or commit, JPA synchronizes changes.
5. The persistence context closes.

For read-only queries, `@Transactional(readOnly = true)` communicates intent and enables provider optimizations. This does not guarantee the database rejects all writes; it is transaction metadata whose optimization behavior depends on the stack.

Do not rely on Open Session in View to keep entities managed across every application layer. Define transaction boundaries at the service/use-case level and return DTOs when passing data to APIs or views after the transaction ends.

## 8. Updating Aggregates Without Redundant save() Calls

Suppose `PurchaseOrder` exposes `addLine()` and `cancel()`. The service can load the aggregate, mutate it via its API, and let the transaction finish:

~~~java
@Transactional
public void addLine(Long orderId, String sku, int quantity) {
    PurchaseOrder order = repository.findById(orderId)
            .orElseThrow(() ->
                    new EntityNotFoundException("Order not found"));

    order.addLine(new OrderLine(sku, quantity));
}
~~~

If `PurchaseOrder.lines` has appropriate `PERSIST` cascading and helper methods keep the owning side `OrderLine.order` in sync, Hibernate can persist the new order line at flush time. There is no need to call `save()` on both the order and the line here.

Distinguish these cases:

- Managed parent entity: dirty checking tracks property changes on the parent.
- New child entity added to a relationship: needs `CascadeType.PERSIST` or explicit child persistence.
- Detached child entity: requires an explicit merge/persist strategy; you cannot merely add it to a collection and expect it to reattach.
- Bidirectional relationships: always synchronize the owning side so foreign keys are written properly.

Avoiding redundant `save()` calls does not mean ignoring cascades or entity states. Always know whether an entity is new, managed, or detached before deciding.

## 9. Choosing the Right Repository API for the Job

| Need | Suitable approach |
|---|---|
| Save a new aggregate | `repository.save(newEntity)` |
| Load an aggregate by ID | `repository.findById(id)` |
| Update an already managed entity in a transaction | Mutate the entity; rely on dirty checking |
| Intentionally synchronize a detached entity | Use the returned instance from `repository.save()`/`merge` |
| Catch constraint violations immediately at call site | Deliberate `flush()` or `saveAndFlush()` |
| Dedicated reporting/projection queries | Query repository or read service |
| Complex dynamic searches | Specification, Criteria API, or repository fragment |
| Execute a use case spanning multiple repositories | Application service with an appropriate transaction |

API names should reflect intent. For example, `findByOrderNumber()` describes a query; `cancelOrder()` describes a use case and belongs in a service. Do not turn a repository into a catch-all bucket simply because it already has database access.

## 10. Common Anti-Patterns

**One `GenericService<T, ID>` for all business logic.** Generic layers accumulate entity-type conditionals and cannot express invariants. Reuse small technical utilities while keeping business behavior in concrete services and domain models.

**One repository for every table.** Blanket repositories blur aggregate boundaries, encourage direct child-entity updates, and make domain rules harder to enforce.

**Repositories containing orchestration logic.** If a method invokes other repositories, sends emails, calls payment gateways, or sequences multiple business steps, that responsibility usually belongs in an application service.

**Splitting repositories into overly tiny single-method interfaces.** One interface per method does not automatically improve design. Split only when responsibilities or consumers truly differ; for organizing query implementations, fragments may fit better.

**Calling `save()` after every mutation.** For managed entities inside a transaction, dirty checking already handles changes. Redundant saves clutter code and confuse readers about entity lifecycles.

**Using `save()` to partially update detached entities.** Merging can overwrite managed state with nulls or defaults. Load the aggregate and apply intentional updates instead.

**Calling `saveAndFlush()` everywhere.** Excessive flushing adds round-trips and reduces SQL batching opportunities. Flush only with clear justification.

**Exposing delete-by-ID everywhere.** Some aggregates must verify preconditions or record history before deletion. Let services enforce rules before calling the appropriate persistence operation.

## 11. Verifying Design After Refactoring

After splitting a large repository or removing generic CRUD, verify:

1. Each repository has cohesive data responsibilities and clear aggregate boundaries.
2. Reporting or read-model queries do not clutter aggregate mutation APIs when responsibilities diverge.
3. Services orchestrate use cases, transactions, and required dependencies.
4. Domain models protect invariants through clearly named methods.
5. Generic base repositories contain only genuinely shared contracts and do not expose dangerous operations to all entities.
6. Creation flows use `save()` appropriately; managed-entity updates leverage dirty checking.
7. Detached-entity merges use the returned object and avoid unintended overwrites.
8. Integration tests confirm persisted state after flush/clear and inspect SQL counts when needed.

Do not refactor a repository solely because it has many lines. Base decisions on cohesion, cross-use-case coupling, and ease of change.

## Conclusion

Repositories should express data operations belonging to an aggregate or a cohesive group of queries. Generic CRUD helps only when contracts are truly shared without sacrificing domain rules. For managed entities inside a transaction, dirty checking writes changes automatically on flush or commit, so calling `save()` again is typically unnecessary.

Good design keeps queries in repositories, use-case orchestration in services, invariants in domain models, and transactions at appropriate application boundaries. When each layer maintains its role, Spring Data JPA code becomes easier to read, test, and keep free of redundant persistence calls.