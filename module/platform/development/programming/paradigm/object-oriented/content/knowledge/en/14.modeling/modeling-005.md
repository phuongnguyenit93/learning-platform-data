# UML Class Diagrams: Members and Relationships in Java OOP Design

> **Goal:** Read, draw, and validate *UML class diagrams* showing class names, attributes, operations, visibility, types, multiplicity, and relationships. Translate them into Java and recognize what diagrams merely **describe**, rather than enforce automatically in Java/UML.

## 1. What Questions Do Class Diagrams Answer?

A class diagram is a **static structural model** showing which concepts exist, their state and behavior, and the relationships connecting them.

For example, an e-commerce requirement where “customers place orders, each order has several lines, each line selects a product, and payment uses a gateway” raises these questions:

- Which data belongs to `Customer`, `Order`, `OrderLine`, and `Product`?
- Who **owns** order lines, and who merely **references** products?
- How many orders may a customer have? May a draft order have no lines?
- Which behaviors belong in `Order` to protect business rules?
- How does `CheckoutService` depend on `PaymentGateway`, and how can implementations be swapped?

Class diagrams aid **design communication, responsibility allocation, relationship discovery, and architecture reviews**. They do not describe execution order; use an appropriate *sequence diagram* or *activity diagram* for checkout call sequences.

Class diagrams can be drawn at three levels:

| Model level | Focus | Useful details |
|---|---|---|
| **Domain analysis** | Concepts and rules | `Order` contains `OrderLine`; `Customer` places `Order` |
| **Software design** | Responsibilities, APIs, dependencies | `Order.addLine(...)`, `PaymentGateway.charge(...)`, multiplicities |
| **Implementation** | Structure close to Java code | Visibility, concrete types, constructors, collections, interfaces, static members |

Do not crowd a simple analysis diagram with every getter, setter, DTO, library type, and infrastructure dependency. Include only members and relationships necessary to explain its design decisions.

## 2. What Does a Class Box Contain?

The usual notation is a rectangle divided into three compartments: **class name**, **attributes**, and **operations**.

~~~text
┌──────────────────────────────────────┐
│                Order                 │  (1) Tên lớp
├──────────────────────────────────────┤
│ - id: String                         │  (2) Thuộc tính
│ - lines: List<OrderLine>             │
│ - status: OrderStatus                │
├──────────────────────────────────────┤
│ + addLine(p: Product, qty: int): void│  (3) Phương thức
│ + totalCents(): long                 │
│ + confirm(): void                    │
└──────────────────────────────────────┘
~~~

Common UML conventions:

- **Class name** goes in the top compartment; abstract classes may be italicized or marked `«abstract»`.
- **Attributes** describe state using `visibility name: Type [multiplicity] = defaultValue {property}`. Not every part must appear on every diagram.
- **Operations** describe provided behavior using `visibility name(parameter: Type = default): ReturnType`. Several parameters may appear.
- **Compartments or irrelevant members may be hidden** to improve readability; this changes the presentation detail, not what methods the class actually has.
- UML distinguishes *operations* (callable contracts) from *methods* (implementations). Java tutorials often call both “methods,” but the diagram does not necessarily show the method body.

### Visibility Symbols

| UML | Meaning | Approximate Java equivalent |
|---|---|---|
| `+` | Public | `public` |
| `-` | Private | `private` |
| `#` | Protected | `protected` |
| `~` | Package visibility | No modifier (package-private) |

One subtlety: Java `protected` permits same-package access and specific cross-package subclass access; it is not necessarily identical to all UML access interpretations across programming languages.

UML marks **derived attributes** with `/`, such as `/totalCents: long`: a value computed from order lines rather than necessarily stored in a Java `totalCents` field. Constraints like `{readOnly}` can represent readonly properties. Standard UML **underlines** `static` members; in Java they correspond to `static`. Diagram tools may have their own syntax and limitations for these details.

### UML Example with Mermaid

~~~mermaid
classDiagram
    class Order {
        -String id
        -List~OrderLine~ lines
        -OrderStatus status
        +addLine(Product product, int quantity) void
        +totalCents() long
        +confirm() void
    }
~~~

Mermaid fits READMEs because diagrams can be versioned alongside documentation. However, UML details such as text styling, derived properties, and complex constraints may not render faithfully across Mermaid implementations. Add nearby prose for important details.

## 3. Read Attributes and Operations Precisely

Sample attribute declarations:

~~~text
- id: UUID
- capacity: int = 30
- members: Set<Member> [0..*]
- /remainingSeats: int {readOnly}
~~~

Interpretation:

- `id` has identifier type `UUID` and is hidden from external access.
- `capacity` has a model default of 30 (which does not guarantee that the Java implementation sets 30).
- `members` holds several `Member` references; multiplicity `[0..*]` specifies the expected number of associated elements.
- `remainingSeats` is a **derived**, read-only value; Java may implement it as `remainingSeats()` rather than a stored field.

Sample operation declarations:

~~~text
+ enroll(student: Student): EnrollmentReceipt
+ findById(id: UUID): Optional<Member>
- validateCapacity(requested: int): void
# onStatusChanged(old: Status, next: Status): void
~~~

UML puts **parameter names before types**, while Java uses `Type parameterName`. For example:

~~~java
public EnrollmentReceipt enroll(Student student) {
    // implementation
    throw new UnsupportedOperationException("Example signature only");
}
~~~

`Optional<Member>` is a Java **return type**, not an association multiplicity. Do not infer from `Optional` that an entity must be stored in a collection, or from `List<>` that the association must be aggregation.

### Interfaces, Abstract Classes, and Enums

~~~mermaid
classDiagram
    class PaymentGateway {
        <<interface>>
        +charge(String orderId, long amountCents) void
    }
    class AbstractDiscountPolicy {
        <<abstract>>
        +discount(long amount) long
    }
    class OrderStatus {
        <<enumeration>>
        DRAFT
        CONFIRMED
    }
~~~

In Java:

- An `interface` defines a behavioral contract; concrete classes use `implements`.
- An `abstract class` can hold state and implemented methods as well as declare abstract methods.
- An `enum` represents a finite set of values and can have behavior; include it where transitions or allowed values matter.
- Not every class needs an interface or abstract superclass. Use these when a shared contract or meaningful substitution point exists.

## 4. Comparing UML Relationship Types

Arrowheads and diamonds convey distinct meanings; **do not decorate diagrams with every line type without purpose**.

| Relationship | UML / Mermaid notation | Meaning | Common Java representation |
|---|---|---|---|
| **Association** | `--` or `-->` | Objects are associated with each other | Field/reference or domain relationship |
| **Shared aggregation** | `o--` | Whole–part grouping with weak ownership semantics | `Team` references an independent `Employee` |
| **Composition** | `*--` | Whole owns a part; a part belongs to at most one composite at a time | `Order` owns `OrderLine` |
| **Generalization** | `<|--` | Subclass is a kind of superclass | `extends` |
| **Realization** | `<|..` | Class implements an interface | `implements` |
| **Dependency** | `<..` / `..>` | One element uses another for definitions or operations | Parameter, local variable, method call |
 
Key characteristics:

**Association:** A structural connection between objects. A line **without an arrow** indicates association but does not by itself specify navigability; an arrow conveys navigation or direction in the chosen notation. **Both classes need not hold reciprocal reference fields.**

**Aggregation:** A **hollow diamond at the whole end**, such as a team grouping employees. UML shared aggregation has fewer strict ownership semantics than composition; ordinary association is often clearer unless whole–part grouping is important.

**Composition:** A **filled diamond at the whole end**. Parts have strong ownership and cannot belong to two composites simultaneously. Domain rules and APIs must enforce this. Java GC does not automatically “delete a part when the whole is deleted”; DB cascading/orphan removal must also be configured intentionally.

**Generalization:** A **hollow triangle pointing to the superclass**. `Car extends Vehicle` is sound only when `Car` fulfills the `Vehicle` contract. Inheritance merely to “borrow code” often harms maintainability.

**Realization:** A **dashed line ending with a hollow triangle** pointing to the interface. `StripeGateway implements PaymentGateway` illustrates this, but an interface does not have to have multiple implementations.

**Dependency:** A **dashed line with a plain arrowhead** toward the used element. It often means a class receives a parameter or calls another API **without necessarily retaining a long-lived reference**. Do not equate dependency with composition.

A quick mnemonic: **association lines** connect objects; **diamonds** mark whole–part; **hollow triangles** indicate a parent type or contract; **simple dashed lines** indicate usage dependencies.

## 5. Multiplicity, Role Names, and Navigability

Multiplicity says how many objects at one end can correspond to **one object at the other end**.

| UML multiplicity | Interpretation |
|---|---|
| `1` | Exactly one |
| `0..1` | Zero or one |
| `*` or `0..*` | Zero or many |
| `1..*` | At least one |
| `2..5` | From two through five, inclusive |

Example:

~~~mermaid
classDiagram
    Customer "1" <-- "0..*" Order : places
    Order "1" *-- "0..*" OrderLine : owns
    OrderLine "0..*" --> "1" Product : refers to
~~~

Interpret the relationships:

- **Each `Order` belongs to exactly one `Customer`**; a customer may have 0 or more orders.
- **Each `OrderLine` belongs to exactly one `Order`**; a draft may have 0 lines. If confirmed orders require at least one line, that is a separate **state-dependent constraint**.
- **Each `OrderLine` references one `Product`**; a product may appear in many order lines across orders. Products exist independently and **are not** parts deleted with orders.

**The diamond is at `Order`**, not `OrderLine`. For relationships with role names (such as `customer` and `lines`), label association ends to clarify their roles; renderer support varies.

Corresponding Java API example:

~~~java
final class Order {
    private final Customer customer;          // Order --> 1 Customer
    private final List<OrderLine> lines;       // Order *-- 0..* OrderLine
    // ...
}
~~~

In Java, **field syntax does not automatically enforce multiplicity**: `Customer customer` may still be null if allowed by the constructor, and `List<OrderLine>` may contain an element from a different order unless checked. Enforce invariants, prevent direct collection mutation, and add DB constraints where necessary.

## 6. Full Design Example: Customer, Order, and Payment

Assumed requirements:

1. A customer may create many orders; each order belongs to one customer.
2. Every order has **its own lines**, each containing a product, quantity, and unit price fixed when added.
3. Catalog products remain independent when an order is canceled or deleted.
4. Draft orders may have no lines; only nonempty orders can be confirmed.
5. Checkout sends payment requests through an interface to allow adapter replacement.

### Class Diagram

~~~mermaid
classDiagram
    direction LR
    class Customer {
        <<entity>>
        +String id
        +String name
    }
    class Product {
        <<entity>>
        +String sku
        +String name
        +long priceCents
    }
    class Order {
        -String id
        -Customer customer
        -List~OrderLine~ lines
        -Status status
        +addLine(Product product, int quantity) void
        +totalCents() long
        +isEmpty() boolean
        +confirm() void
        +status() Status
    }
    class OrderLine {
        -Product product
        -int quantity
        -long unitPriceCents
        +subtotalCents() long
    }
    class CheckoutService {
        -PaymentGateway gateway
        +checkout(Order order) void
    }
    class PaymentGateway {
        <<interface>>
        +charge(String orderId, long amountCents) void
    }
    class ConsolePaymentGateway {
        +charge(String orderId, long amountCents) void
    }

    Customer "1" <-- "0..*" Order : places
    Order "1" *-- "0..*" OrderLine : owns
    OrderLine "0..*" --> "1" Product : refers to
    CheckoutService ..> Order : checkout parameter
    CheckoutService --> PaymentGateway : injected dependency
    ConsolePaymentGateway ..|> PaymentGateway : implements
~~~

Reasons for each choice:

- `Customer` is referenced by `Order` but can exist without orders: **association**. The diagram does not require a reverse collection on `Customer`.
- `OrderLine` is a part created and managed by `Order`: **composition**. Each line belongs to one order and its instance is not shared across orders.
- `Product` is an independent referenced entity/structure, not an order child: **association**.
- `CheckoutService` invokes `Order` behavior through parameters: **dependency**. It stores a constructor-injected `PaymentGateway` field; its directed line models association/dependency.
- `ConsolePaymentGateway` implements `PaymentGateway`: **realization**. Other adapters can replace it without changing checkout's interface.
- The `«entity»` stereotypes on `Customer` and `Product` emphasize stable `id`/`sku` identity and lifecycles independent of `Order`. The Java example uses immutable `record` types for simplicity; `record` alone does not determine whether a domain object is an entity or value object.

### Runnable Single-File Java 17+ Example

Create **`OrderDiagramDemo.java`** with the full code below:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

// Độc lập với vòng đời của một Order.
record Customer(String id, String name) {
    Customer {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(name, "name");
        if (id.isBlank() || name.isBlank()) {
            throw new IllegalArgumentException("Invalid customer");
        }
    }
}

record Product(String sku, String name, long priceCents) {
    Product {
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(name, "name");
        if (sku.isBlank() || name.isBlank() || priceCents < 0) {
            throw new IllegalArgumentException("Invalid product");
        }
    }
}

// Chủ sở hữu vòng đời của từng dòng đơn.
final class Order {
    enum Status { DRAFT, CONFIRMED }

    private final String id;
    private final Customer customer;
    private final List<OrderLine> lines = new ArrayList<>();
    private Status status = Status.DRAFT;

    // Chỉ Order có thể tạo một dòng; không cung cấp API đổi owner.
    private static final class OrderLine {
        private final Product product;
        private final int quantity;
        private final long unitPriceCents;

        private OrderLine(Product product, int quantity) {
            this.product = Objects.requireNonNull(product, "product");
            if (quantity <= 0) {
                throw new IllegalArgumentException("Quantity must be positive");
            }
            this.quantity = quantity;
            this.unitPriceCents = product.priceCents(); // Chốt đơn giá
            Math.multiplyExact(unitPriceCents, quantity); // Kiểm tra tràn số
        }

        private long subtotalCents() {
            return Math.multiplyExact(unitPriceCents, quantity);
        }
    }

    Order(String id, Customer customer) {
        this.id = Objects.requireNonNull(id, "id");
        this.customer = Objects.requireNonNull(customer, "customer");
        if (id.isBlank()) {
            throw new IllegalArgumentException("Order id is blank");
        }
    }

    String id() {
        return id;
    }

    Customer customer() {
        return customer;
    }

    Status status() {
        return status;
    }

    boolean isEmpty() {
        return lines.isEmpty();
    }

    int lineCount() {
        return lines.size();
    }

    // Command: Owner kiểm tra và tạo part trong phạm vi của mình.
    void addLine(Product product, int quantity) {
        ensureDraft();
        lines.add(new OrderLine(product, quantity));
    }

    // Query: Tính tổng không sửa trạng thái.
    long totalCents() {
        long total = 0;
        for (OrderLine line : lines) {
            total = Math.addExact(total, line.subtotalCents());
        }
        return total;
    }

    void confirm() {
        ensureDraft();
        if (lines.isEmpty()) {
            throw new IllegalStateException("Cannot confirm empty order");
        }
        status = Status.CONFIRMED;
    }

    private void ensureDraft() {
        if (status != Status.DRAFT) {
            throw new IllegalStateException("Order is not a draft");
        }
    }
}

// Interface là hợp đồng, không có quan hệ sở hữu OrderLine.
interface PaymentGateway {
    void charge(String orderId, long amountCents);
}

final class ConsolePaymentGateway implements PaymentGateway {
    @Override
    public void charge(String orderId, long amountCents) {
        System.out.printf("Charge %s: %d cents%n", orderId, amountCents);
    }
}

// Use case nhận Order làm tham số, giữ dependency qua constructor.
final class CheckoutService {
    private final PaymentGateway gateway;

    CheckoutService(PaymentGateway gateway) {
        this.gateway = Objects.requireNonNull(gateway, "gateway");
    }

    void checkout(Order order) {
        Objects.requireNonNull(order, "order");

        if (order.status() != Order.Status.DRAFT || order.isEmpty()) {
            throw new IllegalStateException("Order not ready");
        }

        long amount = order.totalCents();
        gateway.charge(order.id(), amount);
        order.confirm();
    }
}

public class OrderDiagramDemo {
    public static void main(String[] args) {
        Customer customer = new Customer("C-01", "Linh");
        Product book = new Product("JAVA", "Java Book", 125_000);
        Product notebook = new Product("NOTE", "Notebook", 30_000);

        Order order = new Order("O-100", customer);
        order.addLine(book, 2);
        order.addLine(notebook, 1);

        System.out.println(order.totalCents()); // 280000
        CheckoutService checkout =
                new CheckoutService(new ConsolePaymentGateway());
        checkout.checkout(order);
        System.out.println(order.status()); // CONFIRMED
        System.out.println(order.customer().name()); // Linh
    }
}
~~~

Run:

~~~bash
javac OrderDiagramDemo.java
java OrderDiagramDemo
~~~

Expected output:

~~~text
280000
Charge O-100: 280000 cents
CONFIRMED
Linh
~~~

When comparing the diagram above with the Java code, note these points:

- `Order.customer` is a **private field**, but `Customer` may still exist independently and be referenced elsewhere.
- `OrderLine` is a **private nested class**; the diagram draws it as a separate box to clarify its structural role.
- `Order.addLine(...)` does not expose `OrderLine`, so callers cannot attach a part of order A to order B.
- `Product.priceCents` is sampled when creating a line and fixed as `unitPriceCents`. Real commerce requires additional rules for discounts, tax, currency, rounding, and price validity periods.
- `CheckoutService` does not inherit `PaymentGateway`; it collaborates with an instance of the interface.
- `Order.confirm()` changes state to `CONFIRMED` without solving an entire distributed transaction.

**Example scope:** This is a single-threaded flow with simulated console payments. If a real gateway charges money but the app fails before persisting `CONFIRMED`, state may become inconsistent. Production systems need transaction, idempotency, and reconciliation strategies. Class diagrams cannot fully express these temporal failure scenarios.

## 7. From Java to UML: Avoid Incorrect Relationships

Consider this Java code:

~~~java
final class ReportService {
    private final ReportRepository repository;

    ReportService(ReportRepository repository) {
        this.repository = repository;
    }

    Report generate(long id) {
        Report report = repository.findById(id);
        return report;
    }
}
~~~

Model `ReportService → ReportRepository` as a directed relationship because the service **holds a reference field**. However, `Report` appears only as an operation parameter/return type; at the relevant detail level this may be a dependency rather than a persistent association.

~~~mermaid
classDiagram
    class ReportService
    class ReportRepository {
        <<interface>>
    }
    class Report
    ReportService --> ReportRepository : collaborator
    ReportService ..> Report : uses as result
~~~

Useful mapping heuristics:

| Code pattern | Possible UML relationship | Further questions |
|---|---|---|
| `private B b;` | Association from A to B | Can B be null? Is it owned or only referenced? |
| `List<B> members;` | Association with many-valued multiplicity | Are elements shared? Who manages their lifecycle? |
| `new B()` inside A | May suggest composition | Does A exclusively own B? |
| `A extends B` | Generalization | Does A fulfill B's substitutability contract? |
| `A implements I` | Realization | At which layer does I define a contract? |
| B is a local variable or method parameter | Dependency | Is the relationship important enough for this diagram? |
| `@OneToMany` in JPA | Association with multiplicity | Do cascades, orphan removal, and DB ownership match the domain? |

**There is no automatic inference** from “has a field ⇒ composition.” An `Order` may reference a `Customer` without owning the customer's lifecycle. Nor does “no field ⇒ no relationship” hold: methods accepting `Customer` create source-code dependencies.

## 8. Inheritance, Interfaces, and Substitutability in Diagrams

A separate example illustrating class relationship types:

~~~mermaid
classDiagram
    class Animal {
        <<abstract>>
        +move() void
    }
    class Dog {
        +move() void
    }
    class Identifiable {
        <<interface>>
        +id() String
    }
    class Shelter {
        +register(Identifiable animal) void
    }
    Animal <|-- Dog : extends
    Identifiable <|.. Dog : implements
    Shelter ..> Identifiable : parameter
~~~

In Java:

~~~java
abstract class Animal {
    abstract void move();
}

interface Identifiable {
    String id();
}

final class Dog extends Animal implements Identifiable {
    private final String name;

    Dog(String name) {
        this.name = name;
    }

    @Override void move() {
        System.out.println("Running");
    }

    @Override public String id() {
        return name;
    }
}

final class Shelter {
    void register(Identifiable animal) {
        System.out.println(animal.id());
    }
}
~~~

**Read the UML lines accurately:**

- `Dog --|> Animal` is **generalization**: Dog is a subtype of Animal.
- `Dog ..|> Identifiable` is **realization**: Dog implements the interface.
- `Shelter ..> Identifiable` is **dependency**: the shelter accepts a contract-typed parameter; this diagram does not claim it stores every animal.

When drawing inheritance, check the *Liskov Substitution Principle*: `Dog` must meet the expectations of `Animal`. Do not inherit merely to reuse a helper method.

## 9. Class Diagram Quality Checklist

A useful diagram need not contain many classes. During review, check:

1. **Scope and detail level:** Is this domain analysis, design, or implementation? Are levels mixed excessively?
2. **Class names:** Use domain nouns or clear technical roles rather than unrelated collections of responsibilities named `Manager`/`Util`.
3. **Attributes:** Place state and invariants with their owners. Are fields unnecessarily public?
4. **Operations:** Does each behavior belong to the correct object? Are mutations named to convey intent?
5. **Visibility:** Is the public API minimal? Should helpers be private/protected/package-private?
6. **Types:** Are units such as money, identifiers, and time explicit? Is `double` used unsafely for monetary values?
7. **Multiplicity:** Are `1`, `0..1`, `0..*`, and `1..*` labels explained and enforced where needed?
8. **Relationship direction:** Are dependencies/navigability arrows correct? Is the diamond at the whole end?
9. **Ownership:** Is a whole–part relationship association, shared aggregation, or composition? Is there sufficient domain justification for a filled diamond?
10. **Inheritance/realization:** Do hollow triangles point to the superclass/interface? Is there a valid *is-a* relationship and subtype contract?
11. **Dependency cycles:** Are there unnecessary A → B → A paths? Could a policy/port be extracted or coordination moved up a level?
12. **Code consistency:** Are any important methods, fields, types, or access levels different from the diagram without updates?
13. **Notation limitations:** Do transactions, concurrency, state transitions, or operational failures need another diagram or explanatory note?

A diagram that omits internal attributes to emphasize the domain is not necessarily “wrong.” But **incorrect relationship types or multiplicities inconsistent with domain requirements** can mislead implementation and architecture decisions.

## 10. Common Class Diagram Mistakes

| Mistake | Why it is wrong | Correction |
|---|---|---|
| Diamond placed at the part end | Reverses whole–part meaning | Place diamond at the whole end |
| Drawing composition merely because of `List<T>` | Collections do not imply ownership | Check lifecycle and exclusivity |
| Drawing inheritance to reuse one method | Misrepresents the *is-a* type relationship | Use collaboration/delegation where appropriate |
| Omitting multiplicity | Cannot tell whether 0, 1, or many instances relate | Label and explain both association ends |
| Drawing transient dependency as long-lived association | Suggests an object stores state it does not own | Use dashed dependency when only briefly used |
| Defaulting to getters/setters for every field | Exposes state and breaks encapsulation | Use domain behaviors and necessary queries |
| Marking all fields and methods public | Callers can violate invariants easily | Use minimum appropriate visibility |
| Putting every DB table on the domain diagram | Loses class responsibility and meaning | Separate domain models from ERDs/persistence mappings |
| Assuming UML enforces rules in code | Diagrams are descriptive | Implement validation, tests, and needed DB constraints |
| Not updating diagrams after code changes | Documentation drifts from reality | Maintain diagram and code through reviews/version control |

## 11. Test What the Diagram Promises

Diagrams cannot execute themselves. Select **relationship invariants** and verify them through Java behavior.

For `OrderDiagramDemo.java` above, create `OrderDiagramTest.java` with JUnit Jupiter 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class OrderDiagramTest {
    @Test
    void oneOrderOwnsItsLinesAndKeepsCustomerReference() {
        Customer customer = new Customer("C-01", "Linh");
        Product product = new Product("JAVA", "Java Book", 125_000);
        Order first = new Order("O-1", customer);
        Order second = new Order("O-2", customer);

        first.addLine(product, 2);
        second.addLine(product, 1);

        assertSame(customer, first.customer());
        assertSame(customer, second.customer());
        assertEquals(1, first.lineCount());
        assertEquals(1, second.lineCount());
        assertEquals(250_000L, first.totalCents());
        assertEquals(125_000L, second.totalCents());
    }

    @Test
    void checkoutChangesStatusOnlyAfterSuccessfulCharge() {
        Order order = new Order(
                "O-3", new Customer("C-02", "Minh"));
        order.addLine(new Product("N", "Notebook", 30_000), 1);

        final long[] amountCharged = {0L};
        PaymentGateway gateway = (id, amount) -> amountCharged[0] = amount;

        new CheckoutService(gateway).checkout(order);

        assertEquals(30_000L, amountCharged[0]);
        assertEquals(Order.Status.CONFIRMED, order.status());
        assertThrows(IllegalStateException.class,
                () -> order.addLine(
                        new Product("P", "Pen", 1000), 1));
    }

    @Test
    void chargeFailureDoesNotConfirmOrder() {
        Order order = new Order(
                "O-4", new Customer("C-03", "An"));
        order.addLine(new Product("JAVA", "Java Book", 125_000), 1);

        PaymentGateway failingGateway = (id, amount) -> {
            throw new IllegalStateException("Gateway unavailable");
        };

        assertThrows(IllegalStateException.class,
                () -> new CheckoutService(failingGateway).checkout(order));
        assertEquals(Order.Status.DRAFT, order.status());
    }

    @Test
    void emptyOrderCannotBeConfirmed() {
        Order order = new Order(
                "O-5", new Customer("C-04", "Hoa"));
        assertThrows(IllegalStateException.class, order::confirm);
    }
}
~~~

The test checks meaningful model commitments: orders share references to independent customers/products, own **separate lines**, calculate totals correctly, do not transition on payment errors, and reject confirmation of empty orders.

**Limitation:** One test cannot prove that lines are “never shared” across every possible code revision, but this API uses a private nested `OrderLine` and exposes no operation for reattaching a part. Nor does the test prove that real payment transactions roll back completely after a network failure mid-processing; integration tests and reconciliation are still needed.

## 12. A Workflow for Drawing Class Diagrams from Requirements

~~~mermaid
flowchart TD
    A[Đọc tình huống sử dụng và quy tắc] --> B[Chọn khái niệm có identity/state]
    B --> C[Phân trách nhiệm và invariant]
    C --> D[Đặt thuộc tính và operation]
    D --> E[Chọn association / ownership / kiểu cha]
    E --> F[Ghi multiplicity và visibility]
    F --> G[Đối chiếu use case, Java và test]
    G --> H{Thể hiện đủ, không mâu thuẫn?}
    H -->|Chưa| C
    H -->|Rồi| I[Chốt sơ đồ cho mức thiết kế đã chọn]
~~~

**Practical approach:**

1. **Gather use cases:** for example, “Customer adds products to a draft order and pays.” Include the happy path and exceptions such as empty orders, invalid quantities, and failed payment.
2. **Select objects with responsibilities:** `Order` protects state and its line collection; `PaymentGateway` is an integration port.
3. **Identify owned data:** compare lines belonging to individual orders with shared product references.
4. **Identify necessary APIs:** `addLine`, `totalCents`, `confirm`, `checkout`, `charge`; avoid public setters on `status` and `lines`.
5. **Choose relationships:** composition for Order–Line, association for Order–Customer/Product, realization for a gateway implementation, dependency when a use case uses Order.
6. **Label multiplicities:** consider draft and confirmed states; specify an additional constraint if multiplicity depends on state.
7. **Verify with Java and tests:** where are objects created? Who may mutate them? Do tests protect invariants? Has code changed the diagram?

**You need not draw everything:** if too many classes or arrows clutter a diagram, split it by bounded context, use case, or design level and note omitted relationships.

## 13. Applied Exercise: Library Loans

**Sample requirement:** The library manages `BookTitle` records and physical `BookCopy` instances. A `Member` may borrow multiple copies through `Loan` records, but each physical copy may have at most one **active** loan at a time. Each loan records borrowing date, due date, and status.

Complete the following:

1. Identify minimal classes/relationships: `BookTitle`, `BookCopy`, `Member`, `Loan`. Decide identities: ISBN identifies a title, copy ID identifies a physical copy, loan ID identifies a borrowing event.
2. Draw a class diagram with attributes, operations, and visibility. Label parameter names/types in `borrowCopy(member, copy)`, `returnCopy()`, and `isAvailable()`.
3. Add multiplicities to `BookTitle–BookCopy`, `Member–Loan`, and `Loan–BookCopy` relationships. Distinguish “many **historical** loans for one copy” from “at most one **active** loan.”
4. Choose association, aggregation, or composition only after confirming lifecycles. Does removing a catalog title require destroying physical copies? Must member loan history remain for retention rules after deletion?
5. Implement a Java model preserving “one copy cannot have two simultaneous active loans,” with suitable commands and queries.
6. Test a successful loan, a duplicate active loan, returns, and competing requests; specify the DB transaction mechanism for multi-node execution.

**Self-assessment:** Can a new teammate use the diagram to determine **who owns which data**, **which operations protect invariants**, **how many other instances one object can reference**, and **which direction dependencies point**?

---

**Remember:** Class diagrams communicate meaningful **members and relationships**: class names and responsibilities; attributes, operations, and visibility; association, aggregation, composition, generalization, realization, dependency; plus multiplicity and navigability. Treat a diagram as a **design contract that Java and tests must enforce**, not as a picture that automatically guarantees every rule.
