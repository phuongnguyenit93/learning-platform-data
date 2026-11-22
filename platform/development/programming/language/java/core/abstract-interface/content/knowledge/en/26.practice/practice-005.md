# Splitting a Large Interface into Small Roles

Splitting a large interface into small interfaces by role is a way to apply the **Interface Segregation Principle (ISP)** — the interface segregation principle in SOLID. This principle advises that a client should not be forced to depend on operations it does not use. Instead of a single interface covering all system capabilities, create small contracts with clear meaning tied to each group of needs.

For example, a multifunction device can print, scan, and send faxes. But a basic printer only has printing capability. If both are forced to implement the same `Machine` interface with all three methods, the basic printer class has to provide unsupported methods or throw artificial exceptions. Splitting the contract into `Printable`, `Scannable`, and `Faxable` helps each class commit only to the capabilities it actually has.

## 1. What Does ISP Say?

Robert C. Martin describes ISP along the lines that clients should depend on small interfaces tailored to their needs. A large interface might group many methods together because they belong to the same real-world object, but that does not necessarily mean they belong to the same software contract.

ISP does not require every interface to have only one method. The goal is to group related methods that are typically used together by the same group of clients. An interface with multiple methods is still reasonable if they form a consistent role.

This principle can be expressed through three questions:

- Which operations does this client actually need to call?
- When a new capability is added to the interface, which clients are forced to change even though they do not use that capability?
- Can each implementation properly fulfill all the methods it commits to?

If a group of clients uses only a small part of the interface and the remaining parts change independently, the interface may be taking on too many roles.

## 2. Signs of an Overly Large Interface

Imagine a `Machine` contract with the methods `print()`, `scan()`, and `fax()`. The following signs indicate that splitting should be considered:

- A class supports only a subset of the methods and has to throw `UnsupportedOperationException` or return dummy values for the remaining methods.
- Clients use only some of the methods yet still depend on the entire interface. Adding a new method can force unrelated clients or implementations to modify their code.
- Groups of methods change for different reasons. For example, document scanning capability changes depending on the scanner type, while fax sending capability depends on communication configuration.
- Implementations require different dependencies to satisfy the methods. A simple printer should not have to configure a fax service.
- Testing becomes confusing because a fake implementation has to declare many behaviors unrelated to the scenario being tested.

An interface with many methods is not a problem by itself. If every implementation needs all the methods and the methods belong to a cohesive contract, splitting the interface may only add extra complexity.

## 3. From One Large Interface to Role-Based Interfaces

Before splitting, the design typically looks like this:

```text
Machine
  ├── print(document)
  ├── scan()
  └── fax(document, destination)

BasicPrinter implements Machine
  └── only has print capability

OfficeMultifunctionDevice implements Machine
  ├── print
  ├── scan
  └── fax
```

With this design, `BasicPrinter` must declare scan and fax behavior even though the hardware does not support it. If implemented with exceptions, any client calling the wrong method only discovers the issue at runtime. If empty methods are used, errors may be hidden.

After splitting by role:

```text
Printable     Scannable     Faxable
     ^             ^            ^
     |             |            |
BasicPrinter   Scanner      FaxDevice

OfficeMultifunctionDevice implements
Printable, Scannable, Faxable
```

A class can implement multiple small interfaces if it genuinely provides multiple capabilities. A client that only needs printing can depend on `Printable`; it does not need to know whether the object can scan or send faxes.

## 4. Complete Java Example

The following program demonstrates three role-based interfaces, a print-only printer, a multifunction device, and services that depend on the minimal contract they require.

Save all the code into `Main.java`:

```java
interface Printable {
    void print(String document);
}

interface Scannable {
    String scan();
}

interface Faxable {
    void fax(String document, String destination);
}

final class BasicPrinter implements Printable {
    @Override
    public void print(String document) {
        System.out.println("print:" + document);
    }
}

final class OfficeMultifunctionDevice
        implements Printable, Scannable, Faxable {
    @Override
    public void print(String document) {
        System.out.println("print:" + document);
    }

    @Override
    public String scan() {
        return "scanned-page";
    }

    @Override
    public void fax(String document, String destination) {
        System.out.println("fax:" + document + "->" + destination);
    }
}

final class PrintService {
    private final Printable printer;

    PrintService(Printable printer) {
        this.printer = printer;
    }

    void printInvoice(String invoice) {
        printer.print(invoice);
    }
}

final class ScanService {
    private final Scannable scanner;

    ScanService(Scannable scanner) {
        this.scanner = scanner;
    }

    void archive() {
        System.out.println("scan:" + scanner.scan());
    }
}

public class Main {
    public static void main(String[] args) {
        Printable basic = new BasicPrinter();
        PrintService printService = new PrintService(basic);
        printService.printInvoice("invoice-42");

        OfficeMultifunctionDevice office =
                new OfficeMultifunctionDevice();
        new ScanService(office).archive();
        office.fax("contract-7", "555-0100");
    }
}
```

Compile and run with Java 17 or later:

```text
javac Main.java
java Main
```

Exact stdout output:

```text
print:invoice-42
scan:scanned-page
fax:contract-7->555-0100
```

### Why Does This Design Satisfy ISP?

- `BasicPrinter` only implements `Printable`. It does not need to declare scan or fax methods.
- `OfficeMultifunctionDevice` implements all three interfaces because it genuinely provides all three capabilities.
- `PrintService` accepts an object of type `Printable`. This service does not need to depend on a scanner or fax.
- `ScanService` only requires `Scannable`. You can pass a standalone scanner or a multifunction device into the service without changing the service's code.
- The services receive dependencies via constructors. This is simple constructor injection: the dependency is expressed directly in the contract that the client needs.

The key point is that the parameter type accurately reflects the client's needs. If `PrintService` accepted `OfficeMultifunctionDevice` directly, the service would depend on a concrete implementation and lose the benefits of small interfaces.

## 5. Process for Splitting an Interface in a Real-World Project

Do not split interfaces merely by counting methods. Start from the clients and actual behavior:

1. **List the clients.** Identify which classes or modules use the interface, and record the methods each client actually calls.
2. **Group methods by role.** Find methods that serve the same need, change for the same reason, or are typically used together.
3. **Define small contracts.** Create an interface for each meaningful role, with a name expressing a capability or responsibility such as `Readable`, `Writable`, `Searchable`, or `Exportable`.
4. **Update client dependency types.** Have each client accept the smallest interface sufficient to perform its job. Prefer receiving dependencies through a constructor or method rather than creating the implementation inside the client.
5. **Update implementations.** A class implements only the roles it actually supports. A class that needs multiple roles can implement multiple interfaces.
6. **Remove fake behavior.** Once the small interfaces are in place, review empty methods or exceptions that only existed because the old interface was too broad.
7. **Test by role and contract.** Verify that the client works with every valid implementation of the interface it requires, including fake implementations in unit tests.
8. **Evaluate complexity after splitting.** If a new interface is used in only one place and does not represent a meaningful boundary, consider merging it back.

When refactoring a running system, you can keep the old interface as a temporary compatibility layer and have existing implementations implement the new small interfaces. After clients are migrated to the new contracts, remove the old interface in a controlled change if no consumers still depend on it. Maintaining compatibility depends on the project's public API requirements and versioning rules.

## 6. Design Principles to Remember

**Interfaces should be small per client, not necessarily per object.** A physical device can do many things, but a client placing a print order only needs printing capability. Design contracts around client needs while ensuring interface names and behaviors remain meaningful in the problem domain.

**Split by capability and responsibility, not mechanically method by method.** Creating one interface per method is sometimes useful, but it can also make the system hard to understand if certain operations always go together. ISP calls for right-sized contracts, not the maximum number of interfaces.

**An interface is not a place to declare every conceivable capability.** Only add a method when it belongs to the contract's responsibility. If an optional capability can be modeled as a separate role, clients that do not need that capability will not have to depend on it.

**An implementation can combine multiple roles.** Java allows a class to implement multiple interfaces. Splitting interfaces does not force splitting an object into multiple classes if those capabilities truly belong to the same object and share the same lifecycle.

**ISP complements the Dependency Inversion Principle (DIP).** DIP aims for depending on abstractions rather than concrete implementations; ISP keeps those abstractions from being too broad for the client. The two principles complement each other: a client depending on an abstract interface that contains too many methods can still be affected by unrelated changes.

## 7. When Should You Keep a Large Interface?

Keeping the interface as-is can be a good choice if:

- The methods form a cohesive contract and most valid implementations need them.
- Clients typically use nearly all the methods together.
- Splitting the interface increases the number of types, names, and forwarding classes without reducing actual dependencies.
- The interface is a stable public API and the cost of breaking compatibility outweighs the benefit of splitting immediately. You can plan smaller APIs for the next version or add new abstractions while preserving a compatibility path.

Do not confuse a class having many methods with an ISP violation. You need to examine the relationship between clients, contracts, and changes in the system.

## 8. Common Mistakes

- **Splitting by count instead of responsibility:** an interface with one method is not necessarily better than an interface with three related methods.
- **Creating an interface just to avoid a dependency on paper:** if the client still calls many other broad abstractions, the dependency issue may remain unresolved.
- **Keeping clients dependent on concrete implementations:** splitting interfaces while services still declare parameters using the multifunction class diminishes the benefits.
- **Letting unsupported methods return `null` or do nothing:** this hides contract violations and creates hard-to-find bugs. You should accurately define the capabilities that an implementation commits to.
- **Over-fragmenting:** too many interfaces with blurred boundaries make it hard for readers to know which type to use. Name them by role and keep related methods together.
- **Changing a public API without checking compatibility:** external clients may be compiling against the old interface. Consider a migration strategy and compatibility testing.

## 9. Review Checklist

Before finalizing the split, check that:

- [ ] Each interface has a name that clearly describes a role or group of related behaviors.
- [ ] Each client depends only on the operations it needs.
- [ ] Each implementation can fully satisfy the contract it implements.
- [ ] There are no remaining dummy, empty, or exception-throwing methods that existed solely because the interface was too broad.
- [ ] Clients can be tested with small implementations or appropriate test doubles.
- [ ] Classes needing multiple capabilities can still implement multiple interfaces.
- [ ] Compatibility of changes with existing clients and APIs has been considered.

Splitting a large interface into small roles helps limit the impact of changes, clarify responsibilities, and make implementations easier to replace. Start with the clients that are being forced to depend on methods they do not use; then create right-sized contracts, migrate the clients to those contracts, and verify behavior through tests.
