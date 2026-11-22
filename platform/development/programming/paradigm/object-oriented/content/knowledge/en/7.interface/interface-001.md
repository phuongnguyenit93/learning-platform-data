# Interfaces as contracts and roles in Java

In Java, **an interface (`interface`)** describes **capabilities that an object commits to providing**, allowing client code to invoke those capabilities without knowing the object's concrete class.

Imagine an application that needs to send notifications. Its business logic only cares about **delivering a notification to a recipient**. It should not need to know whether delivery uses email, SMS, an in-app notification, or a test double. We can name this shared capability `DeliveryChannel`.

These two perspectives complement each other:

- **Interface as a contract:** if a class `implements DeliveryChannel`, it must provide the interface's operations and honor its published usage rules.
- **Interface as a role:** an object can be used *in the role of* a notification delivery channel even if it has other capabilities. A class can fulfill multiple roles by implementing multiple interfaces.

Contracts enable reliable collaboration between components. Roles let us discuss **what an object can do** rather than **which class created it**.

## 1. What does an interface define?

A simple example:

~~~java
interface DeliveryChannel {
    DeliveryReceipt deliver(Notice notice);
}
~~~

To the Java compiler, this interface declares an operation named `deliver` that accepts a `Notice` and returns a `DeliveryReceipt`.

Here, the method is implicitly `public abstract` even though neither keyword appears. A concrete class implementing the interface must provide a corresponding `public` implementation unless the class itself is abstract.

However, **a method signature is not the entire contract**. Interface authors and users must also agree on the following:

| Question | Required agreement |
|---|---|
| Who may invoke it? | Code holding a reference of type `DeliveryChannel` |
| What input is valid? | A `Notice` that is not `null`, with a valid recipient and content |
| What does a successful call mean? | In this learning example: completing one **simulated** delivery |
| What does the return value convey? | A `DeliveryReceipt` that is not `null`, identifying the channel and operation details |
| Is the input modified? | No; `Notice` is designed to be immutable |
| What happens on failure? | Report an error as specified; do not arbitrarily return `null` or pretend to succeed |
| Are there side effects? | The real contract must state them; this example only simulates delivery and sends nothing over a network |

An interface provides **a syntactic structure checked by the compiler**. Rules such as “do not return `null`,” “do not silently drop notifications,” and “use the intended recipient” are part of the **behavioral contract**, enforced through design, validation, and tests.

## 2. Complete Java example: one role, multiple implementations

Scenario: a system sends a welcome message through a delivery channel configured externally. We have a shared service, two simulated delivery implementations, and an additional role for checking channel health.

Save everything in **`Demo.java`** and run it with Java 17 or later:

~~~java
import java.util.Objects;

public class Demo {
    public static void main(String[] args) {
        NotificationService byEmail = new NotificationService(
                new EmailChannel()
        );

        DeliveryReceipt emailReceipt = byEmail.sendWelcome("U-01");
        System.out.println(emailReceipt.channel()
                + " -> " + emailReceipt.detail());

        SmsChannel sms = new SmsChannel();

        // Cùng một đối tượng, nhìn qua hai vai trò.
        DeliveryChannel deliveryRole = sms;
        HealthCheck healthRole = sms;

        NotificationService bySms = new NotificationService(deliveryRole);
        DeliveryReceipt smsReceipt = bySms.sendWelcome("U-02");

        System.out.println(smsReceipt.channel()
                + " -> " + smsReceipt.detail());
        System.out.println("SMS sẵn sàng: " + healthRole.isHealthy());
    }
}

// Dữ liệu gửi đi: recipientId là mã người nhận logic,
// không phải địa chỉ email hay số điện thoại thực.
record Notice(String recipientId, String text) {
    Notice {
        Objects.requireNonNull(recipientId, "recipientId");
        Objects.requireNonNull(text, "text");

        if (recipientId.isBlank() || text.isBlank()) {
            throw new IllegalArgumentException(
                    "Người nhận và nội dung không được rỗng");
        }
    }
}

record DeliveryReceipt(String channel, String detail) {
    DeliveryReceipt {
        Objects.requireNonNull(channel, "channel");
        Objects.requireNonNull(detail, "detail");

        if (channel.isBlank()) {
            throw new IllegalArgumentException("Thiếu tên kênh");
        }
    }
}

/**
 * Hợp đồng mô phỏng gửi thông báo:
 * - notice phải khác null;
 * - trả về DeliveryReceipt khác null khi hoàn tất bình thường;
 * - không sửa notice;
 * - không có hoạt động gửi mạng thật trong bài minh họa.
 *
 * @throws NullPointerException nếu notice là null
 */
interface DeliveryChannel {
    DeliveryReceipt deliver(Notice notice);
}

// Cách thực hiện thứ nhất.
final class EmailChannel implements DeliveryChannel {
    @Override
    public DeliveryReceipt deliver(Notice notice) {
        Objects.requireNonNull(notice, "notice");

        return new DeliveryReceipt(
                "EMAIL",
                notice.recipientId() + ": " + notice.text()
        );
    }
}

// Một vai trò độc lập: kiểm tra sức khỏe.
interface HealthCheck {
    boolean isHealthy();
}

// Một lớp có thể đồng thời đảm nhiệm nhiều vai trò.
final class SmsChannel implements DeliveryChannel, HealthCheck {
    @Override
    public DeliveryReceipt deliver(Notice notice) {
        Objects.requireNonNull(notice, "notice");

        return new DeliveryReceipt(
                "SMS",
                notice.recipientId() + ": " + notice.text()
        );
    }

    @Override
    public boolean isHealthy() {
        return true; // Trạng thái giả lập cho mục đích học tập.
    }
}

// Client phụ thuộc vào hợp đồng, không phụ thuộc EmailChannel/SmsChannel.
final class NotificationService {
    private final DeliveryChannel channel;

    NotificationService(DeliveryChannel channel) {
        this.channel = Objects.requireNonNull(channel, "channel");
    }

    DeliveryReceipt sendWelcome(String recipientId) {
        Notice notice = new Notice(recipientId, "Chào mừng bạn!");
        return channel.deliver(notice);
    }
}
~~~

Run:

~~~bash
javac Demo.java
java Demo
~~~

Output:

~~~text
EMAIL -> U-01: Chào mừng bạn!
SMS -> U-02: Chào mừng bạn!
SMS sẵn sàng: true
~~~

The `EmailChannel` and `SmsChannel` classes **do not send real emails or SMS messages**. This example illustrates how to separate an interface from its implementations. In a real system, each adapter must map recipient IDs to actual destinations, handle network failures and timeouts, and ensure that results have the agreed meaning.

### Reading the program from three perspectives

**Client perspective:** `NotificationService` only has a field of type `DeliveryChannel`. It can therefore call `deliver(Notice)` without knowing either channel's internal algorithm or procedure.

**Implementation perspective:** `EmailChannel` and `SmsChannel` declare `implements DeliveryChannel`, provide a public `deliver()` method, validate inputs, and return results according to the shared contract.

**Role perspective:** the `sms` object is both a `DeliveryChannel` and a `HealthCheck`. The `deliveryRole` and `healthRole` variables may reference **the same object**, but each exposes only the operations defined by its declared interface type.

There is no need to create two objects just because one object fulfills two roles.

~~~mermaid
classDiagram
    class DeliveryChannel {
        <<interface>>
        +deliver(Notice) DeliveryReceipt
    }
    class HealthCheck {
        <<interface>>
        +isHealthy() boolean
    }
    class EmailChannel {
        +deliver(Notice) DeliveryReceipt
    }
    class SmsChannel {
        +deliver(Notice) DeliveryReceipt
        +isHealthy() boolean
    }
    class NotificationService {
        -DeliveryChannel channel
        +sendWelcome(String) DeliveryReceipt
    }
    DeliveryChannel <|.. EmailChannel
    DeliveryChannel <|.. SmsChannel
    HealthCheck <|.. SmsChannel
    NotificationService --> DeliveryChannel : phụ thuộc
~~~

## 3. How is “being a role” different from “being a type of entity”?

A **class** typically contains concrete state and implementation details. An **interface** typically specifies a capability that different kinds of objects can fulfill.

For example, an application might define:

~~~java
interface Printable {
    void print();
}

interface Exportable {
    byte[] export();
}
~~~

A report can act as `Printable` when printed and as `Exportable` when exported. An invoice can fulfill those same roles even though reports and invoices need not share a specific business superclass.

The type system makes this idea explicit:

~~~java
void printDocument(Printable document) {
    document.print();
}
~~~

This method fragment belongs inside an appropriate class. Its caller only needs an object that can fulfill the `Printable` role. The method need not accept an `Invoice` or `PdfReport` specifically, or check each concrete type using an `if/else` chain.

In Java, an interface **is also a data type (a reference type)**. It can be used as a variable type, parameter type, return type, generic type argument, or field type. It is more than an architectural description.

Examples from the JDK:

| Interface | Role represented | Possible concrete implementers |
|---|---|---|
| `Runnable` | Provides `run()` behavior | A task submitted to an executor/thread |
| `Comparable<T>` | Defines a natural order for comparison with a compatible type | `String`, `Integer`, and many value objects |
| `Comparator<T>` | Provides a strategy for comparing two values | Comparators by price, date, or name |
| `Iterable<T>` | Supports iteration over elements | A collection or custom type |
| `AutoCloseable` | Supports closing a resource | File streams or custom resources |

An object can implement multiple interfaces without belonging to a single class hierarchy.

## 4. The declared type determines which operations can be called

Consider this fragment from the example:

~~~java
SmsChannel sms = new SmsChannel();

DeliveryChannel channel = sms;
HealthCheck monitor = sms;

channel.deliver(new Notice("U-10", "Xin chào"));
System.out.println(monitor.isHealthy());
~~~

When `channel` has type `DeliveryChannel`, we **cannot** directly call `channel.isHealthy()` even though the actual object is a `SmsChannel`:

~~~java
// channel.isHealthy(); // Lỗi biên dịch: phương thức không thuộc
//                     // kiểu DeliveryChannel.
~~~

This restriction is intentional. A component that only needs delivery capability should not accidentally depend on the monitoring API.

If monitoring is genuinely required, pass a separate `HealthCheck` parameter or design an appropriate dependency. Avoid repeatedly casting to `SmsChannel` to “get access” to methods outside the contract; such casts make the client depend on a specific implementation.

**Polymorphism** occurs at the `channel.deliver(...)` call: Java invokes the `deliver()` implementation belonging to the referenced concrete class, rather than some “default algorithm” selected by the variable name.

## 5. A good contract goes beyond the compiler

Consider another class that declares:

~~~java
final class BrokenChannel implements DeliveryChannel {
    @Override
    public DeliveryReceipt deliver(Notice notice) {
        return null;
    }
}
~~~

This class **compiles**, because returning `null` is valid for a reference type. But it **violates the behavioral contract** requiring a non-null result.

Alternatively, a class could:

- Return a receipt for **a different recipient** from the input.
- Throw `UnsupportedOperationException` for every valid `Notice`.
- Report “delivered” even though it never performed the promised operation.
- Modify input data contrary to its commitment.
- Unexpectedly require callers to pass a secret subtype even though the interface accepts a broader parent type.

The compiler cannot prove these rules on its own.

### Elements of a behavioral contract

| Element | Meaning | Example for `DeliveryChannel` |
|---|---|---|
| **Precondition** | Conditions the caller must satisfy | Pass a valid, non-null `Notice` |
| **Postcondition** | Guarantee after normal completion | Return a non-null `DeliveryReceipt` |
| **Invariant** | Condition an object must maintain | A receipt contains a valid channel name |
| **Failure contract** | When and how failures are reported | `NullPointerException` when the notice is null |
| **Side-effect contract** | Which state or resources may be affected | The simulation does not send anything over a real network |

Avoid making promises in an interface that not every implementation can keep. For example, a promise that “`deliver()` always completes within 1 ms” would be difficult for a real HTTP adapter to honor. A contract should be strong enough for correct client use while allowing multiple valid implementations.

### Substitution principle

A class implementing an interface must be usable in place of other implementations **within the contract's guarantees** without surprising clients in ways that violate shared promises. This is closely related to the **Liskov Substitution Principle (LSP)**.

However, there is no requirement that:

- Two channels use the same algorithm.
- Two receipts contain the same channel name.
- Two providers have identical performance unless the contract specifies it.
- Every implementation is created and managed in the same way.

Implementation details may differ. The stable part is the contract clients rely on.

## 6. Contracts keep clients independent of delivery mechanisms

In the main example, `NotificationService` receives a `DeliveryChannel` through its constructor. The application setup code can pass `new EmailChannel()` or `new SmsChannel()`; the `sendWelcome` method only knows `deliver(Notice)` and needs no changes when switching channels.

~~~java
DeliveryChannel selected = new SmsChannel();
NotificationService service = new NotificationService(selected);
DeliveryReceipt result = service.sendWelcome("U-04");
~~~

Receiving an existing dependency from outside is called **constructor injection**. It isolates the decision about which implementation to use, but does not mean every class needs an additional interface. Define a contract when it reflects **a capability the client actually requires**; the *Programming to interfaces* lesson explores dependency direction, the composition root, and concrete fake tests.

## 7. A role should not promise unavailable capabilities

If `DeliveryChannel` also required every implementation to provide `revoke(messageId)`, a channel unable to retract sent messages would have to implement a meaningless method or always throw an exception. It is better to separate the two roles:

~~~java
interface Sender {
    DeliveryReceipt deliver(Notice notice);
}

interface Revocable {
    void revoke(String messageId);
}
~~~

A class should only `implements Revocable` when it can actually satisfy the revocation contract. A client that only sends messages requires `Sender`; one that needs revocation requires `Revocable`. This reflects the **Interface Segregation Principle (ISP)**: limit dependencies according to client needs, rather than mechanically creating one interface per method. The *Small interfaces and role segregation* lesson shows how to refactor an overly broad contract.

## 8. Roles and class families sharing implementations are separate dimensions

| Question | Interface | Abstract class |
|---|---|---|
| Main purpose | Define the behavioral contract for a role | Share state, constructors, or algorithms within a class family |
| Composition options | A class can `implements` multiple interfaces | A class can directly `extends` at most one superclass |
| Instance state | Cannot declare instance fields | Can hold instance fields and invariants |
| Constructor | None | Supported |

For example, `Invoice` and `AnalyticsReport` can both `implements Exportable` without sharing a business superclass. If a group of exporters truly needs the same buffer and configuration constructor, it can use an abstract base class that **also** implements `Exportable`, while others implement the interface directly. The *Choosing an interface or an abstract class* lesson fully illustrates inheritance versus composition.

## 9. Some Java interface members can include implementations

Although the main member of `DeliveryChannel` is the `public abstract` method `deliver`, Java 17 also allows interfaces to contain:

~~~java
interface Greeter {
    String greet(String name); // Ngầm public abstract

    default String greetEveryone() {
        return greet("mọi người");
    }

    static boolean hasName(String name) {
        return name != null && !name.isBlank();
    }

    private static String normalize(String name) {
        return name.strip();
    }
}
~~~

`default` provides a body shared by implementations; `static` is called through `Greeter.hasName(...)` rather than an instance; `private` is a helper usable only **inside the interface** (the example above does not use `normalize` yet). Interface fields are implicitly `public static final` and **do not** create per-object state. If two unrelated interfaces define default methods with the same signature, a class may need to override the method to resolve the conflict. The *Default members and language-specific limitations* lesson explains modifiers, conflicts, `Object` limitations, and version differences in detail.

## 10. Interfaces as roles passed into callbacks

An interface with **one abstract method** can be declared a *functional interface* and implemented with a lambda.

For example:

~~~java
@FunctionalInterface
interface PriceRule {
    long apply(long originalPriceVnd);
}
~~~

Usage:

~~~java
PriceRule tenPercentOff = original -> original * 90 / 100;

System.out.println(tenPercentOff.apply(200_000)); // 180000
~~~

The `tenPercentOff` variable fulfills the `PriceRule` role even though we did not manually write a named implementation class. Java turns the lambda into an object that can fulfill the functional interface contract.

Here the formula only demonstrates a 10% discount on sufficiently small positive integers to avoid `long` overflow; a real financial contract must specify how to validate negative values, round amounts, and handle overflow.

Interfaces such as `Runnable`, `Comparator<T>`, `Predicate<T>`, and `Function<T,R>` are familiar examples of **roles** that allow behavior to be passed as an argument.

`@FunctionalInterface` instructs the compiler to verify that the interface still has exactly one abstract method under the applicable rules. The annotation is useful but not required for Java to recognize a valid functional interface.

## 11. A clear contract lets us test clients with fakes

We do not need to send real SMS messages to verify that `NotificationService` constructs the correct `Notice`. A test double can record incoming notifications:

~~~java
final class RecordingChannel implements DeliveryChannel {
    Notice last;

    @Override
    public DeliveryReceipt deliver(Notice notice) {
        last = java.util.Objects.requireNonNull(notice);
        return new DeliveryReceipt("FAKE", "Đã nhận");
    }
}

RecordingChannel fake = new RecordingChannel();
NotificationService service = new NotificationService(fake);
service.sendWelcome("U-03");
if (!"U-03".equals(fake.last.recipientId())) {
    throw new AssertionError("Sai người nhận");
}
~~~

This test reuses `Notice`, `DeliveryReceipt`, and `NotificationService` from the main example. It only verifies that **the client invokes the contract correctly**; it does not prove that real email or SMS adapters work. Testing multiple implementations against one contract and detecting semantic violations is the focus of *Replacing implementations while preserving contracts*.

## 12. Evolving an interface changes promises to many parties

When multiple modules use an interface, changing `deliver(Notice)` to `deliver(String)` may prevent implementations and clients from compiling. Adding an abstract method also usually forces concrete implementers to add code; adding a default method reduces some source-level impact but may still introduce conflicts or change behavior.

More dangerously, developers might **keep the signature while changing what the result means**. For example, if `DeliveryReceipt` used to mean *accepted by the provider*, it must not silently change to *read by the recipient* while claiming to preserve the same guarantee. Callers could make wrong decisions even though all code still compiles.

When switching channels, consistently preserve promised input conditions, results, errors, and side effects. If semantics must change, publish a new contract version or a clear migration strategy, and run behavioral tests against each implementation.

## 13. When should we avoid creating another interface?

Interfaces are useful but add maintenance costs. Consider skipping a new interface when:

- There is only one simple class and no dependency boundary that needs stability yet.
- The interface mirrors nearly every public method of a class without defining a clear role.
- Consumers repeatedly cast to a concrete implementation to reach methods omitted from the interface.
- The interface has many methods that only some implementations support.
- The API is changing quickly, so a stable consumer contract is not yet clear.

Conversely, interfaces are especially useful for **external integration adapters, replaceable strategies, plugins, callbacks, cross-module collaboration, and dependency injection**.

A practical test is to describe the interface in one sentence: **“this object can…”**. If that statement is clear, has a specific consumer, and defines verifiable promises, the interface has a good reason to exist.

## 14. Practice scenarios

### Scenario 1 — Designing around roles

A system contains `PdfReport`, `Invoice`, and `EmailMessage`. `PdfReport` can be printed and exported; `Invoice` can be printed; `EmailMessage` can be sent. Should they all be forced to `extends Document` with every `print()`, `export()`, and `send()` method?

**Hint:** not necessarily. Use role-based interfaces such as `Printable`, `Exportable`, and `Sendable`; each class should only `implements` the capabilities it actually provides.

### Scenario 2 — Spotting contract violations

~~~java
class NullChannel implements DeliveryChannel {
    @Override
    public DeliveryReceipt deliver(Notice notice) {
        return null;
    }
}
~~~

**Answer:** the class can compile but violates the `deliver` contract, which requires a non-null receipt on normal completion.

### Scenario 3 — Roles versus runtime types

~~~java
SmsChannel sms = new SmsChannel();
DeliveryChannel sender = sms;
HealthCheck health = sms;
~~~

Question: how many `SmsChannel` objects are created? Can we call `sender.isHealthy()` directly?

**Answer:** one object; `sender.isHealthy()` does not compile because the method is absent from the `DeliveryChannel` interface, although `health.isHealthy()` is valid.

### Scenario 4 — A client depending on an implementation

~~~java
class Job {
    private final EmailChannel channel = new EmailChannel();
}
~~~

Question: to test `Job` using a fake channel, how should the dependency direction change?

**Hint:** let `Job` receive `DeliveryChannel` through its constructor; the code that creates `Job` supplies a real `EmailChannel` or fake `RecordingChannel` according to the environment.

### Scenario 5 — An overly broad interface

If every class implementing `StorageManager` must support `upload()`, `read()`, and `delete()`, but one module is allowed only to read, which design makes access control easier to enforce?

**Hint:** provide a `ReadableStorage` role exposing only `read()` and give write/delete roles only to code with the corresponding permissions. Splitting roles also reduces the API surface that clients might call by mistake.

### Scenario 6 — Expressing an algorithm through an interface

To sort employees by name or salary, must you modify the `Employee` class whenever the criterion changes?

**Hint:** no. Pass different `Comparator<Employee>` implementations to the sort operation. `Comparator` represents **the comparison strategy role**, while `Employee` represents the data entity. When the criterion changes, the client chooses another implementation or lambda.

## Key takeaways for Java OOP design

Choose interfaces by starting with **the consumer**: what should an object be able to do, what inputs are valid, which results can be trusted, and how should failures be handled? Then let classes implement those behaviors using their own details.

A good interface names a **meaningful role**, exposes operations focused enough for independent client use, and specifies a **clear behavioral contract**. An implementing class may change algorithms, data structures, or providers, but must continue honoring the guarantees clients depend on. This makes OOP designs more flexible while keeping them readable, testable, and extensible in a controlled way.
