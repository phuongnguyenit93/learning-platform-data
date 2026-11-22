# Combining Objects Using Composition and Dividing Responsibilities in Java

**Composition** (combining objects, often called *object composition*) is a way of building the behavior of a large object from **smaller collaborating objects**. Instead of placing all processing in a giant class or overusing `extends`, we assign each object a clear role and **coordinate** them through fields, constructors, methods, and interfaces.

The idea in brief:

- An `Order` **has** `OrderLine` objects and asks them to calculate the subtotal.
- A `ReportService` **uses** a `Formatter` to format and a `Destination` to send the result.
- A `Car` **has** an engine; an engine is a component, **not** a type of car.
- A `CheckoutService` **depends on** `PaymentGateway` through an interface, instead of having to inherit from a payment gateway class to change how processing works.

Composition is especially useful when you want to divide responsibilities according to the principles of **high cohesion** (each class focuses on closely related tasks) and **low coupling** (knowing little about other classes' implementation details), protect invariants, and change algorithms by **replacing collaborating objects** without needing to change the inheritance structure.

> In Java, **there is no `composition` keyword**. It is a design choice and a relationship between objects. An object-typed field is a common way to represent it, but **having a field alone is not enough to prove an ownership/lifecycle model in the UML sense**; you need to consider who creates, who controls, and who is allowed to use that object.

This Knowledge README is written for **Java 17+**, progressing from concepts, distinguishing `has-a` from `is-a`, responsibilities, inter-object communication, ownership and lifecycle, defensive copies, delegation, dependency injection, interfaces, testability, concurrency, and Java records to common anti-patterns. Examples that include `main` all have a defined file, run command, and stdout.

## 1. What Does Composition Mean?

Consider the problem of an invoice generation service. We have at least three responsibilities:

1. **Representing invoice data:** invoice number, product lines, quantities.
2. **Calculating monetary amounts:** summing subtotals, checking for overflow/valid values.
3. **Outputting the result:** converting information into text, writing to storage, or sending to the user.

A single class doing everything easily becomes a *God Object*: reading input, storing state, calculating amounts, formatting, and communicating externally. Composition allows coordinating more specialized objects:

~~~text
InvoiceService
    |
    +-- has/uses --> Invoice
    |                 |
    |                 +-- contains --> InvoiceLine (many)
    |
    +-- uses -------> InvoiceFormatter
    |
    +-- uses -------> InvoicePublisher
~~~

Here, the object on the left **collaborates** with the object on the right. It does not necessarily have to **inherit from** the class on the right.

Java can represent the structure as follows:

~~~java
class InvoiceService {
    private final InvoiceFormatter formatter;
    private final InvoicePublisher publisher;

    InvoiceService(InvoiceFormatter formatter,
                   InvoicePublisher publisher) {
        this.formatter = formatter;
        this.publisher = publisher;
    }

    void publish(Invoice invoice) {
        String text = formatter.format(invoice);
        publisher.send(text);
    }
}
~~~

This is an **illustrative snippet**, assuming the types `Invoice`, `InvoiceFormatter`, and `InvoicePublisher` exist; it is not yet a standalone program. It shows **delegation**: `InvoiceService` coordinates, but delegates formatting to `formatter` and delegates sending to `publisher`. The two dependencies can be provided through the constructor.

### 1.1. The Emphasis Is Collaboration, Not “Class Containing Class”

Composition does not require an object to be a nested class, does not require inheritance, and does not require placing every object in the same `.java` file. Components can be:

- A concrete object stored directly in a `private final` field.
- An object injected via an interface.
- A collection of components held in a `List<Component>`.
- An immutable record or value object.
- A service assembled at a **composition root**, such as `main` or application configuration.

What matters most is **who is responsible for which invariant** and **how clear the call flow between objects is**.

## 2. Comparing Composition and Inheritance

The two models answer two different questions:

- **Inheritance:** `Child extends Parent` expresses an **“is-a”** relationship when Child is genuinely a form of Parent by contract and can substitute for Parent appropriately.
- **Composition:** `Engine engine` in `Car` expresses a **“has-a”** or **“uses-a”** relationship; Car is not an Engine, rather Car uses Engine to get the work done.

Example:

~~~java
// is-a relationship (when the contract holds):
abstract class Shape {
    abstract double area();
}

final class Circle extends Shape {
    private final double radius;

    Circle(double radius) {
        this.radius = radius;
    }

    @Override
    double area() {
        return Math.PI * radius * radius;
    }
}
~~~

~~~java
// has-a / collaboration relationship:
class Car {
    private final Engine engine;

    Car(Engine engine) {
        this.engine = engine;
    }

    void start() {
        engine.start();
    }
}

interface Engine {
    void start();
}
~~~

Both snippets are **illustrative declaration code**; validation parameters and business rules are simplified to focus on the relationship.

| Criterion | Inheritance | Composition |
| --- | --- | --- |
| Common syntax | `extends` | Fields, constructor arguments, interface references |
| Meaning | “Is a kind of” | “Has/uses/collaborates with” |
| Reuse | Inherits behavior/state per Java rules | Delegates behavior to collaborator |
| Changing behavior | Override/hook in subclass | Swap collaborator object or strategy |
| Coupling | Easily depends on superclass details | Can depend on a small interface |
| Has runtime polymorphism? | Yes, via overriding | Yes, when the collaborator is an interface implementation |
| Object lifecycle | Does not by itself create multiple component instances | Requires designing who creates/holds/shares components |

**It is not true that “composition is always better than inheritance”.** Inheritance is appropriate when there is a genuine is-a relationship, a clearly designed extension contract, and a need for hierarchy polymorphism. Composition is usually more flexible for combining **independent capabilities**, though too many pointless delegation layers also make a design cumbersome.

### 2.1. Why Is `Car extends Engine` Usually Wrong?

If you write `class Car extends Engine` just to use `start()`, you are asserting that a car *is an engine*. Engine's public/protected APIs can become part of Car's API, whereas the domain wants Car to **have** an engine. This makes the type relationship and contract hard to understand.

With composition:

~~~java
interface Engine {
    void start();
}

class Car {
    private final Engine engine;

    Car(Engine engine) {
        this.engine = java.util.Objects.requireNonNull(engine);
    }

    void start() {
        engine.start();
    }
}
~~~

Car controls the **publicly exposed behavior** and is not forced to expose every method of Engine. Replacing a simulated engine with another Engine implementation may not affect Car's API.

## 3. Composition, Association, Aggregation, and Dependency Are Not Completely Synonymous

At the Java source level, many relationships use the same kind of field:

~~~java
private final Customer customer;
private final List<OrderLine> lines;
private final PaymentGateway gateway;
~~~

However, when modeling, we need to distinguish **ownership semantics**, not just syntax.

| Conceptual Relationship | How It Is Understood | Example | Does Java Enforce It Automatically? |
| --- | --- | --- | --- |
| Association | Object A relates to or knows B | `Order` references `Customer` | No dedicated keyword |
| Aggregation | A groups Bs; B can exist independently and be shared | `Department` relates to `Employee` objects | Does not automatically manage lifecycle |
| UML Composition (strong ownership) | Whole owns parts in the model; a part does not belong to multiple wholes simultaneously; lifecycle is tied to whole | `Order` owns `OrderLine` objects | Not automatically enforced merely by a field |
| Dependency / uses-a | A temporarily uses B to perform an operation | Method accepts a `Formatter` parameter | Does not imply ownership |
| Inheritance / is-a | Subtype of a type | `Circle extends Shape` | Java has `extends`/`implements` |

**Important note:** in programming literature, “composition” is sometimes used broadly to mean **combining objects using fields/delegation**, even when an object is shared among multiple owners. In UML, **composition** usually carries the meaning of **strong ownership and a coupled lifecycle**. You should state your intent clearly when designing and avoid inferring full UML semantics solely from the code `private final Engine engine`.

### 3.1. Java Does Not Have “Composition-Based Destructors” Like Some Other Languages

A Java object becomes eligible for garbage collection when it is no longer reachable according to GC rules; **the whole becoming unreferenced does not cause Java to automatically invoke a destructor for each part**. A part still referenced elsewhere can remain alive.

If a part holds resources such as a file, socket, or database connection, an **explicit resource-closing** policy (`AutoCloseable`, `try-with-resources`, lifecycle manager) is needed, rather than relying on Java GC to “destroy the child when the parent dies”.

### 3.2. Ownership Must Be Protected by the API

If an `OrderLine` is only allowed to belong to one `Order` in terms of the domain, merely having a `List<OrderLine> lines` field does not stop callers from using the **same OrderLine object** in two orders. You can choose to:

- Create `OrderLine` inside `Order.addItem(...)`.
- Use an immutable line value and copy it when accepted.
- Do not expose the internal mutable list.
- If transferring a part between wholes is needed, provide an explicit API and keep invariants consistent.

A `final` reference prevents reassigning the field, **but does not lock ownership** of the object the field points to.

## 4. Dividing Responsibilities: Who Should Know and Do What?

A composition is useful when each collaborator has a **relatively clear reason to change**. Sales example:

- `Product`: SKU, name, and unit price of a product, or a **price snapshot at selection time** if designed that way.
- `OrderLine`: the product/unit price used and quantity; calculates the amount for one line.
- `Order`: owns the list of order lines, checks add/remove conditions, and calculates the total.
- `PaymentGateway`: communicates with a specific payment system.
- `CheckoutService`: orchestrates the checkout use case, without directly implementing all algorithms itself.
- `ReceiptFormatter`: transforms normalized data into a receipt representation.

You do not always need **six classes**. If the problem is small, splitting too much can create **indirection** with no value. A quality division is one where each abstraction clarifies an invariant or a real axis of variation.

### 4.1. “Information Expert”: Assign Work to the Object Holding the Necessary Data

If `OrderLine` holds `unitPriceCents` and `quantity`, then it itself has enough data to calculate:

~~~java
long subtotalCents() {
    return Math.multiplyExact(unitPriceCents, quantity);
}
~~~

`Order` does not have to repeat the multiplication formula and access a bunch of fields it does not own. It only needs to ask each line: `line.subtotalCents()`, and then sum them.

This creates **high cohesion** and reduces duplicating formulas across multiple classes. When the pricing policy changes, we know where the responsibility lives.

### 4.2. “Creator”: Who Creates Child Objects?

When `Order` is what controls the collection of lines, the API:

~~~java
order.addProduct(product, quantity);
~~~

can **create** `new OrderLine(product, quantity)` **itself** after validation, instead of accepting a mutable `OrderLine` controlled by arbitrary external code. This supports ownership, though **it is not a universal rule**: with immutable value objects, accepting an instance directly can also be safe.

### 4.3. “Controller”: Who Orchestrates the Use Case?

`CheckoutService` can call `order.totalCents()`, `gateway.charge(...)`, and `receiptPublisher.publish(...)`, but should not also own the line-by-line pricing algorithm. Orchestration and business calculation are two responsibilities that can be separated.

An oversized controller is still a God Object if it knows every internal detail of each collaborator; having many fields does not automatically guarantee the Single Responsibility Principle.

## 5. Complete Example: Order **Composes** Product and OrderLine

This example uses a Java 17 **record** for value-based data and a controlled mutable class for the `Order` aggregate. Monetary amounts are stored as **`long` in cents** to avoid fundamental errors when representing money with `double`.

Create the file **`OrderCompositionDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class OrderCompositionDemo {
    record Product(String sku, String name, long unitPriceCents) {
        Product {
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException("SKU rỗng");
            }
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Tên rỗng");
            }
            if (unitPriceCents < 0) {
                throw new IllegalArgumentException("Giá âm");
            }
        }
    }

    record OrderLine(Product product, int quantity) {
        OrderLine {
            Objects.requireNonNull(product, "product");
            if (quantity <= 0) {
                throw new IllegalArgumentException("Số lượng sai");
            }
        }

        long subtotalCents() {
            return Math.multiplyExact(product.unitPriceCents(), quantity);
        }
    }

    static final class Order {
        private final String id;
        private final List<OrderLine> lines = new ArrayList<>();

        Order(String id) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("ID rỗng");
            }
            this.id = id;
        }

        void add(Product product, int quantity) {
            // Order decides how to create elements of the collection it owns.
            lines.add(new OrderLine(product, quantity));
        }

        List<OrderLine> lines() {
            return List.copyOf(lines);
        }

        long totalCents() {
            long total = 0;
            for (OrderLine line : lines) {
                total = Math.addExact(total, line.subtotalCents());
            }
            return total;
        }

        String id() {
            return id;
        }
    }

    public static void main(String[] args) {
        Product book = new Product("B-1", "Book", 15_000);
        Product pen = new Product("P-2", "Pen", 7_000);

        Order order = new Order("ORD-7");
        order.add(book, 2);
        order.add(pen, 2);

        System.out.println("Order = " + order.id());
        System.out.println("Lines = " + order.lines().size());
        System.out.println("Book subtotal = "
                + order.lines().get(0).subtotalCents());
        System.out.println("Total = " + order.totalCents());

        List<OrderLine> snapshot = order.lines();
        try {
            snapshot.clear();
        } catch (UnsupportedOperationException ex) {
            System.out.println("Snapshot cannot be edited");
        }

        try {
            order.add(book, 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected = " + ex.getMessage());
        }

        System.out.println("Final lines = " + order.lines().size());
    }
}
~~~

Run with JDK 17+:

~~~bash
javac -encoding UTF-8 OrderCompositionDemo.java
java OrderCompositionDemo
~~~

**Exact stdout:**

~~~text
Order = ORD-7
Lines = 2
Book subtotal = 30000
Total = 44000
Snapshot cannot be edited
Rejected = Số lượng sai
Final lines = 2
~~~

### 5.1. Responsibilities That Have Been Separated

**`Product`** is responsible for product data and validation at the level of a single product value. In the example, the unit price is the price captured when Product is created; if an application uses a catalog whose prices change continuously, distinguish between the **current catalog price** and the **price locked at order placement** with a separate model.

**`OrderLine`** is responsible for a selected product, its quantity, and the subtotal. It uses `Math.multiplyExact` to signal an error when `long` multiplication overflows, rather than silently producing an incorrect total.

**`Order`** is responsible for owning the `lines` collection, adding lines after `OrderLine` validation, exposing a read-only snapshot, and calculating the total by **calling each component**. `Order` does not need to know OrderLine's internal fields to multiply price by quantity itself.

### 5.2. Why Is This Reasonable Composition?

- An Order has **multiple OrderLines**; each OrderLine plays the role of a component of the order.
- The `order.add(...)` API creates a new OrderLine, avoiding accepting an arbitrarily shared mutable line.
- The internal list is private; its structure cannot be modified through `order.lines()`.
- The `Product` and `OrderLine` records have final component fields; because Product's data consists of String/long and OrderLine points to an immutable Product value, the snapshot avoids many aliasing risks.
- Order can add lines according to rules, while the ID is fixed (`final`).

**Do not confuse:** List.copyOf returns a structurally unmodifiable collection and shallow-copies its elements; here it is conveniently safe **because the elements are immutable records containing immutable components**. If `Product` or `OrderLine` contains mutable references, an additional defensive-copying policy is required.

### 5.3. Limitations of the Example

A real ordering system might require discounts, taxes, currencies, exchange rates, auditing, inventory, idempotency, concurrency, and persistence. If there is a rule that every order contains only one line for a SKU, `add(...)` would need to merge lines and validate quantities; the example allows duplicate SKU lines. Those details belong to the domain contract and are not automatically solved by `composition`.

## 6. Delegation: Dividing Behavior Alongside Dividing Data

When combining multiple objects, a component is not only for holding state: the enclosing object can **delegate part of the work to a specialized object**.

~~~java
interface Formatter {
    String format(String value);
}

class Printer {
    private final Formatter formatter;

    Printer(Formatter formatter) {
        this.formatter = formatter;
    }

    void print(String value) {
        System.out.println(formatter.format(value));
    }
}
~~~

In this illustrative declaration snippet, `Printer` decides **when to print**, while `Formatter` decides **how to represent it**. `Printer` does not need `extends Formatter`; the interface field expresses collaboration between objects. This is an example of **keeping the right responsibility in each class**, not a requirement to create wrappers for every method.

Do not confuse delegation with UML composition requiring lifecycle ownership: the `Formatter` component can be created and shared by the caller. The separate article **Delegating Operations to a Component Object** explores forwarding methods, transforming arguments/results, exception propagation, boundary invariants, testing with fakes, and coordinating multiple delegates in depth.

## 7. Dependency Injection Is a Way of Assembling Objects

When a class needs a collaborator, there are two common approaches.

**Hardcoding the dependency internally:**

~~~java
class ReportService {
    private final HtmlFormatter formatter = new HtmlFormatter();
}
~~~

If `ReportService` depends concretely on `HtmlFormatter`, changing the algorithm to JSON or plain text requires modifying ReportService.

**Receiving the dependency from the constructor:**

~~~java
class ReportService {
    private final Formatter formatter;

    ReportService(Formatter formatter) {
        this.formatter =
                java.util.Objects.requireNonNull(formatter);
    }
}
~~~

If `Formatter` is an interface, ReportService only needs to know the **`format(...)` contract**, without knowing the concrete implementation.

This is **constructor injection** — a form of dependency injection that requires no framework. The object creator, such as `main`, chooses and combines appropriate implementations. Benefits:

- Clarity about required dependencies.
- Easy to swap behavior by environment.
- Easy to test with fakes/stubs.
- Avoids using static/global mutable service state.
- A `final` field helps keep the dependency reference stable after construction.

**`final` does not mean the collaborator itself is immutable or thread-safe**; that is a separate issue.

### 7.1. Composition Root

In a small application:

~~~java
Formatter formatter = new PlainTextFormatter();
Publisher publisher = new ConsolePublisher();
ReportService service = new ReportService(formatter, publisher);
~~~

This is an illustrative snippet with the corresponding classes. The place where the **object graph is assembled** is called the *composition root*. It knows about concrete implementations; the remaining services depend only on the contracts they need.

An application using Spring or another DI framework still has to address the same assembly responsibility, but at the Java Core level, calling constructors yourself is sufficient to learn the exact essence.

## 8. Interfaces and the Strategy Pattern Help Change Behavior Without `extends` on a Service

A service may need varying policies:

- Fixed or weight-based shipping fees.
- Invoice formatting as text or JSON.
- Discount policies by customer or campaign.
- How data is stored in a file, database, or memory.
- How notifications are sent via email, SMS, or log.

Instead of creating subclasses `ShippingServiceFlat` and `ShippingServiceWeight` and overriding the entire service logic, you can put **the varying part** into the `ShippingCost` interface and inject the implementation via composition.

~~~text
ShippingService
   |-- ShippingCost (interface)
   |      |-- FlatRate
   |      +-- WeightBased
   |
   +-- NoticeSink (interface)
          |-- InMemoryNotice
          +-- EmailNotice
~~~

`ShippingService` still orchestrates the label-creation/fee-collection flow without having to handle every fee-calculation method and every notification channel.

## 9. Complete Example: Coordinating ShippingCost and NoticeSink

Create the file **`ShippingCompositionDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class ShippingCompositionDemo {
    interface ShippingCost {
        long calculateCents(int grams);
    }

    static final class FlatRate implements ShippingCost {
        @Override
        public long calculateCents(int grams) {
            if (grams <= 0) {
                throw new IllegalArgumentException("Khối lượng sai");
            }
            return 25_000;
        }
    }

    static final class WeightBased implements ShippingCost {
        @Override
        public long calculateCents(int grams) {
            if (grams <= 0) {
                throw new IllegalArgumentException("Khối lượng sai");
            }
            return Math.addExact(
                    5_000, Math.multiplyExact(15L, grams));
        }
    }

    interface NoticeSink {
        void send(String text);
    }

    static final class InMemoryNotice implements NoticeSink {
        private final List<String> messages = new ArrayList<>();

        @Override
        public void send(String text) {
            messages.add(text);
        }

        List<String> messages() {
            return List.copyOf(messages);
        }
    }

    static final class ShippingService {
        private final ShippingCost cost;
        private final NoticeSink notice;

        ShippingService(ShippingCost cost, NoticeSink notice) {
            this.cost = Objects.requireNonNull(cost, "cost");
            this.notice = Objects.requireNonNull(notice, "notice");
        }

        String createLabel(String code, int grams) {
            if (code == null || code.isBlank()) {
                throw new IllegalArgumentException("Mã rỗng");
            }

            long fee = cost.calculateCents(grams);
            notice.send("Created " + code);
            return code + ":" + fee;
        }
    }

    public static void main(String[] args) {
        InMemoryNotice inbox = new InMemoryNotice();

        ShippingService flat =
                new ShippingService(new FlatRate(), inbox);
        ShippingService weighted =
                new ShippingService(new WeightBased(), inbox);

        System.out.println("Flat = "
                + flat.createLabel("S-1", 800));
        System.out.println("Weight = "
                + weighted.createLabel("S-2", 800));
        System.out.println("Messages = " + inbox.messages());

        try {
            flat.createLabel("S-3", 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected = " + ex.getMessage());
        }
        System.out.println("Final messages = "
                + inbox.messages().size());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 ShippingCompositionDemo.java
java ShippingCompositionDemo
~~~

**Exact stdout:**

~~~text
Flat = S-1:25000
Weight = S-2:17000
Messages = [Created S-1, Created S-2]
Rejected = Khối lượng sai
Final messages = 2
~~~

### 9.1. What the Example Demonstrates

- `ShippingService` is **assembled from two collaborators**: `ShippingCost` and `NoticeSink`.
- The two implementations `FlatRate` and `WeightBased` swap out the fee calculation algorithm. For 800g, the fees are 25,000 cents and `5000 + 15 * 800 = 17000` cents, respectively.
- `InMemoryNotice` is a simple fake that stores notifications in a collection. The example uses the same sink for both services to show that collaborators **can be shared** when the contract allows it.
- `ShippingService` does not know whether the sink is in-memory, email, or another type; it only calls `send(...)`.
- An input weight of 0 is rejected by the strategy **before** any notification is sent, so `Final messages = 2`.

**Design note:** this is *object composition in the sense of wiring collaborators together*, but having **two services share the same NoticeSink** is not an exclusive ownership relationship of a service in the strong UML composition sense. When modeling the lifecycle, you should clearly state who owns the sink and where it is managed.

### 9.2. Atomicity and Consistency Issues

`createLabel` calculates the fee, calls notice, and then returns the label. In a real system, if `notice.send` throws an exception or finishes sending but another transaction fails, you must decide whether to retry, roll back, or use an outbox. Composition only makes **responsibility boundaries clearer**; it **does not automatically create transactions** between objects.

If multiple threads share `InMemoryNotice`, the `ArrayList` in the example **is not designed to be thread-safe**. You can inject a thread-safe sink or implement appropriate synchronization. `final NoticeSink notice` does not make the sink thread-safe on its own.

## 10. Dividing Responsibilities by “Reason to Change”

A practical criterion for splitting classes is that each class **has a single group of reasons to change**.

Example:

| Requirement Change | Potentially Responsible Class |
| --- | --- |
| How shipping fee is calculated | `ShippingCost` implementation |
| Sending notifications through another channel | `NoticeSink` implementation |
| Rules allowing shipping label creation | `ShippingService` or validation policy |
| Order information model | `Order`/`OrderLine` |
| How order summary is displayed | `OrderFormatter` |
| Order persistence mechanism | `OrderRepository` |
| HTTP or command-line connectivity | Outer-layer controller/adapter |

The table is a **suggested division**, not a rule forcing a change to always touch exactly one file. There are changes that reasonably span multiple classes, especially when the business contract genuinely changes. The goal is to **reduce change propagation caused by unnecessary dependencies**.

### 10.1. Different Responsibilities Do Not Always Mean Splitting into Classes Immediately

A simple class with two fields and one calculation method can be clearer than creating three interfaces, two factories, and a configuration layer. You need to balance:

- **Cohesion:** do the methods/fields genuinely serve one task together?
- **Coupling:** does the class know too much about another class's internals?
- **Axis of variation:** do those algorithms/dependencies actually vary independently?
- **Testability:** can it be unit-tested through clear contracts?
- **Abstraction cost:** does a reader have to jump through too many files just to understand one calculation?

**Split for responsibility, not to hit a class count.**

## 11. Ownership: Who Has the Right to Modify and Who Is Responsible for Closing Resources?

An object that has a field referencing a component **does not automatically have exclusive ownership** of it:

~~~java
class Service {
    private final DatabaseConnection connection;

    Service(DatabaseConnection connection) {
        this.connection = connection;
    }
}
~~~

This snippet assumes a `DatabaseConnection` type exists. The connection is passed in by the caller; it may be shared elsewhere. Therefore, **do not automatically close the connection inside Service** solely because it has a `connection` field. The API needs to specify ownership:

- **Service owns:** Service creates/receives ownership of the resource and is responsible for closing it per the contract.
- **Service borrows/uses:** Service uses a resource managed by the caller/application, and normally does not close it itself.
- **Shared ownership:** multiple components use a single resource, while a lifecycle manager coordinates closing it at the right time.

### 11.1. Resource Composition and `AutoCloseable`

Example illustrating an owning API:

~~~java
final class FilePipeline implements AutoCloseable {
    private final java.io.BufferedWriter writer;

    FilePipeline(java.io.BufferedWriter writer) {
        this.writer =
                java.util.Objects.requireNonNull(writer);
    }

    void write(String text) throws java.io.IOException {
        writer.write(text);
    }

    @Override
    public void close() throws java.io.IOException {
        writer.close();
    }
}
~~~

This is a declaration; **it implicitly adopts the contract that FilePipeline owns the writer**. If the caller only lends the writer, closing it here automatically can be wrong. The choice must be documented.

~~~java
try (FilePipeline pipeline = new FilePipeline(writer)) {
    pipeline.write("Hello");
}
~~~

This is a fragment; `writer` must be initialized beforehand. `try-with-resources` guarantees that `close()` is called per Java rules when exiting the scope, even on exceptions. **Composition does not make Java automatically close resources; `AutoCloseable` and the ownership contract manage that.**

### 11.2. When the Whole Loses References, Is the Part Guaranteed to Be GC'd?

No. If an `Engine` is referenced by both `Car` and held by another controller, it can remain reachable after Car is no longer used. GC evaluates reachability, rather than relying directly on a UML “filled diamond” diagram.

Saying **“Order has OrderLines”** is a domain decision, not a statement that the JVM is forced to reclaim the lines' memory at the exact same time as Order.

## 12. Aliasing: Multiple References to the Same Component

Suppose:

~~~java
final class SharedSettings {
    String mode = "safe";
}

class Worker {
    private final SharedSettings settings;

    Worker(SharedSettings settings) {
        this.settings = settings;
    }

    String currentMode() {
        return settings.mode;
    }
}
~~~

If we create:

~~~java
SharedSettings shared = new SharedSettings();
Worker first = new Worker(shared);
Worker second = new Worker(shared);
shared.mode = "fast";
~~~

The two Worker objects have separate field references, yet **point to the same SharedSettings object**. Both `first.currentMode()` and `second.currentMode()` see the updated mode in a sequential context.

That is **aliasing**. It can be intentional (shared configuration) or dangerous (external code mutating internal state).

### 12.1. When a Snapshot Is Needed Instead of Sharing

If a `Request` needs a fixed configuration from initialization time, instead of holding a mutable settings reference, you can capture the value:

~~~java
final class Request {
    private final String mode;

    Request(SharedSettings settings) {
        this.mode = settings.mode;
    }

    String mode() {
        return mode;
    }
}
~~~

`Request.mode` is a final String, unaffected by the subsequent assignment `settings.mode = "fast"`. This is **choosing ownership/temporal semantics**, not merely adding the final keyword.

### 12.2. Not All Sharing Is Wrong

A stateless formatter, an immutable Clock, a properly managed connection pool, or a thread-safe cache can reasonably be shared across multiple services. Ask:

1. Does the object have mutable state?
2. Who is allowed to mutate it?
3. Should changes be reflected immediately across all consumers?
4. Is it thread-safe if used concurrently?
5. Who owns its lifecycle?

Composition is useful because it makes these choices **describable at the boundaries between objects**.

## 13. Encapsulating Collections When the Whole Owns Many Parts

A whole often holds a `List<Part>` or `Map<Key, Part>`. Common mistake:

~~~java
class Team {
    private final java.util.List<String> members =
            new java.util.ArrayList<>();

    public java.util.List<String> members() {
        return members; // Exposes internal mutable list
    }
}
~~~

The caller can call `team.members().clear()` or add unvalidated elements. Even though the field is `private final`, the composition boundary is broken because the mutable object escaped.

A better approach is for the whole to have **commands**:

~~~java
class Team {
    private final java.util.List<String> members =
            new java.util.ArrayList<>();

    void addMember(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên rỗng");
        }
        members.add(name.trim());
    }

    java.util.List<String> members() {
        return java.util.List.copyOf(members);
    }
}
~~~

`List.copyOf` returns a structurally unmodifiable collection; with immutable Strings, this is a safe snapshot of members. However, if the List contains **mutable objects**, it is a shallow copy — callers can still mutate the state of objects inside the list.

### 13.1. Constructors Also Need to Protect Inputs

~~~java
class Catalog {
    private final java.util.List<String> names;

    Catalog(java.util.List<String> source) {
        this.names = java.util.List.copyOf(source);
    }

    java.util.List<String> names() {
        return names;
    }
}
~~~

If you only store `this.names = source`, the caller could keep the source variable and call `source.clear()` after Catalog is constructed. Copying in the constructor prevents structural modification through the source alias.

To understand this accurately:
- `List.copyOf` rejects null elements.
- The copy is shallow; it does not deep-copy mutable elements.
- `Collections.unmodifiableList(source)` creates an **unmodifiable view**, which can reflect changes made to source through another alias.
- Taking a snapshot while concurrent writers are active requires an explicit synchronization protocol if consistency across multiple elements is required.

## 14. Complete Example: Ownership via Defensive Snapshot

Create the file **`LibraryCompositionDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class LibraryCompositionDemo {
    record Book(String title) {
        Book {
            if (title == null || title.isBlank()) {
                throw new IllegalArgumentException("Tên sách rỗng");
            }
        }
    }

    static final class Shelf {
        private final String label;
        private final List<Book> books;

        Shelf(String label, List<Book> initialBooks) {
            this.label = Objects.requireNonNull(label, "label");
            this.books = List.copyOf(initialBooks);
        }

        String label() {
            return label;
        }

        List<Book> books() {
            return books;
        }

        int count() {
            return books.size();
        }
    }

    public static void main(String[] args) {
        List<Book> input = new ArrayList<>();
        input.add(new Book("Java"));
        input.add(new Book("OOP"));

        Shelf shelf = new Shelf("S-A", input);
        input.clear();
        input.add(new Book("Changed"));

        System.out.println("Shelf = " + shelf.label());
        System.out.println("Books = " + shelf.books());
        System.out.println("Count = " + shelf.count());
        System.out.println("Input count = " + input.size());

        try {
            shelf.books().add(new Book("Extra"));
        } catch (UnsupportedOperationException ex) {
            System.out.println("Shelf list is read-only");
        }

        System.out.println("Final count = " + shelf.count());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 LibraryCompositionDemo.java
java LibraryCompositionDemo
~~~

**Exact stdout:**

~~~text
Shelf = S-A
Books = [Book[title=Java], Book[title=OOP]]
Count = 2
Input count = 1
Shelf list is read-only
Final count = 2
~~~

Here, `Shelf` has a collection of `Book` value objects:

- The mutable input list is **copied** when creating Shelf. Modifying `input` afterward does not change the structure of `shelf.books`.
- `books()` returns a read-only list, so callers cannot add or remove directly.
- `Book` is a record with an immutable String component; this makes the snapshot result safe enough for the example.
- `Shelf` does not need to “own” Book in an exclusive sense: the same immutable Book instance can appear on multiple shelves without causing mutation conflicts. If the domain requires each physical book to be on only one shelf, you need a BookCopy/InventoryItem model with its own identity and ownership invariant.

**A composition can be safe thanks to immutable parts** without needing to forbid every shared reference.

## 15. “Do Not Ask for the Internals” of a Component: Tell, Don't Ask and the Law of Demeter

A sign of high coupling is **train-wreck navigation**:

~~~java
order.getCustomer()
     .getAddress()
     .getCity()
     .getName();
~~~

This is an illustrative fragment: each getter can pull the caller into depending on the structure of multiple objects. If the model changes `Address`, the caller has to be modified even though its only need is getting the place name for delivery.

An alternative:

~~~java
String deliveryCity = order.deliveryCityName();
~~~

Or let `DeliveryPlanner` accept a value object exposed by `Order` under a clear contract.

**Law of Demeter** is commonly interpreted as: an object should work primarily with its direct collaborators, its arguments, and objects it creates itself, avoiding digging deep into the structure of components that are not its responsibility. This is a heuristic, not a compiler rule.

### 15.1. Do Not Hide All Data Just Out of Fear of Getters

If the caller truly needs an immutable `Address` to compute a shipping route, returning an immutable Address value object can be a clean design. You are not forced to add `order.deliveryCityName()`, `order.deliveryPostalCode()`, and `order.deliveryCountry()` if the value object's API already has stable meaning.

The goal is to **reduce unnecessary coupling**, not to forbid every traversal.

## 16. An Object Can Hold Multiple Roles Without Becoming a God Object

An `Order` can:

- Check the logic for adding order lines.
- Calculate the total from its OrderLines.
- Manage the state of the aggregate.
- Provide a snapshot for the presentation layer.

All of these can belong to one **unified responsibility**: maintaining Order's invariants. The Single Responsibility Principle **does not mean each class may only have one method or one field**.

At the same time, having `Order` send emails itself, run SQL queries itself, format HTML itself, and control HTTP transport itself may represent **independent reasons to change** that do not need to live inside the aggregate.

### 16.1. Separating Domain and Infrastructure

~~~text
Order (domain)
   |
   +-- OrderLine (domain value/part)

CheckoutService (application)
   |
   +-- PaymentGateway (port/interface)
   +-- OrderRepository (port/interface)
   +-- ReceiptPublisher (port/interface)

Adapters (infrastructure)
   |
   +-- HttpPaymentGateway
   +-- SqlOrderRepository
   +-- EmailReceiptPublisher
~~~

This is a suggested **way of organizing**, not a mandatory structure for every exercise. The application service orchestrates the use case, domain objects hold business invariants, and adapters handle I/O.

In Java Core examples, it is completely possible to use in-memory implementations without needing a framework or database.

## 17. Designing Just-Enough Interfaces for Collaborators

An interface is useful when an object needs to depend on **behavior** rather than a concrete implementation. However, extracting an interface for **every class** even when there is no varying use case can make code harder to read.

Example of a small interface:

~~~java
interface TaxPolicy {
    long taxFor(long subtotalCents);
}
~~~

It defines the exact responsibility of calculating tax from a subtotal. A `CheckoutService` accepts `TaxPolicy` instead of knowing about multiple concrete tax classes.

If a class has only one stable implementation, needs no mocking, has no multiple policies, and does not expose an open API, using a concrete class can also be appropriate.

### 17.1. Interface Segregation Principle

Do not force a collaborator to implement unrelated methods:

~~~java
interface EverythingGateway {
    void charge(long amount);
    void sendEmail(String text);
    void saveToDatabase(Object object);
}
~~~

Each consumer should depend only on the capabilities it actually needs, such as `PaymentGateway`, `NotificationSink`, and `OrderStore`. Splitting interfaces reduces coupling between independent changes.

### 17.2. Dependency Inversion

If a high-level service depends on a concrete low-level adapter, changing the adapter can force changes in the service. Depending on a sufficiently small interface/port directs dependencies toward the **functional contract**.

**Do not confuse Dependency Inversion with “using interfaces for everything”.** An immutable domain value object can be used directly without needing an `IProduct` just to look flexible.

## 18. Testability: Collaborating Objects Can Be Replaced with Fakes

Composition often makes unit testing easier because a class can be wired with test collaborators.

For example, an `InvoiceService` that needs a `Clock` to get the time can have `Clock.fixed(...)` injected:

~~~java
class InvoiceService {
    private final java.time.Clock clock;

    InvoiceService(java.time.Clock clock) {
        this.clock = java.util.Objects.requireNonNull(clock);
    }

    java.time.Instant issueTime() {
        return clock.instant();
    }
}
~~~

A test can create:

~~~java
java.time.Clock fixed = java.time.Clock.fixed(
        java.time.Instant.parse("2026-01-01T00:00:00Z"),
        java.time.ZoneOffset.UTC);
InvoiceService service = new InvoiceService(fixed);
System.out.println(service.issueTime());
~~~

Output (if the fragment is placed inside an appropriate method):

~~~text
2026-01-01T00:00:00Z
~~~

There is no need to modify a global clock or override InvoiceService's logic just for testing. `Clock` is a collaborator via composition; the `final` field keeps the dependency reference stable.

### 18.1. Test Doubles Without a Mocking Framework

An `InMemoryNotice` in the shipping example is a **fake** you can write yourself in Java Core. It records the messages the service sends, helping verify behavior at the boundary:

- Did the service call the right collaborator?
- When input validation fails, are any side effects produced?
- When swapping the strategy implementation, does the service preserve its orchestration contract?

For real tests, you should use assertions from JUnit or the corresponding testing tool instead of just printing to stdout; this article uses main to demonstrate standalone execution.

### 18.2. Do Not Add Dependency Setters Just for Testing

If a class has `private final PaymentGateway gateway`, do not rush to remove final and add `setGateway` just so unit tests can replace the dependency after the object is created. Constructor injection lets tests supply a fake **right when creating the object**, keeping the contract clearer.

## 19. Composition and Immutability

Composition pairs well with **immutable value objects**. If the parts cannot be mutated, the whole can share references more safely under appropriate conditions.

~~~java
record Address(String city, String street) {
    Address {
        if (city == null || city.isBlank()) {
            throw new IllegalArgumentException("City rỗng");
        }
        if (street == null || street.isBlank()) {
            throw new IllegalArgumentException("Street rỗng");
        }
    }
}

record Recipient(String name, Address address) {
    Recipient {
        java.util.Objects.requireNonNull(name);
        java.util.Objects.requireNonNull(address);
    }
}
~~~

These are Java 17 records. `Recipient` **has** an `Address`; the two objects compose a data structure, yet the Address value can be safely shared because String is immutable and records have no auto-generated setters.

### 19.1. Java Records Only Have Shallow Immutability

If `record Recipient(String name, List<String> tags)` holds a mutable List, the component reference is final, yet the List can still be modified. Use a compact constructor to create a snapshot:

~~~java
record TaggedRecipient(String name,
                       java.util.List<String> tags) {
    TaggedRecipient {
        java.util.Objects.requireNonNull(name);
        tags = java.util.List.copyOf(tags);
    }
}
~~~

At the same time, if tags is a list of mutable objects, a shallow copy is not enough to lock the internal state of each object. Composition does not replace deciding **how deep defensive copying needs to go**.

### 19.2. Mutable Aggregate + Immutable Parts

An Order model can be mutable at the level of its line list, while each line is an immutable value. This is often a reasonable combination: the aggregate owns changes to its components, while each line's state cannot be arbitrarily mutated from outside.

## 20. Composition and Inheritance Can Coexist

You do not have to choose **only one**. For example:

~~~java
interface PaymentGateway {
    void charge(long cents);
}

abstract class RetryingGateway implements PaymentGateway {
    // Can hold common retry logic and expose appropriate hooks.
}

final class CheckoutService {
    private final PaymentGateway gateway;

    CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    void checkout(long cents) {
        gateway.charge(cents);
    }
}
~~~

`CheckoutService` uses **composition** with PaymentGateway. A PaymentGateway implementation can use **inheritance** to reuse an internal workflow if the is-a/extension contract genuinely fits.

**What to avoid** is having CheckoutService **inherit from PaymentGateway** just to get the `charge` method, because CheckoutService is not a payment gateway.

### 20.1. Avoid “Inheritance for Code Reuse” That Violates the Subtype Contract

A class might inherit all public methods of a superclass even when it only needs one helper. If the subclass fails to preserve the superclass's expectations (preconditions, postconditions, invariants), polymorphic code can easily break.

Composition exposes only **the methods the whole chooses**, so it usually helps protect the contract against changes in implementation details.

## 21. The “Shared Mutable State” Pitfall When Composing Multiple Objects

Even when each class is cleanly separated, shared mutable collaborators can still cause data races:

~~~java
class Counter {
    private int value;

    void increment() {
        value++;
    }

    int current() {
        return value;
    }
}

class JobService {
    private final Counter counter;

    JobService(Counter counter) {
        this.counter = counter;
    }

    void execute() {
        counter.increment();
    }
}
~~~

If multiple `JobService` objects hold the **same Counter**, and multiple threads call `execute`, `Counter.value++` is not atomic and can lose updates. `private final Counter counter` only prevents reassigning the reference; it **does not make Counter thread-safe**.

You can choose:

- Give each service its own counter if the domain wants independent state.
- `AtomicInteger` or synchronization for a shared counter.
- An immutable value snapshot if updating shared state is not needed.
- Explicitly specify the concurrency model for the collaborator.

**Good responsibility division and thread safety are two different problems.** Composition creates a sensible place to put a synchronization policy, but does not implement it automatically.

## 22. Bidirectional Relationships and Reference Cycles

A model that has both:

~~~java
class Parent {
    private final java.util.List<Child> children =
            new java.util.ArrayList<>();
}

class Child {
    private Parent parent;
}
~~~

has a bidirectional relationship. This can be useful for navigation, yet increases synchronization responsibilities:

- When adding Child to Parent, who sets `child.parent`?
- When moving Child to another Parent, who removes the old link?
- Who is allowed to modify the list and the parent field?
- If serialization/toString/equals traverses reference cycles, how do you avoid infinite loops?
- Are multiple threads mutating the graph at the same time?

One way to reduce risk is to **designate one aggregate root to control both directions of the relationship**, preventing callers from modifying the two fields independently. Sometimes, however, only a **unidirectional** relationship is needed; do not add a back-reference when there is no real use case.

### 22.1. Reference Cycles Do Not Mean Java GC Is Helpless

The Java garbage collector can reclaim objects forming a cycle **if the entire cycle is no longer reachable from GC roots**. The bigger issues here are usually **invariants, traversal, and lifecycle**, rather than every cycle being a memory leak.

If a static registry still holds an object in the cycle, the entire object graph remains reachable along the corresponding reference paths; you must examine actual reachability.

## 23. Composition and equality/hashCode

When a whole contains parts, you need to decide:

- Is the whole an **entity** with its own identity (such as Order ID), or a **value object** defined by its components?
- Should equality compare all parts or only identity?
- Are the parts immutable?
- If you put a mutable aggregate into a `HashSet` or use it as a `HashMap` key, will mutating fields involved in hashCode break lookups?

An immutable record like:

~~~java
record Point(int x, int y) {
}
~~~

has component-based equality per the record contract, fitting value semantics. An Order entity with its own ID does not necessarily consider two orders with the same list of items to be equal.

Composition **does not decide equality automatically**. Do not mechanically generate `equals/hashCode` based on every field if the graph has mutable fields, cycles, or entity identities.

## 24. Composition and Performance

Composing objects can introduce additional:

- Allocations for component instances.
- Some method calls through interfaces/delegation.
- Indirection when accessing data.
- Snapshots/defensive copies if you want to protect ownership.

However, it also helps:

- Isolate data and logic, reducing maintenance costs.
- Reuse collaborators in the right places.
- Swap implementations without modifying many places.
- Test without needing the real system.
- Place specialized optimizations in the exact responsible component.

You should not assume “inheritance is faster than composition” or “one giant class is always more efficient”. The JVM/JIT has optimizations such as inlining and escape analysis depending on context. If performance matters, **measure the actual workload** with an appropriate benchmark rather than breaking the responsibility model based on guesswork.

## 25. Distinguishing Object Graph, Class Diagram, and Runtime Ownership

A class diagram showing `Order` referencing `List<OrderLine>` is a **class-level relationship**. At runtime, however, it can look like:

~~~text
Order A --> Line 1
        --> Line 2

Order B --> Line 3

ShippingService A --+
                    +--> SharedNoticeSink
ShippingService B --+
~~~

In this graph, each Order holds its own OrderLines according to the designed API. Two ShippingServices reference the same sink. If the domain wants exclusive ownership, the invariant must be enforced, not just drawn as a filled UML diamond.

**The domain model is a design decision; object references are the mechanism that enforces that decision.**

## 26. Common Anti-Patterns

### 26.1. God Object

One class contains every field, every database call, every calculation, and every output format. You need to find **responsibility boundaries** instead of adding more and more private helpers to the same class without control.

### 26.2. Inheritance Instead of has-a

`class Invoice extends PdfWriter` to reuse `write` makes Invoice a kind of PDF writer at the type level, which misrepresents the domain relationship. Use `private final PdfWriter writer` or a `DocumentPublisher` interface instead.

### 26.3. Exposing Mutable Components Directly

`getLines().clear()` allows callers to corrupt Order's invariants. Provide commands and immutable snapshots when needed.

### 26.4. Overly Deep Object Graph

`a.getB().getC().getD().execute()` forces the caller to know many implementation details. Consider delegation at meaningful boundaries rather than building mechanical wrappers at every level.

### 26.5. An Interface for Every Class Despite No Real Abstraction

Creating `IOrderLine`, `IProduct`, and `IOrderId` just because every class “must have an interface” can clutter code. Use interfaces where there is a useful **behavioral contract, variation, or dependency boundary**.

### 26.6. Protecting the Reference Without Protecting the Object

`final List<Item>` does not make the list or the Items immutable. Consider aliasing, defensive copying, and state-mutating methods.

### 26.7. Unclear Resource Ownership

A service receives a shared connection from outside yet calls `close()` itself when done, breaking other consumers. Document clearly who owns it and when it should be closed.

### 26.8. Business Logic in the Orchestration Layer Instead of Domain Objects

The service accesses the price/quantity fields of each line and calculates subtotals itself in multiple places. Place calculations close to the data and invariants they protect.

### 26.9. Shared Mutable Collaborator Without a Concurrency Protocol

Multiple services have the same mutable fake/cache/counter injected, causing data races. Choose a thread-safe collaborator or give each owner its own instance.

### 26.10. Uncontrolled Circular Dependency

A needs B to initialize, while B also needs A right in its constructor. This easily makes constructor chaining difficult, exposes partially initialized objects, or prevents a dependency injection container from resolving the cycle. Revisit responsibilities, use an abstraction/mediator, or move state appropriately.

### 26.11. Over-Composition

A small piece of business logic is split into ten layers of wrappers that merely forward a single method. Do not chase class counts; evaluate whether the testability/coupling benefits are real.

### 26.12. Using `static` as a Global Dependency

A mutable global `PaymentGateway.INSTANCE` makes it hard for services to have independent configurations and causes tests to interfere with one another. Plain constructor injection is clearer when there are multiple implementations.

## 27. Step-by-Step Guide to Designing Composition

**Step 1 — Write the use case.** For example: “Create an order, add products, calculate total, calculate shipping fee, and send a notification”.

**Step 2 — List the data and invariants.** Non-negative price, positive quantity, valid order ID, no total overflow, do not expose mutable lists.

**Step 3 — Identify which object knows which data.** OrderLine knows product/quantity and computes subtotal; Order holds lines and computes total; the shipping policy knows the fee algorithm.

**Step 4 — Find axes of variation.** An application might swap multiple shipping policies or notification channels. Use interfaces for those variation points.

**Step 5 — Choose ownership.** Does Order create lines or accept immutable lines? Is the sink shared or owned? Which resources need closing? Are input/output copies needed?

**Step 6 — Design the behavioral API.** `order.add(product, qty)`, `order.totalCents()`, `service.createLabel(...)`. Minimize setters/getters that expose internals.

**Step 7 — Assemble from the outside.** `main` or the composition root creates collaborators and injects them into services.

**Step 8 — Test at the boundaries.** Check invariants, negative inputs, exceptions, fake collaborators, aliasing, and shared-state cases.

**Step 9 — Review coupling.** Does changing a formatter force modifying Order? Does changing storage force modifying Product?

**Step 10 — Expand the model only when the need arises.** Avoid adding unused layers/interfaces just to “follow the pattern”.

## 28. Self-Check Exercises with Answers

**Question 1.** `Car` uses `Engine` to start. Which relationship is more natural: `Car extends Engine` or `Car` holding an `Engine` field?

**Answer:** Usually composition: Car **has/uses** Engine, whereas Car is not an Engine.

**Question 2.** `Order` holds `private final List<OrderLine> lines`. Does `final` alone protect the list's invariant?

**Answer:** No. Final prevents reassigning the field, yet a mutable List can still be modified through methods or aliases. A controlled API and appropriate snapshot/defensive copying are required.

**Question 3.** Why should `OrderLine` calculate the subtotal instead of `Order` reading the price and quantity fields of each line itself?

**Answer:** OrderLine holds the necessary data, so logic alongside its responsibility is more cohesive and avoids duplicating the business rule across multiple owners.

**Question 4.** A service has `NotificationSink` injected via constructor. Must it necessarily own and close the sink when finished?

**Answer:** No. A field reference does not by itself establish lifecycle ownership. A clear contract is needed regarding owned, borrowed, or shared dependencies.

**Question 5.** Does `List.copyOf(List<MutableItem>)` create a deep copy of each MutableItem?

**Answer:** No. It creates a structurally unmodifiable snapshot, but does not deep-copy mutable elements.

**Question 6.** Are two services holding the same `InMemoryNotice` instance an example of exclusive strong ownership UML composition?

**Answer:** Not in the sense of exclusive ownership; that is a shared collaborator. It can still be called object composition in the broad sense of wiring dependencies.

**Question 7.** Why is composition usually easy to unit test?

**Answer:** Because collaborators are injected and can be replaced with fakes/stubs to verify behavior without needing real external services.

**Question 8.** Must every domain class have an interface for it to be good composition design?

**Answer:** No. Use interfaces where there is a behavioral contract, variation, or boundary that genuinely benefits. Concrete immutable value objects usually do not need interfaces.

**Question 9.** Can using `private final Clock clock` yield different timestamps?

**Answer:** Yes. Final keeps the reference fixed, while `clock.instant()` can return different values over time.

**Question 10.** If two Workers share a mutable Counter, does `final Counter counter` make increment thread-safe?

**Answer:** No. Shared mutable state requires a thread-safe implementation or appropriate synchronization.

**Question 11.** What risks does a bidirectional Parent–Child relationship have?

**Answer:** Requiring bidirectional synchronization on add/remove/move, avoiding exposing mutable state, cycles during traversal/serialization, and defining who owns updates.

**Question 12.** With a reference cycle A↔B, does Java GC always suffer a memory leak?

**Answer:** No. If the entire graph is no longer reachable from GC roots, GC can reclaim objects involved in a cycle.

**Question 13.** Should an `Order` entity use `equals` to compare all mutable `lines`?

**Answer:** There is no default answer. Identity/equality must be decided per the domain; mutable fields in hash-based collections can break lookups when hashCode changes.

**Question 14.** Does composition make all code faster than inheritance?

**Answer:** There is no guarantee. Choose the design based on semantics/coupling and benchmark when performance truly matters.

**Question 15.** When is inheritance still appropriate?

**Answer:** When there is a valid is-a relationship, the base class's subclassing contract is clear, and polymorphism through a hierarchy is genuinely required.

**Question 16.** What is wrong with the API `order.getLines().get(0).getProduct().getPrice()`?

**Answer:** The caller depends deeply on the object graph structure, increasing coupling. You can use `order.totalCents()` or an API returning an appropriate immutable value if the caller only needs the total.

**Question 17.** Why should a service not format SQL/email/HTML itself if its main responsibility is checkout?

**Answer:** Those parts have different reasons to change than checkout orchestration, and should usually live in appropriate collaborators/adapters.

**Question 18.** If a part is created by a whole, when the whole is GC'd, must the JVM immediately invoke the part's destructor?

**Answer:** No. Java uses GC/reachability and explicit resource management; there is no destructor mechanism synchronized with UML composition.

## 29. Checklist When Reviewing Composition Relationships

1. **Is the true relationship has-a/uses-a or is-a?** Do not use inheritance just to reuse a single method.
2. **Does each class have a clear responsibility?** It should be clear why that class exists.
3. **Does the whole delegate specialized work to its parts?** Or does it manipulate parts' fields itself and duplicate logic?
4. **Does the API hide its internal representation?** Avoid unnecessarily exposing mutable collections and the object graph.
5. **Are mutable inputs copied when needed?** Do not retain aliases that can break invariants.
6. **Do getters return mutable parts?** Consider snapshots, immutable values, or read-only views according to the contract.
7. **Are parts shared?** If so, are shared mutability, lifecycle, and ownership clear?
8. **Who creates the part and who may move a part to another whole?** Is there an exclusivity constraint?
9. **Who closes resources?** Constructor injection does not automatically decide ownership.
10. **Are dependencies injected from outside when reasonable?** Avoid hardcoding every implementation.
11. **Are there sensible interfaces for variation points?** Do not force an interface onto every value object.
12. **Is the composition root clear?** There should be one place that selects implementations and wires objects.
13. **Can tests use fake collaborators?** Can side effects be observed/controlled?
14. **Are there unnecessary reference cycles or bidirectional relationships?** Avoid coupling and difficult two-way state updates.
15. **Is there a concurrency protocol for shared mutable objects?** A final reference does not replace thread safety.
16. **Are wrappers/layers overused?** Every intermediate layer needs a real role.
17. **Does equality/identity reflect the domain?** Do not mechanically generate it over every mutable field.
18. **Do methods enforce validation/invariants in the owning place?** Do not leave everything up to callers.
19. **Does the design allow swapping an algorithm without modifying every other class?** If not, examine coupling.
20. **Is the code still readable for a new developer?** Good composition should make structure and behavior clearer, not merely create more files.

## Conclusion

**Composition** combines objects to accomplish a larger goal, in which **each object is responsible for a clear portion of behavior or state**. In Java, we typically use fields, constructor injection, interfaces, and delegation to realize that. With a domain aggregate like `Order`, the whole can manage its parts and protect invariants; with an application service like `ShippingService`, the whole coordinates collaborators that implement different policies.

Do not confuse **object composition in the sense of combining behavior** with **strong-ownership UML composition**: the JVM does not automatically enforce exclusivity, lifecycle, or destructors from a reference field. Ownership, defensive copying, resource management, thread safety, and mutation boundaries must be designed intentionally.

Use composition when it helps **divide responsibilities, increase cohesion, reduce coupling, make behavior easy to change, and make testing easy**. Use inheritance when there is a genuine subtype contract. A good choice is not “the most classes” but **the right boundaries where data and behavior belong**, with a small, unambiguous API that protects valid state.
