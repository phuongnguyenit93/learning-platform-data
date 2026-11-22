# Splitting Interfaces by Usage Needs and Avoiding Overly Large Interfaces

The Interface Segregation Principle (ISP), often translated as the **interface segregation principle**, is the letter I in the SOLID principles. This principle states that a client should not be forced to depend on methods that it does not use. When an interface bundles too many capabilities that are not relevant to all callers, implementing classes may have to provide meaningless methods, while clients must know about a contract broader than their actual needs.

In Java, ISP can be applied by designing small interfaces with a clear purpose based on client roles or a unified business capability. A class can still implement multiple interfaces if it genuinely supports multiple capabilities. The goal is not to create an interface for each method, but to let each client depend only on the contract it needs.

## 1. The Problem with an Overly Large Interface

Imagine an office application that has a basic printer, a scanner, and a multifunction device. If every device must implement a single interface containing `print`, `scan`, and `fax`, the basic printer has to declare even the operations it does not support.

~~~java
interface OfficeMachine {
    void print(String document);
    String scan();
    void fax(String number, String document);
}

class BasicPrinter implements OfficeMachine {
    @Override
    public void print(String document) {
        System.out.println("Print: " + document);
    }

    @Override
    public String scan() {
        throw new UnsupportedOperationException("Scanning is unavailable");
    }

    @Override
    public void fax(String number, String document) {
        throw new UnsupportedOperationException("Fax is unavailable");
    }
}
~~~

This is an example illustrating a problematic design. The code can still compile, but the `OfficeMachine` contract declares that every implementation can scan and fax, whereas `BasicPrinter` cannot perform those two operations. A client that only needs printing still has to depend on an interface describing both scanning and faxing. As the interface continues to grow, each implementation may have to add empty methods, throw exceptions, or provide dummy behavior to satisfy the contract.

Common signs of an overly large interface:

- Some implementations only support a subset of the methods, while the other methods must be left empty or throw `UnsupportedOperationException`.
- Changing a group of methods can cause many unrelated classes to be modified or recompiled.
- A client receives a general type and then has to check the actual type using `instanceof` or cast it to find the capability it needs.
- Test doubles or mocks have to implement many methods unrelated to the behavior under test.
- The interface name is too generic, such as `Manager`, `Service`, or `Worker`, yet it contains multiple groups of responsibilities that do not share the same role.

An interface with many methods does not necessarily violate ISP. The problem arises when different clients depend on different parts of the contract and have to carry unnecessary methods.

## 2. Splitting by Capability or Client Role

Instead of forcing every device to use one shared contract, define smaller interfaces based on truly meaningful capabilities:

~~~java
interface Printable {
    void print(String document);
}

interface Scannable {
    String scan();
}

interface Faxable {
    void fax(String number, String document);
}
~~~

Now, the basic printer only implements `Printable`. The multifunction device can implement `Printable`, `Scannable`, and `Faxable`. A client that wants to print only needs to accept a `Printable`, without needing to know whether that device can scan or fax.

~~~java
class BasicPrinter implements Printable {
    @Override
    public void print(String document) {
        System.out.println("Print: " + document);
    }
}

class OfficeMfp implements Printable, Scannable, Faxable {
    @Override
    public void print(String document) {
        System.out.println("Print: " + document);
    }

    @Override
    public String scan() {
        return "scanned-page";
    }

    @Override
    public void fax(String number, String document) {
        System.out.println("Fax " + document + " to " + number);
    }
}
~~~

These interfaces describe the contracts that clients need. A class can combine multiple capabilities by implementing multiple interfaces; there is no need to create one large interface to represent every possible device combination.

### How Does ISP Change Dependency Relationships?

Before splitting, a print-only method might require `OfficeMachine`, causing the client to depend on both scanning and faxing:

~~~java
void printReport(OfficeMachine machine) {
    machine.print("report.pdf");
}
~~~

After splitting, the method only requires the printing capability:

~~~java
void printReport(Printable printer) {
    printer.print("report.pdf");
}
~~~

Both `BasicPrinter` and `OfficeMfp` can be passed to `printReport`. The client does not need a conditional branch to ask whether the device supports scanning or faxing. The parameter contract accurately expresses what the method needs.

## 3. Complete Java 17+ Example

Save the following code snippet into a file named `InterfaceSegregationDemo.java`. The example uses nested interfaces inside the demo class so that only a single source file is needed and it can run standalone.

~~~java
public class InterfaceSegregationDemo {
    interface Printable {
        void print(String document);
    }

    interface Scannable {
        String scan();
    }

    interface Faxable {
        void fax(String number, String document);
    }

    static final class BasicPrinter implements Printable {
        @Override
        public void print(String document) {
            System.out.println("Print: " + document);
        }
    }

    static final class OfficeMfp implements Printable, Scannable, Faxable {
        @Override
        public void print(String document) {
            System.out.println("Print: " + document);
        }

        @Override
        public String scan() {
            return "scanned-page";
        }

        @Override
        public void fax(String number, String document) {
            System.out.println("Fax " + document + " to " + number);
        }
    }

    static void printReport(Printable printer) {
        printer.print("report.pdf");
    }

    static void scanDocument(Scannable scanner) {
        System.out.println("Scan: " + scanner.scan());
    }

    public static void main(String[] args) {
        Printable basicPrinter = new BasicPrinter();
        printReport(basicPrinter);

        OfficeMfp mfp = new OfficeMfp();
        printReport(mfp);
        scanDocument(mfp);
        mfp.fax("555-0100", "invoice.pdf");
    }
}
~~~

Compile and run with JDK 17 or later:

~~~text
javac --release 17 InterfaceSegregationDemo.java
java InterfaceSegregationDemo
~~~

Exact stdout output:

~~~text
Print: report.pdf
Print: report.pdf
Scan: scanned-page
Fax invoice.pdf to 555-0100
~~~

The example illustrates three points:

1. `BasicPrinter` only needs to implement `Printable`; it does not declare operations that the device does not support.
2. `OfficeMfp` combines three capabilities by implementing three independent interfaces.
3. `printReport` and `scanDocument` accept different types matching each client's exact needs. The printing method does not depend on the scanning or faxing contract.

The nested types inside `InterfaceSegregationDemo` are member interfaces and classes declared using Java syntax. They are accessed in the example by their simple names because they reside within the same enclosing class. This is a complete runnable program; the snippets in the earlier sections are code fragments used to explain the design.

## 4. How ISP Relates to Cohesion and Change

Splitting interfaces helps reduce the scope of dependencies. When a client only accepts `Printable`, changing the `Scannable` contract alone usually does not require changing the signature or logic of the printing client. This allows loosely related parts to evolve more independently.

ISP also helps contracts exhibit cohesion: methods placed in the same interface should serve one role or a group of clients with closely aligned needs. If two groups of clients change for different reasons and only use separate groups of methods, that is a signal to consider splitting the interface.

| Aspect | Overly Large Interface | Segregated Interface |
| --- | --- | --- |
| Client contract | Depends on multiple capabilities at once | Depends on the capability currently needed |
| Implementation | May have to provide unsupported methods | Only implements capabilities it actually has |
| API changes | Easily affects unrelated classes | Usually limited to the relevant group of clients |
| Testing | Mocks may need many redundant methods | Mocks are small and closely aligned with the behavior under test |
| Feature combination | One interface represents every combination | Classes combine multiple interfaces when needed |

ISP does not guarantee that every change affects only a single class. If a client genuinely needs multiple capabilities, or multiple interfaces change together due to a shared business concept, they can still depend on one another. This principle helps choose the right dependency boundaries rather than trying to eliminate all relationships.

## 5. Distinguishing ISP from Related Principles

The **Single Responsibility Principle (SRP)** focuses on the reason for a module or class to change. The **Interface Segregation Principle (ISP)** focuses on the contract that a client depends on. The two principles are related but not synonymous: a class can have a clear responsibility while still implementing an overly broad interface; conversely, a small interface does not by itself guarantee that an implementation has only one responsibility.

The **Dependency Inversion Principle (DIP)** is about having high-level and low-level modules depend on appropriate abstractions. ISP helps keep those abstractions small and closely matched to client needs. A small interface can still be misused if a high-level client depends on an inappropriate abstraction.

The **Open/Closed Principle (OCP)** encourages extending behavior without having to continually modify stable code. Capability-based interfaces can make adding new implementations easier, but splitting interfaces by itself does not guarantee OCP.

Keep in mind: ISP asks "must the client depend on methods it does not need?", whereas SRP asks "what unrelated reasons to change does this module have?".

## 6. Do Not Split Interfaces Mechanically

ISP does not require creating a separate interface for every method. Excessive splitting increases the number of types to understand, naming, relationships between abstractions, and maintenance overhead. Methods should stay together if they express a meaningful contract and are commonly used together by clients.

For example, an `InputStream` contract does not become better simply by splitting `read()` and `close()` into separate interfaces in every case. The two operations can belong to the same abstraction because a stream's lifecycle and usage are closely tied together. Decisions should be based on client needs and contract semantics, not merely on method count.

Avoid the following splitting patterns:

- **One interface per getter or setter** when they only create many fragmented types without expressing independent roles.
- **Empty interfaces or overly vague names** just to force classes into a hierarchy.
- **Splitting while still requiring clients to depend on all interfaces** through an unnecessary parameter or composite abstraction.
- **Using `instanceof` or casting everywhere** to discover hidden capabilities. If a client needs a capability, it should directly request the interface that represents that capability.
- **Keeping dummy methods** that return `null`, perform no-op work, or throw exceptions just so a class satisfies an interface.
- **Splitting tightly coupled business operations**, forcing the client to orchestrate a workflow on its own that ought to be one consistent contract.

A composite interface is still useful if a specific client genuinely needs all of the capabilities. You can define `interface MultifunctionDevice extends Printable, Scannable, Faxable {}` to name that combination. Print-only clients should still accept `Printable`; they do not need to depend on `MultifunctionDevice`.

## 7. Designing Interfaces Around Client Needs

A practical process for applying ISP:

1. **List the clients.** Identify the classes, services, or use cases that call the current contract.
2. **Mark the methods used.** Build a client–method table to see the actual groups of needs; do not assume every client needs every method.
3. **Find meaningful contract groups.** Group methods by role, capability, or related client group.
4. **Create specialized interfaces.** Choose names that express the behavior the client requires, such as `Printable`, `Scannable`, `Clock`, or `MessageSender`.
5. **Adjust implementations.** Have each class implement the interfaces corresponding to its actual capabilities. If a class supports multiple roles, implement multiple interfaces.
6. **Narrow parameter and field types.** Let each client depend on the smallest interface that fulfills its job.
7. **Test the important behaviors.** Verify that clients only invoke the capabilities they need and that implementations fulfill their contracts properly.
8. **Review public APIs.** If the current interface is already used by external parties, plan a compatible migration rather than deleting or changing the contract abruptly.

For example, an initial needs table might look like this:

| Client | Print | Scan | Fax |
| --- | --- | --- | --- |
| `ReportPrinter` | Yes | No | No |
| `ArchiveService` | No | Yes | No |
| `LegacyFaxSender` | No | No | Yes |
| `OfficeConsole` | Yes | Yes | Yes |

The first three clients only need interfaces corresponding to a single capability. `OfficeConsole` can accept multiple interfaces or accept a composite abstraction if the design genuinely needs all three. This table is a needs-analysis tool, not a rule that every column must become a new interface.

## 8. ISP in Testing and Extensibility

Small interfaces often make test doubles easier to write. If a service only needs to print reports, a test can provide a fake implementation of `Printable` without having to create scanning and faxing behaviors. The test therefore focuses on the contract that is actually relevant.

Similarly, when adding a new device type, the new class can implement precisely the capabilities it supports. A network printer only needs `Printable`; a document feeder might need `Scannable`; a multifunction device implements multiple interfaces. There is no need to modify all existing implementations just because the system adds an independent capability.

However, ISP does not replace contract testing. A class declaring `implements Printable` can still print incorrectly or fail to follow the intended meaning of the method. An interface defines the shape of the contract at the type level; tests and documentation define the expected behavior.

## 9. Considerations When Changing an Existing API

If a public library already has `OfficeMachine`, removing the interface or changing method signatures can break library users' code. In that case, consider:

- Adding small interfaces such as `Printable` and `Scannable`, and having existing implementations implement them.
- Providing adapters to help clients transition from the old contract to the new contract.
- Keeping the old interface during a transition period if binary or source compatibility is required.
- Marking the old API as deprecated once there is a clear removal strategy, while guiding users to migrate to the new contract.
- Not silently changing the meaning of old methods or returning dummy results just to fit the new design.

Whether to keep the old interface and how to bridge it with the new interfaces depends on the actual API. There is no single compatible migration approach for every library; check existing clients and the level of compatibility the project commits to.

## 10. Common Design Mistakes and How to Address Them

| Symptom | Possible Cause | How to Address |
| --- | --- | --- |
| Multiple implementations throw `UnsupportedOperationException` | The interface requires capabilities that some classes do not have | Split the contract by capability; let classes implement only supported capabilities |
| Clients cast to a concrete class | The parameter type does not express the capability the client actually needs | Move the capability into its own interface and accept that interface as the parameter |
| Adding a method to an interface forces many unrelated classes to change | Clients or implementations depend on an overly broad contract | Inspect method groups and segregate them by stable needs |
| Too many single-method interfaces | Splitting syntactically rather than based on roles | Combine methods with closely related semantics and usage needs |
| Composite interfaces appear everywhere | Every client depends on the large combination even when using only part of it | Use the composite type only for clients that need all capabilities |
| API modifications break library users | Changing a public contract without a compatibility path | Add appropriate interfaces, adapters, or a deprecation plan |

A `default` method in Java can help an interface evolve compatibly in some cases, but it does not solve the design problem on its own. If clients still depend on a large contract with many unrelated capabilities, the interface boundaries need to be reconsidered. Similarly, turning a method into a `default` method and leaving implementations doing nothing can hide the problem rather than fix it.

## 11. Checklist Before Accepting an Interface

- Does the interface name describe a specific role or capability?
- Must a client using the interface know about methods it does not need?
- Can implementations fulfill the full intended meaning of the contract they declare?
- Are any methods frequently left empty, returning dummy results, or throwing exceptions because they are unsupported?
- Do different clients use distinct groups of methods?
- Is a composite interface needed for some clients while other clients only need small interfaces?
- Does splitting confusingly increase the number of abstractions without reducing actual dependencies?
- If a public interface is already in use, does the migration plan preserve the required level of compatibility?
- Can tests provide simple implementations of the needed contract without mocking many redundant capabilities?

ISP is a principle for designing dependency boundaries. Let clients declare their needs using small, meaningful interface types; let implementing classes combine the capabilities they genuinely support. This approach makes contracts easier to understand, keeps implementations honest about their capabilities, and makes changes less likely to ripple into unrelated parts.
