# Contracts, Implementations, and Consumer Code in Java

In Java, designing by **contract** allows one part of a program to describe *what can be requested* without forcing the caller to know *how the work is performed*. The three roles to distinguish are the **contract**, the **implementation**, and the **code using the contract (consumer/client)**. This is the foundation of polymorphism, implementation substitution, independent testing, and reducing dependencies between components.

After this lesson, you should be able to explain the three roles, trace the method call flow, design a meaningful interface on your own, swap implementations without modifying the consumer, and identify cases of "matching the signature but violating the behavior".

## 1. Three Roles in the Same Design

| Role | Primary Responsibility | What Does It Know? | Example |
| --- | --- | --- | --- |
| **Contract** | Declares the allowed operations and expected behavioral rules | Parameter types, return type, exceptions, meaning of operations | Interface MessageSender |
| **Implementation** | Performs the contract's operations using a specific mechanism | How to send emails, write logs, call APIs, or store data | EmailSender, ConsoleSender |
| **Consumer** | Calls operations to handle business logic | Only needs the capability provided by the contract | AlertService |

Typical relationship:

~~~text
                   uses via MessageSender type
AlertService ------------------------------------------> MessageSender
                                                              ^
                                                              |
                                                 implements   |   implements
                                                EmailSender   |   ConsoleSender
~~~

The arrow from the consumer to the interface represents a **source-code-level dependency**: the consumer declares fields, parameters, or variables using the contract type. At runtime, a concrete implementation object is passed into the consumer, and that object's method implementation is called.

For example, AlertService needs the ability to "send notifications" without needing to know whether they are sent via SMTP, REST, in-memory, or the console screen. If AlertService creates EmailSender itself and calls EmailSender's specific methods, the two components become tightly coupled; replacing the sending method or testing becomes harder.

**Distinguishing the two layers of meaning of the term "contract":**

- **Structural contract**: the elements Java can verify at compile time, such as method names, parameters, return types, accessibility, and override rules.
- **Behavioral contract**: the meaning of the method, input preconditions, results, possible errors, and side effects agreed upon by the author and the user. The Java compiler **cannot automatically prove** that an implementation fully complies with these rules.

For example, an interface declaring the send(Message) method does not guarantee that the method actually sends anything, handles errors properly, or avoids duplicate deliveries. Those aspects must be documented and tested.

## 2. Complete Example: One Contract, Two Implementations, One Consumer

Create a file named **ContractDemo.java** with the contents below. All types in the example reside in a single file; only ContractDemo is a public class. Both senders only **simulate sending notifications via the console**, without making network connections or sending real emails.

~~~java
import java.util.Objects;

// Data passed across the contract boundary.
record Message(String recipient, String body) {
    Message {
        Objects.requireNonNull(recipient, "recipient");
        Objects.requireNonNull(body, "body");
        if (recipient.isBlank() || body.isBlank()) {
            throw new IllegalArgumentException("recipient/body khong duoc trong");
        }
    }
}

// (1) CONTRACT: the consumer only needs to know this method.
interface MessageSender {
    void send(Message message);
}

// (2a) First IMPLEMENTATION.
final class EmailSender implements MessageSender {
    @Override
    public void send(Message message) {
        System.out.println("EMAIL (mo phong) -> "
                + message.recipient() + ": " + message.body());
    }
}

// (2b) Second IMPLEMENTATION.
final class ConsoleSender implements MessageSender {
    @Override
    public void send(Message message) {
        System.out.println("CONSOLE -> "
                + message.recipient() + ": " + message.body());
    }
}

// (3) CONSUMER: depends only on MessageSender.
final class AlertService {
    private final MessageSender sender;

    AlertService(MessageSender sender) {
        this.sender = Objects.requireNonNull(sender, "sender");
    }

    void notifyUser(String recipient, String body) {
        sender.send(new Message(recipient, body));
    }
}

public class ContractDemo {
    public static void main(String[] args) {
        AlertService productionLike =
                new AlertService(new EmailSender());
        productionLike.notifyUser(
                "an@example.com", "Don hang da duoc duyet");

        AlertService consoleMode =
                new AlertService(new ConsoleSender());
        consoleMode.notifyUser("tester", "Da gui thong bao");
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 ContractDemo.java
java ContractDemo
~~~

Expected output:

~~~text
EMAIL (mo phong) -> an@example.com: Don hang da duoc duyet
CONSOLE -> tester: Da gui thong bao
~~~

Reading the example in sequence:

1. **MessageSender** states that a sender accepts a Message and performs send; it does not decide how printing or sending is done.
2. Both **EmailSender** and **ConsoleSender** declare implements MessageSender and provide send(Message). The **@Override** annotation helps the compiler detect certain method-signature mistakes.
3. **AlertService** receives a MessageSender through its constructor, stores it in a field of the same type, and only calls send. Either implementation can be passed in without modifying AlertService's code.
4. In main, the expressions new EmailSender() and new ConsoleSender() determine the **concrete object** at the time the consumer is created. That is how components are "wired" together (wiring/composition).
5. **Message** is a record that holds data and checks for blank inputs. This rule reduces the chance of the consumer accidentally sending a request with empty content; it does not guarantee that an external service has delivered it successfully.

Key point to remember: the consumer still *needs an object to perform the work*; "depending on an interface" does not mean you can run the program without providing an implementation.

## 3. Reference Types and Dynamic Dispatch

In Java, the declared type of a variable determines **which methods can be called at compile time**. For overridden instance methods, the actual class of the object determines **which implementation is executed at runtime**.

~~~java
MessageSender sender = new EmailSender();
sender.send(new Message("an@example.com", "Xin chao"));
~~~

The snippet above is an illustration placed inside a method of the previous example file. The variable sender has the static type MessageSender, while the actual object is an EmailSender. The compiler accepts the call because MessageSender declares send; at runtime, the EmailSender.send method is called.

If EmailSender has an additional specific method connectSmtp(), the expression sender.connectSmtp() **will not compile**, because connectSmtp() is not part of the MessageSender API. Downcasting to EmailSender might make the code work with one implementation, but it breaks substitutability; only use it when implementation-specific logic is truly required and after checking the type.

Do not confuse **polymorphism via method overriding** with **overloading**: overloading selects the appropriate signature primarily based on parameter types at compile time; overriding of instance methods is dispatched based on the runtime object. Static methods are not overridden with this kind of dispatch.

## 4. Designing a Good Contract

Start from **what the consumer needs to do**, then define operation names, input/output data, error rules, and side effects. Avoid putting technical details specific to a single implementation into a shared interface.

For MessageSender, a practical behavioral agreement might specify:

| Contract Question | Rule to Define |
| --- | --- |
| Input preconditions | Message is non-null; recipient and body are non-empty |
| What does success mean? | Does send complete after handing off to the sender, or after the system receives confirmation? One meaning must be chosen |
| When sending fails? | Throw an exception, return a failure result, or retry? Specify consistently |
| Can duplicates be sent? | If retrying, is an idempotency key required or not? |
| What side effects exist? | Network calls, logging, state mutations, billing charges... |
| Is it thread-safe? | Can multiple threads call the same sender concurrently? If so, to what level of guarantee? |

In the runnable example above, send only prints to the console. Therefore, you cannot infer **successful email delivery**, retry mechanisms, or thread safety of a real delivery system. Those guarantees should only be added to the contract and implementations when actually needed.

**Rule for replacing an implementation:** the consumer should not have to change its logic or encounter outcomes contrary to the declared guarantees. For example, if the contract promises that a failed send command will report a failure, an implementation that silently ignores the error violates the **behavioral contract** even though it still compiles. This is the spirit of substitutability (Liskov substitution): an implementation must not weaken the conditions that the consumer is entitled to expect.

Naming by **capability** generally makes a contract clearer than naming by technology: MessageSender expresses "sending a message"; SmtpMessageSender or EmailSender describes one way of implementing it. However, do not create a pointless single-method interface for every class; a contract has value when it represents a boundary that is actually used or has the potential for substitution/testing.

## 5. Interfaces, Abstract Classes, and Concrete Classes

Java provides multiple ways to represent a contract. Choose based on the need to share API, state, and logic.

| Feature | Interface | Abstract class |
| --- | --- | --- |
| Primary purpose | Declares a capability for multiple types to implement | Provides a template and shared implementation for classes in an inheritance relationship |
| Relationship from concrete class | implements multiple interfaces | extends at most one superclass |
| Instance state | No instance fields; fields declared in an interface are implicitly public static final | Can have instance fields, constructors, and protected state |
| Methods | Can have abstract, default, static, and private methods (depending on the appropriate Java version) | Can have abstract methods and methods with bodies; can use protected |
| Constructor | No constructors | Has constructors to initialize the superclass's portion of state |

An interface can declare default methods to share default behavior, but **a default method does not turn an interface into a holder of instance state**. Since Java 9, interfaces can also have private methods to reuse internal logic among default/static methods.

An abstract class is suitable when subclasses genuinely share a workflow or invariant. Illustrative example (not a standalone program):

~~~java
abstract class BaseSender implements MessageSender {
    protected void validate(Message message) {
        Objects.requireNonNull(message, "message");
    }
}

final class LoggingSender extends BaseSender {
    @Override
    public void send(Message message) {
        validate(message);
        System.out.println("Logging: " + message.body());
    }
}
~~~

This snippet uses import java.util.Objects and the Message record and MessageSender interface declared in the earlier example. It shows that an abstract class can **implement an interface** and provide shared logic. Having validation logic available is not enough on its own to conclude that inheritance is required; in many cases, passing a separate Validator object via **composition** is more flexible.

Some important compilation rules:

- When a class implements an interface, the method implementing a public interface method must have **public** access (it cannot be reduced to package-private or private).
- The return type of an overriding method must be compatible; it may be a subtype according to Java's covariant return rules.
- An implementation must not declare additional or broader checked exceptions than what the method in the contract allows. Unchecked exceptions can still be thrown, though their contractual meaning should be documented.
- A concrete class must implement all inherited abstract methods; otherwise, it must itself be declared abstract.
- If two interfaces provide default methods with the same signature and there is no valid precedence resolution, the implementing class must override the method to resolve the conflict.
- An interface does not automatically make an object immutable. Immutability and thread safety are properties of the implementation and its associated data.

## 6. Who Creates the Implementation, and Who Uses It?

A design involves two distinct kinds of work:

- **Composition/wiring**: deciding which concrete object to create and where to pass it. In the example, main handles this using new EmailSender() or new ConsoleSender().
- **Business behavior**: the consumer calls the contract to execute business logic. AlertService does not construct the sender; it receives the sender via its constructor.

Passing dependencies via the constructor (constructor injection) offers three benefits: the consumer's code explicitly states what it needs, the object has valid dependency state right after creation, and implementations can be swapped at the wiring site. A DI framework such as Spring can help automatically create and wire objects, but the design principle applies fully in **plain Java** and requires no framework.

Comparison:

~~~java
// Tightly coupled to a specific implementation:
final class TightlyCoupledAlertService {
    private final EmailSender sender = new EmailSender();
}

// Flexible via contract:
final class LooselyCoupledAlertService {
    private final MessageSender sender;

    LooselyCoupledAlertService(MessageSender sender) {
        this.sender = Objects.requireNonNull(sender, "sender");
    }
}
~~~

These are illustrative snippets reusing EmailSender/MessageSender and import java.util.Objects from the first example, not a standalone file. The main difference does not lie in whether new is used anywhere at all: new still appears in the **wiring layer**; what to avoid is the consumer choosing the implementation itself and depending on the sender's details.

You should also avoid over-engineering: if a feature only has one implementation, has no boundary that needs testing or swapping, and has a simple API, a direct concrete class may be a good choice. Evaluate based on actual usage needs.

## 7. Testing the Consumer with a Fake Implementation

One concrete benefit of a contract is the ability to verify that **AlertService sent the expected message** without needing a network connection or looking at console output. Create a second file **ContractDemoTest.java** alongside ContractDemo.java:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ContractDemoTest {
    static final class RecordingSender implements MessageSender {
        final List<Message> sent = new ArrayList<>();

        @Override
        public void send(Message message) {
            sent.add(message);
        }
    }

    public static void main(String[] args) {
        RecordingSender fake = new RecordingSender();
        AlertService service = new AlertService(fake);

        service.notifyUser("tester", "Da gui thong bao");

        Message expected = new Message("tester", "Da gui thong bao");
        if (fake.sent.size() != 1 || !fake.sent.get(0).equals(expected)) {
            throw new AssertionError("Sai so lan gui hoac noi dung");
        }
        System.out.println("PASS: 1 message");
    }
}
~~~

Compile and run (both files in the same directory, with no package declaration):

~~~bash
javac -encoding UTF-8 ContractDemo.java ContractDemoTest.java
java ContractDemoTest
~~~

Output:

~~~text
PASS: 1 message
~~~

RecordingSender is a **test double/fake**: it conforms to the same interface, but replaces actual sending with recording calls. The test above proves that the consumer creates and forwards the right message; it **does not prove** that EmailSender can connect to SMTP or that the email provider is working. Real implementations require separate tests for their external integrations and behavioral rules.

## 8. Contract Changes and Compatibility

A contract is the connection point between multiple parts of the codebase, so changing it can affect both consumers and implementations:

1. **Adding an abstract method to an interface**: existing implementing classes will typically have to add the method; otherwise, compilation errors will occur upon rebuilding.
2. **Adding a default method**: this can preserve source compatibility for many implementations, yet you still need to consider default-method conflicts, default semantics, and the different types of compatibility (source/binary/behavioral).
3. **Changing parameter types, method names, or return types**: this can force both consumers and implementations to modify their code; its impact must be assessed rather than treating it as an internal change.
4. **Changing behavior while keeping the signature unchanged**: this is also a contract change. For example, switching from "throw an exception when sending fails" to "ignore errors" can cause consumers to handle things incorrectly, even though the code still compiles.

A safe way to extend a contract is to describe expectations first, review all implementations, run contract and consumer tests, and only then put the new API into use. If a specialized capability is needed for only a few implementations, consider creating a separate contract rather than forcing all existing classes to carry methods that are invalid for them. This is the idea behind segregating interfaces according to the actual needs of their users.

For published libraries, compatibility must be evaluated against both already-compiled code and clients outside the repository; you should not conclude a change is "compatible" merely because an internal Java project still builds.

## 9. Common Pitfalls and How to Self-Check

| Mistake | Consequence | How to Fix |
| --- | --- | --- |
| Consumer declares a field with a concrete implementation and instantiates it with new | Tightly coupled to one technology; hard to replace | Accept a parameter of the contract type in a constructor or method |
| Interface has a generic name but contains too many unrelated methods | Implementing classes are forced to have meaningless operations | Split contracts by consumer group or capability |
| Assuming implements guarantees correct business behavior | An implementation may return wrong values, swallow errors, or cause unexpected side effects | Document the behavioral contract and test each implementation |
| Casting from an interface to a concrete class to call a specific API | Swapping implementations can cause a ClassCastException or break logic | Move genuinely shared capabilities into an appropriate interface or separate the flow |
| Using an abstract class just to reuse a few utility lines | Locked into a single superclass; forced inheritance | Consider composition or an appropriate utility |
| Using a default method to hide risky behavior | Older implementations silently inherit unwanted behavior | Use only when the default makes contractual sense and is tested |
| Testing only with a fake and declaring integration successful | Misses infrastructure/IO failures and implementation differences | Separate consumer unit tests from implementation integration/contract tests |

When reading a piece of Java code that uses an interface, ask yourself:

1. **What is the contract?** Which methods is the consumer allowed to call, and what behavioral rules have been committed to?
2. **What is the implementation?** Which classes declare implements or inherit from a base class, and which part contains the real processing?
3. **What is the consumer?** What type does it use to declare its dependency? Does it know any implementation details?
4. **What handles the wiring?** Where is the concrete object created, and how is it delivered to the consumer?
5. **Can the implementation be swapped?** If you replace EmailSender with RecordingSender or ConsoleSender, does the business logic run as expected without modification?
6. **What evidence confirms it?** Do the compilation command, sample output, consumer unit tests, and implementation behavioral/integration tests each answer their own specific questions?

## 10. Summary of Practical Mindset

Good design starts from the **consumer's needs**: define a small, easy-to-understand API along with the necessary behavioral guarantees; provide one or more implementations; and then pass an implementation into the consumer through the contract. **The interface describes the capability, the implementation provides the mechanism, the consumer handles the business logic, and the wiring layer selects the actual object.**

This structure proves effective when you need polymorphism, strategy substitution, environment configuration, independent testing, and dependency management. It does not replace behavioral specification, real-world testing, or choosing sensible module boundaries.
