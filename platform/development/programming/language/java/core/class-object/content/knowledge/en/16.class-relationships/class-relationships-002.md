# Usage, Association, and Object Ownership Relationships in Java

In object-oriented programming (OOP), classes do not exist in isolation: an object may **use** another object to perform an operation, **hold a reference** to another object over a long period, or **be responsible for creating, managing, and ending the lifecycle** of component objects.

The three core design questions are:

1. **Usage (dependency):** Does class A only need B's service at a given moment or within a single operation?
2. **Association:** Does object A have a stable relationship with object B and need to store/navigate to B?
3. **Ownership (ownership/composition):** Is object A responsible for controlling the lifecycle, integrity, and modification rights of object B?

In UML, these concepts are commonly presented under the names **dependency**, **association**, **aggregation**, and **composition**. In Java, they are typically expressed through **parameters, local variables, reference fields, constructor injection, collections**, along with **lifecycle contracts**. Java **has no dedicated `composition` or `aggregation` keyword**: ownership semantics are primarily established by the design/API.

## 1. Overview Map

| Relationship | Common Meaning | Typical Java Representation | Design Question |
| --- | --- | --- | --- |
| **Dependency (uses)** | A needs B to perform work | B is a method parameter; local variable; calling B's service | Does A **use** B? |
| **Association** | A has a connection with B | Field `B`, `Optional<B>`, `List<B>`, or querying B | Does A **know/maintain a connection** with B? |
| **Aggregation** | **Shared** whole–part, where the part can exist independently | A holds B objects created/owned externally | Can B belong to multiple wholes or live independently? |
| **Composition** | **Strongly owned** whole–part, where the part's lifecycle depends on the whole in the model | A creates/manages B itself; the API restricts sharing and exposing mutable references | Who **determines the lifecycle** of B? |

Examples in a training application:

- `ReportService.generate(report, formatter)` **uses** a `Formatter` provided by the caller.
- `Course` holds an `Instructor instructor` field to know who teaches it: **association**.
- `Department` groups `Employee` objects that can transfer departments or exist independently: **shared aggregation** if the business model treats it as a shared whole–part.
- `Order` creates and controls `OrderLine` instances that have no independent business identity/lifecycle: **composition**.

The table should not be read as an automatic formula that "having a field means composition." A field only proves that the object **holds a reference**; it is not enough to conclude who owns it.

### Interaction, Structure, and Lifecycle

A useful classification:

```text
             SHORT-TERM INTERACTION
        A ------ uses ------> B
                  dependency

             STRUCTURAL CONNECTION
        A ------- knows ----- B
                  association

             WHOLE–PART RELATIONSHIP
        Whole ----- shares ---> Part
                 aggregation

        Whole ----- owns -----> Part
                 composition
```

In practice, a relationship can exhibit multiple aspects simultaneously: A **depends** on interface B at compile time and **holds an association** to an instance of B at runtime. When drawing UML, choose the appropriate perspective and level of abstraction, and avoid treating these terms as four strictly separate "Java field types."

## 2. Unit of Analysis: Class or Object?

A **class** defines a type and behavior; an **object** is a concrete instance created at runtime.

```java
class Author {
    private final String name;

    Author(String name) {
        this.name = name;
    }
}

class Book {
    private final Author author;

    Book(Author author) {
        this.author = author;
    }
}
```

At the **class diagram** level, we say `Book` has an association with `Author`.

At the **object diagram** level, we have:

```text
book1:Book -----> authorA:Author
book2:Book -----> authorA:Author
```

The two `Book` objects are referencing **the same `Author` object**. They do not create two Authors just because there are two fields named `author`.

This is especially important when discussing ownership: **having a reference does not mean having exclusive ownership**. If the same `Author` is shared by two `Book` objects, the model should not assume by default that deleting one Book will delete the Author.

## 3. Dependency: The Usage Relationship

**Dependency** describes one model element **needing** another element to carry out one of its behaviors or declarations. At the code level, the most common form is a **method receiving the needed object as a parameter without retaining it**.

Example:

```java
interface Formatter {
    String format(String text);
}

class GreetingService {
    String greet(String name, Formatter formatter) {
        return formatter.format("Xin chào " + name);
    }
}
```

`GreetingService` uses `Formatter` inside the `greet` method. It **does not necessarily hold a `Formatter` field**. The caller is free to provide different formatters across calls.

Identifying characteristics:

- B is a parameter, local variable, or object invoked during an operation.
- A needs an API of B to complete its work.
- Once the call finishes, A may not retain any reference to B.
- Changes to B's interface may affect the compilation/operation of A.

**Not every `import` represents a runtime object relationship.** An import is a mechanism for using names in source code; it can contribute to a source-level dependency, but it does not prove that two instances have a lasting connection.

### Runnable Java 17 Example: Dependency via Parameter

Save **`DependencyDemo.java`**:

```java
interface Formatter {
    String format(String text);
}

final class UppercaseFormatter implements Formatter {
    @Override
    public String format(String text) {
        return text.toUpperCase(java.util.Locale.ROOT);
    }
}

final class BracketFormatter implements Formatter {
    @Override
    public String format(String text) {
        return "[" + text + "]";
    }
}

final class GreetingService {
    String greet(String name, Formatter formatter) {
        return formatter.format("Xin chào " + name);
    }
}

public class DependencyDemo {
    public static void main(String[] args) {
        GreetingService service = new GreetingService();

        System.out.println(
                service.greet("An", new UppercaseFormatter()));
        System.out.println(
                service.greet("Bình", new BracketFormatter()));
    }
}
```

Run with JDK 17+:

```bash
javac -encoding UTF-8 DependencyDemo.java
java DependencyDemo
```

**Stdout:**

```text
XIN CHÀO AN
[Xin chào Bình]
```

`GreetingService` is **reused** with two different `Formatter` instances. This is an example of **method injection**: the dependency is supplied at the call site and is not retained as part of the service's state.

### When to Use a Short-Term Dependency?

- A processing function receives a strategy/callback used only within a single task.
- A utility method processes an object passed into it.
- A validator/formatter chosen per call.
- A service operates on a repository/session owned by the orchestration layer within a short scope.

If A needs to use B throughout **A's entire lifecycle**, a field association/constructor injection is usually more appropriate.

## 4. Association: Links Between Objects

**Association** is a structural relationship: one object can **know** and navigate to another object in the model.

Example:

```java
class Course {
    private Instructor instructor;

    Course(Instructor instructor) {
        this.instructor = instructor;
    }
}
```

The `instructor` field shows that each `Course` holds a reference to an `Instructor` in its current state. This is a **unidirectional association** from `Course` to `Instructor` if the instructor does not hold a back-reference.

An association does not assert that:

- Course creates Instructor.
- Course exclusively owns Instructor.
- Instructor is destroyed when Course is no longer used.
- An Instructor can participate in only one Course.

To assert those guarantees, separate **business contracts and APIs** are needed.

### Unidirectional and Bidirectional Navigation

Unidirectional:

```text
Course --------> Instructor
```

Bidirectional:

```text
Course <-------> Instructor
```

In Java, a bidirectional association typically requires **both sides to store references** or an equivalent query mechanism, while keeping the relationship's invariant synchronized.

A common bidirectional example: `Department` knows `Employee` and `Employee` knows `Department`. When transferring an employee to another department, the system must ensure **both sides** are updated consistently.

**Do not create two independent setters** that allow clients to change one side while forgetting the other.

## 5. Unidirectional Association Example: Course – Instructor

Save **`AssociationDemo.java`**:

```java
import java.util.Objects;

final class Instructor {
    private final String name;

    Instructor(String name) {
        this.name = Objects.requireNonNull(name, "name");
    }

    String name() {
        return name;
    }
}

final class Course {
    private final String title;
    private Instructor instructor;

    Course(String title, Instructor instructor) {
        this.title = Objects.requireNonNull(title, "title");
        this.instructor = Objects.requireNonNull(instructor, "instructor");
    }

    void changeInstructor(Instructor next) {
        instructor = Objects.requireNonNull(next, "next");
    }

    String description() {
        return title + " - " + instructor.name();
    }
}

public class AssociationDemo {
    public static void main(String[] args) {
        Instructor an = new Instructor("An");
        Instructor binh = new Instructor("Bình");

        Course java = new Course("Java", an);
        Course sql = new Course("SQL", an);

        System.out.println(java.description());
        System.out.println(sql.description());

        java.changeInstructor(binh);
        System.out.println(java.description());
        System.out.println(sql.description());
    }
}
```

Run:

```bash
javac -encoding UTF-8 AssociationDemo.java
java AssociationDemo
```

**Stdout:**

```text
Java - An
SQL - An
Java - Bình
SQL - An
```

Characteristics:

1. Both `java` and `sql` are initially **associated with the same Instructor An**.
2. `java.changeInstructor(binh)` changes the association of **one Course**, without affecting the other Course.
3. Instructor exists as an independent object, created by the caller and passed into Course.
4. `Course` has no logic to create or close `Instructor`. Therefore, **this should not be called composition** merely because it has a field.

`Objects.requireNonNull` guarantees that Course in the example always has a non-null Instructor. If a course may not yet be assigned an instructor, the model needs to replace that constraint with cardinality `0..1` and an appropriate API.

## 6. Cardinality / Multiplicity: Number of Participating Objects

In UML, an association can specify **multiplicity** at the association ends:

| Multiplicity | How to Read | Java Model Options |
| --- | --- | --- |
| `1` | Exactly one | Required non-null field |
| `0..1` | Zero or one | Nullable field or `Optional` in the read API |
| `0..*` or `*` | Zero or many | `List<T>`/`Set<T>` that can be empty |
| `1..*` | One or many | Collection + non-empty validation |
| `2..5` | Two to five | Collection + count validation |
| `n` | Exactly n | Collection/array + size invariant |

**Java types do not automatically enforce UML multiplicity.** Declaring `List<Student> students` does not mean "at least one Student"; the list can still be empty. Similarly, declaring `Instructor instructor` does not automatically forbid null.

Invariant example:

```java
Course(String title, Instructor instructor) {
    this.title = Objects.requireNonNull(title);
    this.instructor = Objects.requireNonNull(instructor);
}
```

The claim "Course always has exactly one Instructor" becomes more trustworthy if every creation/update path checks for non-null and the class controls state exposure.

### Navigability Is Not the Same as Cardinality

- **Navigability:** from which object can you reach which object through the model?
- **Multiplicity:** how many objects at the other end can an object at this end be linked to?

An association `Course -> Instructor` can have multiplicity `1` at the Instructor end, while an Instructor can teach `0..*` Courses. These are two different pieces of information.

## 7. Bidirectional Association: Keeping Both Sides Synchronized

If `Department` holds a collection of employees and each `Employee` holds its department, updates must ensure:

```text
employee.department == department
  equivalent to
department.members contains employee
```

Avoid faulty APIs:

```java
employee.setDepartment(newDepartment);
// But newDepartment.members is not updated.
```

There are two design approaches:

1. **One side is the source of truth**, and the other side queries instead of storing a redundant reference.
2. **Keep both sides, but have only a single link/transfer operation manage the entire change**.

The complete example below uses `Employee.transferTo` to coordinate the update. It illustrates how to design the association; it does not yet address transaction/thread-safety constraints for multithreaded systems.

### Program: Managed Bidirectional Association

Save **`BidirectionalAssociationDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class Department {
    private final String name;
    private final List<Employee> employees = new ArrayList<>();

    Department(String name) {
        this.name = Objects.requireNonNull(name);
    }

    String name() {
        return name;
    }

    void addInternal(Employee employee) {
        if (!employees.contains(employee)) {
            employees.add(employee);
        }
    }

    void removeInternal(Employee employee) {
        employees.remove(employee);
    }

    int size() {
        return employees.size();
    }
}

final class Employee {
    private final String name;
    private Department department;

    Employee(String name) {
        this.name = Objects.requireNonNull(name);
    }

    void transferTo(Department next) {
        if (department == next) {
            return;
        }

        if (department != null) {
            department.removeInternal(this);
        }

        department = next;

        if (next != null) {
            next.addInternal(this);
        }
    }

    String location() {
        return name + "@" + (department == null
                ? "NONE" : department.name());
    }
}

public class BidirectionalAssociationDemo {
    public static void main(String[] args) {
        Department dev = new Department("DEV");
        Department qa = new Department("QA");
        Employee an = new Employee("An");

        an.transferTo(dev);
        System.out.println(an.location());
        System.out.println("DEV: " + dev.size());

        an.transferTo(qa);
        System.out.println(an.location());
        System.out.println("DEV: " + dev.size());
        System.out.println("QA: " + qa.size());

        an.transferTo(null);
        System.out.println(an.location());
        System.out.println("QA: " + qa.size());
    }
}
```

Command:

```bash
javac -encoding UTF-8 BidirectionalAssociationDemo.java
java BidirectionalAssociationDemo
```

**Stdout:**

```text
An@DEV
DEV: 1
An@QA
DEV: 0
QA: 1
An@NONE
QA: 0
```

**Explanation:** `Employee.transferTo` coordinates detaching the old relationship, updating the `department` field, and then adding the employee to the new Department. If there were only an independent `Department.employees.add(an)` without updating `an.department`, the association could go out of sync.

### Limitations to Note Explicitly

The example leaves `addInternal`/`removeInternal` at package-private visibility for brevity. In a large library, other code in the same package can still call those methods and break the invariant. You can use a dedicated association manager class, restrict module/package access, or design a **single source of truth** model to reduce this risk.

In addition, `List.contains`/`remove` uses `equals`; in the example, `Employee` does not override `equals`, so it compares by identity. If `equals` is based on a business key, you must carefully consider the risk of duplicates/accidental removal and the lookup cost.

## 8. Association Is Not Inheritance

Two relationships are very easy to confuse:

- `class Manager extends Employee`: **is-a**, a type/inheritance relationship.
- `class Employee { Department department; }`: **has-a/knows-a**, an association relationship.
- `class ReportService { void generate(Printer p) { ... } }`: **uses-a**, a dependency.

A `Car` having an `Engine` does not mean `Car extends Engine`. A `Student` having an `Address` does not mean `Student is-a Address`.

**Rule:** use inheritance when there is a true subtype that fulfills the supertype's contract; use association/composition when an object **collaborates with or contains** other objects.

A Vietnamese phrase "có một" ("has a") can suggest has-a, but you still need to determine the **degree of ownership/lifecycle**; that alone is not enough to conclude it is composition.

## 9. Aggregation: Shareable Whole–Part

UML **shared aggregation** is usually represented by a **hollow diamond** at the whole end. The common idea is that a whole holds a collection of parts, but a part can **exist independently or be used in multiple wholes**.

Organizational model example:

- `Department` groups `Employee` objects.
- An `Employee` remains a business entity when transferring departments.
- Deleting/merging a Department does not necessarily delete the Employee.

```text
Department ◇──────── Employee
      whole             part
```

**UML Warning:** shared aggregation has weak semantics and inconsistent practical usage across models. Do not infer a very specific set of runtime constraints solely from a hollow diamond. When ownership/lifecycle is unclear, an **association with multiplicity and a business description** is usually easier to understand.

### Aggregation Has No Dedicated Java Syntax

```java
class Department {
    private final List<Employee> employees;
}
```

This line **does not yet prove** aggregation. It could be a many-to-many association, shared aggregation, or an internal cache structure; you must inspect the API, actual object ownership, and business contract.

## 10. Aggregation Example: Multiple Teams Sharing the Same Member

Save **`AggregationDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class Member {
    private final String name;

    Member(String name) {
        this.name = Objects.requireNonNull(name);
    }

    String name() {
        return name;
    }
}

final class Team {
    private final String name;
    private final List<Member> members = new ArrayList<>();

    Team(String name) {
        this.name = Objects.requireNonNull(name);
    }

    void add(Member member) {
        members.add(Objects.requireNonNull(member));
    }

    String describe() {
        return name + ": " + members.stream()
                .map(Member::name)
                .toList();
    }
}

public class AggregationDemo {
    public static void main(String[] args) {
        Member an = new Member("An");
        Member binh = new Member("Bình");

        Team api = new Team("API");
        Team quality = new Team("QA");

        api.add(an);
        api.add(binh);
        quality.add(an);

        System.out.println(api.describe());
        System.out.println(quality.describe());

        api = null; // Only drops one reference to Team API.
        System.out.println("Member còn được dùng: " + an.name());
        System.out.println(quality.describe());
    }
}
```

Run:

```bash
javac -encoding UTF-8 AggregationDemo.java
java AggregationDemo
```

Stdout:

```text
API: [An, Bình]
QA: [An]
Member còn được dùng: An
QA: [An]
```

Analysis:
- `an` is created by the caller **before** being added to the Teams.
- The same `an` object is linked from two Teams.
- `api = null` only stops the local variable `api` from holding the reference; it **does not mean the JVM immediately deletes the Team**, nor does it destroy `an`.
- `quality` still references `an`, so it can still be used normally.

The goal of this example is to model **a part having a lifecycle independent of a whole**, rather than demonstrating the exact moment when the garbage collector frees memory.

## 11. Composition: Strong Ownership in Whole–Part

In UML, **composition** is usually represented by a **filled diamond** at the whole end:

```text
Order ◆──────── OrderLine
 whole              part
```

General idea:

- The whole is what controls the **business lifecycle** of the part.
- In the model at any point in time, a part instance has **at most one composite owner** under composition semantics.
- When the whole is deleted/closed in business logic, dependent parts are also handled accordingly (deleted, disconnected, transaction finalized, resources released, etc.).
- A part is usually not treated as an entity with a completely independent lifecycle in the domain.

**Important:** The JVM does not enforce those constraints just because you write a `private final Line line;` field. A Java reference can be shared if you expose it externally. Ownership is a **contract and invariant that must be enforced through the API**.

### Composition Does Not Mean Every Part Must Be Created with `new` Inside the Whole's Constructor

An Order can be created from existing input data, or receive an object created by a factory and then **transfer ownership** by contract. What matters is that **after the transfer**, the owner controls the lifecycle and no unauthorized update paths remain.

Therefore, the criterion "A creates B using `new`" is a **common indicator**, not a complete definition or the sole necessary condition for composition.

## 12. Composition Example: Order Owns OrderLine

Design: Order does not return internal mutable `OrderLine` instances to the caller. An order line has no public API to exist independently as an external entity, and `Order` manages adding items.

Save **`CompositionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class Order {
    private record Line(String sku, int quantity, int unitPrice) {
        Line {
            Objects.requireNonNull(sku, "sku");
            if (sku.isBlank() || quantity <= 0 || unitPrice < 0) {
                throw new IllegalArgumentException("Invalid order line");
            }
        }

        long amount() {
            return (long) quantity * unitPrice;
        }
    }

    private final List<Line> lines = new ArrayList<>();

    void addLine(String sku, int quantity, int unitPrice) {
        lines.add(new Line(sku, quantity, unitPrice));
    }

    long total() {
        long result = 0;
        for (Line line : lines) {
            result += line.amount();
        }
        return result;
    }

    int lineCount() {
        return lines.size();
    }
}

public class CompositionDemo {
    public static void main(String[] args) {
        Order order = new Order();

        order.addLine("BOOK", 2, 120);
        order.addLine("PEN", 3, 10);

        System.out.println("Số dòng: " + order.lineCount());
        System.out.println("Tổng: " + order.total());
    }
}
```

```bash
javac -encoding UTF-8 CompositionDemo.java
java CompositionDemo
```

**Stdout:**

```text
Số dòng: 2
Tổng: 270
```

This is a sound **composition model**:
1. `Order` creates each `Line` itself via `addLine`.
2. `Line` is a `private` nested record, not exposed externally as a public mutable child.
3. The sku/quantity/unitPrice data is validated when creating the line.
4. The caller cannot call `order.lines.clear()` because the field is private and there is no getter returning the list.
5. `Order` is responsible for managing the collection of lines in the domain model.

**Limitation:** there is no "language feature that automatically deletes OrderLine when Order disappears." If `Order` and its `Line` objects are no longer referenced by reachable code, the garbage collector *may* reclaim memory at a time decided by the JVM. **Domain ownership** and **memory reclamation** are two different mechanisms.

### Why Use Type `long` for amount?

The multiplication is widened to `long` by casting `(long) quantity`, avoiding **int** overflow in the intermediate product across the value domain of two int parameters (the product of two positive ints fits within the long range). However, the **sum across multiple lines** can still overflow long if the business domain allows extremely large quantities. When handling real money, you should consider `BigDecimal`, currency units, overflow policy, and transaction invariants. This example focuses on composition and does not replace a production monetary model.

## 13. Aggregation and Composition: Different in Contract, Not in Field Type

Consider two similar declarations:

```java
class Team {
    private final List<Member> members = new ArrayList<>();
}
```

and:

```java
class Order {
    private final List<Line> lines = new ArrayList<>();
}
```

Syntactically, both hold a `List`. However, their domain meanings differ:

| Criterion | Team – Member (aggregation/association) | Order – Line (composition) |
| --- | --- | --- |
| Who creates the part? | The caller/HR system can create Member independently | Order controls the creation of Line |
| Does the part have an independent business identity? | Possibly yes | Usually no |
| Can the part belong to multiple wholes? | Possibly, depending on the domain | Usually not simultaneously |
| Does deleting the whole mean deleting the part? | Usually no | Usually deletes/closes parts along with the whole's lifecycle |
| Can the API allow sharing the part reference? | Usually allowed if the contract permits | Usually restricted to protect ownership |
| Java field representation | `List<Member>` | `List<Line>` |
| Does Java automatically enforce semantics? | No | No |

**You cannot deduce** aggregation or composition solely from `List<T>`, `final`, `private`, or a `new` call. Determine the semantics of the application.

## 14. What Is Object Ownership in Java?

**Object ownership** is the assignment of **who is responsible for managing an object**. There are several dimensions:

- **Construction ownership:** who creates the object or has the right to choose the implementation?
- **Mutation ownership:** who is allowed to change state and uphold invariants?
- **Lifetime ownership:** who decides when the object is no longer valid in business logic?
- **Resource ownership:** who must call `close()` on a connection/file/stream?
- **Concurrency ownership:** which thread or component is permitted to write?
- **Publication ownership:** who authorizes exposing the reference externally?

These dimensions **may not coincide**. For example, a caller creates an `OutputStream` and passes it to a service for writing. The service **uses** the stream, while the caller still **owns the responsibility for closing** the stream. If the service closes the stream without agreement, it has violated the ownership contract.

### Java Does Not Have a General Move Ownership System Like Rust

Java has no general modifier that guarantees at compile time that every mutable reference is **exclusive** or has had ownership transferred in a linear/affine style. One object can have multiple aliases.

Therefore, the rule "a part has only one owner" needs to be enforced through:
- Restricted APIs;
- Defensive copying;
- Immutable value objects;
- Factories/builders with clear contracts;
- State validation guards;
- Resource lifecycle design;
- Tests and reviews.

Do not treat `final` as an ownership keyword: `final` primarily restricts **reassigning a variable/field**, and does not forbid mutating the referenced mutable object.

## 15. Aliasing: Multiple References to the Same Object

```java
List<String> source = new ArrayList<>();
List<String> alias = source;

alias.add("Java");
System.out.println(source); // [Java]
```

Both variables point to **the same list**. If a class stores a mutable parameter directly:

```java
class Registry {
    private final List<String> values;

    Registry(List<String> values) {
        this.values = values; // Shares an alias with the caller.
    }
}
```

then the caller can modify the contents of `values` after the constructor finishes. Having `Registry.values` be `private final` is not enough to control state.

This is a risk when trying to express composition by "keeping a private final field" while the caller still holds a reference to the mutable object.

### Distinguishing Domain Ownership from Aliasing

Two references can point to the same object while the system still **stipulates that only one owner may mutate it**. However, if the API allows the caller to violate this, the ownership contract is very hard to verify.

When strong protection guarantees are needed, use immutable data or copy at the ownership boundary instead of relying on implicit promises.

## 16. Defensive Copying in Constructors and Getters

If an independent snapshot is needed for a collection containing immutable values such as `String`, you can use `List.copyOf`.

Example:

```java
final class Playlist {
    private final List<String> tracks;

    Playlist(List<String> source) {
        tracks = List.copyOf(source);
    }

    List<String> tracks() {
        return tracks;
    }
}
```

Why can `tracks` be returned directly?
- `List.copyOf` creates an **unmodifiable** list by contract.
- `String` is immutable.
- Structural modifications to the mutable `source` after copying do not automatically update the snapshot.

**Do not call `List.copyOf` a deep copy.** If the elements are `MutableAddress`, the element objects may still be shared; having the caller change a field of an element affects what is read from the list snapshot.

### `Collections.unmodifiableList` Is a View, Not a Snapshot

```java
List<String> source = new ArrayList<>(List.of("A"));
List<String> view = Collections.unmodifiableList(source);
source.add("B");
System.out.println(view); // [A, B]
```

A view does not allow direct modification through itself, but still observes the backing list. If the whole needs complete control over changes, a view may not be sufficient if the caller holds an alias to the backing list.

## 17. Runnable Program: Protecting Collection Ownership

Save **`OwnershipCopyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class SnapshotGroup {
    private final List<String> names;

    SnapshotGroup(List<String> source) {
        names = List.copyOf(source);
    }

    List<String> members() {
        return names;
    }
}

public class OwnershipCopyDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("An");

        SnapshotGroup group = new SnapshotGroup(source);
        source.add("Bình");

        System.out.println("source = " + source);
        System.out.println("group = " + group.members());

        try {
            group.members().add("Chi");
        } catch (UnsupportedOperationException error) {
            System.out.println("snapshot không cho sửa");
        }
    }
}
```

```bash
javac -encoding UTF-8 OwnershipCopyDemo.java
java OwnershipCopyDemo
```

**Stdout:**

```text
source = [An, Bình]
group = [An]
snapshot không cho sửa
```

Takeaway: ownership requires both **input control** (not retaining a mutable source alias) and **output control** (not returning the backing mutable collection). This is how a whole protects its invariants.

## 18. Java Object Lifecycle and Garbage Collection

A statement often made when teaching composition is: *"When the whole is destroyed, the part is also destroyed."* That statement describes the **lifecycle in the UML/domain model**, **not a Java runtime instruction that automatically invokes a destructor**.

Java has **garbage collection (GC)**:
- GC determines memory reclaimability based on **reachability** and runtime rules.
- `whole = null` only changes one reference variable; there is no guarantee that the whole object has no other references.
- The part may still be referenced by another object if the API exposed its reference.
- There is no guarantee of when GC will run or reclaim memory after a null assignment.
- `finalize()` is not a reliable lifecycle design mechanism for modern Java applications.

### A More Accurate Model

**Domain lifecycle:**

```text
Order "cancelled"
  -> the OrderLines are no longer valid as lines of that order.
```

**Memory lifecycle:**

```text
An object is no longer reachable from GC roots
  -> eligible for the collector to process under JVM rules,
     at a time not determinable by simple business code.
```

**Resource lifecycle:**

```text
An owner closes a connection/stream/file
  -> calls close() according to the contract,
     not waiting for GC to release the resource on time.
```

Distinguishing these three layers helps avoid confusing composition with calling `System.gc()` or assuming Java has C++-like destructors.

## 19. Resource Ownership: `AutoCloseable` and try-with-resources

Objects holding resources outside the JVM heap (file descriptors, sockets, database connections, streams) require a **resource-closing contract**.

If an object **creates and owns** a resource, that object is usually responsible for calling `close()`. If an object merely **borrows** a resource, it should not close the caller's resource unless agreed upon.

### The Owner Closes Its Own Resource

```java
class ResourceOwner implements AutoCloseable {
    private final SomeCloseable resource;

    ResourceOwner() {
        resource = new SomeCloseable();
    }

    @Override
    public void close() throws Exception {
        resource.close();
    }
}
```

This is **illustrative code**, because `SomeCloseable` has not been declared. The runnable program below uses a simulated resource class to observe the lifecycle.

### Complete Java 17 Example

Save **`ResourceOwnershipDemo.java`**:

```java
final class Connection implements AutoCloseable {
    private boolean closed;

    void query() {
        if (closed) {
            throw new IllegalStateException("Connection closed");
        }
        System.out.println("query");
    }

    @Override
    public void close() {
        if (!closed) {
            closed = true;
            System.out.println("connection closed");
        }
    }
}

final class ConnectionSession implements AutoCloseable {
    private final Connection connection = new Connection();

    void run() {
        connection.query();
    }

    @Override
    public void close() {
        connection.close();
    }
}

public class ResourceOwnershipDemo {
    public static void main(String[] args) {
        try (ConnectionSession session = new ConnectionSession()) {
            session.run();
        }

        System.out.println("done");
    }
}
```

```bash
javac -encoding UTF-8 ResourceOwnershipDemo.java
java ResourceOwnershipDemo
```

**Stdout:**

```text
query
connection closed
done
```

`ConnectionSession` **creates and owns** `Connection`, so `ConnectionSession.close()` calls `connection.close()`. `try-with-resources` guarantees calling `session.close()` according to language rules when exiting scope, even if the try body throws an exception (exceptions can be attached as suppressed exceptions under Java's mechanism).

**This is composition in terms of resource lifecycle**, not GC closing the connection automatically.

### Avoid Closing Borrowed Resources

If a method receives:

```java
void write(OutputStream borrowed, byte[] data) throws IOException {
    borrowed.write(data);
}
```

then **the caller normally owns** `borrowed`. The `write` method only **uses** the stream; closing it here could prevent the caller from continuing to use it. If you want the method to assume ownership, the method name/documentation/API must explicitly state the **transfer of close responsibility**.

## 20. Ownership Transfer and Borrowed References

Two different contracts with the same Java signature:

```java
void register(Resource resource);
```

It can have one of two meanings:

1. **Borrowed:** the service only uses the resource, does not close it, and does not retain it after the call.
2. **Ownership transfer:** after `register`, the service becomes responsible for managing/closing the resource; the caller should not continue performing operations that violate invariants.

The Java compiler **does not infer** this difference from the `Resource` parameter.

### Write Clear Contracts

Example API specification:

```text
registerOwned(resource):
  If successful, the registry takes responsibility for closing the resource.
  The caller must not close the resource while the registry still owns it.

inspect(resource):
  Only reads during the call; the caller retains ownership.
  The method does not store the reference and does not close the resource.
```

This is contract documentation, not Java syntax.

If the application needs strict guarantees, you can use a **state-transitioned wrapper**, check `closed/transferred`, or provide an interface with restricted access. Keep in mind that external aliases may still exist if the caller retains a reference and the Java type permits operations.

## 21. Not Every "has-a" Is Composition

The statement `Car has an Engine` is not enough to classify the relationship:

**Case A: Engine is exclusively owned by Car**

```java
class Car {
    private final Engine engine = new Engine();
}
```

If Engine is not exposed, is created/managed by Car, and is tied to Car's lifecycle by contract, this can be **composition**.

**Case B: Car uses an Engine provided by the caller**

```java
class Car {
    private final Engine engine;

    Car(Engine engine) {
        this.engine = engine;
    }
}
```

This case clearly has an **association**, but **there is not enough information** to conclude ownership. The caller may own the Engine, or ownership may be transferred to Car; the contract decides.

**Case C: Car only borrows Engine for inspection**

```java
class Diagnostics {
    void inspect(Engine engine) {
        engine.selfTest();
    }
}
```

If no reference is retained, the relationship is **uses/dependency** at the level under consideration.

You usually need to ask further: "Can Engine change owner? Can it be shared? Who has to close it? Does the API return Engine externally?" before drawing a filled diamond.

## 22. Composition and Immutable Value Objects

Parts carrying immutable data are usually easier to control. Example:

```java
record Coordinates(double latitude, double longitude) {
}

final class Location {
    private final Coordinates point;

    Location(double latitude, double longitude) {
        point = new Coordinates(latitude, longitude);
    }

    Coordinates point() {
        return point;
    }
}
```

`Coordinates` is immutable with respect to the state of its two primitive components under the standard record API; sharing the `point` reference does not allow the caller to modify latitude/longitude after initialization.

However, **not every record is deeply immutable**:

```java
record MutableBox(int[] values) {
}
```

`MutableBox` holds a mutable array. If you want to protect ownership, you need to copy the array in the constructor/accessor or switch to an immutable representation.

### Takeaway

Composition does not require every part to be mutable or value objects to be completely hidden. An **immutable value object** can be safely shared with respect to mutation even though domain ownership must still be properly defined.

## 23. Constructor Injection: Dependency or Association?

Example:

```java
interface MessageSender {
    void send(String message);
}

final class NotificationService {
    private final MessageSender sender;

    NotificationService(MessageSender sender) {
        this.sender = sender;
    }

    void notifyUser(String text) {
        sender.send(text);
    }
}
```

`NotificationService` **depends** on the `MessageSender` abstraction and simultaneously **holds an association** to a sender instance.

**Dependency Injection (DI)** is generally a mechanism for **providing dependencies**, rather than classifying aggregation or composition on its own.

If `sender` is created and managed by a DI container, `NotificationService` may **borrow** the sender. If `NotificationService` creates the sender directly and takes responsibility for closing it, ownership is different.

Therefore:
- **Constructor injection**: refers to how dependencies are passed when constructing an object.
- **Association**: refers to the reference-holding relationship between objects.
- **Ownership**: refers to lifecycle/mutation/resource responsibility.

All three can be true simultaneously at different levels.

## 24. Example of DI via Interface and Long-Lived Association

Save **`ConstructorInjectionDemo.java`**:

```java
interface MessageSender {
    void send(String message);
}

final class ConsoleSender implements MessageSender {
    @Override
    public void send(String message) {
        System.out.println("SEND: " + message);
    }
}

final class NotificationService {
    private final MessageSender sender;

    NotificationService(MessageSender sender) {
        this.sender = java.util.Objects.requireNonNull(sender);
    }

    void welcome(String name) {
        sender.send("Xin chào " + name);
    }
}

public class ConstructorInjectionDemo {
    public static void main(String[] args) {
        MessageSender sharedSender = new ConsoleSender();

        NotificationService first =
                new NotificationService(sharedSender);
        NotificationService second =
                new NotificationService(sharedSender);

        first.welcome("An");
        second.welcome("Bình");
    }
}
```

```bash
javac -encoding UTF-8 ConstructorInjectionDemo.java
java ConstructorInjectionDemo
```

Stdout:

```text
SEND: Xin chào An
SEND: Xin chào Bình
```

The two services share **the same sender object**. There is an association via a field and a dependency on the interface. However, neither service exclusively owns the sender; the caller/container can manage the lifecycle of `sharedSender`.

### Design Benefits

- Depends on an **interface** rather than a concrete implementation.
- Can be swapped with a test double/mock sender for unit testing.
- The sender's lifecycle can be managed by an outer layer/container.
- Avoids instantiating `new ConsoleSender()` deep inside the service when the caller needs configuration control.

However, DI is not mandatory for every class; for a simple immutable value object, a direct constructor may be sufficient.

## 25. Collection Associations: One-to-Many and Many-to-Many

A `University` can manage multiple `Course` objects:

```java
class University {
    private final List<Course> courses = new ArrayList<>();
}
```

This is a candidate for a `University 1 -> 0..* Course` association, but you should ask:
- Does a Course belong to exactly one University?
- Can a Course transfer between Universities?
- Does a Course exist independently outside a University?
- Is University responsible for deleting a Course?
- Is the List exposed externally so clients can remove Courses at will?

If Course is an independent domain entity, association/aggregation can be chosen. If a structure depends tightly on University and does not exist outside it, composition may be appropriate.

### Many-to-Many in Code

In the domain, `Student` and `Course` may have a many-to-many relationship:
- One Student takes many Courses.
- One Course has many Students.

It is not strictly necessary to store two mutable collections directly inside Student and Course. You can use an **Enrollment** object as an associative entity, containing metadata such as enrollment date/grade:

```java
record Enrollment(String studentId, String courseId, int year) {
}
```

In database-backed systems, many-to-many relationships are typically managed via a join table/separate aggregate. This is a domain/data modeling concern, not an automatic indicator of composition.

## 26. Relationships by ID vs. Relationships by Object Reference

Two designs:

```java
class Order {
    private Customer customer;
}
```

and:

```java
class Order {
    private String customerId;
}
```

In the first design, Order holds an **object reference** (a direct association in memory).

In the second design, Order holds an **identifier** to look up Customer when needed. At the domain level, an Order–Customer relationship still exists, but in the Java object graph there may not be a direct reference to Customer.

This is important for:
- Persisted entities;
- Microservices and remote boundaries;
- Serialization;
- Lazy loading;
- Avoiding reference cycles;
- Reducing coupling between aggregates.

**Do not draw UML based solely on whether there is a field of type `Customer` or `String`.** A business relationship can be represented indirectly by ID or query.

## 27. Aggregates and Aggregate Root: Not Synonymous with UML Aggregation

In Domain-Driven Design (DDD), an **aggregate** is a consistency boundary for a cluster of domain objects, and the **aggregate root** is the entry point for modifying them in accordance with invariants.

The DDD term **aggregate** does not mean the exact same thing as **shared aggregation (hollow diamond) in UML**.

For example, `Order` can be an **aggregate root**; `OrderLine` is modified through `Order.addLine`/`Order.removeLine`. This is close to composition in design, but you need to separate:
- The transaction/invariant boundary of a DDD aggregate;
- UML whole–part semantics;
- Java object references and memory lifecycle.

An aggregate root may reference an entity belonging to another aggregate by **ID**; that does not mean it owns that entity's entire lifecycle.

### Practical Rule

If a child is not permitted to be updated while bypassing the owner's validation, **do not return the mutable child or backing collection** for callers to modify at will. Provide command methods on the owner and appropriate read models/snapshots.

## 28. Shared Mutable Objects and Mutation Rights

An aggregation often creates opportunities for **sharing parts** across multiple owners/whole objects.

For example, an `Employee` can appear in multiple `Team` objects. If Employee is mutable, calling `employee.rename(...)` in one place can cause all Teams to observe the new name.

That may be the **intended behavior**, but it must be stated explicitly:
- Does each Team use a shared Employee identity or a snapshot?
- Who has permission to modify Employee?
- Are events/notifications needed when Employee changes?
- If multithreaded, who handles synchronization?

In composition, ways to avoid aliasing include:
- Creating the part inside the owner;
- Avoiding returning mutable parts directly;
- Using immutable value objects;
- Copying mutable inputs;
- Exposing mutation APIs through the owner.

**Not all sharing is wrong.** It is mainly wrong when an object is modified **outside the intended contract/invariants**.

## 29. Object Graph Cycles and Serialization Risks

Bidirectional associations easily create a graph:

```text
A -> B -> A
```

Example:

```java
class Parent {
    Child child;
}

class Child {
    Parent parent;
}
```

If you use a serializer that recursively traverses fields without managing identity/cycles, it can lead to infinite loops or stack errors.

In modern Java GC, **a cycle by itself does not prevent garbage collection** when the entire cycle is no longer reachable from GC roots; you do not need to break every reference cycle just for Java heap GC to work.

However, you still need to watch out for:
- JSON serialization may require identity references/DTO mapping or omitting back-references.
- A's `toString()` calling `B.toString()` and vice versa can cause recursion.
- `equals`/`hashCode` traversing a bidirectional graph can cause recursion or be overly expensive.
- UI/data binding may need to avoid automatically looping through the object graph.

### Reducing Coupling

A unidirectional association is usually simpler if the business logic does not need reverse traversal. Do not create a back-reference just to make it "complete in both directions on UML."

## 30. Do Not Equate Strong/Weak References with Aggregation/Composition

Java has reference APIs such as `java.lang.ref.WeakReference`, but they are **not** a direct way to encode UML shared aggregation.

- **Strong reference**: the ordinary form of reference, affecting reachability under JVM rules.
- **WeakReference**: a special reference that may not keep an object alive against GC in the same way a strong reference does.
- **Aggregation/composition**: describe **domain relationship semantics and ownership**.

Using `WeakReference` does not automatically turn a relationship into UML aggregation. Nor does composition always require a strong reference for the entire lifetime of the program.

Only consider weak/soft/phantom references for well-understood caching, canonical mapping, or special lifecycle management problems; do not use them as a mechanical translation of a UML diamond.

## 31. Reading Basic UML Notation

Commonly seen:

```text
A  - - - - > B        Dependency (dashed line)
A  -------- B         Association (solid line)
Whole ◇----- Part     Shared aggregation (hollow diamond at Whole)
Whole ◆----- Part     Composition (filled diamond at Whole)
Child ------▷ Parent  Generalization/inheritance (hollow triangle pointing to Parent)
```

Arrow direction, role names, multiplicity, and navigability have their own notation rules. Here we only use **approximate ASCII** for recognition; when drawing formal UML, choose the exact arrowhead/diamond style.

### Key Point to Remember When Reading a Diamond

**The diamond is placed on the whole/owner side**, not on the part side.

Example:

```text
Order ◆-------- OrderLine
 1                 1..*
```

Approximate meaning: an Order consists of one or more lines (if the domain requires at least one); each line belongs to one composite Order at a time according to UML semantics.

Java does not automatically prevent an Order from having zero lines. If the diagram specifies `1..*`, the API/order lifecycle must enforce that invariant according to the model — for example, disallowing order completion if it is empty.

## 32. How to Translate UML into Java Design

A useful workflow:

1. **Identify object identities**: do the entities have their own lifecycles or are they just values?
2. **Determine navigation direction**: who needs to know whom?
3. **Determine multiplicity**: `1`, `0..1`, `0..*`, or `1..*`?
4. **Determine ownership**: who creates, who holds, who modifies, and who ends the lifecycle?
5. **Choose the API**: method parameter, constructor injection, field, collection, ID, or repository query?
6. **Lock down invariants**: non-null, uniqueness, no duplicate ownership, bidirectional consistency.
7. **Control aliasing**: are mutable internals returned, or are mutable inputs accepted directly?
8. **Manage resources**: does the owner need `AutoCloseable`/`close`?
9. **Evaluate concurrency** if the object graph is shared.
10. **Write tests** for moving associations, shared parts, deleting composites, snapshots, and closing resources.

### Do Not Draw Class Diagrams from Code Mechanically

A static helper calling a method on an object passed as a parameter is not necessarily a structural association. A collection field does not prove composition. A Java class can include both a **dependency on an abstraction** and an **association to an instance** at the same time.

The goal of a diagram is to communicate **meaningful relationships to the reader**, not to copy every local variable.

## 33. Distinguishing Inheritance, Composition, and Delegation

**Inheritance:** `extends`; a subtype is-a relationship.

**Composition:** an owning object contains/manages one or more component objects; focused on whole–part ownership.

**Delegation:** object A receives a call and delegates the work to object B, regardless of whether B is owned or borrowed.

Example:

```java
final class PrinterService {
    private final Printer printer;

    PrinterService(Printer printer) {
        this.printer = printer;
    }

    void print(String text) {
        printer.print(text);
    }
}
```

`PrinterService` **delegates** printing to `Printer`. It is **associated** with Printer via a field. However, it **does not necessarily own Printer's lifecycle** — if the printer is provided by a DI container, the service usually only borrows the instance.

Therefore, "delegation" is not synonymous with "composition," even though they can appear together in the same design.

## 34. Composition Over Inheritance: Understanding the Advice Correctly

The advice "prefer composition over inheritance" generally recommends using collaborating objects to compose behavior instead of overusing subclass hierarchies.

For example, instead of:

```java
class SpecialReport extends BaseReport {
    // Overrides many steps to replace the formatter.
}
```

you can use:

```java
final class ReportService {
    private final Formatter formatter;

    ReportService(Formatter formatter) {
        this.formatter = formatter;
    }
}
```

This is **object composition/delegation** in the common parlance of design patterns, but under UML lifecycle semantics, `ReportService` may simply have an **association** with a Formatter shared via DI. The term "composition" in design advice **does not always** refer to the UML filled diamond.

### When Inheritance Is Still Right

Inheritance can be appropriate when:
- The subtype complies with the supertype's contract;
- The framework has intentional extension points;
- Polymorphism through a class hierarchy carries genuine domain meaning;
- It is not merely to reuse a few lines of code.

Association/composition is usually more appropriate when A **has** B or **uses** B, rather than A **is a** B.

## 35. Choosing an Interface at the Dependency Boundary

Suppose `CheckoutService` needs to calculate tax. Depending directly:

```java
class CheckoutService {
    private final FixedTaxCalculator calculator =
            new FixedTaxCalculator();
}
```

causes the service to choose the implementation right inside itself.

You can use an abstraction:

```java
interface TaxCalculator {
    long tax(long subtotal);
}

final class CheckoutService {
    private final TaxCalculator calculator;

    CheckoutService(TaxCalculator calculator) {
        this.calculator = calculator;
    }
}
```

Benefits:
- Easy to swap tax calculation rules without modifying the core service.
- Easy to test using a simple implementation.
- The TaxCalculator's lifecycle can be managed by an upper-level owner.
- The service depends on a **contract**, not a concrete class.

However, an interface does not automatically solve:
- Who owns the calculator?
- Does the calculator have mutable state?
- Is the calculator thread-safe when shared?
- Is the service allowed to close the calculator?

**Dependency inversion and object ownership are two separate questions.**

## 36. Example of a Service Using and Holding the Same Abstraction

Save **`StrategyAssociationDemo.java`**:

```java
interface Discount {
    int apply(int price);
}

final class FixedDiscount implements Discount {
    private final int amount;

    FixedDiscount(int amount) {
        this.amount = amount;
    }

    @Override
    public int apply(int price) {
        return Math.max(0, price - amount);
    }
}

final class Checkout {
    private final Discount discount;

    Checkout(Discount discount) {
        this.discount = java.util.Objects.requireNonNull(discount);
    }

    int calculate(int price) {
        return discount.apply(price);
    }
}

public class StrategyAssociationDemo {
    public static void main(String[] args) {
        Discount promotion = new FixedDiscount(20);

        Checkout first = new Checkout(promotion);
        Checkout second = new Checkout(promotion);

        System.out.println(first.calculate(100));
        System.out.println(second.calculate(15));
    }
}
```

```bash
javac -encoding UTF-8 StrategyAssociationDemo.java
java StrategyAssociationDemo
```

Stdout:

```text
80
0
```

Two `Checkout` objects are both associated with a single `Discount` object. Each `calculate` call uses this object. This is an **association with a strategy** together with a **dependency on an interface**, which does not prove that each checkout owns a distinct Discount.

## 37. When to Use a Single Source of Truth Instead of Back-References?

Bidirectional associations increase the risk of **inconsistency**:

```text
Department.employees contains An
Employee.department is QA instead
```

If the system does not need direct traversal from Employee back to Department, you can keep only `Department.employees`.

If bidirectional querying is needed while data resides in a database, a repository can return an Employee's `Department` by querying by ID instead of holding two mutable references simultaneously on the heap.

Trade-offs:
- **Unidirectional**: fewer invariants, easier to maintain, may require a query.
- **Bidirectional**: more convenient navigation, but must be updated atomically/synchronously on both sides.
- **By ID**: decouples the object graph, suits bounded contexts/serialization, requires an ID resolution mechanism.

There is no default rule that "a proper association must be bidirectional." Only create a back-reference if the use case genuinely requires it.

## 38. Thread-Safety of Shared Aggregation

In shared aggregation, a `Member` or `Formatter` may be used by multiple owners/consumers.

If the shared object is **immutable**, sharing is usually simpler with respect to mutation.

If the shared object is **mutable**:
- Multiple clients may make overlapping state updates.
- Other threads may observe unsynchronized state.
- One service may inadvertently "close" a resource that another service still needs.
- Collection membership may change during iteration.

Solutions depending on the domain:
- Immutable value objects/snapshots;
- Synchronization;
- Concurrent collections;
- Ownership confined to a single thread;
- Event-driven model;
- Copy-on-write where appropriate.

**`final` on a reference field does not make a shared object thread-safe.**

For example, `private final List<String> items = new ArrayList<>();` only prevents reassigning the field; multiple threads adding/removing on `ArrayList` still require protection.

## 39. Lifecycle Tests: Verifying Ownership by Behavior

Do not just look at a pretty diagram. Design these tests/scenarios:

**Dependency:**
- Can two different formatters be passed into the same service?
- After the call, does the service need to retain the formatter?

**Association:**
- Does moving an Employee to another Department update all sides?
- Can two Courses use the same Instructor without creating a copy?
- If Instructor changes name, should Courses see the new value?

**Aggregation:**
- Does the part exist independently after the whole is no longer used?
- Can the part be shared among multiple wholes according to the contract?
- Is the whole allowed to close/delete a part that another service is still using?

**Composition:**
- Is the caller allowed to hold a mutable reference to a part and modify it outside the owner?
- Does the owner validate invariants every time a part is added/removed?
- Does closing the owner actually close the resource owned by the owner?
- Does the part still carry valid business meaning after the owner's lifecycle ends?

These tests help verify **semantics**, instead of guessing based solely on `private final`.

## 40. Common Mistakes

| Misconception / Faulty Design | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| "Having a `B` field means composition" | A field is only a reference | Define domain ownership and lifecycle |
| "Having `new B()` guarantees composition" | B may be returned and shared arbitrarily | Inspect the contract, aliasing, and responsibilities |
| "Composition means GC deletes the part immediately when the whole is null" | GC has no deterministic timing | Separate domain lifecycle, GC, and resource closing |
| "Aggregation is always enforced by Java using List" | Java has no aggregation keyword | Enforce invariants through the API |
| "A dependency must be a field" | It can be a parameter/local variable | Model uses according to the usage scope |
| "Association is only one-way" | It can be unidirectional or bidirectional | Determine the required navigability |
| "Bidirectional association synchronizes automatically" | Two references/collections easily go out of sync | Centralize link-management operations |
| "List means a 1..* relationship" | A List can be empty | Validate multiplicity |
| "`private final List` means immutable" | A mutable List can still be modified | Use encapsulation, snapshots/immutables |
| "`List.copyOf` deep-copies objects" | It only shallow-copies elements | Protect mutable elements |
| "`Collections.unmodifiableList` is a snapshot" | It is usually a live view | Use a snapshot if needed |
| "DI means the service owns the dependency" | The container/caller may own it | State ownership/closing contracts explicitly |
| "The helper should close a borrowed stream to be safe" | Violates the caller's lifecycle | Only the owner closes unless there is a valid transfer |
| "Two Teams using one Member means two copies of Member" | The same reference can be shared | Track object identity |
| "`extends` works for any has-a" | Is-a differs from has-a | Use association/composition |
| "UML shared aggregation always has semantics as clear as composition" | Shared aggregation is weak/inconsistent | Use association + notes if needed |
| "A Java reference cycle will not be garbage-collected" | GC uses reachability, not simple reference counting | Separate memory from association |
| "WeakReference must be used for UML aggregation" | Weak references have different runtime semantics | Do not translate UML notation mechanically |
| "If an object has no direct reference, the domain has no relation" | IDs/queries can be used | Distinguish code graph from domain model |
| "A final class is an immutable composite" | A final class forbids subclassing, not state mutation | Design immutable state separately |
| "UML composition replaces transaction consistency" | A diagram does not implement invariants on its own | Design synchronized APIs/transactions |
| "Each part can have only one reference" | Composition ownership does not mean strictly one Java reference | Control mutation/lifetime contracts |

## 41. Exercises with Answers

### Exercise 1 — Uses or Association?

```java
class InvoicePrinter {
    void print(Invoice invoice, Formatter formatter) {
        System.out.println(formatter.format(invoice.toString()));
    }
}
```

**Question:** Does `InvoicePrinter` retain `Formatter` long-term?

**Answer:** No, according to the given code. `Formatter` is passed in and used inside the method; this is an appropriate **dependency (uses)**. If the code actually stored the formatter in a field elsewhere, association would also need to be considered.

### Exercise 2 — Does a Field Guarantee Composition?

```java
class Course {
    private final Instructor instructor;

    Course(Instructor instructor) {
        this.instructor = instructor;
    }
}
```

**Answer:** Not enough information. There is an association. Having Instructor passed in by the caller suggests an independent relationship, though it does not rule out ownership transfer by contract; concluding composition/aggregation requires additional semantics.

### Exercise 3 — Sharing a Part

```java
Member an = new Member("An");
teamA.add(an);
teamB.add(an);
```

**Answer:** Both Teams hold the same `an` object. If Member has an independent lifecycle, it can be modeled as shared aggregation/association according to the domain. They are not two copies of Member.

### Exercise 4 — Order–Line

Order creates each line itself, a line has no independent domain identity, all modifications must go through Order, and deleting Order entails ending the business lifecycle of its lines.

**Answer:** This is a classic candidate for **composition**. However, Java does not enforce it automatically; the API must uphold the contract.

### Exercise 5 — UML Multiplicity

A diagram describes `Course 1 ---- 1 Instructor`. Is declaring `Instructor instructor;` sufficient?

**Answer:** No. The variable can be null. Validation is needed in the constructor/update, or the API/state machine must guarantee a valid Instructor in the required states.

### Exercise 6 — Getter Returning a Mutable List

```java
class Order {
    private final List<Line> lines = new ArrayList<>();

    List<Line> getLines() {
        return lines;
    }
}
```

**Answer:** The caller can invoke `getLines().clear()` or add elements bypassing validation. This is representation exposure that weakens ownership/invariants. Return an immutable snapshot/read model or provide an appropriate read-only API.

### Exercise 7 — Composition and GC

```java
Order order = new Order();
order = null;
```

**Answer:** You cannot conclude that Order and all its parts have been immediately destroyed by the JVM. Other references may still exist; GC has no guaranteed collection timing. Domain lifecycle and GC memory lifecycle are different.

### Exercise 8 — Borrowed Resource

A method receives an `OutputStream` managed by the caller and only needs to write once.

**Answer:** This is a dependency/borrowed use under a sensible contract. Do not automatically `close()` the stream inside the helper unless the API explicitly states that the method takes ownership.

### Exercise 9 — Constructor Injection

`NotificationService` holds a `MessageSender sender` field received from the constructor, while the DI container manages the sender.

**Answer:** The service has an association to the sender instance and depends on the `MessageSender` interface, but **does not necessarily own the resource lifetime** of the sender.

### Exercise 10 — Bidirectional Link

Employee transfers from DEV to QA, yet `DEV.members` still contains Employee.

**Answer:** The bidirectional association invariant is broken. The transfer operation needs to handle detaching the old link, adding the new link, and updating Employee; under multithreading, appropriate transactions/synchronization are needed.

### Exercise 11 — Aggregation and Composition

A `Library` manages multiple physical `Book` objects. When the library ceases operations, books can be transferred to another library; Book has an ID and an independent lifecycle.

**Answer:** Association/aggregation usually reflects this requirement better than composition tied to Library's lifecycle. However, the model depends on the specific domain, not just class names.

### Exercise 12 — Composition with a Nested Value Object

`Order` has a private nested record `Line(String sku,int count)`, creates lines internally, and only exposes `total()`.

**Answer:** This is a sound composition design: Order controls creation and invariants without exposing mutable children. An immutable record with simple String/int components helps prevent alias mutation.

### Exercise 13 — Cycles and GC

`A` references `B`, and `B` references `A` back. No GC roots can reach either A or B.

**Answer:** A reference cycle **does not by itself prevent** the Java garbage collector from reclaiming them. However, a recursive serializer/toString can still run into recursion if cycles are not managed.

### Exercise 14 — Association via ID

Order stores only `String customerId`, not a `Customer` object.

**Answer:** An Order–Customer relation can still exist in the domain/UML. The Java object graph is not required to have a direct reference; the system can resolve it via a repository.

### Exercise 15 — "Composition over Inheritance"

`ReportService` has an injected `Formatter` field and calls `formatter.format(...)`. Is this UML composition?

**Answer:** It clearly uses **delegation** and has an association to the formatter. In the advice "composition over inheritance," people are referring to combining objects instead of subclassing; that **does not automatically prove strong ownership** in the sense of UML composition.

## 42. Class Relationship Design Checklist

1. **Clarify the roles of A/B:** who is the consumer, provider, whole, or part?
2. **Determine domain identity:** can B exist as an independent entity?
3. **Check uses-only:** does A only use B within a method and then let go?
4. **Check association:** does A need to hold a link to B in its state?
5. **If it is a bidirectional association**, is it truly needed, and who maintains the invariant?
6. **Determine multiplicity**: `1`, `0..1`, `0..*`, `1..*`, and validation.
7. **Determine navigability:** only A→B, or is B→A also needed?
8. **If whole–part**, can the part be shared/moved, or does it belong exclusively to the whole?
9. **If choosing aggregation**, explicitly document lifetime independence; do not rely solely on a hollow diamond.
10. **If choosing composition**, describe who creates/transfers ownership, who mutates, and who ends the lifetime.
11. **Do not equate a `private final` field with ownership**.
12. **Check aliasing:** is a mutable input still retained by the caller? Does a getter expose state?
13. **Use immutable value types/defensive copies** when needed to protect invariants.
14. **If resources are involved**, specify who must call `close()` and use `AutoCloseable` where appropriate.
15. **If using DI**, determine whether the container/caller or the service owns the dependency.
16. **If an object is shared**, check concurrency/thread-safety and avoid closing resources prematurely.
17. **If modeling via ID**, ensure resolution/consistency according to the persistence system.
18. **If cycles exist**, verify whether the serializer, `toString`, and `equals/hashCode` handle them safely.
19. **Do not use inheritance for has-a/uses-a**; is-a must satisfy the behavioral contract.
20. **Write tests for lifecycle**, membership transfers, sharing, removal, snapshots, and exceptions.
21. **Draw just enough UML**, with role/multiplicity labels when the reader needs them.
22. **Distinguish a DDD aggregate from UML shared aggregation**.
23. **Do not use `WeakReference` as an indicator of UML aggregation**.
24. **Confirm the relationship type from business semantics** rather than guessing solely from Java syntax.

## Key Takeaways

- **Dependency (uses):** A needs B to perform an operation, possibly only via a parameter without storing a reference.
- **Association:** A and B have a structural link, usually expressed via a field/collection or a relationship by ID.
- **Aggregation:** shared whole–part, where the part can have an independent lifecycle; the UML hollow diamond has relatively weak semantics and requires domain explanation.
- **Composition:** strongly owned whole–part, where the part is controlled by the owner regarding lifecycle/invariants; UML filled diamond on the whole side.
- **Java has no keyword for aggregation/composition.** `private`, `final`, `new`, or `List<T>` do not by themselves prove ownership.
- **An object can have multiple references**; aliasing, defensive copying, and immutable values determine how well state is protected in practice.
- **GC does not mean business deletion or `close()`**. For resources, design closing responsibility explicitly.
- **Constructor injection** passes a dependency; it does not necessarily transfer resource ownership to the service.
- **Inheritance (is-a) differs from association/composition (has-a) and dependency (uses-a)**.
- The best model is one that expresses **identity, multiplicity, navigability, ownership, and testable invariants** — not just using the right UML arrow.
