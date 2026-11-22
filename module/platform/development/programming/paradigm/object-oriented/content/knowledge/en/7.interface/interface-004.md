# One object implementing multiple interfaces in Java

An office device may **print**, **scan documents**, and **report its status**. Someone printing only needs the printing capability; someone scanning only needs scanning. Java lets **one object fulfill multiple behavioral contracts** by allowing its class to `implements` multiple `interface` types.

The key point is that each `interface` describes a **role or capability**, not necessarily a separate object. One instance can be used simultaneously through several reference variables with different interface types, and all operations still affect **the same instance**.

## 1. Core syntax

~~~java
interface Printable {
    void print(String document);
}

interface Scannable {
    String scan(String pageId);
}

class OfficeMachine implements Printable, Scannable {
    @Override
    public void print(String document) {
        System.out.println("In: " + document);
    }

    @Override
    public String scan(String pageId) {
        return "PDF:" + pageId;
    }
}
~~~

~~~java
OfficeMachine machine = new OfficeMachine();

Printable printer = machine;
Scannable scanner = machine;

printer.print("Báo cáo");
System.out.println(scanner.scan("HD-001")); // PDF:HD-001
~~~

Here:

- `OfficeMachine` is **one concrete class** implementing two interfaces.
- `new OfficeMachine()` creates **only one OfficeMachine object**.
- `printer` and `scanner` are **two reference variables**, each viewing the object through a different contract.
- A `Printable` variable exposes only the public behaviors available through the `Printable` contract (and other members callable under the type rules), even if the actual object can also scan.
- At runtime, Java invokes the concrete class's implementation of `print` or `scan`.

Assigning an object to two interface variables does not create two separate “halves” of the object. This is **interface polymorphism**: one instance can be treated as several contract types.

## 2. Complete example: one machine, multiple roles

Create **`MultipleInterfacesDemo.java`**. The example runs on Java 11+ and uses only the Java standard library.

~~~java
import java.util.Objects;

public class MultipleInterfacesDemo {

    interface Printable {
        void print(String document);
    }

    interface Scannable {
        String scan(String pageId);
    }

    interface StatusReadable {
        String status();
    }

    static final class OfficeMachine
            implements Printable, Scannable, StatusReadable {

        private final String machineId;
        private int printedPages;
        private int scannedPages;

        OfficeMachine(String machineId) {
            String checked = Objects.requireNonNull(
                    machineId, "machineId").trim();

            if (checked.isEmpty()) {
                throw new IllegalArgumentException(
                        "Mã máy không được rỗng");
            }
            this.machineId = checked;
        }

        @Override
        public void print(String document) {
            String checked = requireText(document, "document");
            printedPages++;
            System.out.println("[PRINT] " + checked);
        }

        @Override
        public String scan(String pageId) {
            String checked = requireText(pageId, "pageId");
            scannedPages++;
            return "PDF:" + checked;
        }

        @Override
        public String status() {
            return machineId + " | printed=" + printedPages
                    + " | scanned=" + scannedPages;
        }

        private static String requireText(String value, String name) {
            String checked = Objects.requireNonNull(
                    value, name).trim();
            if (checked.isEmpty()) {
                throw new IllegalArgumentException(
                        name + " không được rỗng");
            }
            return checked;
        }
    }

    // Thành phần chỉ yêu cầu năng lực in.
    static final class PrintDesk {
        private final Printable printer;

        PrintDesk(Printable printer) {
            this.printer = Objects.requireNonNull(printer);
        }

        void printReport(String report) {
            printer.print(report);
        }
    }

    // Thành phần chỉ yêu cầu năng lực quét.
    static final class ScanDesk {
        private final Scannable scanner;

        ScanDesk(Scannable scanner) {
            this.scanner = Objects.requireNonNull(scanner);
        }

        String digitize(String pageId) {
            return scanner.scan(pageId);
        }
    }

    public static void main(String[] args) {
        OfficeMachine machine = new OfficeMachine("OFFICE-01");

        Printable printPort = machine;
        Scannable scanPort = machine;
        StatusReadable monitorPort = machine;

        System.out.println("Cùng instance: "
                + ((Object) printPort == (Object) scanPort));

        PrintDesk printDesk = new PrintDesk(printPort);
        ScanDesk scanDesk = new ScanDesk(scanPort);

        printDesk.printReport("Báo cáo tháng");
        String file = scanDesk.digitize("HD-001");

        System.out.println("Kết quả quét: " + file);
        System.out.println("Trạng thái: " + monitorPort.status());
    }
}
~~~

Run:

~~~bash
javac MultipleInterfacesDemo.java
java MultipleInterfacesDemo
~~~

Output:

~~~text
Cùng instance: true
[PRINT] Báo cáo tháng
Kết quả quét: PDF:HD-001
Trạng thái: OFFICE-01 | printed=1 | scanned=1
~~~

**What happens?**

1. `machine` references the newly created `OfficeMachine` object.
2. Assigning `printPort = machine`, `scanPort = machine`, and `monitorPort = machine` **copies reference values**; it does not call `new` again.
3. `PrintDesk` receives that object in the `Printable` role, calls `print`, and increments `printedPages`.
4. `ScanDesk` receives the same object in the `Scannable` role, calls `scan`, and increments `scannedPages`.
5. `monitorPort.status()` observes **both counters on the same object**.

Note: in production, incrementing a counter before printing or scanning succeeds may not reflect completed work. Here the methods only simulate operations using strings and the console; no real device or I/O is involved.

## 3. Class–interface relationships and objects at runtime

A class may `implements` multiple interfaces using commas:

~~~java
class OfficeMachine implements Printable, Scannable, StatusReadable {
    // ...
}
~~~

~~~mermaid
classDiagram
    class Printable {
        <<interface>>
        +print(String) void
    }
    class Scannable {
        <<interface>>
        +scan(String) String
    }
    class StatusReadable {
        <<interface>>
        +status() String
    }
    class OfficeMachine {
        -machineId String
        -printedPages int
        -scannedPages int
        +print(String) void
        +scan(String) String
        +status() String
    }
    Printable <|.. OfficeMachine
    Scannable <|.. OfficeMachine
    StatusReadable <|.. OfficeMachine
~~~

The class diagram shows **one concrete type** implementing **three contracts**. The reference diagram below, however, depicts **one existing instance**:

~~~mermaid
flowchart LR
    P["printPort: Printable"] --> M["OfficeMachine instance\nOFFICE-01\nprinted=1, scanned=1"]
    S["scanPort: Scannable"] --> M
    R["monitorPort: StatusReadable"] --> M
~~~

Do not confuse three **reference types** with three objects. An object implementing multiple interfaces can be passed to APIs requiring different types.

## 4. The declared type controls which operations may be called

Suppose:

~~~java
OfficeMachine machine = new OfficeMachine("OFFICE-02");
Printable printer = machine;
Scannable scanner = machine;
~~~

Valid calls:

~~~java
printer.print("Tài liệu A");
String result = scanner.scan("Trang B");

machine.print("Tài liệu C");
machine.scan("Trang D");
machine.status();
~~~

But:

~~~java
// printer.scan("Trang E"); // LỖI BIÊN DỊCH
// scanner.print("Tài liệu F"); // LỖI BIÊN DỊCH
~~~

The `printer` variable has the **static type** `Printable`; the compiler disallows calling `scan` through that variable because the `Printable` contract does not declare `scan`. That **does not mean** the underlying instance has lost its scanning capability.

If an API really needs both roles, define a contract type that combines the two interfaces:

~~~java
interface MultiFunctionDevice extends Printable, Scannable {
    // Kế thừa hai hợp đồng; chưa cần khai báo thêm phương thức.
}

class FullOfficeMachine implements MultiFunctionDevice {
    @Override
    public void print(String document) {
        System.out.println("In: " + document);
    }

    @Override
    public String scan(String pageId) {
        return "PDF:" + pageId;
    }
}

MultiFunctionDevice device = new FullOfficeMachine();
device.print("Kế hoạch");
System.out.println(device.scan("Trang 01"));
~~~

This is **an interface extending multiple interfaces**, which is legal in Java. It differs from a class extending multiple classes: Java **does not support a class `extends` multiple classes**.

Comparison:

| Declaration | Valid? | Meaning |
| --- | --- | --- |
| `class X implements A, B` | Yes | One class implements multiple interfaces |
| `interface C extends A, B` | Yes | Combines/inherits multiple contracts |
| `class X extends Parent implements A, B` | Yes | One direct superclass and multiple interfaces |
| `class X extends Parent1, Parent2` | No | Java disallows multiple class inheritance |
| `Printable p = new OfficeMachine(...)` | Yes | Uses a concrete instance through an interface reference |
| `new Printable()` | No | Cannot instantiate an interface directly |

## 5. Clients should only see the roles they use

`PrintDesk(Printable printer)` accepts an `OfficeMachine` or a printer-only device. If its constructor required `OfficeMachine` instead, printing would become unnecessarily coupled to that specific model's scanning and monitoring features.

~~~java
class CloudPrinter implements Printable {
    @Override
    public void print(String document) {
        System.out.println("Đưa vào hàng đợi: " + document);
    }
}

// PrintDesk desk = new PrintDesk(new CloudPrinter());
~~~

The lesson is that **one class may fulfill many roles, but each client should require only the role it needs**. Forcing a print-only device to implement `Scannable` and then throw `UnsupportedOperationException` means the contract is too broad. The *Small interfaces and role segregation* lesson explores the Interface Segregation Principle and how to divide interfaces by client needs.

## 6. Interfaces do not share instance fields

| Element | Interface | Class |
|---|---|---|
| Method contract | Yes | Can declare and implement methods |
| Per-instance state fields | No | Yes |
| Constructor | No | Yes |
| Inheriting multiple interfaces | Yes, through `extends` | Can `implements` multiple interfaces |
| Inheriting from a class | No | Can directly `extends` only one class |

That is why `OfficeMachine` stores `printedPages` and `scannedPages` in the **class**, while `Printable` and `Scannable` only expose operations clients can invoke. Abstract interface methods are implicitly `public`; implementing classes cannot reduce their accessibility. Interfaces may also contain `default`/`static`/`private` methods, but these do not create separate instance state.

The *Choosing an interface or an abstract class* lesson compares when to use an abstract class to share constructors, state, and algorithms.

## 7. Method name collisions across interfaces

A class implementing multiple interfaces may encounter methods with the same name. Distinguish between **identical abstract contracts**, **overloads with different parameters**, and **conflicting default implementations**.

### Two interfaces require the same abstract method

~~~java
interface Auditable {
    void log(String message);
}

interface Loggable {
    void log(String message);
}

class AuditConsole implements Auditable, Loggable {
    @Override
    public void log(String message) {
        System.out.println(message);
    }
}
~~~

One implementation of `log(String)` is sufficient because both interfaces require the same signature with compatible return types. The two interfaces **do not create two copies of the method** inside the object.

### Two interfaces declare overloaded methods

~~~java
interface TextWriter {
    void write(String text);
}

interface NumberWriter {
    void write(int number);
}

class Writer implements TextWriter, NumberWriter {
    @Override
    public void write(String text) {
        System.out.println(text);
    }

    @Override
    public void write(int number) {
        System.out.println(number);
    }
}
~~~

The two `write` methods have different parameter lists, so the class implements both as **overloads**.

### Two interfaces declare the same `default` method signature

This case often causes confusion:

~~~java
interface LocalLabel {
    default String label() {
        return "LOCAL";
    }
}

interface RemoteLabel {
    default String label() {
        return "REMOTE";
    }
}

// LỖI nếu bỏ override:
// class Hybrid implements LocalLabel, RemoteLabel { }
~~~

Java does not arbitrarily choose one `default`. The implementing class must resolve the conflict, for example by providing its own implementation:

~~~java
class Hybrid implements LocalLabel, RemoteLabel {
    @Override
    public String label() {
        return LocalLabel.super.label()
                + " + " + RemoteLabel.super.label();
    }
}
~~~

~~~java
Hybrid hybrid = new Hybrid();
System.out.println(hybrid.label()); // LOCAL + REMOTE
~~~

The `Hybrid.label()` method is a single implementation that explicitly combines the two defaults. If business logic requires choosing only one, the class can return one of them or provide an entirely new implementation.

**Important precedence rule:** when a superclass provides a matching instance method, the class method generally takes precedence over an interface default method with the same signature; default conflicts do not always require an override. When two defaults cannot be resolved, however, the compiler requires an explicit solution.

**Changing only the return type cannot overload** two methods with the same name and parameters. If two interfaces require incompatible return types, no valid implementation may exist; the contract design must be revised.

## 8. One object, multiple references, and casts

In the main program:

~~~java
OfficeMachine machine = new OfficeMachine("OFFICE-03");
Printable a = machine;
Scannable b = machine;
StatusReadable c = machine;
~~~

`a`, `b`, and `c` all reference **one** object, but the operations accessible through each variable differ. Assignment creates no copy of the device or its state.

We can inspect the actual type using `instanceof`:

~~~java
if (a instanceof Scannable) {
    Scannable scanner = (Scannable) a;
    System.out.println(scanner.scan("HD-002"));
}
~~~

This is valid because the object referenced by `a` really supports `Scannable`. But not every `Printable` is `Scannable`: `new CloudPrinter()` in the earlier example does not automatically support scanning. An unchecked cast can cause a `ClassCastException`.

If a method **always needs both printing and scanning**, give it a `MultiFunctionDevice` parameter or another suitable abstraction instead of accepting `Printable` and always casting to find extra features. Using `instanceof` for optional capabilities is sometimes reasonable, but overuse weakens the benefits of interface-based design.

Note the comparison in the runnable example:

~~~java
((Object) printPort == (Object) scanPort)
~~~

`==` on references checks **object identity**, not contents or contract equality. Both sides are cast to `Object` here only to make it explicit that we are comparing object identities.

## 9. Roles can provide small default operations

For example, a printing interface could define a print-twice operation **using its existing printing contract**:

~~~java
interface RepeatablePrinter {
    void print(String document);

    default void printTwice(String document) {
        print(document);
        print(document);
    }
}
~~~

A class implementing `RepeatablePrinter` only needs to define `print` to reuse the default `printTwice` behavior; calls still dispatch to the actual object's implementation. However, a default method **does not add instance fields**, and its semantics must work for every implementation (for example, “print two copies” only makes sense when calling `print` twice is valid). For `static`/`private` rules, default conflicts, and interface evolution across Java versions, see *Default members and language-specific limitations*.

## 10. Interfaces are not “multiple inheritance of state”

A Java class directly `extends` only one superclass but may `implements` multiple interfaces:

~~~java
class Device {
    protected final String serial;

    Device(String serial) {
        this.serial = serial;
    }
}

interface Printable {
    void print(String text);
}

interface Scannable {
    String scan(String pageId);
}

class AllInOne extends Device implements Printable, Scannable {
    AllInOne(String serial) {
        super(serial);
    }

    @Override
    public void print(String text) {
        System.out.println(serial + " in: " + text);
    }

    @Override
    public String scan(String pageId) {
        return serial + "/PDF/" + pageId;
    }
}
~~~

`AllInOne` inherits `serial` state from one superclass while fulfilling two contracts. It **does not** receive two sets of instance fields from the interfaces because interfaces do not have instance fields.

When a capability needs a complex independent component (such as a scanner connection or print queue), the class can use **composition**:

~~~java
class PrintEngine {
    void execute(String text) {
        System.out.println("Print engine: " + text);
    }
}

class ScanEngine {
    String execute(String id) {
        return "PDF:" + id;
    }
}

class ComposedOfficeMachine implements Printable, Scannable {
    private final PrintEngine printEngine = new PrintEngine();
    private final ScanEngine scanEngine = new ScanEngine();

    @Override
    public void print(String document) {
        printEngine.execute(document);
    }

    @Override
    public String scan(String pageId) {
        return scanEngine.execute(pageId);
    }
}
~~~

Here, **one `ComposedOfficeMachine` object** still implements both interfaces while delegating work to two component objects. Composition keeps device logic separate without requiring multiple class inheritance.

## 11. When should two roles be required on the same object?

If printing and scanning operate independently, two dependencies of types `Printable` and `Scannable` may come from **two different devices**, which is more flexible than a combined interface. If the business requirement is to print and scan **on the same device**, a `MultiFunctionDevice extends Printable, Scannable` contract expresses that constraint in the type system.

Even if a class `implements` multiple interfaces, its caller must still verify **behavioral contracts**: does `scan(pageId)` return the correct data, does `print(document)` fulfill its promise, and do methods sharing state interact unexpectedly? In this learning example, each simulated operation increments a counter once; real systems must define what constitutes a completed task.

Multiple roles are useful when each interface has independent meaning to its clients, rather than turning a class into a collection of unrelated features.

## 12. Common mistakes and how to recognize them

| Mistake | Why it is wrong | Fix |
| --- | --- | --- |
| Assuming `implements A, B` creates two objects | `implements` declares and fulfills contracts at class level | Count `new` expressions to determine how many instances are created |
| Calling `scan()` through a `Printable` variable | The declared type does not expose that method | Use `Scannable` or a combined contract type |
| Implementing interface methods with default access | Reduces the visibility of a `public abstract` method | Declare the override `public` |
| Forgetting an abstract method | The concrete class does not fulfill the contract | Implement all methods or declare the class `abstract` |
| Leaving conflicting `default` methods unresolved | Java cannot choose an arbitrary implementation | Override to resolve the conflict |
| Casting every `Printable` to `Scannable` | Some implementations can only print | Check the type when needed or design an appropriate abstraction |
| Creating an oversized interface | Classes that support only some features must add meaningless methods | Split by capabilities clients actually use |
| Placing mutable state in interface constants | Interface fields are `static final` and shared at the type level | Keep per-instance state in classes |
| Creating an interface for every class without a clear role | Increases the number of types and complexity | Extract an abstraction when substitution or a shared contract is needed |

## 13. Self-check exercises

**Question 1.** How many objects does the following code create?

~~~java
OfficeMachine m = new OfficeMachine("A1");
Printable p = m;
Scannable s = m;
StatusReadable r = m;
~~~

**Answer:** One `OfficeMachine`. The three following assignments only create reference variables/copy reference values, not new instances.

**Question 2.** Will `Printable p = new OfficeMachine("A2"); p.scan("X");` compile and run?

**Answer:** It does not compile because `Printable` does not declare `scan()`. The instance may be capable of scanning, but the compiler only considers the API available through the static `Printable` type of variable `p`.

**Question 3.** Why does `PrintDesk` accept `Printable` instead of `OfficeMachine`?

**Answer:** It only needs printing. It can therefore use `OfficeMachine`, `CloudPrinter`, or another suitable implementation without depending on a specific class.

**Question 4.** If two interfaces have the same abstract `void reset()` method, must a class implementing both define two `reset()` methods?

**Answer:** No. If signatures and return types are compatible, one public `reset()` implementation satisfies both. If two default `reset()` methods conflict, the class must explicitly resolve them.

**Question 5.** Can one interface extend both `Printable` and `Scannable`? Can a class `extends` two classes?

**Answer:** `interface MultiFunctionDevice extends Printable, Scannable` is valid. A Java class cannot `extends` two direct superclasses.

**Question 6.** Is `final class OfficeMachine implements Printable, Scannable` valid?

**Answer:** Yes. `final` prevents other classes from extending `OfficeMachine`, but does not prevent `OfficeMachine` itself from implementing multiple interfaces. Its objects can still be used as `Printable` or `Scannable`.

**Question 7.** When software needs printing and scanning, should it receive separate `Printable` and `Scannable` dependencies or a combined type?

**Answer:** It depends. If the capabilities may come from **two different devices**, independent parameters offer more flexibility. If business rules require both capabilities to belong to **the same device**, a combined contract such as `MultiFunctionDevice` makes the constraint explicit at the type level.

**Remember:** One object can play multiple roles; interfaces describe **what others may ask the object to do**, while classes determine **how the object does it and manages its state**. A class that `implements` multiple interfaces expands the contracts one instance fulfills; it neither duplicates the instance nor inherits state from multiple classes.
