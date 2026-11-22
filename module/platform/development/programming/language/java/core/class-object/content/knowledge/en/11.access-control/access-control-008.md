# Choosing the Least Access Level That Meets Needs in Java

## 1. Principle: Expose Only the Parts of the Program That Truly Need to Be Used

In Java, an **access modifier** determines which parts of the code are allowed to access a class, constructor, field, or method according to the language rules. When designing a class, you should not mark everything `public` merely for compilation convenience. Instead, start with **the narrowest scope that allows legitimate consumers to use it** and widen it only when there is a specific need.

This is the **least privilege / least visibility** principle in API design: an implementation detail should only be visible to the components that genuinely need it.

- An object's internal state fields are usually `private`.
- Helper methods used only within the class are usually `private`.
- Helper types or methods that **classes in the same package** must share can be **package-private**.
- Members intended for **subclass customization** can be `protected` when there is a real extension contract.
- Only members that form the **public contract of the API** should be `public`.

Choosing the least access is not a trick to shorten code; rather, it is a way to **reduce coupling, protect invariants, and preserve the ability to change the implementation** without forcing every caller to change along with it.

### A More Important Question Than “Which Modifier Makes the Code Work?”

> **Who needs to use this member — the class itself, classes in the same package, subclasses in another package, or all clients of the API?** Answer based on actual needs, then choose the appropriate access level.

A simple example:

```java
public class Wallet {
    private int balance;

    public Wallet(int openingBalance) {
        if (openingBalance < 0) {
            throw new IllegalArgumentException("negative balance");
        }
        this.balance = openingBalance;
    }

    public void deposit(int amount) {
        validatePositive(amount);
        balance += amount;
    }

    public int getBalance() {
        return balance;
    }

    private static void validatePositive(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
    }
}
```

This is a **compilable class**, without `main` yet. In this design:

- `Wallet` and the constructor are `public` because callers need to create a wallet.
- `deposit` and `getBalance` are `public` because callers need to perform valid operations and read the result.
- `balance` is `private` so callers **cannot directly assign a negative number** or bypass the validation process.
- `validatePositive` is `private static` because only the implementation needs it. Being `static` here does not determine access; rather, it indicates that the helper does not need receiver state.

There is no reason to make `balance` or `validatePositive` `public` just because another class “might need” them later.

## 2. The Four Access Levels and Their Usage Scopes

The table below applies to **members of a class** in a typical Java context:

| Access | Within the same class / valid nest | Other class in the same package | Subclass in another package | Non-inheriting client in another package |
| --- | --- | --- | --- | --- |
| `private` | Yes | No | No under normal subclass relationships | No |
| No modifier (*package-private*) | Yes | Yes | No via inheritance alone | No |
| `protected` | Yes | Yes | Yes, subject to **special protected rules** | No |
| `public` | Yes | Yes | Yes | Yes, if the enclosing type/package/module is accessible |

**Commonly used scope ordering for reasoning:** `private` → package-private → `protected` → `public`. However, this is **not** a simple linear subset model for every expression: in particular, `protected` in **another package** has constraints on the subclass context and receiver type. When analyzing a specific line, you must apply Java's rules rather than relying solely on a “broader” diagram.

### Two Notes You Cannot Overlook

1. A **top-level class** may only use `public` or **package-private**. Writing `private class X` or `protected class X` at the top level is a compile-time error. A **member class** inside a class can use all four levels.
2. **The access of a class, its constructors, and its methods/fields are three separate checks.** A `public` class can declare a `private` constructor or a `private` method; being able to see the class name does **not** mean you can instantiate an object or call all of its methods.

Access modifiers are not an encryption mechanism or a barrier against all forms of reflection. They are **part of the language's access-control contract**, which is crucial for architecture and API stability.

## 3. Process for Choosing an Access Modifier Based on Actual Needs

Whenever you add a declaration, ask in order:

1. **Does this member serve the implementation of a single class?** If yes, prefer `private`.
2. **Are there classes in the same package that need to call or share it?** If yes, and they intentionally form the same functional module, consider **package-private**.
3. **Is there a contract for subclasses in other packages to override or access it?** Only when there is a clear need for extension, consider `protected`.
4. **Must code outside the package use it directly?** If yes, consider `public`, typically through a stable API with validated behavior.
5. **Is it a top-level class or a member class?** Top-level classes cannot be `private`/`protected`; if you truly want a private helper type, you can turn it into a **private nested class**.
6. **Do callers need access to the class without creating instances?** Consider a `private` or package-private constructor, accompanied by an explicit factory.
7. **Can a public field be replaced with a method that expresses business behavior?** If so, protect the field and expose only the necessary behavior.
8. **Would broader access cause callers to depend on the implementation?** If so, keep it behind an internal boundary.
9. **Have you tried compiling clients in the intended packages and subclasses that need to be supported?** Do not guess from intuition.
10. **If using named modules (JPMS), is the package exported?** `public` is still subject to module boundaries.

A practical approach is to **start by writing a narrow scope** and then compile the clients intended to be allowed access. When an access error occurs, examine **whether the client should really depend on that declaration**, instead of immediately widening it to `public`.

## 4. Why Is `private field` Usually Better Than `public field`?

Consider a risky design:

```java
public class BankAccount {
    public int balance;
}
```

If other classes can assign `account.balance = -100000;`, the `BankAccount` class can hardly guarantee the “non-negative balance” invariant. Later, if you want to add logging, transaction fees, validation, or access permissions, every place directly writing to the field may have to be modified.

Design following encapsulation:

```java
public class BankAccount {
    private int balance;

    public BankAccount(int openingBalance) {
        if (openingBalance < 0) {
            throw new IllegalArgumentException("opening balance is negative");
        }
        balance = openingBalance;
    }

    public void deposit(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("deposit must be positive");
        }
        balance += amount;
    }

    public int balance() {
        return balance;
    }
}
```

**Why does this make sense?**

- Callers see the **behavior** `deposit` without needing to know how the field is stored.
- `private int balance` limits the places where the field can be modified directly in the Java source.
- Validation has a single place of control.
- The implementation can be migrated later to a different structure while still preserving `deposit(int)` and `balance()` if the API contract does not change.

**Not every class needs a getter/setter for every field.** A public `setBalance(int x)` setter that performs no validation can **defeat the very purpose** of a private field. Expose **the necessary business behavior**, rather than automatically exposing every assignment capability.

### Standalone Program Confirming the Protection Scope

Create the file **`MinimalVisibilityDemo.java`**:

```java
class BankAccount {
    private int balance;

    BankAccount(int openingBalance) {
        if (openingBalance < 0) {
            throw new IllegalArgumentException("negative opening balance");
        }
        balance = openingBalance;
    }

    void deposit(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("positive amount required");
        }
        balance += amount;
    }

    int balance() {
        return balance;
    }

    private void resetForInternalTest() {
        balance = 0;
    }
}

public class MinimalVisibilityDemo {
    public static void main(String[] args) {
        BankAccount account = new BankAccount(100);
        account.deposit(25);

        System.out.println(account.balance());

        // account.balance = -20;  // Error: field balance is private.
        // account.resetForInternalTest(); // Error: private method.
    }
}
```

Compile and run:

```bash
javac MinimalVisibilityDemo.java
java MinimalVisibilityDemo
```

**Standard output:**

```text
125
```

The intentionally invalid lines are commented out, so the program is valid. Here, `BankAccount` is a top-level **package-private** class, and the constructor and `deposit`/`balance` methods are also package-private because the client program `MinimalVisibilityDemo` resides in **the same default package** and does not require a public API. In a real application with clients in other packages, `public` may be needed for the type, constructor, and business methods.

**Takeaway:** even for the same class design, access scope should be chosen based on **actual usage locations**, rather than mechanically assuming that constructors or every getter must be public.

## 5. `private method`: Starting with Helpers That Only Serve the Implementation

Suppose the scoring, normalization, and validation steps are called only within a single class. Those steps are not a public promise to clients.

```java
class RegistrationService {
    String register(String rawName) {
        String name = normalize(rawName);
        checkName(name);
        return "registered:" + name;
    }

    private static String normalize(String raw) {
        return raw == null ? "" : raw.trim();
    }

    private static void checkName(String name) {
        if (name.isEmpty()) {
            throw new IllegalArgumentException("name required");
        }
    }
}
```

This is a **valid class declaration**, without `main`. `register` is **package-private** because in this hypothetical example only code in the same package needs to call it. The two helpers `normalize` and `checkName` are private: callers must not depend on those internal steps.

### When Should You Consider Widening from Private to Package-Private?

Only when a client in the same package **genuinely** needs that behavior, and sharing it reflects a sensible functional module boundary. If multiple classes need the same normalization operation, you can:

- Keep it private if sharing would expose architecturally inappropriate details and the classes should call a higher-level API.
- Extract it into a **package-private helper class/method** if it is genuinely a utility for the same package.
- Make it `public` only when it is a public API with a stable contract that external clients need.

Do not widen access simply because an arbitrary test happens to be in another package; prioritize testing behavior through the public API, or structure your test scope appropriately, before exposing the implementation.

## 6. Package-Private: Sharing Within a Package Without Exposing an External API

The package-private level is especially useful when a package serves as **a collaborative unit** among a few classes:

```text
src/
  shipping/
    ShippingService.java
    FeeCalculator.java
  app/
    Main.java
```

**File `src/shipping/FeeCalculator.java`:**

```java
package shipping;

final class FeeCalculator {
    private FeeCalculator() {
    }

    static int feeFor(int weight) {
        if (weight < 0) {
            throw new IllegalArgumentException("negative weight");
        }
        return weight <= 5 ? 10 : 20;
    }
}
```

`FeeCalculator` is a top-level **package-private** class. The `feeFor` method is also package-private. The constructor is private because the helper only has static methods and does not need to be instantiated. `final` prevents the class from being subclassed; it **does not make the class private**.

**File `src/shipping/ShippingService.java`:**

```java
package shipping;

public class ShippingService {
    public int quote(int weight) {
        return FeeCalculator.feeFor(weight);
    }
}
```

`ShippingService` is the public API. It uses the same-package helper without needing to expose the name `FeeCalculator` externally.

**File `src/app/Main.java`:**

```java
package app;

import shipping.ShippingService;
// import shipping.FeeCalculator; // Invalid: package-private.

public class Main {
    public static void main(String[] args) {
        ShippingService service = new ShippingService();
        System.out.println(service.quote(3));
        System.out.println(service.quote(8));

        // FeeCalculator.feeFor(3); // Not accessible from package app.
    }
}
```

Compile/run from the root directory containing `src`:

```bash
javac -encoding UTF-8 -d out src/shipping/FeeCalculator.java src/shipping/ShippingService.java src/app/Main.java
java -cp out app.Main
```

```text
10
20
```

Design result: the code in `app.Main` depends only on the `ShippingService` public API; the fee-calculation detail `FeeCalculator` can change its name, structure, or implementation without requiring clients to import that type.

### A Package Does Not Mean a Parent Folder or Subpackage

`shipping` and `shipping.internal` are **two different packages**. If `FeeCalculator` is moved to `shipping.internal`, `ShippingService` can no longer automatically access the package-private type, even though the two packages share a common name prefix. When organizing packages, plan ahead for the **sharing boundaries** you want.

**Package-private is not reserved solely for top-level classes.** Methods, constructors, instance fields, and member classes declared without a modifier are also package-private. Use it where needed, rather than turning every helper into a top-level class out of habit.

## 7. `protected`: Expose Only for Designs Intended to Support Inheritance

`protected` may seem like an option “between private and public”, but using it arbitrarily can cause subclasses to depend on the internal implementation. Therefore, `protected` should only be chosen if the class is **intentionally designed for extension**.

An example of a template method:

```java
abstract class ReportGenerator {
    public final String generate() {
        String data = loadData();
        return "Report: " + data;
    }

    protected abstract String loadData();
}
```

Here, `generate()` is the stable public API and `final` keeps the workflow from being overridden; `loadData()` is an **extension point** designed for subclasses to provide. `protected` makes sense because clients should not call the internal step directly, yet subclasses need to implement it.

### Compile/Run Example Within One Package

File **`ProtectedExtensionDemo.java`**:

```java
abstract class ReportGenerator {
    public final String generate() {
        String data = loadData();
        return "Report: " + data;
    }

    protected abstract String loadData();
}

class MonthlyReport extends ReportGenerator {
    @Override
    protected String loadData() {
        return "October";
    }
}

public class ProtectedExtensionDemo {
    public static void main(String[] args) {
        ReportGenerator report = new MonthlyReport();
        System.out.println(report.generate());
    }
}
```

```bash
javac ProtectedExtensionDemo.java
java ProtectedExtensionDemo
```

```text
Report: October
```

**Meaning of the access levels:**

- `generate` is public because callers need to receive the report; it is `final` to protect the designed processing sequence.
- `loadData` is protected because subclasses must override it; callers only need `generate()`.
- `MonthlyReport.loadData` remains `protected`, rather than narrowing it to package-private or private.
- `MonthlyReport` is a top-level package-private class in the example file; in a real library, if clients outside the package need to instantiate it, you can provide an appropriate concrete public type/factory.

**Do not automatically replace `private` with `protected` just so subclasses can read every field.** When a subclass genuinely needs data, it is usually better to use a protected **behavioral method** with a clear contract rather than a protected mutable field that tightly couples subclasses to the superclass's layout/state.

### Protected in Another Package Has Receiver Rules

Suppose a superclass declares `protected int number`. A subclass in another package can access `this.number` in an appropriate context, but **cannot** use an arbitrary receiver of the superclass type to read `other.number` if the special conditions for cross-package protected access are not met.

Therefore, when designing a protected API for subclasses, try compiling an example with the **subclass in another package**, matching the intended extension target; do not test only in the same package and generalize from that.

## 8. Public API: Only the Part Committed to External Clients

A declaration should be `public` when clients in other packages have a legitimate reason to use it **directly**. This is a communication commitment, not a way to make the compiler “stop reporting access errors”.

An example of an order API:

```java
public final class Order {
    private final String id;
    private boolean paid;

    public Order(String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id required");
        }
        this.id = id;
    }

    public String id() {
        return id;
    }

    public void markPaid() {
        if (paid) {
            throw new IllegalStateException("already paid");
        }
        paid = true;
    }

    public boolean isPaid() {
        return paid;
    }

    private void clearInternalCache() {
        // Serves the implementation only when genuinely needed.
    }
}
```

In the example:

- `Order` is public because clients need to name the type.
- The constructor is public so clients can create valid orders; if tighter control over object creation is desired, a factory can replace it.
- The `id`, `markPaid`, and `isPaid` methods are public because they are the **promised behavior/API**.
- `id` and `paid` are private because clients should not modify them directly.
- `clearInternalCache` is private because it is not a capability clients need.

The example code is a **valid class declaration**, saved in `Order.java` if used. `clearInternalCache` is currently unused; in real code, if a helper is no longer needed, remove it rather than maintaining a useless method.

**Making a method public creates an expectation of stability**: callers outside the package can depend on its name, signature, exceptions, and behavior. Narrowing its access later can prevent client code from compiling or break linkage at runtime depending on the context. Therefore, the public surface must be managed as an API product.

## 9. Constructors: Being Able to See a Type Does Not Mean `new` Is Allowed

A constructor has its own access level and is not inherited like an instance method.

### Utility Classes That Do Not Need Instances

```java
public final class MathHelpers {
    private MathHelpers() {
    }

    public static int square(int value) {
        return value * value;
    }
}
```

`MathHelpers` is a public top-level class; `square` is the public static API; the constructor is private so callers neither need to nor can instantiate a `MathHelpers` object outside the allowed scope. `final` prevents subclassing, not access.

### Controlled Creation via a Factory

```java
public final class UserId {
    private final String value;

    private UserId(String value) {
        this.value = value;
    }

    public static UserId of(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("invalid user id");
        }
        return new UserId(value);
    }

    public String value() {
        return value;
    }
}
```

Here, clients cannot call `new UserId("...")` from code outside the class, but they can call `UserId.of("U01")`. A factory allows validating, normalizing, caching, or changing the object-creation strategy without exposing the constructor.

### Standalone Runnable Example

File **`FactoryVisibilityDemo.java`**:

```java
final class UserId {
    private final String value;

    private UserId(String value) {
        this.value = value;
    }

    static UserId of(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("invalid id");
        }
        return new UserId(value.trim());
    }

    String value() {
        return value;
    }
}

public class FactoryVisibilityDemo {
    public static void main(String[] args) {
        UserId id = UserId.of(" A7 ");

        System.out.println(id.value());
        // UserId other = new UserId("A7"); // Error: constructor is private.
    }
}
```

```bash
javac FactoryVisibilityDemo.java
java FactoryVisibilityDemo
```

```text
A7
```

`UserId` is top-level package-private in the demonstration program because only clients in the same file/package use it; the `of` factory is also package-private for the same reason. If extracted into a library for other packages, expose `UserId` and `of` publicly while still keeping the constructor `private`.

### A Default Constructor Can Accidentally Open the Door to Object Creation

If a class declares no constructors, the compiler may provide a **default constructor**. For an ordinary `public class Utility { }`, the default constructor has the corresponding access level of public. If a class contains only static helpers and does not need instances, writing an explicit private constructor avoids situations where clients create meaningless objects.

On the other hand, do not create a private constructor in a class intentionally supporting inheritance if doing so prevents subclasses from calling the superclass constructor. For a framework extension point, you can use a `protected` constructor with a clear contract.

## 10. Top-Level Classes and Member Classes: Access Levels Can Differ

For a **top-level class**, Java only allows:

- `public class X { }`
- `class X { }` — package-private.

Not allowed:

```java
// private class X { }   // Invalid at the top level.
// protected class Y { } // Invalid at the top level.
```

For a **member class** inside a class:

```java
public class DocumentService {
    public static class Result {
        public final String message;

        public Result(String message) {
            this.message = message;
        }
    }

    protected static class ExtensionHook {
    }

    static class PackageHelper {
    }

    private static class InternalParser {
    }
}
```

All four access levels **can be valid**, provided they satisfy the other class rules. Here, the nested classes are declared `static` because they do not need an enclosing `DocumentService` instance; being static or non-static does not determine the access modifier.

**How to choose:**

- `Result` is public if clients must use that specific result type.
- `ExtensionHook` is protected if the API is genuinely intended for subclass extension and constructor/method accessibility conditions have been accounted for.
- `PackageHelper` is package-private if only peers in the same package need it.
- `InternalParser` is private if it is purely an implementation detail of the enclosing class.

Do not make all member classes public just because the outer class is public. And if the outer class itself is package-private, making a member class public does not automatically make the name `Outer.Member` accessible from another package.

## 11. Type, Constructor, and Method Access Are Three Separate Checks

A common API mistake is making a nested type public while forgetting the constructor's access level:

```java
package example;

public class Catalog {
    public static class Entry {
        Entry() {
        }

        public String name() {
            return "entry";
        }
    }
}
```

From another package, code can **name the type** `Catalog.Entry`, but cannot instantiate it with `new Catalog.Entry()` because the explicit `Entry()` constructor is package-private.

If clients need to instantiate `Entry`, declare `public Entry()` or provide an accessible factory. If clients should only **read Entry instances provided by Catalog**, keeping the constructor narrow can be the right intention.

Similarly, an instance method without a modifier inside a public class is still **package-private**. The modifier of the enclosing type does not automatically apply to all its members.

### A Checklist Before Using `public`

Check the following:

1. Does the client truly need to know **the concrete class name**, or does it only need an interface/supertype?
2. Does the client need to call the **constructor** directly, or is a factory sufficient?
3. Does the client need to call the **method**, or does it only need the result of a higher-level method?
4. If a member returns an inaccessible type, does the client need to name that type? It can be replaced with a public interface or an appropriate DTO.
5. When expanding the API, is there a stable contract for clients to rely on?

These three separate layers help you choose the right access level without exposing the entire implementation.

## 12. Do Not Create a Public Setter for Every Private Field

A class with a private field but an unconditional public setter can still allow callers to break invariants:

```java
class Product {
    private int quantity;

    public void setQuantity(int quantity) {
        this.quantity = quantity;
    }
}
```

If a negative quantity is invalid, the setter above allows callers to create an invalid state. A better design might be:

```java
class Product {
    private int quantity;

    Product(int quantity) {
        if (quantity < 0) {
            throw new IllegalArgumentException("negative quantity");
        }
        this.quantity = quantity;
    }

    void addStock(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("positive amount required");
        }
        quantity += amount;
    }

    int quantity() {
        return quantity;
    }
}
```

The two versions of `Product` are **two independent declarations for comparison** and are not meant to be placed together in the same source set. In the second version, callers perform only meaningful operations; the class protects its own invariant.

**Least visibility means choosing both the scope and the kind of behavior to expose**, not merely adding the `private` keyword to every field and mechanically generating getters and setters.

## 13. Encapsulation and Object References: A Private Field Can Still Expose Mutable State

Keeping a field `private` is not enough if a public getter directly returns the mutable object that the field references.

A risky example:

```java
import java.util.List;

class UnsafeGroup {
    private final List<String> names;

    UnsafeGroup(List<String> names) {
        this.names = names;
    }

    List<String> names() {
        return names;
    }
}
```

Even though the field is private, callers that hold a reference to the list through the constructor or getter can continue mutating **the same list object**. Access control restricts **syntactic access paths to the field**, but it does not automatically make the referenced object immutable.

### Standalone Program: Defensive Copy

File **`EncapsulationCopyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

class Group {
    private final List<String> names;

    Group(List<String> input) {
        this.names = new ArrayList<>(input);
    }

    List<String> names() {
        return List.copyOf(names);
    }

    void add(String name) {
        names.add(name);
    }
}

public class EncapsulationCopyDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("An");

        Group group = new Group(source);
        source.add("Binh");

        System.out.println("source=" + source);
        System.out.println("group=" + group.names());

        group.add("Chi");
        System.out.println("group=" + group.names());
    }
}
```

```bash
javac EncapsulationCopyDemo.java
java EncapsulationCopyDemo
```

```text
source=[An, Binh]
group=[An]
group=[An, Chi]
```

The constructor creates its own `ArrayList`, isolating structural changes to the caller's list from the internal list. The getter returns `List.copyOf(names)` instead of handing out the original mutable list directly. This is a shallow copy with respect to elements; for immutable `String` elements as in this example it is suitable, whereas for mutable element objects you must still consider whether each element needs to be copied.

**Connection to access levels:** private fields and defensive copying both serve encapsulation, but they address **two different problems**: permission to name the field in source code and aliasing of mutable objects.

## 14. Public Interfaces and Implementations: Expose the Contract, Hide the Details

When clients do not need to depend on a concrete class, a public interface can serve as a good API boundary:

```java
interface Notifier {
    void send(String message);
}

final class ConsoleNotifier implements Notifier {
    @Override
    public void send(String message) {
        System.out.println("sent:" + message);
    }
}
```

This is a **valid class/interface declaration** in the same package, without `main` yet. In a larger program with clients in other packages, the interface would be declared `public` in its own file (following the file-naming rule), while the concrete implementation can remain **package-private** if it is provided through a factory.

When implementing a public interface method, the implementing method must be **public** and cannot be narrowed to package-private or protected. `@Override` lets the compiler verify your intent.

### Runnable Example Demonstrating a Factory Returning an Interface

Create the file **`NotifierDemo.java`**:

```java
interface Notifier {
    void send(String text);
}

final class ConsoleNotifier implements Notifier {
    @Override
    public void send(String text) {
        System.out.println("notify:" + text);
    }
}

final class NotifierFactory {
    private NotifierFactory() {
    }

    static Notifier create() {
        return new ConsoleNotifier();
    }
}

public class NotifierDemo {
    public static void main(String[] args) {
        Notifier notifier = NotifierFactory.create();
        notifier.send("ready");

        // The client does not need to instantiate ConsoleNotifier itself.
    }
}
```

```bash
javac NotifierDemo.java
java NotifierDemo
```

```text
notify:ready
```

Here, all helper top-level types are package-private because the single-file example only has a client in the same package. In a multi-package library, you can make `Notifier` a public interface and provide a public factory API, while keeping `ConsoleNotifier` package-private as an implementation detail.

Choosing a **public interface + hidden implementation** allows changing how notifications are sent (console, file, network) while callers still only know `Notifier.send`. You should not create an interface just for the sake of “having an interface”; it is useful when you genuinely need abstraction/multiple implementations or a stable dependency boundary.

## 15. `protected field` Is Often a Choice That Makes an API Hard to Maintain

Suppose a superclass has:

```java
class BaseCounter {
    protected int count;
}
```

Subclasses can depend directly on how `count` is stored. If you later change the storage to an `AtomicInteger`, a computed property, or data split across multiple fields, you may have to modify the subclasses.

A better approach:

```java
abstract class BaseCounter {
    private int count;

    protected final void addCount(int delta) {
        if (delta < 0) {
            throw new IllegalArgumentException("negative delta");
        }
        count += delta;
    }

    public final int count() {
        return count;
    }
}
```

Now subclasses are given **controlled extension behavior** via `addCount` rather than direct assignment to the field. The `protected final` method is part of the extension contract: subclasses can call it when access is valid, but cannot override it to bypass validation.

Of course, adding a protected method still increases the API surface for subclasses. If not even subclasses need that access, keep the method `private` rather than “opening it up just in case”.

## 16. `private` Does Not Prevent Valid Access Within the Enclosing Class and Nest

A private nested class can be used normally by its enclosing class:

File **`PrivateHelperDemo.java`**:

```java
public class PrivateHelperDemo {
    private static class Formatter {
        private static String format(int value) {
            return "[" + value + "]";
        }
    }

    public static String display(int value) {
        return Formatter.format(value);
    }

    public static void main(String[] args) {
        System.out.println(display(42));
    }
}
```

```bash
javac PrivateHelperDemo.java
java PrivateHelperDemo
```

```text
[42]
```

`Formatter` is a private member class; code inside the enclosing `PrivateHelperDemo` is permitted to call the private helper according to the relevant rules. However, external clients cannot use `PrivateHelperDemo.Formatter` as a public type.

**Do not confuse `private` with “only code inside that nested class's own body can access it”.** In Java, enclosing/nestmate relationships have corresponding private access rules; this allows a public class to use private nested helpers without having to expose an API to external callers.

A static nested class does not need an enclosing instance; a non-static member inner class has an appropriate enclosing instance. The rules for **static vs. inner** are independent of **private vs. public**.

## 17. `public` at the Module Level: Package Exports Boundaries Are Still Needed

In Java 9+ with named modules, a `public` top-level class in an **unexported package** may not be accessible from another module when using the module path.

Example configuration:

```java
module store.core {
    exports store.api;
}
```

The `store.core` module exports only `store.api`. A `public class StoreService` in `store.api` can provide an API for a client module that properly depends on it; a public class in `store.internal` **does not automatically become an external module API** when that package is not exported.

A client module can declare:

```java
module store.client {
    requires store.core;
}
```

The two snippets above are **illustrative contents of `module-info.java`**, not Java classes with `main`. They show the need to design **two layers of visibility**:

1. Java access modifiers on types/members.
2. Module boundaries and package exports/requires, if using JPMS.

`exports` does not turn package-private types into public ones; it allows **public types** in the package to be accessed according to module rules. `opens` mainly relates to deep reflection; it is not a replacement keyword for `public` in normal source code.

**Design tip:** if an internal package does not need to be used by other modules, do not export it. Do not broaden exports just so “every public class can be used” if that is not the intended API.

## 18. Is Testing a Valid Reason to Increase Visibility?

This is a practical question: if a private helper is hard to test directly, should it be changed to public?

**Usually, you should not widen it to public just to test an implementation detail.** Instead, consider:

- **Testing through the public/protected contract**: test the behavior that API consumers are allowed to observe, without tightly coupling tests to helper details.
- **Package-private seam**: if a piece of logic has an independent role and multiple classes in the same package genuinely need to use it, a package-private helper can be both sound design and easy to test in the appropriate package.
- **Extracting responsibilities into a separate type**: if a private helper is large enough to need many independent tests, the class may be taking on too much responsibility.
- **Dependency injection/strategy**: if you need to swap dependencies in tests, create an appropriate abstraction instead of exposing all state.
- **Avoid using reflection to call private members merely for convenience**: tests that depend too deeply on the implementation will be brittle during refactoring.

There is no rule that every private method must have a direct unit test. What typically needs to be tested is the class's **behavioral contract**; implementation details can be verified indirectly if coverage is sufficient.

### Testing in the Same Package Is Not Necessarily a Design Flaw

For a package-private class/method, tests can be declared in the same package to access it. This can be reasonable when the package is an implementation unit that needs verification. However, if the actual module imposes other restrictions, the test/runtime configuration must be taken into account; do not arbitrarily change every modifier just to work around a build configuration.

## 19. When Should You Not Use `private` at All Costs?

“Least access that meets needs” does not mean “everything is private”. There are legitimate needs that require a broader scope:

- **Methods implementing a public interface** must be accessible according to the contract, typically `public`.
- **Genuinely supported subclasses** need extension points with an appropriate scope, which may be `protected`.
- **Peer classes in the same package** that need to use a package-level helper make package-private appropriate.
- **A public API** needs external clients to use its types, constructors, and methods for their intended purpose.
- **Frameworks/serializers/DI** may have their own access requirements; read the framework's contract and choose a level that is just sufficient, rather than exposing all data by default.
- **Simple data models** such as a public record can intentionally expose component accessors according to their contract; there is no reason to hide everything behind a complex wrapper layer.

**Decision point:** a broader scope must have a **clearly stated usage reason**. If you write `protected` or `public` without being able to explain which client or subclass needs it, reconsider the design.

## 20. Access Modifiers and Overriding: You Cannot Arbitrarily Narrow Access

If a superclass has a `public` method and a subclass overrides it, the overriding method **must not reduce** the access to `protected`, package-private, or `private`.

Example:

```java
class Parent {
    public String title() {
        return "parent";
    }
}

class Child extends Parent {
    @Override
    public String title() {
        return "child";
    }
}
```

The subclass is valid because it keeps `public`. If you change the method in `Child` to `protected String title()`, the compiler reports an error for reducing visibility. For a protected superclass method, a subclass may keep `protected` or **widen it to `public`** if appropriate, but cannot narrow it to package-private/private.

**Why?** Clients holding a variable of type `Parent` must continue to be able to call the public method according to the supertype contract, regardless of which subclass the runtime object belongs to. If overrides were allowed to narrow access, API substitutability would be broken.

### A Superclass `private` Method Is Not an Extension Point

`private void work()` cannot be overridden normally by a subclass. A subclass declaring `void work()` with the same name/signature may be defining a **new method**, rather than overriding the parent's private method. The `@Override` annotation helps catch this mistake.

When designing a base class, **do not open a private method up to protected merely because you “want subclasses to override it for flexibility”** if the workflow does not actually support changing that behavior. Every protected overridable method is an extension contract that must be maintained.

## 21. Read-Only Fields, Constants, and Minimal Access

For a constant that is genuinely a public part of the API, `public static final` can be used:

```java
public final class Protocol {
    public static final int VERSION = 2;

    private Protocol() {
    }
}
```

However, you should not expose a mutable static field publicly:

```java
// public static int retryCount = 3;
// External code can assign any value if the class is accessible.
```

With a mutable reference, `public static final List<String> NAMES` does **not** guarantee an immutable list: `final` only forbids reassigning the field, while the elements/structure can still change if the list supports mutation.

Usually better:

```java
public final class Defaults {
    private static final java.util.List<String> INTERNAL =
            java.util.List.of("A", "B");

    private Defaults() {
    }

    public static java.util.List<String> names() {
        return INTERNAL;
    }
}
```

`List.of` returns an unmodifiable list by contract. In this example, the elements are immutable Strings, so this API can return that list directly without allowing callers to modify its structure. However, an unmodifiable list containing mutable objects **does not automatically make the elements immutable**.

**Selection principle:** make a constant public only when it belongs to the real contract; keep mutable state private and control changes through an appropriate API. An “uppercase” constant name does not provide access control.

## 22. Pros and Cons of Changing Scope Later

If a declaration is promoted from `private` to `public`, much client code may begin depending on it. When it needs to be narrowed again, that change can break the library's source compatibility or binary compatibility.

| Decision | Benefits | Trade-offs to consider |
| --- | --- | --- |
| Keep `private` | Easy to refactor details, protects invariants | Clients that genuinely need it must go through the API |
| Use package-private | Collaboration within the package, avoids expanding external API | Dependencies among classes in the same package still need to be managed |
| Use `protected` | Supports selective subclass extension | Expands the inheritance contract; harder to change implementation |
| Use `public` | Easy to use from any accessible client | Broad API contract, may be difficult to narrow later |

**Best practice:** when exposing a declaration, treat it as an architectural decision that requires justification. When narrowing access, audit all legitimate callers and API compatibility; in a released library, consider a migration path rather than abruptly changing modifiers.

## 23. Common Misconceptions

| Misconception | Correct understanding |
| --- | --- |
| “Making every method public is most convenient” | Increases coupling and the contract that must be maintained |
| “Every private field must have a getter/setter” | Expose only necessary behaviors; setters can break invariants |
| “Omitting a modifier means private” | No: that is package-private |
| “Package-private works only within a single file” | Usable by appropriate code in **the same package** |
| “A subpackage is the same package” | `x.y` is different from `x.y.z` |
| “Protected can only be accessed by subclass code” | Code in the same package can also access protected members |
| “Protected allows subclasses in another package to access via any Base receiver” | There are specific cross-package/receiver constraints |
| “A top-level class can be private to hide it” | No; top-level classes can only be public or package-private |
| “A public class automatically has a public constructor even if a no-arg constructor is written” | An explicit constructor without a modifier is package-private |
| “A public nested class is automatically accessible even if the outer class is not” | The entire chain of enclosing types must be considered |
| “A private nested class is useless because the outer class cannot use it either” | Enclosing classes/nestmates have appropriate private access |
| “`static` is an access level” | `static` is not an access modifier |
| “`final` on a reference makes a mutable object immutable” | Only prevents reassigning the variable/field; immutability must be designed separately |
| “A public field is safe if clearly named” | Callers can still modify it and bypass validation |
| “A `private final List` cannot be modified by callers” | If the mutable list is shared via an alias, callers can still mutate that object |
| “Changing to protected for direct testing is always right” | Testing is one factor, not an automatic reason to expand the extension surface |
| “An interface implementation can narrow a public method” | Overrides/implementations must preserve valid access |
| “A public type in an unexported JPMS package is automatically usable by other modules” | Exports/requires boundaries still apply |
| “Access modifiers guarantee security against all reflection” | These are primarily language-level access checks; reflection/modules have separate rules |
| “Minimizing public at all costs is the best design” | Must be balanced against genuine client/subclass needs |

## 24. Comprehensive Practice: Encapsulation Based on Needs

Consider this problem: an order management system has:

- An `Order` type that code in other packages must instantiate and pay.
- Order-code validation logic needed only inside `Order`.
- An `OrderFormatter` class used only by other classes **in the same package**.
- No requirement for subclasses to override the payment workflow.
- A `Receipt` result type that external callers may name and read information from.

Proposal:

1. `Order` is a **public top-level class**.
2. The state fields of `Order` are **private**.
3. The constructor and the `pay` method are **public** if callers need them.
4. The internal validation method is **private**.
5. `OrderFormatter` is a **package-private top-level class** if multiple classes in the same package need it; if only `Order` needs it, a private nested helper can be used.
6. `Receipt` is a **public static nested class** (or public top-level type) if callers must name it; the constructor can be narrowed when only `Order` creates it.
7. `protected` is unnecessary when the class is not designed for subclassing.

### Single-File Runnable Example for the Core Behavior

File **`OrderAccessDemo.java`**:

```java
import java.util.Objects;

final class Order {
    private final String code;
    private boolean paid;

    Order(String code) {
        this.code = requireCode(code);
    }

    private static String requireCode(String raw) {
        Objects.requireNonNull(raw, "code");
        if (raw.isBlank()) {
            throw new IllegalArgumentException("blank code");
        }
        return raw;
    }

    Receipt pay() {
        if (paid) {
            throw new IllegalStateException("already paid");
        }
        paid = true;
        return new Receipt(code);
    }

    static final class Receipt {
        private final String code;

        private Receipt(String code) {
            this.code = code;
        }

        String display() {
            return "paid:" + code;
        }
    }
}

public class OrderAccessDemo {
    public static void main(String[] args) {
        Order order = new Order("O-1");
        Order.Receipt receipt = order.pay();

        System.out.println(receipt.display());
        // order.paid = false; // Error: private field.
        // Order.Receipt r = new Order.Receipt("x"); // Error: private constructor.
    }
}
```

```bash
javac OrderAccessDemo.java
java OrderAccessDemo
```

```text
paid:O-1
```

**Why are `Order` and `Receipt` package-private in the demo?** In a single-file program, there is no demand from other packages, so keeping them just sufficient is appropriate. When turning the example into a library for clients in other packages, you must make `Order` a `public` top-level class in `Order.java`, adjust the access of the constructor/`pay`, and if clients need to name `Receipt`, declare `public static final class Receipt` with a public accessor method. You should still keep `code`, `paid`, and the validation helper private; the `Receipt` constructor can stay private so only `Order` creates instances.

This exercise deliberately distinguishes between **the minimal access for a same-package example** and **the required access for a multi-package API** — demonstrating how to choose scope based on actual consumers.

## 25. Self-Check: 15 Questions with Answers

**Question 1.** If a field is only used to store the internal state of an object, which access level should be considered first?

**Answer:** `private`; provide an appropriate behavior API if callers need to interact with it.

**Question 2.** Does a helper method called only by methods of the same class need to be public?

**Answer:** No. It should usually be `private`.

**Question 3.** What should be chosen for a top-level helper used only by multiple classes in the same package?

**Answer:** A package-private top-level class is the natural choice if no public API is needed.

**Question 4.** Can you write `private class Parser { }` at the file level?

**Answer:** No. A top-level class can only be public or package-private. If you want a private helper type, use a private member class inside an appropriate class.

**Question 5.** Is `protected` the default choice for any class where “maybe there will be subclasses later”?

**Answer:** No. Expose members as protected only when there is a specific extension contract.

**Question 6.** Why can a public getter that directly returns a mutable list break encapsulation?

**Answer:** Callers can mutate **the same list object** through the alias even though the field holding the reference is declared private.

**Question 7.** Does `final List<String> names` guarantee that no one can modify the list?

**Answer:** No. `final` prevents reassigning the variable/field; mutability depends on the list object itself.

**Question 8.** A public class has `X() {}` without writing public; can a caller in another package call `new X()`?

**Answer:** No. An explicit constructor without a modifier is package-private.

**Question 9.** A class implements an interface with a public method contract; can the implementation be marked protected?

**Answer:** No. Access cannot be reduced compared to the public method contract.

**Question 10.** Can a `protected field` in a superclass always be read via `other.field` from a subclass in another package?

**Answer:** No. There are specific receiver rules for protected access via a subclass in another package.

**Question 11.** If the package `shop.internal` is not exported from a named module, is `public class Helper` automatically accessible from another module?

**Answer:** Not under normal module access; appropriate exports/requires declarations are also needed.

**Question 12.** When clients need to create an object without needing to know its constructor, what technique is used?

**Answer:** A public static factory with a private/package-private constructor is one option.

**Question 13.** Should you expose an unconditional `setBalance(int)` setter just because the `balance` field is private?

**Answer:** No. You should expose business behavior with appropriate validation, such as `deposit(int)`.

**Question 14.** Why can narrowing the access of a public API member cause problems?

**Answer:** Clients that already depend on the previous accessibility may fail to compile or fail to link against the new version.

**Question 15.** What is the ultimate criterion for choosing an access level?

**Answer:** **The smallest legitimate usage need** of callers, the package, or subclasses combined with the ability to protect invariants and stabilize the contract; not “which modifier makes the error go away fastest”.

## 26. Code Review Checklist: Have You Exposed Too Much?

Before approving a new class or changing an access modifier, check:

- [ ] Is a top-level class public only if clients outside the package need to use it directly?
- [ ] Are non-public helper types kept appropriately as package-private/private members?
- [ ] Does every instance field truly need to be public/protected, or is private sufficient?
- [ ] Are public getters/setters genuinely part of the API contract, and do they protect invariants?
- [ ] Does the constructor need to be public, or is a static factory or narrower access more appropriate?
- [ ] Are private methods kept private if only the implementation uses them?
- [ ] Are methods/package helpers made package-private only when the same package genuinely needs them?
- [ ] Do protected methods/constructors have a documented extension contract, and have they been tested with a subclass in another package?
- [ ] Does the public API have return types/parameters that are accessible to intended clients?
- [ ] Do overrides follow the rule of not reducing visibility?
- [ ] Is mutable internal state exposed via references, arrays/lists, or getters?
- [ ] Are `final`/`static`/`abstract` being confused with access modifiers?
- [ ] Is package-private being misunderstood as applying to subpackages?
- [ ] If using JPMS, are only the necessary API packages exported?
- [ ] Does the access change require a migration/compatibility review?
- [ ] Was access widened merely for test convenience instead of fixing the design?
- [ ] Is any client code depending on an implementation helper when it should be calling a higher-level API?
- [ ] Have examples/access checks been run from the perspective of an actual consumer?

---

**Final takeaway:** **Choosing the least access level that meets needs** means defining the boundaries of the class contract. Use `private` to keep the implementation and state internal; package-private to collaborate within a package; `protected` when there is a legitimate need for subclass extension; and `public` when external clients must be supported. Top-level classes have only public and package-private; member classes have all four levels. Do not widen access just to quickly resolve a compilation error if doing so forces clients to depend on implementation details or forfeits the ability to protect invariants. Good design means **exposing only the necessary behavior and keeping the rest inside**.
