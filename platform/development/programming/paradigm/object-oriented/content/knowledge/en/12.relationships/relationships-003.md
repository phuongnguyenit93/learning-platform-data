# Aggregation and composition in Java OOP

**Topic:** Two ways of representing **whole–part relationships** between objects: **aggregation** and **composition**. This lesson focuses on choosing the appropriate relationship, identifying **ownership**, designing object lifecycles, and representing relationships in Java/UML.

> **Terminology:** "Aggregation" here means **aggregation in object modeling/UML**, not the `Collection`, `List`, or `Set` types of the Java Collections Framework. A field of type `List<T>` alone does not tell you whether the relationship is aggregation or composition.

## 1. Foundations: a "has/contains" relationship is not enough

Suppose a `Team` has multiple `Employee` objects, and an `Order` has multiple `OrderLine` objects. Both can be represented using reference fields or Java lists:

~~~java
class Team {
    private java.util.List<Employee> employees;
}

class Order {
    private java.util.List<OrderLine> lines;
}
~~~

The syntax above **does not prove** that either relationship is composition. To choose a model, ask:

1. **Does the part have an identity and meaning outside the whole?** An employee remains an employee after leaving a team; an order line usually has meaning only within its particular order.
2. **Who owns and controls the creation, attachment, removal, and destruction of the part?** An order typically manages its own lines, while a team merely groups participating employees.
3. **Can one part belong to several wholes simultaneously?** An employee may join two teams if the business allows it; a particular order line should not belong to two orders at the same time.
4. **What happens when the whole is deleted according to business rules?** Dissolving a team does not mean deleting its employees from the system; deleting a draft order may delete its lines.

These are business rules, not automatic properties of `List`, `new`, `final`, or garbage collection.

## 2. Three commonly confused relationships

| UML relationship | Basic meaning | Example | Notation at the whole end |
|---|---|---|---|
| **Association** | Objects know or interact with one another; not necessarily a whole–part relationship | A `Doctor` examines a `Patient` | Ordinary connecting line |
| **Aggregation** (shared aggregation) | An object groups/contains other objects; the parts can exist independently | A `Team` consists of `Employee` objects | **Hollow** diamond |
| **Composition** | Whole–part relationship with **strong ownership**; each part belongs to at most one whole at a time | An `Order` owns its `OrderLine` objects | **Filled** diamond |

**An important distinction:** UML defines *shared aggregation* (the hollow diamond) loosely, without assigning any specific lifecycle rule. Thus, in a rigorous design document, if all you mean is "the team references employees," an ordinary **association** may be clearer than a hollow diamond. **Composition** has stronger semantics: a part is owned by one composite at a time; when the whole is destroyed in the model, its parts are also destroyed according to the ownership contract.

~~~mermaid
classDiagram
    class Team
    class Employee
    class PurchaseOrder
    class OrderLine
    Team "1" o-- "0..*" Employee : tập hợp / tham gia
    PurchaseOrder "1" *-- "0..*" OrderLine : sở hữu
~~~

In a class diagram, **the diamond always appears at the whole end**: the `Team` or `PurchaseOrder` side, not the part side. The `0..*` multiplicity is specific to this example: a team may have no members yet, and a draft order may have no lines. If a confirmed order must have at least one line, model and enforce that constraint in the appropriate state.

## 3. Aggregation: a team grouping independent employees

Suppose employees may join multiple work teams. `Team` holds references to `Employee` objects, but each `Employee` is created and managed independently. Removing an employee from a team leaves the employee object available for other teams.

**File `AggregationDemo.java` — Java 17+:**

~~~java
import java.util.LinkedHashSet;
import java.util.Objects;
import java.util.Set;

record Employee(String id, String name) {
    Employee {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(name, "name");
        if (id.isBlank() || name.isBlank()) {
            throw new IllegalArgumentException("Employee id/name must not be blank");
        }
    }
}

final class Team {
    private final String name;
    private final Set<Employee> members = new LinkedHashSet<>();

    Team(String name) {
        this.name = Objects.requireNonNull(name, "name");
    }

    void addMember(Employee employee) {
        members.add(Objects.requireNonNull(employee, "employee"));
    }

    boolean removeMember(Employee employee) {
        return members.remove(employee);
    }

    Set<Employee> members() {
        return Set.copyOf(members); // Trả về bản xem không sửa được.
    }

    String name() {
        return name;
    }
}

public class AggregationDemo {
    public static void main(String[] args) {
        Employee lan = new Employee("E01", "Lan"); // Tồn tại độc lập
        Team backend = new Team("Backend");
        Team mentoring = new Team("Mentoring");

        backend.addMember(lan);
        mentoring.addMember(lan); // Cùng một Employee ở hai Team

        backend.removeMember(lan);

        System.out.println(backend.members().contains(lan));  // false
        System.out.println(mentoring.members().contains(lan)); // true
        System.out.println(lan.name());                        // Lan
    }
}
~~~

Compile and run: `javac AggregationDemo.java`, then `java AggregationDemo`.

**Important design points:**

- `Employee` is created **before and independently of** `Team`. Leaving a team does not eliminate the employee entity.
- Under the assumed business rules, one employee may belong to multiple teams. If the system allows only one team per employee, add a domain constraint; UML aggregation neither imposes nor checks that rule automatically.
- `Set.copyOf(members)` produces an unmodifiable set, preventing callers from corrupting internal state through `team.members().clear()`. Here, `Employee` is an immutable `record`; if elements were mutable, returning `Set.copyOf` alone would **not** make them immutable.
- `Set` detects duplicates through `equals()/hashCode()`. For `record Employee`, both `id` and `name` take part in equality; a real system might enforce uniqueness by employee ID instead.

**Do not misinterpret lifecycles:** Deleting a `Team` variable or calling `removeMember` does not trigger a "delete Employee object" operation in the JVM. Java has no manual `delete object` operation like C++; an object becomes eligible for GC only when no strong-reference path keeps it reachable, and garbage-collection timing is not guaranteed.

## 4. Composition: an order owning its line items

An `OrderLine` describes the quantity and unit price of an item **within one particular order**. In this model, a line item is created through `Order`, is not shared between orders, and is not managed as an independent entity.

The example uses **private child objects** and behavior-oriented methods rather than exposing a `List<OrderLine>`. This expresses ownership better than merely declaring `private final List<...>`.

**File `CompositionDemo.java` — Java 17+:**

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class Order {
    private final String orderId;
    private final List<LineItem> lines = new ArrayList<>();
    private boolean submitted;

    // Chỉ Order có thể tạo và truy cập kiểu nội bộ này.
    private static final class LineItem {
        private final String sku;
        private final int quantity;
        private final BigDecimal unitPrice;

        private LineItem(String sku, int quantity, BigDecimal unitPrice) {
            this.sku = sku;
            this.quantity = quantity;
            this.unitPrice = unitPrice;
        }

        private BigDecimal subtotal() {
            return unitPrice.multiply(BigDecimal.valueOf(quantity));
        }
    }

    Order(String orderId) {
        this.orderId = Objects.requireNonNull(orderId, "orderId");
        if (orderId.isBlank()) {
            throw new IllegalArgumentException("Order id must not be blank");
        }
    }

    void addLine(String sku, int quantity, BigDecimal unitPrice) {
        if (submitted) {
            throw new IllegalStateException("Submitted order is locked");
        }
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(unitPrice, "unitPrice");
        if (sku.isBlank() || quantity <= 0 || unitPrice.signum() < 0) {
            throw new IllegalArgumentException("Invalid order line");
        }

        // LineItem được tạo và giữ hoàn toàn bên trong Order.
        lines.add(new LineItem(sku, quantity, unitPrice));
    }

    BigDecimal total() {
        return lines.stream()
                .map(LineItem::subtotal)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
    }

    int lineCount() {
        return lines.size();
    }

    void submit() {
        if (submitted) {
            throw new IllegalStateException("Already submitted");
        }
        if (lines.isEmpty()) {
            throw new IllegalStateException("Cannot submit an empty order");
        }
        submitted = true;
    }

    String id() {
        return orderId;
    }
}

public class CompositionDemo {
    public static void main(String[] args) {
        Order first = new Order("ORD-100");
        Order second = new Order("ORD-101");

        first.addLine("JAVA-BOOK", 2, new BigDecimal("125000"));
        second.addLine("JAVA-BOOK", 1, new BigDecimal("125000"));

        first.submit();
        System.out.println(first.total());     // 250000
        System.out.println(second.total());    // 125000
        System.out.println(first.lineCount()); // 1
        System.out.println(second.lineCount());// 1
    }
}
~~~

Compile and run: `javac CompositionDemo.java`, then `java CompositionDemo`.

Two orders may reference the same **product code** `"JAVA-BOOK"`, but each owns a distinct `LineItem` object. This distinguishes **sharing product information** from **sharing the actual part that makes up an order**. A catalog product has its own lifecycle; `LineItem` represents price and quantity in one order.

In the example, `LineItem` is a `private` nested class created by `Order.addLine()` and never exposed through the API. `BigDecimal` is immutable, and the internal list is not exposed. This supports the business invariant that a line cannot be taken from order A and directly attached to order B. `final` on the list reference only prevents reassigning `lines`; **encapsulation and API control** are what protect the list's contents.

**Distinguish the different lifecycle layers:**

- **Domain/UML layer:** if an order is destroyed in the model, its lines are destroyed with it according to business ownership rules; they cannot remain as lines of another order.
- **Java runtime layer:** the JVM does not recursively delete objects at the exact moment you "destroy an order." GC is based on reference reachability; composition must be expressed through APIs and domain rules. If references to parts have escaped, those parts may still exist in memory.
- **Database layer:** deleting an `orders` row does not automatically delete `order_lines` rows; appropriate mechanisms are needed, such as a transaction, a foreign key with `ON DELETE CASCADE`, or correctly configured ORM cascade/orphan removal.

## 5. Recognizing relationships from business requirements

| Question | Suggests aggregation / association | Suggests composition |
|---|---|---|
| Does the part have independent meaning? | Yes: employee, doctor, account | No, or closely tied to the whole: order line |
| Can it simultaneously belong to several wholes? | Possibly, depending on the model | **No**, under UML composition semantics |
| Who manages the part's creation and deletion? | An independent entity/service | Usually the whole |
| Does deleting the whole delete the part in the model? | Usually not | Yes, according to the ownership contract |
| Can two wholes share a reference to the same part? | Potentially valid | Violates exclusivity if both wholes own it |
| Common Java implementation | References/collections pointing to external objects | Create children through owner methods, hide modification APIs, or enforce owner constraints |

**Be cautious with classic examples:** You cannot decide whether `Car` – `Engine` or `House` – `Room` is composition from the words alone. If an engine can be removed and fitted into another car, or rooms are modeled independently in a property-management system, the business requirements differ. In composition, a part may move from composite A to B, but **its old ownership must end before the new ownership begins**; it cannot belong to both at once.

## 6. UML: notation, direction, multiplicity, and navigability

~~~mermaid
classDiagram
    direction LR
    class Organization {
        +name: String
    }
    class Department {
        +name: String
    }
    class Employee {
        +id: String
    }
    class PurchaseOrder {
        +id: String
        +addLine(...)
        +submit()
    }
    class OrderLine {
        +sku: String
        +quantity: int
    }

    Organization "1" o-- "0..*" Department : nhóm các phòng ban
    Department "0..*" -- "0..*" Employee : phân công
    PurchaseOrder "1" *-- "0..*" OrderLine : các dòng riêng
~~~

- A **hollow diamond (`o--`)** denotes shared aggregation; a **filled diamond (`*--`)** denotes composition. The symbol appears at the **whole** end.
- **Multiplicity** indicates the valid number of related objects at each end. For example, `PurchaseOrder "1" *-- "0..*" OrderLine` means each `OrderLine` belongs to exactly one `PurchaseOrder`, while a draft order may have multiple lines. If deleting/moving lines is supported, valid transition states must be defined.
- **Navigability** indicates which object can navigate to the other; it is not the same as ownership. A composition may or may not allow a part to navigate back to its owner through an `order` reference.
- **Aggregation does not automatically define sharing or longevity:** do not assume that every shared aggregation *must* permit joint ownership. Business requirements determine such constraints. If explicit whole–part semantics are unnecessary, an association is often enough.
- Composition **does not always require child objects to exist at initialization**. A draft with no lines is valid if the "submitted" state requires `lineCount >= 1` and that constraint is checked by `submit()`.

## 7. Practical implementation rules in Java

**To model aggregation as intended:**

1. Pass externally created elements to the group's constructor or `addMember()`.
2. When removing an element from a group, change only **its membership relationship**; do not accidentally delete the original element.
3. Return a collection that does not let callers modify internal state; consider snapshots or immutable collections as appropriate.
4. Specify whether elements can be shared among groups or belong to only one; this is a domain rule, not a feature of the diamond symbol.

**To model composition clearly:**

1. Identify the **owner** and whether each part can exist independently.
2. Let the owner create/add/modify/delete parts through business-oriented methods; prevent a part from being attached to multiple owners simultaneously.
3. Do not expose a directly mutable collection or a part whose owner can be reassigned arbitrarily. If parts must be returned, use immutable values, DTOs/snapshots, or owner validation.
4. Check invariants at aggregate boundaries: positive quantities, nonnegative prices, no editing locked orders, and at least one line in submitted orders.
5. Define persistence policy explicitly: which parts are removed when the owner is deleted, and within which transaction. This **does not happen automatically** because of a Java relationship.

Another common form of composition initializes a part once in the constructor:

~~~java
final class Computer {
    private final Motherboard motherboard;

    Computer() {
        this.motherboard = new Motherboard();
    }
}
~~~

This suggests ownership but **does not prove** composition if `Computer` exposes the part reference, allows outside code to change its owner, or permits sharing. The semantics come from domain rules and API design, not from where `new` appears.

## 8. Working with Spring/JPA

Java object graphs, UML, and relationship persistence are three different layers. An `@OneToMany` association **is not enough** to guarantee composition. A deliberate design in which `PurchaseOrderEntity` manages `OrderLineEntity` objects might use:

~~~java
// Minh họa trường ánh xạ trong PurchaseOrderEntity (không phải lớp đầy đủ)
@OneToMany(mappedBy = "order",
           cascade = CascadeType.ALL,
           orphanRemoval = true)
private List<OrderLineEntity> lines = new ArrayList<>();
~~~

Add suitable `@ManyToOne` and `@JoinColumn` fields on the `OrderLineEntity` side, synchronize **both sides** of the association through `addLine/removeLine` methods, and place transactions appropriately. With orphan removal enabled, removing a line from a managed association may delete that line when changes are flushed; ensure that this is the intended business behavior. `CascadeType.ALL` includes REMOVE and is therefore dangerous when the part is a shared entity, such as an `Employee` referenced by multiple teams.

For `Team` – `Employee` aggregation, you generally should not configure cascade REMOVE from Team to Employee. Deleting a team should remove only its memberships (for example, rows in a join table) if employees remain independent. Whether to use `@ManyToMany`, a `Membership` entity, or a join table with its own constraints depends on whether you need to store joining dates, roles, or change history.

## 9. Test behavior rather than code structure

Useful cases for `AggregationDemo` include:

- An `Employee` joining two `Team` objects when allowed by policy.
- Removing the employee from team A without deleting the employee record or affecting membership in team B.
- Ensuring callers cannot modify internal `members` through the returned collection.
- Rejecting blank/null values according to the contract.

For `CompositionDemo`:

- Two `Order` objects adding the same `sku` while keeping **separate line items** and calculating totals independently.
- Rejecting a line with zero quantity or a negative unit price.
- Ensuring `submit()` rejects empty orders and locks modifications after successful submission.
- Preventing external APIs from taking a `LineItem` from order A and attaching it directly to order B.
- Using integration tests to confirm that an order's lines are transactionally deleted when the order is deleted from the database, if required by policy.

Reflection tests are not needed merely to confirm that a `List<LineItem>` field exists or a constructor calls `new LineItem()`; what matters is protecting **ownership rules and observable behavior**.

## 10. Common misconceptions

| Misconception | Why it is wrong | Correction |
|---|---|---|
| "A `List` always means aggregation" | A collection is just a reference-storage structure | Base the choice on domain meaning and lifecycle |
| "A `new` in a constructor always means composition" | Child objects may still be shared or assigned another owner | Enforce ownership through APIs/invariants |
| "Composition means Java immediately deletes children when a parent is deleted" | GC is not a domain cascade mechanism | Separate domain rules, references, and persistence |
| "Aggregation always permits sharing across multiple wholes" | UML shared aggregation does not impose fixed sharing rules | State specific business constraints |
| "The hollow diamond has as strict a definition as the filled diamond" | UML leaves many shared-aggregation details to the modeler | Use association if ownership semantics are unnecessary |
| "A `final List` cannot be modified" | `final` only fixes the reference | Encapsulate the list; return a snapshot/read-only view |
| "`CascadeType.ALL` works for any has-a relationship" | REMOVE may delete shared data | Choose cascades based on actual ownership |

## 11. Application exercises

**Scenario:** A learning platform has `Course`, `Student`, `Enrollment`, `Quiz`, and `Question`.

Decide which relationships are association, aggregation, or composition based on these requirements:

1. A `Student` enrolls in many `Course` objects; deleting a course must not delete its students.
2. `Enrollment` stores the student, course, enrollment date, and status; it exists only for a valid enrollment, but its history must be retained even after the course closes.
3. Each `Quiz` has its own `Question` objects; discarding a draft quiz discards its draft questions. The original question bank (if any) remains independent and may be used to create copies for another quiz.

**Design guidance:** `Course` – `Student` is related through `Enrollment` rather than direct composition; `Enrollment` has its own lifecycle governed by history-retention rules; `Quiz` and its individually owned `Question` copies may form a composition, while `QuestionBankEntry` is an independent entity that is referenced or copied. The diagram is correct only when its stated constraints are enforced.

**Self-check:** Can you identify who may create/delete a part, which data must be retained when the whole is deleted, and how many wholes a part may belong to at one time?

---

**Remember:** *Aggregation* describes a loose whole–part relationship whose parts can exist independently; *composition* represents **strong, exclusive ownership at any given time**. The distinction lies in the **domain contract** and how it is enforced, not in whether Java uses fields, collections, or `new`.
