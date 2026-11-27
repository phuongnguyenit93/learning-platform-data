# Distinguishing Default Methods, Repository Fragments, and Business Services

In Spring Data JPA, all three mechanisms help organize behavior around repositories, yet they solve three distinct needs:

- A **default method** adds a small Java operation directly on the repository interface, typically by combining existing query methods.
- A **repository fragment** extends a repository with a custom data-access component, suitable when complex queries or persistence operations are needed.
- A **business service** executes an application use case: enforcing business rules, coordinating multiple repositories or other services, and defining transaction boundaries.

Choosing the right place keeps repositories focused on data, services focused on use cases, and the codebase easier to test.

## 1. Architectural Overview

Spring Data generates a proxy for the repository interface. This proxy combines the built-in CRUD/query implementation, any custom fragments the repository extends, and any default methods declared directly on the interface.

~~~mermaid
flowchart TD
    C[Controller] --> S[Business service]
    S --> R[Spring Data repository proxy]
    R --> D[Default method]
    R --> J[CRUD and query methods]
    R --> F[Custom repository fragment]
    J --> DB[(Database)]
    F --> DB
~~~

The service calls the repository to read or write data. Both default methods and fragments are part of the repository API; they do not replace the service's role in orchestrating use cases.

## 2. Default Methods: Small Conveniences on the Repository Interface

A default method is a method with a body declared using the Java `default` keyword inside an interface. A repository can use it to provide a clearer name for an operation composed from existing query methods.

For example, suppose the `PurchaseOrder` entity has properties `customerId`, `status`, and `createdAt`, and the `OrderStatus` enum has a `PENDING` value:

~~~java
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    Optional<PurchaseOrder>
    findFirstByCustomerIdAndStatusOrderByCreatedAtDesc(
            Long customerId, OrderStatus status);

    default Optional<PurchaseOrder> findLatestPendingForCustomer(
            Long customerId) {
        return findFirstByCustomerIdAndStatusOrderByCreatedAtDesc(
                customerId, OrderStatus.PENDING);
    }
}
~~~

Spring Data implements the query method from its method name. The default method simply delegates to that query method and exposes a more readable business name to repository callers.

**Use when:**

- You want a clear operation name built from one or a few existing repository methods.
- The logic is short, has few branches, and concerns only that repository.
- There is no need to coordinate multiple repositories, call external APIs, or orchestrate a business workflow.

**Avoid when:**

- The method has many steps, branches, or frequently changing business rules.
- You need to inject additional repositories, gateways, publishers, or other components into the interface.
- You need complex custom queries using `EntityManager`, the Criteria API, or SQL.

A default method does not generate a new SQL query merely because it has a body. Queries still come from the query methods, derived queries, JPQL, or persistence mechanisms it calls. Keep default methods brief and treat them as conveniences on the repository API.

## 3. Repository Fragments: Extending Data Access

A repository fragment is a custom component composed into a repository. Use a fragment when Spring Data query methods or declarative JPQL cannot conveniently express the required operation—for example, dynamic filters, Criteria API queries, or specialized data access.

A fragment typically has three parts:

1. An interface describing the custom operations.
2. A class implementing that interface.
3. The main repository extending the fragment interface.

The example below implements an order search supporting multiple optional criteria.

**Step 1 — Declare the criteria and fragment interface**

~~~java
import java.time.LocalDateTime;
import java.util.List;

public record PurchaseOrderCriteria(
        Long customerId,
        OrderStatus status,
        LocalDateTime createdFrom,
        LocalDateTime createdBefore) {
}

public interface PurchaseOrderSearch {
    List<PurchaseOrder> search(PurchaseOrderCriteria criteria);
}
~~~

In this example, `createdFrom` is an inclusive timestamp and `createdBefore` is an exclusive end bound. If a criteria property is `null`, the corresponding condition is omitted from the query.

**Step 2 — Implement the fragment using the Criteria API**

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.CriteriaQuery;
import jakarta.persistence.criteria.Path;
import jakarta.persistence.criteria.Predicate;
import jakarta.persistence.criteria.Root;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

public class PurchaseOrderSearchImpl implements PurchaseOrderSearch {

    @PersistenceContext
    private EntityManager entityManager;

    @Override
    public List<PurchaseOrder> search(PurchaseOrderCriteria criteria) {
        CriteriaBuilder cb = entityManager.getCriteriaBuilder();
        CriteriaQuery<PurchaseOrder> query =
                cb.createQuery(PurchaseOrder.class);
        Root<PurchaseOrder> order = query.from(PurchaseOrder.class);

        List<Predicate> predicates = new ArrayList<>();

        if (criteria.customerId() != null) {
            predicates.add(cb.equal(
                    order.get("customerId"), criteria.customerId()));
        }

        if (criteria.status() != null) {
            predicates.add(cb.equal(
                    order.get("status"), criteria.status()));
        }

        Path<LocalDateTime> createdAt = order.get("createdAt");

        if (criteria.createdFrom() != null) {
            predicates.add(cb.greaterThanOrEqualTo(
                    createdAt, criteria.createdFrom()));
        }

        if (criteria.createdBefore() != null) {
            predicates.add(cb.lessThan(
                    createdAt, criteria.createdBefore()));
        }

        query.select(order);
        if (!predicates.isEmpty()) {
            query.where(predicates.toArray(Predicate[]::new));
        }
        query.orderBy(cb.desc(createdAt));

        return entityManager.createQuery(query).getResultList();
    }
}
~~~

**Step 3 — Compose the fragment into the main repository**

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.Optional;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long>, PurchaseOrderSearch {

    Optional<PurchaseOrder>
    findFirstByCustomerIdAndStatusOrderByCreatedAtDesc(
            Long customerId, OrderStatus status);

    default Optional<PurchaseOrder> findLatestPendingForCustomer(
            Long customerId) {
        return findFirstByCustomerIdAndStatusOrderByCreatedAtDesc(
                customerId, OrderStatus.PENDING);
    }
}
~~~

Spring Data detects the fragment implementation class by naming convention: the `PurchaseOrderSearch` interface corresponds to `PurchaseOrderSearchImpl` when the default suffix is `Impl`. If the project configures another suffix, the class name must follow that configuration. Place components within the package scope scanned by Spring Data so they are discovered.

Once composed, callers using the repository can invoke CRUD methods, default methods, and the fragment's `search` method on the same `PurchaseOrderRepository` bean.

**Use a fragment when:**

- A query has many dynamic conditions or requires the Criteria API.
- You need `EntityManager`, native SQL, Querydsl, or a specialized persistence technique.
- You want to split groups of data-access behaviors into small, reusable components composed into multiple repositories.

A fragment still belongs to the data-access layer. It should focus on how data is read/written and must not become a place for orchestrating business workflows such as payments, notifications, or coordinating multiple aggregates.

## 4. Business Services: Executing a Use Case

A business service sits in the application or domain layer. It receives requests from a controller or another caller, checks use-case rules, invokes repositories, and coordinates necessary components.

Example: cancelling an order only when its current status permits cancellation.

~~~java
import jakarta.persistence.EntityNotFoundException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

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
                        new EntityNotFoundException(
                                "Order not found: " + orderId));

        if (!order.canBeCancelled()) {
            throw new IllegalStateException(
                    "Current order cannot be cancelled");
        }

        order.cancel();
    }
}
~~~

This example assumes the `PurchaseOrder` entity has `canBeCancelled()` and `cancel()` methods encapsulating the order's own state rules. The service orchestrates the use case and establishes the transaction with `@Transactional`.

When `findById` is called inside a transaction, the entity is managed by the persistence context. When `order.cancel()` mutates the entity, JPA dirty checking persists the change when the transaction flushes/commits; there is no need to call `save()` just to persist a managed entity.

In a larger use case, the service might coordinate `PurchaseOrderRepository`, `PaymentRepository`, `InventoryService`, and `NotificationPublisher`. The service is the proper place to define step ordering, handle outcomes, and manage the workflow transaction. Rules tightly coupled to a single entity should still be encapsulated inside the entity or value object; the service should not pull all that logic out.

When designing with DDD, distinguish between application services and domain services. An application service orchestrates a use case and depends on repositories or service ports. A domain service holds domain rules that do not naturally belong to a specific entity. Both can be registered with `@Service` in Spring, though the annotation itself does not dictate the class's responsibility.

## 5. Comparing and Choosing the Right Mechanism

| Criterion | Default method | Repository fragment | Business service |
|---|---|---|---|
| Location | Repository interface | Component composed into repository | Application/business layer |
| Responsibility | Short Java convenience around repository API | Custom data-access logic | Use-case orchestration and business rules |
| Typical tools | Calls existing query methods | `EntityManager`, Criteria API, Querydsl, SQL | Repositories, domain objects, gateways, event publishers |
| Coordination scope | Single repository | One group of persistence operations | Potentially multiple repositories and services |
| Examples | `findLatestPendingForCustomer` | `search` with dynamic filters | `cancelOrder`, `checkout`, `approveOrder` |

You can decide using three questions:

- **Just need a clearer name for a repository operation or to combine a couple of simple query methods?** Use a default method.
- **Need to build custom querying or persistence operations?** Use a repository fragment.
- **Need to execute a use case, enforce business rules, or coordinate multiple components?** Use a business service.

A service is allowed to call fragment methods. For example, a service can call `repository.search(criteria)` and then apply business rules to the results. Querying belongs to the fragment; business decisions and orchestration belong to the service.

## 6. Common Design Mistakes

**Putting long workflows into default methods.** Repository interfaces accumulate business branches and become hard to test and extend. Move orchestration into a service; keep default methods for small conveniences.

**Placing business rules inside fragments.** Because fragments have access to `EntityManager`, it is tempting to turn them into catch-all handlers. Keep fragments focused on queries and persistence; let services or domain models handle business rules.

**Writing complex data queries directly inside services.** This couples services to JPA details and makes queries harder to reuse. Encapsulate queries inside repository query methods or fragments.

**Misnaming fragment implementation classes.** If the interface is `PurchaseOrderSearch` but the class does not follow the configured postfix, Spring Data may fail to compose the fragment into the repository. Check names, packages, and repository scanning configuration whenever custom methods are not recognized.

**Using incorrect transaction boundaries.** A use case updating multiple pieces of data usually needs a service-level transaction so steps share a consistent boundary. For read-only queries, consider `@Transactional(readOnly = true)` on the appropriate method or class. Do not assume every query method automatically has a transaction merely because it belongs to a repository.

**Writing pass-through services with no clear responsibility.** A service class that merely forwards a single repository method call may add no value. However, a service remains useful when it serves as a use-case boundary for authorization, transactions, orchestration, or application policies. Ensure class names and responsibilities reflect their actual role.

## 7. Testing According to Responsibility

- **Default methods:** integration-test the repository against a database to verify the default method invokes the intended query method and returns the right result.
- **Repository fragments:** integration-test with JPA to verify filters, boundary conditions, sort order, and behavior when no criteria are supplied.
- **Business services:** test business branches such as order found/not found, cancellable/non-cancellable states, and coordination across dependencies. Use integration tests when you need to verify transactions and dirty checking.

## Conclusion

Default methods keep the repository API concise and readable; fragments add custom data-access capabilities; business services organize the steps of a use case and enforce business rules. When each component stays within its responsibility, Spring Data JPA codebases become easier to maintain, test, and extend.