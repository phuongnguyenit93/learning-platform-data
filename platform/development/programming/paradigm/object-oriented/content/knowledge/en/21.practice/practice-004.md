# Exercise: Choosing inheritance or composition in Java OOP

## Objectives

Two common ways for object-oriented classes to collaborate and reuse behavior are **inheritance** and **composition**. This exercise asks you to choose based on the actual business relationship and then justify your choice with runnable Java code and tests.

After completing this lesson, you should:
- Distinguish an **is-a** relationship (one type of another) from a **has-a/uses-a** relationship (owning or using a component).
- Understand when a subclass can **substitute for** its parent without breaking its behavioral contract.
- Use interfaces and constructor injection to assemble interchangeable components.
- Recognize inheritance used only for code reuse, oversized class hierarchies, and excessive coupling to a superclass.
- Propose a design, write runnable Java, and test both shared contracts and component interchangeability.

**Key point:** There is no universal rule to "always use composition" or "use extends whenever code is shared". Decide based on responsibilities, public contracts, coupling, and how the system may evolve.

## 1. Understanding the two approaches

Java class inheritance uses the **extends** keyword. A subclass inherits eligible behavior from its superclass and can add or override permitted methods.

Composition means an object **holds a reference to another object** and invokes its methods to do work. That reference can have an interface type, allowing the concrete implementation to change without the consuming class knowing its details.

| Design question | Inheritance | Composition |
| --- | --- | --- |
| Model relationship | A **is a type of B** | A **has/uses a B** |
| Java representation | class A extends B | private final B b; |
| Common purpose | Specialize a stable shared contract | Assemble capabilities or collaborators |
| Changing implementation | Substitute another subclass that follows the superclass contract | Inject a different implementation |
| Coupling | Can tightly couple subclasses to superclass design | Can reduce coupling through a small interface |
| Testing | Apply shared contract tests to every subclass | Replace a collaborator with a fake or stub |
| Risk | Subclass weakens the contract or inherits inappropriate APIs | Excessive delegation classes or needless abstractions |

**An interface is not composition.** When a class implements ReportFormatter, it declares that its objects satisfy the ReportFormatter contract. Composition appears when ReportPublisher **contains** a ReportFormatter field and **delegates** formatting to it. The two techniques often work together.

## 2. Classification exercise before the answers

For each scenario, choose **K (inheritance), H (composition)**, or **C (needs clarification)** and explain why. Try answering before reading the solution.

| Scenario | Question to explain |
| --- | --- |
| A. Circle and Rectangle are both Shapes, but have different area() formulas | Can every subclass satisfy a shared Shape contract? |
| B. ReportPublisher exports data as CSV, text, or JSON | Is ReportPublisher actually a type of CSV formatter? |
| C. Car has an Engine and may use different engine types | Is a car a kind of engine? |
| D. SavingsAccount extends BankAccount but prohibits most withdrawals that its parent permits | Can the subclass still substitute for the parent? |
| E. AlertService must send through EmailSender or SmsSender | Can delivery behavior be configured independently of alert rules? |
| F. A framework offers AbstractTask with a clear execute() contract and hooks designed for extension | What expectations must framework subclasses satisfy? |

The code exercise combines cases A and B into a runnable project. The remaining cases are examined in the solutions and extensions.

### Decision diagram

~~~mermaid
flowchart TD
    A["Bạn muốn tạo quan hệ giữa A và B"] --> B{"A thực sự là một loại B?"}
    B -->|Không| C["Ưu tiên kết hợp / ủy quyền"]
    B -->|Có| D{"A thay được B theo hợp đồng?"}
    D -->|Không| E["Thiết kế lại hợp đồng hoặc tách vai trò"]
    D -->|Có| F{"Hợp đồng ổn định và cần chuyên biệt hóa?"}
    F -->|Có| G["Có thể dùng kế thừa"]
    F -->|Không| H["Xem xét interface + kết hợp"]
    C --> I["Kiểm tra trách nhiệm và coupling"]
    G --> I
    H --> I
    E --> I
~~~

These are guiding questions, not an algorithm with absolute answers. Even for an is-a relationship, an interface with independent implementations may be simpler than an abstract class with substantial state.

## 3. Exercise A — Model shapes with inheritance

**Requirements:** Define a Shape type with an area-calculation contract; Circle and Rectangle are concrete Shape types. The program should calculate areas for a list of Shapes without class-specific if/else branches.

Choose an **abstract class Shape** because all shapes share an area() contract and display name and are used as Shapes. Both subclasses must return nonnegative areas for validated dimensions.

~~~mermaid
classDiagram
    class Shape {
        <<abstract>>
        -String name
        +name() String
        +area() double*
    }
    class Circle {
        -double radius
        +area() double
    }
    class Rectangle {
        -double width
        -double height
        +area() double
    }
    Shape <|-- Circle
    Shape <|-- Rectangle
~~~

### 3.1. Shape.java

~~~java
package vn.example;

public abstract class Shape {
    private final String name;

    protected Shape(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        this.name = name;
    }

    public final String name() {
        return name;
    }

    /** Diện tích theo đơn vị bình phương; lớp con phải hiện thực. */
    public abstract double area();
}
~~~

Shape establishes shared state (name), requires a nonblank name, and defines the area() operation. If the classes need no shared state or implementation, an interface Shape with area() would also be valid.

### 3.2. Circle.java

~~~java
package vn.example;

public final class Circle extends Shape {
    private final double radius;

    public Circle(double radius) {
        super("Circle");
        requirePositiveFinite(radius, "radius");
        this.radius = radius;
    }

    @Override
    public double area() {
        return Math.PI * radius * radius;
    }

    private static void requirePositiveFinite(double value, String field) {
        if (!Double.isFinite(value) || value <= 0) {
            throw new IllegalArgumentException(
                    field + " must be finite and positive");
        }
    }
}
~~~

### 3.3. Rectangle.java

~~~java
package vn.example;

public final class Rectangle extends Shape {
    private final double width;
    private final double height;

    public Rectangle(double width, double height) {
        super("Rectangle");
        requirePositiveFinite(width, "width");
        requirePositiveFinite(height, "height");
        this.width = width;
        this.height = height;
    }

    @Override
    public double area() {
        return width * height;
    }

    private static void requirePositiveFinite(double value, String field) {
        if (!Double.isFinite(value) || value <= 0) {
            throw new IllegalArgumentException(
                    field + " must be finite and positive");
        }
    }
}
~~~

**Why is inheritance appropriate here?** A Circle or Rectangle can be used wherever Shape.area() is expected, without making the caller know the underlying formula. Both use area() with the same meaning: geometric area. This demonstrates **polymorphism** and contract-based substitutability.

For very large double values, multiplication may return Infinity even when the input dimensions are finite. This exercise does not guarantee finite areas; if the system requires them, add overflow/precision rules and corresponding tests.

## 4. Exercise B — Export reports through composition

**Requirements:** ReportPublisher receives a sales report, formats it as CSV or text, and stores the result through an output channel. Later it should support JSON formatting and file/database storage without changing orchestration logic.

An **inappropriate** design:

~~~java
// Mã gợi ý về mùi thiết kế; KHÔNG đưa vào dự án chạy bên dưới.
class CsvExporter {
    String toCsv(/* dữ liệu */) { return "..."; }
}

class ReportPublisher extends CsvExporter {
    // Kế thừa chỉ để dùng toCsv().
}
~~~

A report publisher **is not** a kind of CSV exporter. When another format is needed, this inheritance model forces changes to the class relationship or additional conditional branches.

A **better-fitting** design: ReportPublisher has a ReportFormatter and a ReportSink.

~~~mermaid
classDiagram
    class ReportPublisher {
        -ReportFormatter formatter
        -ReportSink sink
        +publish(SalesSummary) void
    }
    class ReportFormatter {
        <<interface>>
        +format(SalesSummary) String
    }
    class CsvFormatter {
        +format(SalesSummary) String
    }
    class TextFormatter {
        +format(SalesSummary) String
    }
    class ReportSink {
        <<interface>>
        +save(String) void
    }
    class SalesSummary {
        +period() String
        +revenueVnd() long
    }
    ReportPublisher --> ReportFormatter : sử dụng
    ReportPublisher --> ReportSink : sử dụng
    ReportPublisher --> SalesSummary : nhận đầu vào
    ReportFormatter <|.. CsvFormatter
    ReportFormatter <|.. TextFormatter
~~~

### 4.1. SalesSummary.java

~~~java
package vn.example;

/** Bản tóm tắt doanh thu cho một tháng, đơn vị tiền nguyên VND. */
public record SalesSummary(String period, long revenueVnd) {
    public SalesSummary {
        // Ví dụ chấp nhận dạng YYYY-MM với tháng từ 01 đến 12.
        if (period == null
                || !period.matches("[0-9]{4}-(0[1-9]|1[0-2])")) {
            throw new IllegalArgumentException("Invalid period");
        }
        if (revenueVnd < 0) {
            throw new IllegalArgumentException(
                    "revenueVnd must not be negative");
        }
    }
}
~~~

SalesSummary is an immutable record that makes input data easy to pass. Its report-period validation belongs in the model class so formatters need not guess whether the input is valid.

### 4.2. ReportFormatter.java

~~~java
package vn.example;

@FunctionalInterface
public interface ReportFormatter {
    String format(SalesSummary summary);
}
~~~

### 4.3. CsvFormatter.java

~~~java
package vn.example;

public final class CsvFormatter implements ReportFormatter {
    @Override
    public String format(SalesSummary summary) {
        return summary.period() + "," + summary.revenueVnd();
    }
}
~~~

The period data contains only digits and hyphens, and revenueVnd contains only digits, so this example does not need comma escaping. A general CSV formatter must correctly handle commas, quotation marks, and line breaks.

### 4.4. TextFormatter.java

~~~java
package vn.example;

public final class TextFormatter implements ReportFormatter {
    @Override
    public String format(SalesSummary summary) {
        return "Thang " + summary.period() + ": "
                + summary.revenueVnd() + " VND";
    }
}
~~~

CsvFormatter and TextFormatter both **implement ReportFormatter** so they are interchangeable. Neither needs to inherit from a concrete formatter.

### 4.5. ReportSink.java

~~~java
package vn.example;

@FunctionalInterface
public interface ReportSink {
    void save(String content);
}
~~~

### 4.6. ReportPublisher.java

~~~java
package vn.example;

import java.util.Objects;

public final class ReportPublisher {
    private final ReportFormatter formatter;
    private final ReportSink sink;

    public ReportPublisher(ReportFormatter formatter, ReportSink sink) {
        this.formatter = Objects.requireNonNull(
                formatter, "formatter");
        this.sink = Objects.requireNonNull(sink, "sink");
    }

    public void publish(SalesSummary summary) {
        Objects.requireNonNull(summary, "summary");
        String content = formatter.format(summary);
        sink.save(content);
    }
}
~~~

ReportPublisher determines the **workflow order**: format first, then store. It does not contain CSV formulas, open files itself, or instantiate a formatter with new. Those capabilities are supplied externally through its constructor.

As a result:
- To add JSON, create JsonFormatter implements ReportFormatter.
- To store in a database, create DatabaseReportSink implements ReportSink.
- To test without writing to a real system, provide a sink that records data in memory.
- ReportPublisher needs no modification for each new format or sink, as long as collaborators satisfy the defined contracts.

## 5. Combining both exercises into a runnable Java program

Project structure:

~~~text
oop-inheritance-or-composition/
├── pom.xml
└── src/
    ├── main/java/vn/example/
    │   ├── Shape.java
    │   ├── Circle.java
    │   ├── Rectangle.java
    │   ├── SalesSummary.java
    │   ├── ReportFormatter.java
    │   ├── CsvFormatter.java
    │   ├── TextFormatter.java
    │   ├── ReportSink.java
    │   ├── ReportPublisher.java
    │   └── Main.java
    └── test/java/vn/example/
        └── DesignChoiceTest.java
~~~

Create pom.xml for Java 17 + JUnit Jupiter:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>oop-inheritance-or-composition</artifactId>
    <version>1.0-SNAPSHOT</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/vn/example/Main.java**

~~~java
package vn.example;

import java.util.List;

public final class Main {
    public static void main(String[] args) {
        // Bài A: cùng kiểu Shape, hai lớp con có cách tính riêng.
        List<Shape> shapes = List.of(
                new Circle(2),
                new Rectangle(3, 4));

        double totalArea = shapes.stream()
                .mapToDouble(Shape::area)
                .sum();

        System.out.println("Tong dien tich = " + totalArea);

        // Bài B: thay formatter và sink bằng cách lắp ghép object.
        SalesSummary report = new SalesSummary("2026-10", 1_500_000);
        ReportSink console = System.out::println;

        ReportPublisher csv = new ReportPublisher(
                new CsvFormatter(), console);
        ReportPublisher text = new ReportPublisher(
                new TextFormatter(), console);

        csv.publish(report);
        text.publish(report);
    }
}
~~~

Running Main adds the areas of Circle and Rectangle through the shared Shape type, then exports the same report in two formats. Business classes do not need to change when the composition root selects another formatter.

Run from the project root:

~~~bash
mvn test
mvn -q -DskipTests package
java -cp target/classes vn.example.Main
~~~

Example output:

~~~text
Tong dien tich = 24.566370614359172
2026-10,1500000
Thang 2026-10: 1500000 VND
~~~

With double values, displayed trailing digits may vary with the calculation environment or formatting choices; tests should compare using an acceptable tolerance.

## 6. Tests that validate design choices

**src/test/java/vn/example/DesignChoiceTest.java**

~~~java
package vn.example;

import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class DesignChoiceTest {

    @Test
    void circleAndRectangleWorkThroughShapeContract() {
        Shape circle = new Circle(2);
        Shape rectangle = new Rectangle(3, 4);

        assertEquals(Math.PI * 4, circle.area(), 1e-9);
        assertEquals(12.0, rectangle.area(), 1e-9);

        List<Shape> mixed = List.of(circle, rectangle);
        double sum = mixed.stream().mapToDouble(Shape::area).sum();

        assertEquals(Math.PI * 4 + 12, sum, 1e-9);
        assertEquals("Circle", circle.name());
        assertEquals("Rectangle", rectangle.name());
    }

    @Test
    void shapeDimensionsMustBePositiveAndFinite() {
        assertThrows(IllegalArgumentException.class,
                () -> new Circle(0));
        assertThrows(IllegalArgumentException.class,
                () -> new Circle(Double.NaN));
        assertThrows(IllegalArgumentException.class,
                () -> new Rectangle(-1, 2));
        assertThrows(IllegalArgumentException.class,
                () -> new Rectangle(2, Double.POSITIVE_INFINITY));
    }

    @Test
    void publisherCanReplaceFormatterWithoutSubclassing() {
        List<String> saved = new ArrayList<>();
        ReportSink sink = saved::add;
        SalesSummary summary = new SalesSummary("2026-10", 1_500_000);

        new ReportPublisher(new CsvFormatter(), sink).publish(summary);
        new ReportPublisher(new TextFormatter(), sink).publish(summary);

        assertEquals(List.of(
                "2026-10,1500000",
                "Thang 2026-10: 1500000 VND"), saved);
    }

    @Test
    void publisherAllowsNewFormatterWithoutChangingItsCode() {
        List<String> saved = new ArrayList<>();
        ReportFormatter custom = summary ->
                "REPORT=" + summary.period();

        ReportPublisher publisher = new ReportPublisher(
                custom, saved::add);

        publisher.publish(new SalesSummary("2026-11", 500));

        assertEquals(List.of("REPORT=2026-11"), saved);
    }

    @Test
    void nullReportDoesNotCallCollaborators() {
        AtomicInteger saves = new AtomicInteger();
        ReportSink sink = ignored -> saves.incrementAndGet();
        ReportPublisher publisher = new ReportPublisher(
                new CsvFormatter(), sink);

        assertThrows(NullPointerException.class,
                () -> publisher.publish(null));
        assertEquals(0, saves.get());
    }

    @Test
    void publisherDoesNotSwallowStorageFailure() {
        ReportSink failing = content -> {
            throw new IllegalStateException("Storage unavailable");
        };

        ReportPublisher publisher = new ReportPublisher(
                new CsvFormatter(), failing);

        assertThrows(IllegalStateException.class,
                () -> publisher.publish(
                        new SalesSummary("2026-10", 10)));
    }

    @Test
    void constructorsValidateTheirContracts() {
        assertThrows(IllegalArgumentException.class,
                () -> new SalesSummary(" ", 20));
        assertThrows(IllegalArgumentException.class,
                () -> new SalesSummary("2026-13", 20));
        assertThrows(IllegalArgumentException.class,
                () -> new SalesSummary("2026-10", -1));

        assertThrows(NullPointerException.class,
                () -> new ReportPublisher(null, text -> {}));
        assertThrows(NullPointerException.class,
                () -> new ReportPublisher(new CsvFormatter(), null));
    }
}
~~~

The test suite above contains **7 @Test methods**. With correctly placed files and JDK 17 + Maven, all tests should pass with 0 failures and 0 errors.

The assertions verify two aspects:

| Test | OOP decision being protected |
| --- | --- |
| circleAndRectangleWorkThroughShapeContract | Subclasses can substitute for Shape and honor the shared meaning of area() |
| shapeDimensionsMustBePositiveAndFinite | Each subclass protects its own invariants |
| publisherCanReplaceFormatterWithoutSubclassing | ReportPublisher uses different implementations of one interface |
| publisherAllowsNewFormatterWithoutChangingItsCode | A new formatter does not require changes to the orchestrator |
| nullReportDoesNotCallCollaborators | Invalid input does not trigger collaborator calls |
| publisherDoesNotSwallowStorageFailure | Collaborator failures are not suppressed |
| constructorsValidateTheirContracts | Objects start in valid states |

Tests show that a subclass meets selected contract cases; a few passing tests cannot prove every subclass is interchangeable in every situation. Large hierarchies need shared contract tests across subclasses and clearly specified preconditions/postconditions.

## 7. Solutions to the opening scenarios

| Scenario | Suggested choice | Reasoning |
| --- | --- | --- |
| A. Circle / Rectangle / Shape | **K** (or shared interface) | Both truly are Shapes and fulfill the shared area contract |
| B. ReportPublisher and formatters | **H** | The publisher uses formatting capability; it is not a formatter |
| C. Car and Engine | **H** | A Car has an engine; changing engine types does not make the car an engine subclass |
| D. SavingsAccount restricts withdrawals against BankAccount's contract | **C: reconsider the model** | The subclass may violate Liskov substitution; revise the contract or extract a policy |
| E. AlertService sends email/SMS | **H** | Separate alert rules from delivery channels; inject a MessageSender interface |
| F. AbstractTask and tasks honoring framework hooks | **K when the contract is clear** | The abstract base class is designed for constrained subclass specialization |

### Case D: do not overuse "is-a"

A real-world SavingsAccount may be called a type of bank account, but the name **does not suffice** to justify inheritance in code. If BankAccount promises to withdraw any valid amount within the remaining balance, but SavingsAccount always throws UnsupportedOperationException, callers relying on the superclass contract may break.

Possible design directions:
- Narrow the common contract to an Account that guarantees only behaviors every account type genuinely supports.
- Use capability interfaces such as Withdrawable when callers need to know whether an account supports withdrawals.
- Compose a WithdrawPolicy **inside** the account when the difference is a changeable rule that should not weaken the common contract.
- For an existing hierarchy, review overridden methods for strengthened preconditions or weakened postconditions compared with the superclass.

The best option depends on business requirements. Adding more subclasses is not an automatic solution.

## 8. Common design pitfalls

### Inheriting only to save a few lines

Suppose an invoice sender extends HttpClient only to call post(). The business relationship is incorrect, and the sender also exposes the technical API of HttpClient. Composing an HttpTransport interface better expresses the dependency.

### Too many subclass combinations

If a system has 3 report types, 4 formats, and 2 storage methods, one subclass per combination could yield 3 × 4 × 2 = **24 classes** just to combine features. When these dimensions are genuinely independent, composing ReportType, ReportFormatter, and ReportSink avoids combinatorial inheritance.

### Inheritance that breaks superclass invariants

In a Rectangle model with independent width and height setters, Square extends Rectangle may need to change both dimensions when one setter is invoked. If callers expect setWidth not to change height, Square no longer fulfills the MutableRectangle contract. Prefer immutable modeling or a common Shape contract without conflicting setters.

### Composition with too many abstractions

A straightforward total calculation may only need a method in the data-owning class. Extracting an interface, factory, and delegate merely to perform simple addition is unnecessary. Composition helps when responsibilities are independent, interchangeability is valuable, or external-system boundaries exist.

### Confusing polymorphism with class inheritance

In Java, polymorphism can work through an **abstract class** or an **interface**. ReportFormatter is an interface with multiple implementations; composition arises because ReportPublisher holds ReportFormatter in a field. You do not need to extend a concrete formatter to achieve polymorphism.

## 9. Advanced exercises

### Exercise 1 — Change formats without altering orchestration

Implement JsonFormatter implements ReportFormatter to produce:

~~~json
{"period":"2026-10","revenueVnd":1500000}
~~~

With period restricted to YYYY-MM and a nonnegative long amount, this example can construct fairly simple JSON. In real systems, use a JSON library for escaping and validation. Add a test for the JSON text and ensure ReportPublisher remains unchanged.

### Exercise 2 — Add another sink

Implement InMemoryReportSink to store received Strings in a list. Inject it into ReportPublisher and check two consecutive reports. Explain why the sink is an interchangeable collaborator, not the publisher's superclass.

### Exercise 3 — Detect contract violations

Design MutableRectangle with setWidth and setHeight, assuming the dimensions change independently. Try Square extends MutableRectangle and write a test against a MutableRectangle reference. Identify which expectation fails and propose a better model.

### Exercise 4 — Compose policies

An application calculates shipping charges using Standard, Express, and International methods. Decide whether to:
- Make Shipment a base class with three subclasses; or
- Give Shipment a ShippingPolicy selected through the constructor.

State at least two business requirements that support your choice. For example, if a parcel can change shipping method during processing, the policy is independently replaceable; if these are distinct object types with entirely different lifecycles and invariants, reconsider the class boundaries.

### Exercise 5 — Assess your choice

For each option you selected, briefly explain:
1. Is the precise relationship between the objects is-a or has-a?
2. Can A be used where B is expected without violating the contract?
3. Which classes would a new requirement force you to change?
4. How would you test a different implementation?
5. What becomes more complicated with your chosen approach?

## 10. Completion criteria

- [ ] Classify 6 scenarios and justify each decision.
- [ ] Write a Java program demonstrating semantically **correct inheritance** and responsibility-aligned **composition**.
- [ ] Run a program with two different Shapes without branching on concrete types.
- [ ] Replace CsvFormatter with TextFormatter or a new formatter without modifying ReportPublisher.
- [ ] Explain extends, implements, and holding references to collaborators.
- [ ] Test contracts, invalid input, and component interchangeability.
- [ ] Recognize when Liskov Substitution Principle is violated by a subclass that restricts superclass behavior.
- [ ] Avoid choosing inheritance solely to reuse one method.

**Expected result:** You can explain why Shape specializes into Circle/Rectangle while ReportPublisher uses ReportFormatter/ReportSink as independent components. Choosing the right relationship makes code reflect business requirements, clarifies contracts, and reduces future change costs.
