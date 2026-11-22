# Reusing Behavior Through Composition and Inheritance in Java OOP

In a Java application, many features can share code for formatting reports, sending notifications, validating data, logging, or storing results. Two common OOP approaches to reuse are:

- **Inheritance:** Create a *subclass* based on a *superclass*, reuse inherited behavior/state, and potentially override designed extension points. The relationship must represent a meaningful **is-a**: "the child object is a kind of parent object."
- **Composition:** An object **has or uses** other objects to perform work and **delegates** part of its behavior to them. The relationship is often described as **has-a / uses-a**. Reuse comes from assembling components with clear responsibilities, without requiring them to share an inheritance hierarchy.

The important question is not "which approach uses fewer lines of code?" but **whether the relationships make sense in the business domain, which parts must vary independently, and how evolving requirements will affect callers**.

## 1. Everyday Example: Is-a and Has-a

An `ElectricCar` is a kind of `Car`. If all behavior promised by `Car` remains meaningful for `ElectricCar`, inheritance may fit:

~~~java
class Car {
    void drive() {
        System.out.println("Xe đang chạy");
    }
}

class ElectricCar extends Car {
    void charge() {
        System.out.println("Đang sạc");
    }
}
~~~

However, a car **has a battery**; it **is not a battery**. Writing `class ElectricCar extends Battery` just to reuse `charge` would misrepresent the model.

A more accurate composition:

~~~java
class Battery {
    void charge() {
        System.out.println("Pin đang sạc");
    }
}

class ElectricCar {
    private final Battery battery;

    ElectricCar(Battery battery) {
        this.battery = battery;
    }

    void chargeCar() {
        battery.charge(); // Ủy quyền cho thành phần.
    }
}
~~~

Here, `ElectricCar` has a `Battery`. Calling `battery.charge()` is **delegation**, a common technique for reuse through composition.

| Question | Inheritance | Composition |
| --- | --- | --- |
| Core relationship | "A **is a kind of** B" | "A **has/uses** B" |
| Typical Java code | `class A extends B` | Reference field `B b`, call `b.doWork()` |
| Source of reused behavior | Inherited methods/state | Methods of collaborating objects |
| Shared superclass required? | A parent–child class relationship | No |
| Changing behavior | Override designed extension points | Replace collaborators or configuration |
| Degree of coupling | A subclass depends on the superclass contract and some implementation details | The caller may depend only on component interfaces |
| Typical risks | Artificial is-a relationships and superclass changes affecting subclasses | Too many intermediary objects or meaningless delegation |

**Terminology note:** In programming, "favor composition" is sometimes used broadly for *assembling objects through fields and delegation*. In strict UML, **composition** with a filled diamond also expresses strong *whole–part* lifecycle ownership. A dependency **injected from outside through a constructor** may be an association/aggregation rather than lifecycle-owning UML composition. This lesson uses "composition" in the broader OOP design sense and will not assign a filled diamond to every object reference.

## 2. Scenario: Generating and Distributing Reports

Suppose a system needs to:

1. Generate sales-report content.
2. Format the report as **plain text** or **Markdown**.
3. Output the report to the **console** or an **in-memory archive**.

Two reasonable reuse approaches address different kinds of change.

### Approach A: Inheritance to Share a Report Template

An `AbstractReport` contains the title and the `render()` template. Each concrete report class provides only the body:

~~~java
abstract class AbstractReport {
    private final String title;

    protected AbstractReport(String title) {
        this.title = title;
    }

    public final String render() {
        return title + "\n" + buildBody();
    }

    protected abstract String buildBody();
}

class SalesReport extends AbstractReport {
    SalesReport(String title) {
        super(title);
    }

    @Override
    protected String buildBody() {
        return "Tổng doanh thu: 1500000 VND";
    }
}
~~~

`SalesReport extends AbstractReport` makes sense because **a sales report is a kind of report**. The rendering template is reused. `render()` is `final` so subclasses cannot bypass the shared template; `buildBody()` is the intended extension point.

Problems arise when each subclass must determine **the content type, format, and output destination**. A hierarchy containing `SalesMarkdownConsoleReport`, `SalesPlainTextConsoleReport`, `SalesMarkdownArchiveReport`, and so on can grow rapidly when these options vary independently.

### Approach B: Composition to Assemble Independent Responsibilities

Separate these roles:

- `ReportData`: The report data to present.
- `Formatter`: Converts the report into a displayable string.
- `Destination`: Receives the string and delivers it to the output target.
- `ReportPublisher`: **Owns the coordination workflow** and calls components in the correct order.

~~~mermaid
flowchart LR
    R["ReportData"] --> P["ReportPublisher"]
    F["Formatter\nPlainText hoặc Markdown"] --> P
    P --> D["Destination\nConsole hoặc Archive"]
~~~

`ReportPublisher` is **neither a kind of** formatter **nor a kind of** destination. It **uses** both to achieve its goal. This is a natural example of composition.

## 3. Complete Java Code: Comparing Both Approaches in One Program

Save as **`ReuseComparisonDemo.java`** and run with **Java 11 or later**; no external libraries are needed.

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class ReuseComparisonDemo {

    private static String requireText(String value, String field) {
        String checked = Objects.requireNonNull(value, field).trim();
        if (checked.isEmpty()) {
            throw new IllegalArgumentException(field + " không được rỗng");
        }
        return checked;
    }

    // ----- PHẦN 1: TÁI SỬ DỤNG BẰNG KẾ THỪA -----

    static abstract class AbstractReport {
        private final String title;

        protected AbstractReport(String title) {
            this.title = requireText(title, "title");
        }

        public final String render() {
            return title + "\n" + buildBody();
        }

        // Điểm mở rộng: lớp con cung cấp phần thân báo cáo.
        protected abstract String buildBody();
    }

    static final class SalesReport extends AbstractReport {
        private final BigDecimal revenue;

        SalesReport(String title, BigDecimal revenue) {
            super(title);
            this.revenue = Objects.requireNonNull(revenue, "revenue");
            if (revenue.signum() < 0) {
                throw new IllegalArgumentException(
                        "Doanh thu không được âm");
            }
        }

        @Override
        protected String buildBody() {
            return "Tổng doanh thu: "
                    + revenue.toPlainString() + " VND";
        }
    }

    // ----- PHẦN 2: TÁI SỬ DỤNG BẰNG KẾT HỢP -----

    static final class ReportData {
        private final String title;
        private final String body;

        ReportData(String title, String body) {
            this.title = requireText(title, "title");
            this.body = requireText(body, "body");
        }

        String getTitle() {
            return title;
        }

        String getBody() {
            return body;
        }
    }

    interface Formatter {
        String format(ReportData report);
    }

    static final class PlainTextFormatter implements Formatter {
        @Override
        public String format(ReportData report) {
            Objects.requireNonNull(report, "report");
            return report.getTitle() + "\n" + report.getBody();
        }
    }

    static final class MarkdownFormatter implements Formatter {
        @Override
        public String format(ReportData report) {
            Objects.requireNonNull(report, "report");
            return "# " + report.getTitle() + "\n\n"
                    + report.getBody();
        }
    }

    interface Destination {
        void deliver(String formattedReport);
    }

    static final class ConsoleDestination implements Destination {
        @Override
        public void deliver(String formattedReport) {
            System.out.println(formattedReport);
        }
    }

    static final class MemoryArchive implements Destination {
        private final List<String> stored = new ArrayList<>();

        @Override
        public void deliver(String formattedReport) {
            stored.add(Objects.requireNonNull(
                    formattedReport, "formattedReport"));
        }

        List<String> readAll() {
            return List.copyOf(stored);
        }
    }

    // Quy trình chung chỉ biết các vai trò, không biết lớp cụ thể.
    static final class ReportPublisher {
        private final Formatter formatter;
        private final Destination destination;

        ReportPublisher(Formatter formatter, Destination destination) {
            this.formatter = Objects.requireNonNull(
                    formatter, "formatter");
            this.destination = Objects.requireNonNull(
                    destination, "destination");
        }

        void publish(ReportData report) {
            Objects.requireNonNull(report, "report");
            String rendered = Objects.requireNonNull(
                    formatter.format(report), "rendered");
            destination.deliver(rendered);
        }
    }

    public static void main(String[] args) {
        // Kế thừa: dùng một lớp con thay cho lớp cha trừu tượng.
        AbstractReport inherited = new SalesReport(
                "Doanh thu tháng", new BigDecimal("1500000"));

        System.out.println("KẾ THỪA:");
        System.out.println(inherited.render());

        // Kết hợp: lắp Formatter và Destination khác nhau.
        ReportData report = new ReportData(
                "Doanh thu tháng",
                "Tổng doanh thu: 1500000 VND");

        ReportPublisher consolePublisher = new ReportPublisher(
                new MarkdownFormatter(), new ConsoleDestination());

        System.out.println("KẾT HỢP:");
        consolePublisher.publish(report);

        MemoryArchive archive = new MemoryArchive();
        ReportPublisher archivePublisher = new ReportPublisher(
                new PlainTextFormatter(), archive);

        archivePublisher.publish(report);
        System.out.println("Đã lưu: " + archive.readAll().size()
                + " báo cáo");
        System.out.println("Nội dung lưu:");
        System.out.println(archive.readAll().get(0));
    }
}
~~~

Run:

~~~bash
javac ReuseComparisonDemo.java
java ReuseComparisonDemo
~~~

Output:

~~~text
KẾ THỪA:
Doanh thu tháng
Tổng doanh thu: 1500000 VND
KẾT HỢP:
# Doanh thu tháng

Tổng doanh thu: 1500000 VND
Đã lưu: 1 báo cáo
Nội dung lưu:
Doanh thu tháng
Tổng doanh thu: 1500000 VND
~~~

In this example, `MemoryArchive` **stores data only in RAM**, not durably. `ConsoleDestination` only prints to the console; it does not send data over a network or create files. These implementations clarify **which code is reused** without adding unrelated dependencies.

### Exactly Where Is Code Reused?

**Inheritance approach:**

~~~java
AbstractReport report = new SalesReport(...);
String output = report.render();
~~~

`SalesReport` **inherits** the `render()` implementation from `AbstractReport`. It only overrides `buildBody()`, and the call from `render()` dispatches to the actual subclass implementation.

**Composition approach:**

~~~java
ReportPublisher publisher =
        new ReportPublisher(new MarkdownFormatter(),
                            new ConsoleDestination());
publisher.publish(reportData);
~~~

`ReportPublisher` **does not inherit from** `MarkdownFormatter` or `ConsoleDestination`. It holds **references** to collaborating objects. The code in `publish()` is reused for any formatter/destination pair satisfying the two interfaces.

Switch the use case without changing `ReportPublisher`:

~~~java
new ReportPublisher(
        new PlainTextFormatter(), new ConsoleDestination());

new ReportPublisher(
        new MarkdownFormatter(), new MemoryArchive());
~~~

`ReportPublisher` executes the same "format, then deliver" algorithm while the components responsible for details can be replaced independently.

## 4. UML Diagrams: Making Relationship Types Clear

### Inheritance: Relationships Between Types

~~~mermaid
classDiagram
    class AbstractReport {
        <<abstract>>
        -title String
        +render() String
        #buildBody() String
    }
    class SalesReport {
        -revenue BigDecimal
        #buildBody() String
    }
    AbstractReport <|-- SalesReport
~~~

A hollow triangle pointing toward the superclass represents **`extends`**. The subclass becomes a subtype; `AbstractReport report = new SalesReport(...)` is a valid assignment.

### Composition: Relationships with Collaborating Objects

~~~mermaid
classDiagram
    class ReportPublisher {
        -formatter Formatter
        -destination Destination
        +publish(ReportData) void
    }
    class Formatter {
        <<interface>>
        +format(ReportData) String
    }
    class Destination {
        <<interface>>
        +deliver(String) void
    }
    class PlainTextFormatter
    class MarkdownFormatter
    class ConsoleDestination
    class MemoryArchive
    ReportPublisher --> Formatter : uses
    ReportPublisher --> Destination : uses
    Formatter <|.. PlainTextFormatter
    Formatter <|.. MarkdownFormatter
    Destination <|.. ConsoleDestination
    Destination <|.. MemoryArchive
~~~

`ReportPublisher` is not a subtype of `Formatter` or `Destination`. Because these objects are **supplied externally** and may be shared, the diagram uses reference/dependency relationships and **does not assume** their entire lifecycles belong to `ReportPublisher`.

If `ReportPublisher` actually creates and owns a dedicated component and manages its lifecycle according to *whole–part* rules, stronger UML composition may be appropriate. A class having a reference field **is not enough** to establish that lifecycle relationship.

## 5. Key Difference: Reusing Implementations or Assembling Behavior

**Inheritance for implementation reuse** is valuable when object types genuinely share a nature and a stable implementation.

In the example, every `AbstractReport` has a title and `render()` behavior. If shared validation must be added to `render()`, the superclass can change once for all subclasses.

But the coupling is also deeper:

- Subclasses must follow the superclass's structure and contract.
- Changes to the superclass's protected API or internal assumptions may affect subclasses.
- Java does not allow a class to `extends` multiple classes directly, so separate functionality cannot be inherited independently from multiple superclasses.
- A subclass overriding a hook may violate invariants or preconditions/postconditions expected by the superclass.

**Composition for behavior reuse** is suitable when capabilities can vary independently.

For example, formatting and storage **are not the same kind of thing** and vary along two distinct dimensions:

| | ConsoleDestination | MemoryArchive |
| --- | --- | --- |
| PlainTextFormatter | Plain text to console | Plain text to archive |
| MarkdownFormatter | Markdown to console | Markdown to archive |

We need only **two formatters, two destinations, and one publisher** for four combinations. If every concrete subclass combines a format and destination, the number of classes can grow rapidly as options are added.

However, **composition does not always use fewer classes**. It may introduce interfaces, adapters, and delegated calls. Its benefit is separating **independent dimensions of change** instead of tying them to a rigid inheritance hierarchy.

## 6. Is "Composition over Inheritance" Always Right?

The advice "**favor composition over inheritance**" is a **design guideline**, not a ban on `extends`.

Consider **inheritance** when:

- There is a genuine *is-a* relationship: `SalesReport` is an `AbstractReport`.
- The superclass provides a consistent contract with well-defined extension points.
- Shared behavior/state is **stable** and can be specialized without violating the contract.
- A subclass object can **substitute for** a superclass object in every relevant situation without surprising behavior.

Consider **composition** when:

- Capabilities must cooperate but are not kinds of one another.
- Several independent dimensions vary: formatting, data source, output destination, retry policy.
- Components need to be replaceable, easily tested with fakes, or injected.
- Subclasses should not depend on too many protected/internal superclass details.
- The requirement is merely to **use another object's functionality**, without a meaningful is-a relationship.

A useful self-check question:

> **"If we removed every duplicated line of code, would A still truly be a kind of B?"**

If the answer is no and the goal is simply to reuse a few methods, **composition/delegation** is usually a better fit than inheritance.

## 7. Is-a Relationships and the Liskov Substitution Principle

A subclass must do more than syntactically "look like" its superclass. It must honor the promises on which superclass clients depend.

Example of a problematic design:

~~~java
class Bird {
    void fly() {
        System.out.println("Bay");
    }
}

class Penguin extends Bird {
    @Override
    void fly() {
        throw new UnsupportedOperationException("Không biết bay");
    }
}
~~~

A function accepting `Bird` and expecting `fly()` to work fails when given a `Penguin`. The category "a penguin is a bird" is valid, but **this Bird class contract is wrong for flightless birds**.

A better design:

~~~java
interface Flyable {
    void fly();
}

abstract class Bird {
    abstract void move();
}

class Sparrow extends Bird implements Flyable {
    @Override
    void move() {
        System.out.println("Chim sẻ di chuyển");
    }

    @Override
    public void fly() {
        System.out.println("Chim sẻ bay");
    }
}

class Penguin extends Bird {
    @Override
    void move() {
        System.out.println("Chim cánh cụt đi hoặc bơi");
    }
}
~~~

Separating **shared identity** from **optional capabilities** avoids turning a method into a runtime error in a subtype. This reflects the **Liskov Substitution Principle (LSP)**: code that uses a superclass should not have valid expectations broken by a subclass.

LSP also matters in composition: a replacement `Destination` must honor the `deliver(...)` contract expected by clients, such as not arbitrarily changing reports or claiming success prematurely if the contract forbids it.

## 8. Changing Behavior at Runtime with Composition

The original example uses **constructor injection**: `ReportPublisher` receives dependencies from outside:

~~~java
ReportPublisher publisher =
        new ReportPublisher(formatter, destination);
~~~

Creating different instances lets us select configurations at runtime:

~~~java
Formatter formatter =
        useMarkdown ? new MarkdownFormatter() : new PlainTextFormatter();

Destination destination =
        keepArchive ? new MemoryArchive() : new ConsoleDestination();

ReportPublisher publisher =
        new ReportPublisher(formatter, destination);
~~~

Here, `useMarkdown` and `keepArchive` are configuration choices. The **`ReportPublisher.publish` algorithm remains unchanged**.

Another option is a setter that replaces the strategy on an existing publisher, but concurrency, lifecycle, and invariant concerns must be considered. Here, `final` fields and constructor injection give each `ReportPublisher` a clearly defined set of dependencies **whose references cannot be replaced after construction**.

**Important:** `final Formatter formatter` prevents only field reassignment; it does not guarantee that the formatter object is immutable or thread-safe. If components hold mutable state and are shared across threads, appropriate synchronization/execution design is required.

### Composition and Dependency Inversion

`ReportPublisher` depends on the **`Formatter` and `Destination` abstractions** rather than directly on `MarkdownFormatter` or `MemoryArchive`. This applies Dependency Inversion: higher-level logic is not tied to a specific implementation.

However, **composition does not require interfaces**. If a component has only one use and does not need substitution, a concrete class field may be reasonable. Avoid creating many interfaces before they solve a clear requirement.

## 9. Reuse Through Composition, Strategy, and Decorator

Two patterns commonly used with object composition:

### Strategy: Switching Algorithms

The `Formatter` interface above defines a **strategy contract**. `PlainTextFormatter` and `MarkdownFormatter` are different formatting algorithms. `ReportPublisher` can use either compatible implementation.

~~~java
Formatter formatter = new MarkdownFormatter();
String content = formatter.format(reportData);
~~~

### Decorator: Wrapping Additional Behavior

Suppose every destination must log before delivery. Instead of subclassing each destination, we can **wrap** one:

~~~java
class LoggingDestination implements Destination {
    private final Destination target;

    LoggingDestination(Destination target) {
        this.target = java.util.Objects.requireNonNull(target);
    }

    @Override
    public void deliver(String formattedReport) {
        System.out.println("[LOG] Đang xuất báo cáo");
        target.deliver(formattedReport);
    }
}
~~~

~~~java
Destination wrapped =
        new LoggingDestination(new ConsoleDestination());

new ReportPublisher(new MarkdownFormatter(), wrapped).publish(reportData);
~~~

`LoggingDestination` **implements the same interface** but reuses behavior by **delegating** to `target`. It can wrap another destination without subclasses such as `LoggedConsoleDestination`, `LoggedMemoryArchive`, and so on.

**Note:** The logging wrapper runs before `deliver`, but this does not prove delivery succeeded. For real audit requirements, define logging timing, failures, and record-keeping obligations explicitly.

## 10. Testing Reuse Through Composition

One strength of composition is **the ability to replace a dependency with a fake**. We can test `ReportPublisher` in isolation without writing files or calling external systems.

JUnit 5 example (requires the JUnit Jupiter dependency; the main demo does not require JUnit):

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class ReportPublisherTest {

    @Test
    void publisherFormatsBeforeDelivering() {
        final String[] delivered = new String[1];

        ReuseComparisonDemo.Formatter formatter =
                report -> "[" + report.getTitle() + "]";

        ReuseComparisonDemo.Destination fakeDestination =
                text -> delivered[0] = text;

        ReuseComparisonDemo.ReportPublisher publisher =
                new ReuseComparisonDemo.ReportPublisher(
                        formatter, fakeDestination);

        publisher.publish(new ReuseComparisonDemo.ReportData(
                "Doanh thu", "Nội dung"));

        assertEquals("[Doanh thu]", delivered[0]);
    }

    @Test
    void archiveDoesNotExposeMutableList() {
        ReuseComparisonDemo.MemoryArchive archive =
                new ReuseComparisonDemo.MemoryArchive();
        archive.deliver("Một báo cáo");

        assertThrows(UnsupportedOperationException.class,
                () -> archive.readAll().clear());

        assertEquals(1, archive.readAll().size());
    }
}
~~~

`Formatter` and `Destination` are both **functional interfaces** (one abstract method each), so lambdas can act as fakes. This is an advantage of depending on abstractions.

Subclasses can certainly be tested when using inheritance, but tests may depend on inherited workflows or protected hooks. If the superclass holds complex state, setting up fixtures and verifying side effects can be harder than assembling small independent components.

## 11. Lifecycles, State, and Exceptions

Code reuse **does not automatically guarantee** correct state updates or error handling.

### Mutable Components Can Be Shared

~~~java
MemoryArchive shared = new MemoryArchive();

ReportPublisher a = new ReportPublisher(
        new MarkdownFormatter(), shared);

ReportPublisher b = new ReportPublisher(
        new PlainTextFormatter(), shared);
~~~

Both publishers **reference the same `MemoryArchive`**. When each calls `publish`, both reports go into **the same `stored` list** in the archive. To maintain separate archives, supply two distinct `MemoryArchive` instances.

### Exceptions Do Not Roll Back Changes Automatically

In `ReportPublisher.publish`, the formatter runs before the destination:

~~~java
String text = formatter.format(report);
destination.deliver(text);
~~~

If the formatter throws, the destination is not called. If the destination writes partially and then throws, composition does not automatically roll back the write. Files, databases, queues, and networks require appropriate transaction, retry, and idempotency rules.

### Thread Safety Does Not Come from `final` or `private`

`MemoryArchive` uses `ArrayList`, which is **not thread-safe** when concurrently updated by multiple threads. `ReportPublisher` holds two `final` fields, but that does not make the referenced mutable components thread-safe. Multithreaded systems need synchronization or an appropriate data structure/architecture.

These issues can arise with either inheritance or composition; do not confuse a code-reuse decision with guarantees about lifecycles, data, or concurrency.

## 12. When Inheritance Is Better Than Many Delegation Layers

Using composition "everywhere, all the time" can produce an overly complex system: operations pass through several meaningless wrappers, every contract has just one implementation, and nothing varies independently.

In the inheritance example, `SalesReport` truly is a report and shares a stable `render()` template with other reports. If the only requirement is **specializing the report body**, with no independently varying formatter/destination, `AbstractReport` may be an excellent abstraction.

Conversely, if tomorrow the system must output **every type of report** as PDF, email, console output, or archived content, embedding output logic in each subclass makes extension harder. Separating `Formatter` and `Destination` makes sense once they become independent dimensions of variation.

You can **combine both approaches**: use `SalesReport extends AbstractReport` to generate content, then pass it to a `ReportPublisher` assembled with a formatter and destination. "Favor composition" does not mean choosing one approach and discarding the other entirely.

## 13. Choosing an Approach in a Project

~~~mermaid
flowchart TD
    A["Muốn tái sử dụng chức năng"] --> B{"Có quan hệ is-a đúng<br/>và hợp đồng cha ổn định?"}
    B -->|Không| C["Ưu tiên kết hợp/delegation"]
    B -->|Có| D{"Subclass chỉ thay vài<br/>điểm mở rộng được thiết kế?"}
    D -->|Có| E["Cân nhắc kế thừa"]
    D -->|Không| F["Tách các chiều thay đổi<br/>thành thành phần"]
    F --> C
    E --> G["Kiểm tra LSP, invariant,<br/>quyền truy cập, coupling"]
    C --> H["Định nghĩa interface khi hữu ích,<br/>inject và test thành phần"]
~~~

Practical questions:

1. **Is-a or has-a?** "A report publisher has a formatter" is more natural than "a report publisher is a formatter."
2. **Which parts have independent reasons to change?** A formatter can vary independently of a destination.
3. **How much must callers know?** `ReportPublisher` only needs `Formatter` and `Destination`.
4. **Are there lifecycle constraints?** Are components privately owned or injected so they can be shared?
5. **Is substitution or faking needed for tests?** Put variable behavior behind an interface when that provides value.
6. **Would this violate the superclass contract?** Must the subclass override a normally valid operation to throw `UnsupportedOperationException`?
7. **Is the structural overhead justified?** A simple class need not become ten interfaces without a real need.

## 14. Common Mistakes

| Mistake | Symptom | Remedy |
| --- | --- | --- |
| Inheriting just to reuse a few methods | `Car extends Engine` | Make `Engine` a component and delegate |
| A subclass violates its superclass promises | Overrides an operation to throw "unsupported" | Reconsider is-a; move optional capabilities into interfaces |
| Making subclasses for every option pair | `CsvEmail`, `CsvFile`, `PdfEmail`, etc. | Separate `Formatter` and `Destination` |
| Composition with overly rigid dependencies | `new EmailClient()` buried inside `ReportPublisher` | Consider role-based constructor injection |
| Wrapping every class in unnecessary interfaces | Many wrappers with no added behavior or substitution | Keep the design appropriately simple |
| Confusing a field with UML lifecycle ownership | Drawing filled diamonds for injected dependencies | Distinguish association/aggregation from strict composition |
| Replacing a component while assuming isolated state | Two publishers share one archive | Define whether an instance is shared or privately owned |
| Assuming composition guarantees atomicity/thread safety | A mutable list is updated concurrently | Design transactions/synchronization separately |
| Confusing type contracts with business contracts | Two strategies share an interface but one returns incorrect results | Write contract tests and valid postconditions |

## 15. Self-Check Exercises

**Question 1.** Does `class PaymentService extends EmailClient` make sense merely to call `sendMail()`?

**Answer:** Usually not. `PaymentService` **uses** email-sending functionality; it **is not a kind of EmailClient**. It should receive a suitable dependency through its constructor or another composition approach.

**Question 2.** A `ReportPublisher` currently uses `MarkdownFormatter`. How can it switch to `PlainTextFormatter` without changing `publish`?

**Answer:** Create/configure `ReportPublisher` with `new PlainTextFormatter()` through the constructor. `publish` still calls `formatter.format(report)` through the interface.

**Question 3.** What is the benefit of `SalesReport extends AbstractReport`?

**Answer:** `SalesReport` reuses the superclass's title validation and `render()` template; it only provides `buildBody()`. This is appropriate if the report subtype relationship and superclass contract are meaningful.

**Question 4.** If two publishers receive the same `MemoryArchive`, how many archives are created?

**Answer:** One `MemoryArchive` is created by the corresponding `new` operation and shared through two reference fields; composition does not clone objects automatically. Each publisher is a separate object, but both share the archive.

**Question 5.** Why avoid creating `SalesMarkdownConsoleReport` and `SalesPlainTextArchiveReport` for every combination?

**Answer:** Report content, formatting, and destination are independent dimensions of variation. Inheritance for every combination creates many interdependent classes; assembling formatters and destinations enables independent reuse.

**Question 6.** `ReportPublisher` holds a `final Destination destination` field. Does that immediately make `MemoryArchive` thread-safe or immutable?

**Answer:** No. `final` prevents reassignment of the field reference; it does not lock the `Destination` object's internal state. Synchronization, immutability, or concurrency controls must be designed separately when needed.

**Question 7.** Should an interface be used for a single class that never changes?

**Answer:** Not necessarily. Interfaces help define independent contracts, facilitate test fakes, or support implementation substitution. Without these needs, a concrete class can be simpler.

**Question 8.** A subclass inherits utility code but cannot meet its superclass's behavioral expectations. What went wrong?

**Answer:** The *is-a* relationship and substitutability principle may be violated. Reconsider the model; composition with a helper/collaborator is often more appropriate.

## Conclusion

**Inheritance** supports reuse through "is a kind of": a subclass receives common superclass behavior and specializes valid extension points. **Composition** supports reuse through "has or uses": an object coordinates components with separate responsibilities and delegates work to them.

There is no formula requiring composition everywhere or inheritance everywhere. Choose **inheritance when the is-a relationship and superclass contract are sound**, and **composition when capabilities must be assembled or varied independently**. Good Java designs often use both appropriately to avoid forced inheritance hierarchies and keep code testable and extensible.
