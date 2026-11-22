# Refactoring from Inheritance to Composition in Java

> **Objective:** Recognize when `extends` is used merely for code reuse, replace that inheritance relationship with collaborators connected through fields and method calls (composition + delegation), preserve behavior, and manage the impact on existing callers.

## 1. Why Refactor?

**Inheritance** says that a subclass is a valid kind of its superclass (*is-a*). In Java, `class Child extends Parent` inherits methods, accessible state, and the behavioral contract of `Parent`; `Child` objects can also be used where `Parent` is required.

**Composition** says that an object **uses** another object to accomplish its work (*has-a / uses-a*). Instead of using `extends`, the business class holds a reference to a collaborator and **delegates** the appropriate work to it.

For example, `OrderService` **is not** an order store; it **uses** `OrderRepository` to persist orders. Defining `OrderService extends OrderStore` just to reuse `save()` indicates a modeling problem.

Signs that refactoring may be worthwhile:

- A subclass calls a few superclass methods but has no meaningful *is-a* relationship.
- A subclass unintentionally exposes superclass operations such as `deleteAll()` or `resetConnection()`.
- A superclass change breaks many subclasses even though they need only part of its functionality.
- Faking dependencies in tests requires inheritance, overrides, or real infrastructure objects.
- Switching algorithms, storage implementations, or notification services at runtime requires more and more subclasses.
- Methods must be overridden with preconditions or postconditions that no longer match the superclass contract (risking violation of the **Liskov Substitution Principle – LSP**).

**There is no rule that "all inheritance is bad."** Keep inheritance when classification is genuinely valid and subclasses fully honor the superclass contract. Refactor when inheritance is mainly used to borrow implementation or creates excessive coupling.

## 2. Before Refactoring: Business Logic Inherits from Storage

The following Java 17+ example uses in-memory storage to focus on design. In a real system, `OrderStore` might access JDBC, JPA, or a remote API.

~~~java
import java.util.HashMap;
import java.util.Map;

record Order(long id, long totalCents) {}

class OrderStore {
    private final Map<Long, Order> data = new HashMap<>();

    public void save(Order order) {
        data.put(order.id(), order);
    }

    public Order find(long id) {
        return data.get(id);
    }

    public void deleteAll() {
        data.clear();
    }
}

// Thiết kế cũ: quan hệ "OrderService is-a OrderStore" không đúng.
class OrderService extends OrderStore {
    public void place(Order order) {
        if (order == null || order.totalCents() <= 0) {
            throw new IllegalArgumentException("Invalid order");
        }
        save(order); // Kế thừa để tái sử dụng phương thức lưu
    }
}
~~~

The problem is not Java syntax but the **public contract**: any code holding an `OrderService` can call `deleteAll()`, `find()`, and `save()` even though those are storage-layer operations. Changes to `OrderStore` may directly affect `OrderService`. Supporting different storage types through `OrderService` subclasses can also multiply the inheritance classes.

Distinguish two kinds of compatibility during refactoring:

1. **Business behavior:** `place()` must still validate the order and save it exactly once; order data must still be retrievable.
2. **API and static typing:** Existing code may pass `OrderService` to an `OrderStore` parameter or call `deleteAll()` directly. Removing `extends` makes such code fail to compile. This may be an intentional design improvement, but callers must be identified and a migration path prepared.

## 3. After Refactoring: Depend on a Small Contract

Separate four independent roles: data model, storage port (`OrderRepository`), storage implementation, and business service.

**Order.java**

~~~java
public record Order(long id, long totalCents) {}
~~~

**OrderRepository.java**

~~~java
import java.util.Optional;

public interface OrderRepository {
    void save(Order order);
    Optional<Order> findById(long id);
}
~~~

**InMemoryOrderRepository.java**

~~~java
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

public final class InMemoryOrderRepository implements OrderRepository {
    private final Map<Long, Order> data = new ConcurrentHashMap<>();

    @Override
    public void save(Order order) {
        data.put(order.id(), order);
    }

    @Override
    public Optional<Order> findById(long id) {
        return Optional.ofNullable(data.get(id));
    }
}
~~~

**OrderService.java**

~~~java
import java.util.Objects;
import java.util.Optional;

public final class OrderService {
    private final OrderRepository repository;

    // Constructor injection: phụ thuộc được cấp từ ngoài.
    public OrderService(OrderRepository repository) {
        this.repository = Objects.requireNonNull(repository, "repository");
    }

    public void place(Order order) {
        if (order == null || order.totalCents() <= 0) {
            throw new IllegalArgumentException("Invalid order");
        }
        repository.save(order); // Ủy quyền đúng trách nhiệm
    }

    public Optional<Order> find(long id) {
        return repository.findById(id);
    }
}
~~~

**Main.java**

~~~java
public class Main {
    public static void main(String[] args) {
        OrderRepository repository = new InMemoryOrderRepository();
        OrderService service = new OrderService(repository);

        service.place(new Order(101L, 125_000L));
        System.out.println(service.find(101L));
        // Optional[Order[id=101, totalCents=125000]]
    }
}
~~~

Create the five files in one directory and run Java 17+: `javac Order.java OrderRepository.java InMemoryOrderRepository.java OrderService.java Main.java` followed by `java Main` (in a terminal with the Java SDK). The example represents `totalCents` as an integer to avoid floating-point currency errors from `double`.

**Result of the refactor:** `OrderService` exposes only the necessary business operations. Persistence can change to JDBC/JPA by replacing the `OrderRepository` implementation without modifying the `place()` algorithm. `OrderService` collaborates with a repository instead of subclassing one.

~~~mermaid
classDiagram
    class OrderService {
        -OrderRepository repository
        +place(Order)
        +find(long)
    }
    class OrderRepository {
        <<interface>>
        +save(Order)
        +findById(long)
    }
    class InMemoryOrderRepository {
        -Map data
        +save(Order)
        +findById(long)
    }
    OrderService --> OrderRepository : ủy quyền
    InMemoryOrderRepository ..|> OrderRepository : triển khai
~~~

In the diagram, the arrow from `OrderService` to `OrderRepository` represents dependency/delegation. With **constructor injection**, a repository's lifecycle may be externally managed, and it may be shared; a filled diamond (*strong ownership composition* in UML) is not necessarily appropriate. The design here is about **assembling objects**, not claiming that the service exclusively owns the repository's lifecycle.

## 4. Direct Comparison

| Criterion | `OrderService extends OrderStore` | `OrderService` contains `OrderRepository` |
|---|---|---|
| Modeled relationship | Implicitly claims the service **is** a storage component | The service **uses** storage |
| Reuse mechanism | Through inherited methods | Through calls to `repository.save(...)` |
| Public API | May inherit technical infrastructure operations | Exposes only explicitly defined service operations |
| Changing storage implementation | Can depend heavily on superclass structure | Replace the interface implementation |
| Unit testing | May depend on superclass behavior and infrastructure state | Inject a fake/stub/spy through the constructor |
| Coupling | Tight to implementation and `extends` type relationship | Limited to the small `OrderRepository` contract |
| Cost | Fewer fields and delegated calls | Adds an abstraction and dependency wiring |

**Note:** `implements OrderRepository` in the storage class still enables polymorphism through a Java interface. "Favor composition over inheritance" mainly addresses **inappropriate implementation inheritance**; it does not prohibit interfaces.

## 5. A Safe Refactoring Process for Running Code

1. **Identify the inheritance relationship:** Find the subclass to refactor, calls to `super.method()`, `protected` methods, superclass fields, constructors, and places that use a supertype variable. Do not infer relationships from class names alone.
2. **Define the behavioral contract:** List valid/invalid inputs, exceptions, call order, data operations, transactions, and outcomes. Capture valuable test cases before restructuring.
3. **Separate responsibilities:** Choose the component that really performs each task (repository, formatter, sender, policy, etc.). Create small interfaces when implementations must be swappable or test doubles are needed. A stable concrete collaborator is reasonable if no abstraction is necessary.
4. **Inject components:** Add a `private final` field and supply it through the constructor; prefer dependency injection over calling `new ConcreteRepository()` inside the service.
5. **Migrate calls individually:** Replace `save(order)` or `super.save(order)` with `repository.save(order)`. Add forwarding methods to the service only when they genuinely belong to its business API.
6. **Migrate callers:** Update code that relies on the service being a repository subtype or on inherited methods. For publicly consumed APIs, define a compatibility strategy and release-version plan.
7. **Remove `extends`:** Once no superclass state or methods are accessed and all supertype call sites have been addressed, remove the inheritance relationship and overrides used only by the old design.
8. **Test and review:** Run unit and integration tests, including real-data cases. Review lifecycles, concurrency, transactions, logging, and object-creation costs.

~~~mermaid
flowchart TD
    A[Nhận diện extends sai trách nhiệm] --> B[Liệt kê hợp đồng và caller]
    B --> C[Tách thành phần và interface khi cần]
    C --> D[Tiêm phụ thuộc qua constructor]
    D --> E[Thay lời gọi kế thừa bằng ủy quyền]
    E --> F[Di chuyển caller và gỡ extends]
    F --> G{Test hành vi và API đạt?}
    G -->|Có| H[Hoàn tất refactor]
    G -->|Chưa| I[Sửa chênh lệch rồi kiểm thử lại]
    I --> G
~~~

In large projects, **caller migration** and **inheritance removal** may span multiple commits or releases. Do not claim a change is compatible if method signatures or type assignability have changed.

## 6. Testing the Behavior That Must Be Preserved

With composition, a call-recording object can stand in for a database. The following example assumes the `Order.java`, `OrderRepository.java`, and `OrderService.java` files already exist and uses JUnit Jupiter 5.

**OrderServiceTest.java**

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.util.Optional;

class OrderServiceTest {
    static final class RecordingRepository implements OrderRepository {
        Order saved;
        int saveCount;

        @Override
        public void save(Order order) {
            saved = order;
            saveCount++;
        }

        @Override
        public Optional<Order> findById(long id) {
            return Optional.ofNullable(saved)
                    .filter(order -> order.id() == id);
        }
    }

    @Test
    void validOrderIsSavedOnce() {
        RecordingRepository repository = new RecordingRepository();
        OrderService service = new OrderService(repository);
        Order order = new Order(7L, 50_000L);

        service.place(order);

        assertSame(order, repository.saved);
        assertEquals(1, repository.saveCount);
        assertEquals(Optional.of(order), service.find(7L));
    }

    @Test
    void invalidOrderDoesNotReachRepository() {
        RecordingRepository repository = new RecordingRepository();
        OrderService service = new OrderService(repository);

        assertThrows(IllegalArgumentException.class,
                () -> service.place(new Order(7L, 0L)));
        assertThrows(IllegalArgumentException.class,
                () -> service.place(null));
        assertEquals(0, repository.saveCount);
    }

    @Test
    void nullDependencyIsRejectedImmediately() {
        assertThrows(NullPointerException.class,
                () -> new OrderService(null));
    }
}
~~~

These tests verify **business outcomes and interactions at boundaries**: a valid order is saved exactly once, invalid orders do not affect the repository, and required dependencies are validated. There is no need to test whether the class has a field named `repository` or contains the source line `repository.save(...)`; those are implementation details.

Alongside these tests, retain an **integration test** with a real repository if the change affects a database: verify persistence, rollback, transaction boundaries, and data reads, since a fake cannot prove those behaviors.

## 7. Easily Overlooked Risks

| Situation | Risk when removing `extends` | Mitigation |
|---|---|---|
| A caller assigns `OrderService` to `OrderStore` | Compile error because the subtype relationship is gone | Migrate callers to `OrderRepository` or an appropriate business API |
| A caller invokes inherited methods | Public API changes | Inventory usages; decide whether to migrate, retain an intentional façade, or version the API |
| Overrides a `protected` hook or uses `super` | Extension points and execution order are lost | Express behavior as a named policy/strategy or callback |
| A superclass owns `protected` state | State no longer resides in the same object | Define state ownership and synchronization; avoid unintentional duplication |
| Calling `new` for a repository on every operation | Lifecycle control is lost, and resources are wasted | Inject a correctly scoped dependency; close resources at the lifecycle owner |
| Frameworks treat subclasses specially | Metadata/proxy/ORM mappings may change | Check JPA inheritance, Spring AOP, serialization, and project-specific lifecycles |
| A wrapper service re-exposes every component method | Infrastructure API still leaks through the design | Delegate only operations belonging to the service's responsibility |
| A shared repository has mutable state | Concurrent calls may cause race conditions | Ensure appropriate thread safety; the example uses `ConcurrentHashMap` for in-memory storage |
| Overly broad interfaces or one interface per class | Boilerplate and artificial abstractions | Design interfaces around client needs; extract them only for useful substitution or boundaries |

In transactional code, pay particular attention to where `@Transactional` is applied: moving methods between beans can change how Spring proxies intercept calls. For JPA entities, `extends` may represent genuine inheritance mapping; do not remove it mechanically without checking the schema and migration requirements.

## 8. When Is Composition Not the Best Choice?

- **Valid, stable classification:** `Circle extends Shape` may fit if `Shape` defines a genuine geometric contract that every `Circle` honors.
- **A framework requires a base class:** Some adapters/frameworks use template methods and specific hooks; understand supported extension points before removing inheritance.
- **An object only wraps a small behavior without needing multiple implementations:** A concrete dependency may be used directly; not every class needs an interface.
- **Behavior is better expressed with function parameters:** For small variations, passing a `Function`/`Predicate` can be simpler than a hierarchy or separate Strategy.

The deciding question is: **"Can every subclass object replace a superclass object while honoring all the superclass's promises?"** If not, and the real goal is simply to use some functionality, prefer composition.

## 9. Practice Exercise

A `ReportService extends CsvFormatter` currently calls `format(report)` to produce CSV. Now JSON and XML are also required.

Sketch a refactor in which `ReportService` contains a `ReportFormatter` collaborator. The `ReportFormatter` contract exposes `String format(Report report)`. Implement `CsvReportFormatter` and `JsonReportFormatter` through the interface, and supply the implementation via the constructor. Verify that `ReportService` no longer inherits any CSV configuration methods and that tests can inject a fake formatter to check returned content.

**Self-assessment:** Have you removed the artificial *is-a* relationship? Is the business contract still clear? Can formatters be replaced without editing `ReportService`? Have callers that previously depended on `CsvFormatter` been addressed?

---

**Key takeaway:** Refactoring from inheritance to composition involves more than replacing `extends` with an object field. It requires **assigning responsibilities correctly, separating contracts, delegating transparently, migrating callers, and preserving behavior through verification**.
