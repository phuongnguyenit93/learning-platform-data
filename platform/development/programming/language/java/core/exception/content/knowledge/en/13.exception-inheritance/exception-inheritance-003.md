# Narrowing or Omitting Checked Exception Declarations When Overriding Methods in Java

When a subclass **overrides** a superclass method or **implements** a method from an interface, Java allows the new method to **declare fewer checked exceptions**, declare a **narrower checked exception type**, or **declare no checked exceptions at all**. Conversely, an overriding method must not arbitrarily widen the contract with a new or broader checked exception that the declaration on the supertype does not permit.

This is an important rule to ensure **substitutability in inheritance**: call sites working with a supertype reference will not unexpectedly have to handle a completely new checked error type just because a subclass implementation is chosen at runtime.

Core example:

```java
interface DataSource {
    String read(String key) throws java.io.IOException;
}

class FileDataSource implements DataSource {
    @Override
    public String read(String key)
            throws java.io.FileNotFoundException {
        if ("missing".equals(key)) {
            throw new java.io.FileNotFoundException(key);
        }
        return "value:" + key;
    }
}

class MemoryDataSource implements DataSource {
    @Override
    public String read(String key) {
        return "value:" + key;
    }
}
```

These are **illustrative declarations** that need to be placed in a valid Java file/package. Both implementing classes satisfy the `DataSource.read() throws IOException` contract:

- `FileNotFoundException` is a **subclass of `IOException`**, so the implementing class is allowed to declare `throws FileNotFoundException`.
- `MemoryDataSource.read()` **omits `throws IOException` completely**, so callers using the concrete type are not forced to catch checked `IOException`.
- However, if a caller holds a reference of type `DataSource`, the compiler still sees the **supertype contract `throws IOException`**, even when the runtime object is a `MemoryDataSource`.

**Remember:** this rule concerns **checked exceptions in the method contract**, not the runtime "converting" the exception object's type or guaranteeing that the subclass will never encounter an error.

## 1. Distinguishing Checked and Unchecked Exceptions

Before understanding how `throws` narrowing works, you must distinguish the two groups according to Java's checking rules.

| Group | Examples | Does the compiler require catching/declaring? |
| --- | --- | --- |
| **Checked exception** | `IOException`, `FileNotFoundException`, `SQLException`, `ParseException` | Yes, when a checked exception can escape the method and has not been handled |
| **Unchecked exception** | `RuntimeException` and its subclasses such as `IllegalArgumentException`, `IllegalStateException` | No |
| **Unchecked `Error`** | `Error` and its subclasses such as `AssertionError`, `OutOfMemoryError` | No, usually not recoverable business errors |

Partial type hierarchy:

```text
Throwable
├── Error                               (unchecked)
└── Exception
    ├── RuntimeException                (unchecked)
    │   ├── IllegalArgumentException
    │   └── IllegalStateException
    └── IOException                     (checked)
        ├── FileNotFoundException       (checked)
        └── EOFException                (checked)
```

This tree is only an **illustrative excerpt** and does not list all exception types. `SQLException` is another checked branch under `Exception`, not under `IOException`.

When saying "an override must not declare a broader exception", it should be stated more precisely:

> **An overriding method must not expand the set of checked exceptions in a way that violates the overridden method's contract.** An overriding method can still declare or throw **unchecked exceptions**; the compiler does not apply the checked-exception restriction to them in the same way.

For example, if the superclass method declares no checked exceptions, the subclass method can still write `throws IllegalStateException`, even though this is usually an optional declaration. However, that does not mean arbitrarily turning normal success conditions into runtime errors is good design.

## 2. Override Rules: Same Type, Narrower Type, or No Checked `throws`

Given a superclass method:

```java
class Parent {
    public void execute() throws java.io.IOException {
        // ...
    }
}
```

When a subclass overrides `execute()`, the declarations below are **valid** if the method body conforms to them.

### A. Keeping the same checked exception

```java
class KeepContract extends Parent {
    @Override
    public void execute() throws java.io.IOException {
        // May throw IOException.
    }
}
```

The subclass preserves the same I/O error scope that callers already know from the superclass.

### B. Narrowing to a subclass of the checked exception

```java
class NarrowContract extends Parent {
    @Override
    public void execute()
            throws java.io.FileNotFoundException {
        // Declares only a narrower checked exception type.
    }
}
```

`FileNotFoundException extends IOException`, so callers protected under `Parent`'s `IOException` contract are still able to catch the subclass exception.

### C. Omitting checked `throws` completely

```java
class NoCheckedContract extends Parent {
    @Override
    public void execute() {
        // Does not let any checked exception escape.
    }
}
```

This is a valid choice. The fact that the superclass method declares `throws IOException` **does not force the subclass to keep the same `throws` list**.

### D. Adding an unchecked exception

```java
class RuntimeFailureContract extends Parent {
    @Override
    public void execute() throws IllegalStateException {
        throw new IllegalStateException("resource not ready");
    }
}
```

This example is valid under checked-exception rules: `IllegalStateException` is unchecked. However, callers must consider the API semantics and actual failure conditions, and should not abuse unchecked exceptions to bypass design constraints.

### E. Widening the checked exception — invalid

```java
// Intentionally DOES NOT COMPILE.
class InvalidWiderContract extends Parent {
    @Override
    public void execute() throws Exception {
        // ...
    }
}
```

`Exception` covers many checked exceptions beyond `IOException`, so an existing contract cannot be replaced with a broader declaration.

### F. Adding a checked exception from a different branch — invalid

```java
// Intentionally DOES NOT COMPILE.
class InvalidNewChecked extends Parent {
    @Override
    public void execute() throws java.sql.SQLException {
        // ...
    }
}
```

`SQLException` is not a subclass of `IOException`, so callers through `Parent` are not prepared to handle that new checked exception type.

**General principle:** for every checked exception type declared by an override, there must be a corresponding checked exception type in the permitted declarations of the overridden method such that the override's type is **the same type or narrower**. At the same time, if the override's body throws another uncaught checked exception, the method body itself must still comply with its declared `throws` list.

## 3. Why Does This Rule Protect Supertype Substitutability?

Consider caller code:

```java
static void process(Parent operation) {
    try {
        operation.execute();
    } catch (java.io.IOException ex) {
        System.out.println("I/O problem");
    }
}
```

This is an illustrative method, based on the `Parent` class that has `throws IOException`. The caller receives a variable of type `Parent` and knows that the checked errors it needs to care about belong to the `IOException` family.

Suppose a subclass were allowed to override it as `throws SQLException`. When the subclass is chosen at runtime:

1. The caller only has `catch (IOException)` because that is `Parent`'s public contract.
2. The subclass could let `SQLException` escape.
3. The caller was never required to catch or declare `SQLException` when compiling against `Parent`.
4. The substitutability contract is broken.

Therefore, Java forbids **widening checked exceptions** in an override. Narrowing is safe: the caller's `catch (IOException)` still catches `FileNotFoundException` as a subclass, and if the subclass throws no checked exceptions at all, there is even less burden.

### "The subclass promises fewer errors" does not mean "the subclass cannot fail"

An implementation that declares no `throws` can still:

- Throw `IllegalArgumentException` on invalid arguments.
- Throw `IllegalStateException` when the object's state is invalid.
- Encounter `NullPointerException` due to programming bugs.
- Be affected by a serious JVM `Error`.
- Convert a caught checked error into an unchecked wrapper if the API contract allows it.

Therefore, omitting checked `throws` is a **change in the compile-time checking contract**, not a guarantee that execution will never throw any exception.

## 4. Java Checks Against the Static Type at the Call Site, Not Just the Runtime Object

A common point of confusion is that the same object can be called through two different reference types:

```java
DataSource source = new MemoryDataSource();
MemoryDataSource memory = new MemoryDataSource();
```

These are two illustrative declarations using the types defined at the beginning of the article.

When calling:

```java
source.read("item");
```

the compiler sees `source` as having the **static type `DataSource`**, so the call has the `throws IOException` contract, even though the actual object is `MemoryDataSource`.

Meanwhile:

```java
memory.read("item");
```

the compiler sees that the method declared by `MemoryDataSource` **has no checked `throws`**. Thus, this specific caller does not have to catch or declare `IOException` for that call.

Similarly, if a subclass only declares `throws FileNotFoundException`:

- Calling through the **interface or superclass type** with `throws IOException`: the caller must handle or declare `IOException`.
- Calling directly through the **subclass type** with `throws FileNotFoundException`: the caller must handle or declare `FileNotFoundException` (or a suitable supertype).
- The object thrown at runtime still retains its **actual class**; Java does not convert it into the broader declared type.

### Example that does not compile if relying only on the runtime subtype

```java
// Intentionally DOES NOT COMPILE if DataSource.read declares throws IOException.
static void incorrect(DataSource source) {
    try {
        source.read("x");
    } catch (java.io.FileNotFoundException ex) {
        System.out.println("missing");
    }
}
```

Catching only `FileNotFoundException` is not enough to cover other `IOException`s permitted by the interface. Fix it by adding `catch (IOException)` after the specific branch or declaring `throws IOException` on the calling method.

**Key takeaway:** Java enforces the contract according to the **type visible at compile time**, without needing to run the program first to know which implementation will be invoked.

## 5. Complete Java 17+ Example: Interface with a Narrowed Override and an Unchecked-Only Override

Save the following content to **`NarrowedThrowsDemo.java`**:

```java
import java.io.FileNotFoundException;
import java.io.IOException;

public class NarrowedThrowsDemo {

    interface DocumentSource {
        String load(String id) throws IOException;
    }

    static final class LocalSource implements DocumentSource {
        @Override
        public String load(String id) throws FileNotFoundException {
            if ("missing".equals(id)) {
                throw new FileNotFoundException("absent: " + id);
            }
            return "local:" + id;
        }
    }

    static final class MemorySource implements DocumentSource {
        @Override
        public String load(String id) {
            return "memory:" + id;
        }
    }

    static void viaInterface(DocumentSource source, String id) {
        try {
            System.out.println("interface value=" + source.load(id));
        } catch (IOException ex) {
            System.out.println(
                    "interface error=" + ex.getClass().getSimpleName());
        }
    }

    static void viaLocal(LocalSource source, String id) {
        try {
            System.out.println("local value=" + source.load(id));
        } catch (FileNotFoundException ex) {
            System.out.println("local error=" + ex.getMessage());
        }
    }

    static void viaMemory(MemorySource source, String id) {
        // No checked exception in this concrete declaration.
        System.out.println("memory value=" + source.load(id));
    }

    public static void main(String[] args) {
        LocalSource local = new LocalSource();
        MemorySource memory = new MemorySource();

        viaInterface(local, "missing");
        viaLocal(local, "missing");
        viaInterface(memory, "ok");
        viaMemory(memory, "ok");
    }
}
```

Compile and run with **JDK 17 or later**:

```bash
javac -encoding UTF-8 NarrowedThrowsDemo.java
java NarrowedThrowsDemo
```

**Exact stdout:**

```text
interface error=FileNotFoundException
local error=absent: missing
interface value=memory:ok
memory value=memory:ok
```

### Output analysis

**`viaInterface(local, "missing")`:** the `source` variable in the helper has static type `DocumentSource`, so the `catch (IOException)` handler matches. Dynamic dispatch selects `LocalSource.load`, throwing a `FileNotFoundException` object; the supertype handler catches it, and `getClass().getSimpleName()` reveals the actual runtime type.

**`viaLocal(local, "missing")`:** the helper accepts the concrete type `LocalSource`. The compiler knows `load` only declares checked `FileNotFoundException`; a `catch (FileNotFoundException)` handler is sufficient. The original message is printed without its type being changed.

**`viaInterface(memory, "ok")`:** the caller still uses the interface type with `throws IOException` and must account for the checked exception per the contract, but the `MemorySource.load` implementation runs successfully without throwing a checked exception.

**`viaMemory(memory, "ok")`:** the caller uses the concrete type whose method declares no checked exception, so the call requires neither `try-catch` nor `throws IOException`.

The example intentionally avoids reading a real file so that output remains consistent across machines and stays focused on the override rule.

## 6. When Is Omitting `throws` Appropriate, and When Is It Hiding Errors?

Omitting `throws IOException` from an override is valid **if the body does not let checked `IOException` escape**. For example, an in-memory implementation does not perform checked I/O, so omitting `throws` is natural.

Conversely, if the subclass actually calls an API that can throw `IOException`:

```java
class RealFileSource implements DataSource {
    @Override
    public String read(String key) {
        return java.nio.file.Files.readString(
                java.nio.file.Path.of(key));
    }
}
```

This is an example that **intentionally DOES NOT COMPILE**: `Files.readString` can throw checked `IOException`, yet the overriding method neither catches the error nor declares that checked exception type.

There are two valid fixes depending on the design:

**Keep the appropriate checked exception declaration:**

```java
@Override
public String read(String key) throws java.io.IOException {
    return java.nio.file.Files.readString(
            java.nio.file.Path.of(key));
}
```

**Or handle the checked error internally without letting it escape:**

```java
@Override
public String read(String key) {
    try {
        return java.nio.file.Files.readString(
                java.nio.file.Path.of(key));
    } catch (java.io.IOException cause) {
        throw new java.io.UncheckedIOException(
                "Cannot read required data", cause);
    }
}
```

The snippets above are **illustrative method bodies** for a `DataSource` implementation; they are not two methods with the same signature to be placed together in a single class.

Note: the second option **does not turn an I/O failure into a success**. It merely converts a checked `IOException` into an unchecked `UncheckedIOException`, preserving the `cause`. Such conversion should be **intentional** when the API contract accepts unchecked failures; you should not wrap exceptions just to silence the compiler without considering caller responsibilities.

### Do not replace it with an unconditional `catch (IOException ex) { return null; }`

A business-logic-flawed way to drop `throws`:

```java
@Override
public String read(String key) {
    try {
        return java.nio.file.Files.readString(
                java.nio.file.Path.of(key));
    } catch (java.io.IOException ex) {
        return null;
    }
}
```

Although this snippet **compiles**, the caller cannot tell whether `null` means valid content, a missing file, or a permission error. The I/O failure is lost and the program may continue in an invalid state.

**Omitting checked exception declarations must match actual behavior and the contract**—it does not mean swallowing exceptions and pretending the operation succeeded.

## 7. Overriding a Method of an Abstract Class

The exact same rules apply when the method is declared in an **abstract class**:

```java
abstract class BaseReader {
    abstract String read()
            throws java.io.IOException;
}

final class ConstantReader extends BaseReader {
    @Override
    String read() {
        return "fixed";
    }
}

final class MissingReader extends BaseReader {
    @Override
    String read()
            throws java.io.FileNotFoundException {
        throw new java.io.FileNotFoundException("record absent");
    }
}
```

These are valid illustrative declarations in an appropriate Java file. `BaseReader.read` permits `IOException`; concrete classes may throw no checked exception or declare the subtype `FileNotFoundException`.

There is no special exception just because the superclass method is `abstract`. It still publishes a contract that subclasses must respect.

### A `final` method cannot be overridden

If the superclass marks a method as `final`:

```java
class Base {
    public final void run() throws java.io.IOException {}
}
```

then a subclass **cannot override** `run()` to change its checked exception list, whether narrowing or widening. Because overriding is prohibited for that method, override rules never come into play.

## 8. A Method with Multiple Checked Exceptions

Suppose a superclass declares two error branches:

```java
class Importer {
    public void importData()
            throws java.io.IOException, java.sql.SQLException {
        // ...
    }
}
```

A subclass can:

- Keep both checked exceptions if genuinely needed.
- **Drop one branch** and keep the other.
- Narrow the I/O branch from `IOException` to `FileNotFoundException`.
- Narrow the SQL branch from `SQLException` to `SQLTimeoutException` if the body only produces that type.
- **Drop both** if no checked exception is allowed to escape.

Valid override example:

```java
class SpecializedImporter extends Importer {
    @Override
    public void importData()
            throws java.io.FileNotFoundException,
                   java.sql.SQLTimeoutException {
        // ...
    }
}
```

This is an illustrative example; both declared types are subtypes of the two checked branches permitted by the superclass.

**Invalid** override:

```java
// Intentionally DOES NOT COMPILE.
class WrongImporter extends Importer {
    @Override
    public void importData()
            throws java.text.ParseException {
        // ...
    }
}
```

`ParseException` is a checked exception not covered by either branch of the superclass. Having "multiple checked exception types" in the superclass does not grant permission to add any new checked exception type.

### Should you repeat both the subtype and the supertype?

For instance, `throws IOException, FileNotFoundException` is syntactically valid, but `FileNotFoundException` is already covered by `IOException`, so the list is usually **redundant**. JavaDoc comments can describe the conditions under which the subtype occurs without lengthening the method signature.

## 9. A Class Implementing Multiple Interfaces with the Same Signature

This is an important scenario for understanding the **do-not-widen checked exceptions** limit.

Suppose two independent interfaces have the same method:

```java
interface FileSync {
    void sync() throws java.io.IOException;
}

interface DatabaseSync {
    void sync() throws java.sql.SQLException;
}
```

A class implements both:

```java
class HybridSync implements FileSync, DatabaseSync {
    @Override
    public void sync() {
        System.out.println("sync complete");
    }
}
```

**Valid.** `HybridSync.sync()` declares no checked exceptions; therefore, it satisfies the contracts of **both** `FileSync` and `DatabaseSync` simultaneously.

Now try declaring:

```java
// Intentionally DOES NOT COMPILE.
class InvalidHybridSync implements FileSync, DatabaseSync {
    @Override
    public void sync() throws java.io.IOException {
        // ...
    }
}
```

Invalid because `DatabaseSync.sync()` **does not permit checked `IOException`**. Similarly, `throws SQLException` is incompatible with `FileSync.sync()`.

With two unrelated checked exception types such as `IOException` and `SQLException`, an implementation satisfying both contracts generally **cannot declare any checked exception belonging exclusively to one branch**. It must handle checked exceptions within its body or choose a suitable interface design.

### Practical rule

When multiple contracts with the same method signature are satisfied simultaneously by one implementation, the implementation's checked exceptions must lie in the **intersection of permitted error types**, not the **union** of `throws` lists from all interfaces.

If the types in the interfaces have a parent/child relationship, the implementation can declare a type compatible with **both**. If the two groups are completely independent with no common checked subtype, omitting all checked `throws` may be the only valid signature.

## 10. Complete Java 17+ Example: Fulfilling Two Interface Contracts

Save the file **`MultipleInterfaceThrowsDemo.java`**:

```java
import java.io.IOException;
import java.sql.SQLException;

public class MultipleInterfaceThrowsDemo {

    interface FileSync {
        void sync() throws IOException;
    }

    interface DatabaseSync {
        void sync() throws SQLException;
    }

    static final class HybridSync
            implements FileSync, DatabaseSync {

        @Override
        public void sync() {
            System.out.println("hybrid: synced");
        }
    }

    static void viaFile(FileSync source) {
        try {
            source.sync();
            System.out.println("file: completed");
        } catch (IOException ex) {
            System.out.println("file: I/O error");
        }
    }

    static void viaDatabase(DatabaseSync source) {
        try {
            source.sync();
            System.out.println("database: completed");
        } catch (SQLException ex) {
            System.out.println("database: SQL error");
        }
    }

    static void viaHybrid(HybridSync source) {
        source.sync();
        System.out.println("hybrid: completed");
    }

    public static void main(String[] args) {
        HybridSync hybrid = new HybridSync();

        viaFile(hybrid);
        viaDatabase(hybrid);
        viaHybrid(hybrid);
    }
}
```

Run:

```bash
javac -encoding UTF-8 MultipleInterfaceThrowsDemo.java
java MultipleInterfaceThrowsDemo
```

**Exact stdout:**

```text
hybrid: synced
file: completed
hybrid: synced
database: completed
hybrid: synced
hybrid: completed
```

### Why does the code compile?

- `HybridSync.sync()` has no checked `throws`, which is compatible with both interfaces.
- `viaFile` takes the **static type `FileSync`**, so the compiler requires handling or declaring `IOException`.
- `viaDatabase` takes the **static type `DatabaseSync`**, so `SQLException` must be accounted for.
- `viaHybrid` takes the **static type `HybridSync`**, so no checked exception needs to be caught from the `sync()` call.
- All three calls executing the same implementation is a **runtime dispatch** decision; checked exception obligations are still checked against the **type declared at the call site**.

This example clearly demonstrates that **an implementation does not need to copy an interface's `throws`**, and callers can see different contracts through different reference types.

## 11. What If the Superclass Declares No Checked Exception?

If the superclass already has a method that declares no checked exceptions:

```java
class BaseTask {
    public void run() {
        System.out.println("base task");
    }
}
```

Valid override:

```java
class FastTask extends BaseTask {
    @Override
    public void run() {
        System.out.println("fast task");
    }
}
```

Invalid override:

```java
// Intentionally DOES NOT COMPILE.
class RiskyTask extends BaseTask {
    @Override
    public void run() throws java.io.IOException {
        throw new java.io.IOException("network unavailable");
    }
}
```

The superclass did not advertise checked `IOException`, so the subclass cannot widen this contract on its own. If the new implementation genuinely calls an API that throws a checked exception, it must catch and handle it internally or intentionally translate it into an unchecked exception; it cannot simply add `throws IOException` to the override.

If multiple implementations should be allowed to let checked I/O errors escape, **the superclass/interface contract needs to be designed accordingly from the start**. Changing a published contract can affect all existing callers and implementers.

## 12. Checked Exceptions from the Method Body Must Still Be Handled Properly

The rule allowing you to **omit** checked `throws` **does not exempt** the override's body from checked-exception handling responsibilities.

Example:

```java
@Override
public void save() {
    writeFile(); // writeFile() throws IOException
}
```

This is an **intentionally invalid example**, assuming `writeFile()` throws checked `IOException` and `save` declares no checked exceptions.

To make it compile:

- Add `throws IOException` if **the superclass contract permits it**.
- Catch `IOException` and genuinely recover inside the body.
- Wrap it in an appropriate unchecked exception with `cause` if the API design requires it.
- Change the separation of responsibilities or redesign the interface if the checked error truly belongs to a contract that cannot be ignored.

You should not simply write:

```java
catch (java.io.IOException ignored) {
}
```

An empty handler bypasses the compiler but typically hides failures. Especially for write operations, callers could receive a false signal of success.

## 13. Checked Exceptions Are Checked by Call Signature, Not by Internal `catch` Blocks

A subclass that declares no checked exceptions can use `try-catch` inside its body:

```java
@Override
public void run() {
    try {
        externalOperation();
    } catch (java.io.IOException ex) {
        reportFailure(ex);
    }
}
```

This is illustrative code; it assumes `externalOperation` can throw checked `IOException`, and `reportFailure` handles it per the contract without letting a new checked error escape.

Because `IOException` is caught and handled inside the override, callers are not forced to catch it. However, this is only sound if the handler **performs a meaningful action** or expresses the failure in terms of the contract's result, rather than automatically turning every error into success.

### Once `catch` handles the error, Java does not force you to declare it

`throws` is a declaration for checked exceptions **that can escape the method**. If all checked exception paths are properly handled internally, the `throws` list can be empty. This lets a subclass provide a more self-contained implementation than the superclass contract without adding extra burden to callers.

## 14. Unchecked Exceptions: Allowed, but Still Part of the Contract

Suppose a superclass method is:

```java
interface Processor {
    void process() throws java.io.IOException;
}
```

An implementing class can write:

```java
class FailingProcessor implements Processor {
    @Override
    public void process() throws IllegalStateException {
        throw new IllegalStateException("processor not initialized");
    }
}
```

This is an illustrative Java snippet. `IllegalStateException` belongs to `RuntimeException` and is unchecked. Java allows declaring it even though the interface does not list it.

However, do not conclude that "unchecked exceptions are not part of the contract at all". For example, a library may document `IllegalArgumentException` for invalid arguments and `IllegalStateException` for disallowed states. Callers may choose to handle these errors even though the compiler does not enforce it.

**Do not convert checked exceptions to unchecked ones just to bypass compilation errors** if callers still need to recover reasonably. Choosing the exception kind is an API design decision.

## 15. Overriding, Overloading, Constructors, and Method References Are Different Things

### Overriding differs from overloading

Two methods that differ only in their `throws` list **do not form an overload**:

```java
// Intentionally DOES NOT COMPILE if both declarations are in the same class.
void fetch() throws java.io.IOException {}
void fetch() throws java.io.FileNotFoundException {}
```

Java does not use `throws` to distinguish overload signatures. Overriding is determined by the method name, parameter list, and the language's signature/subsignature rules—not by whether the `throws` lists are identical.

A new overloaded method with a **different parameter list** can have its own checked exception contract; the override rule against widening `throws` does not apply mechanically across overloads.

### Constructors are not overridden

A **constructor** is not inherited or overridden like a regular method. A subclass constructor can have its own `throws` list and must account for checked exceptions arising from the `super(...)` call as well as its own initialization code.

Therefore, do not apply method-overriding rules verbatim to subclass constructors. If a superclass constructor throws a checked exception, the subclass constructor must handle or declare it according to object initialization rules.

### Method references and lambdas use the functional interface's contract

Example:

```java
@FunctionalInterface
interface Loader {
    String load() throws java.io.IOException;
}
```

A lambda implementing `Loader` can throw no checked exceptions:

```java
Loader loader = () -> "cached";
```

These are illustrative declarations. Still, callers using the `Loader` variable remain obligated to handle checked `IOException` when calling `loader.load()`, per the interface's declaration.

Conversely, a lambda cannot arbitrarily throw a checked exception incompatible with the functional method's `throws`. The rule follows the target type's contract, even though a lambda has no `throws` clause of its own.

## 16. Why Should You Annotate with `@Override`?

`@Override` lets the compiler verify that a method actually overrides a valid declaration. This is especially useful if the author renames the method or gets the parameters wrong:

```java
class Parent {
    void load(String path) throws java.io.IOException {}
}

class Child extends Parent {
    @Override
    void load() {
        // Wrong: does not override load(String).
    }
}
```

This code **intentionally does not compile**, because `load()` has a different signature from `load(String)`.

Without `@Override`, `Child.load()` would become an independent overload, leading the author to think they had removed `throws IOException` from the superclass method when in fact **they had not overridden the intended method at all**.

Therefore, when narrowing or omitting checked `throws`, using `@Override` is an important habit to be sure you are modifying the right inheritance contract.

### Access modifiers must also be compatible

An override cannot make access privileges narrower than the method it overrides. For instance, a `public` method from an interface must be implemented as `public`. This is a **separate** constraint from checked exceptions, though it frequently appears alongside it when writing overrides.

## 17. Common Mistakes in Checked Exception Contract Design

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Subclass declares `throws Exception` when superclass only allows `IOException` | Widens checked exceptions | Keep `IOException` or an appropriate subtype |
| Subclass declares `throws SQLException` when superclass only allows `IOException` | Adds a checked exception from another branch | Catch/translate the error in the implementation or redesign the contract |
| Thinking a subclass must keep `throws IOException` from the interface | Overrides can narrow or omit checked `throws` | Declare only the checked exceptions that can still escape |
| Dropping `throws` while still calling `Files.readString` without catching | Checked `IOException` is unhandled | Catch it, declare it within superclass limits, or translate it intentionally |
| Catching the error and returning `null` without a contract | Hides failure and easily causes bugs at call sites | Recover meaningfully or report the error explicitly |
| Thinking you can omit `catch` when calling through an interface because you know the implementation does not throw | Compile-time checks use the interface type | Handle according to the static type's `throws` |
| Thinking unchecked exceptions are also strictly forbidden in overrides | The main restriction applies to checked exceptions | Understand `RuntimeException` and `Error` |
| Thinking multiple interfaces allow taking the union of all `throws` lists | The implementation must satisfy every contract simultaneously | Use a set of checked exceptions compatible with all of them |
| Thinking constructors follow the same override rules | Constructors are not overridden | Check initialization rules and `super(...)` |
| Thinking changing `throws` creates a different overload | `throws` is not part of overload resolution criteria | Differentiate by name and parameter list |
| Omitting `@Override` and accidentally overloading | May fail to override the intended method | Add `@Override` so the compiler checks it |
| Arbitrarily converting checked exceptions to unchecked ones | Can make proper recovery difficult for callers | Design the contract and `cause` clearly |
| Relying solely on runtime type to ignore checked exception duties | The compiler inspects the static type | Read the signature of the method being called |

## 18. Checklist When Overriding a Method with `throws`

Before modifying the signature in a subclass:

1. **Identify the overridden method** and add `@Override`.
2. **Read `throws` on the superclass/interface**: which checked exception types are permitted?
3. **Determine the implementation's actual errors**: I/O, SQL, parse, or no checked errors at all?
4. **If keeping checked `throws`**, verify each type is the same or a subtype covered by the superclass contract.
5. **If omitting `throws`**, ensure every checked exception arising in the body is meaningfully handled or can no longer escape.
6. **If implementing multiple interfaces**, check that the implementation satisfies all declarations with the same signature simultaneously.
7. **Check the caller's static type**: via interface/superclass or concrete type? Catch/declare obligations may differ.
8. **Consider unchecked exceptions** that may occur: compiler rules differ, but API documentation responsibilities remain.
9. **Do not swallow errors just to compile**: fallbacks must be part of the contract, not false successes.
10. **If wrapping checked errors into unchecked ones**, consider preserving `cause` and choosing a subtype appropriate for the business layer.
11. **Check access and signature**: do not narrow visibility, and do not accidentally overload.
12. **Test and compile for real**: test calls through both the supertype and subtype, including failure cases.

## 19. Self-Check Questions

**Question 1.** The superclass declares `void work() throws IOException`. Is it valid for the subclass to declare `void work() throws FileNotFoundException`?

**Yes.** `FileNotFoundException` is a subtype of `IOException`.

**Question 2.** Can the subclass omit `throws` completely?

**Yes**, provided the override's body does not let any unhandled checked exception escape.

**Question 3.** The superclass declares `throws IOException`; is it valid for the subclass to declare `throws Exception`?

**No.** `Exception` is broader than `IOException` and could allow new checked exceptions.

**Question 4.** The superclass declares `throws IOException`; is it valid for the subclass to declare `throws SQLException`?

**No.** The two checked exception types are on independent branches.

**Question 5.** The superclass declares no checked exceptions; can the subclass declare `throws IllegalStateException`?

**Yes**, because `IllegalStateException` is unchecked. However, the behavioral design must still make sense.

**Question 6.** An interface declares `load() throws IOException`. A concrete class overrides it without `throws`. Can a caller holding a variable of the interface type completely omit catching/declaring `IOException` when calling `load()`?

**No.** The compiler looks at the interface type's contract at the call site.

**Question 7.** A concrete class declares no checked exceptions; the caller only calls through the concrete type. Does the compiler force catching `IOException`?

**No**, if that is the only call and there is no other source of checked `IOException` in the expression/scope being checked.

**Question 8.** Two interfaces have the same `sync()`, one `throws IOException`, the other `throws SQLException`. Is an implementation declaring no checked exceptions valid?

**Yes.** It satisfies both contracts.

**Question 9.** If a subclass method wants to throw checked `ParseException` while the superclass only allows `IOException`, what should you do?

You **cannot** directly add `throws ParseException` to the override. You need to handle it in the body, convert it to a type permitted by the contract when meaningful, or redesign the API at an appropriate boundary.

**Question 10.** Does adding `throws RuntimeException` force callers to `catch RuntimeException`?

**No.** `RuntimeException` is unchecked, even if explicitly written in `throws`.

**Question 11.** Do two methods with the same name and parameters—one `throws IOException` and the other `throws FileNotFoundException`—form a valid overload?

**No.** Differing only in `throws` does not create two distinct overload signatures.

**Question 12.** Does a subclass constructor "override the superclass constructor" and have to declare narrower checked exceptions?

**No.** Constructors are not overridden; a subclass constructor's exceptions are checked according to initialization rules and `super(...)`.

## 20. API Design Guidelines to Avoid "Workarounds" for Checked Exceptions

### Choose the right abstraction level for error types

An interface with multiple implementations—file, network, memory—might choose `throws IOException` if all operations are consistently modeled as I/O. But if only one implementation accesses a database while the interface is not a general storage contract, adding `throws SQLException` on a concrete class will not be compatible with the existing interface.

During design, ask:

- Can callers actually **recover** from this checked error?
- Does the supertype contract anticipate **multiple implementations**?
- Is a domain-level abstract exception needed to decouple callers from file/SQL details?
- Is an error a predictable business failure or a bug/precondition violation?
- Is it appropriate to use result types like `Optional`, `Result`, or an explicit status instead of a checked exception for a normal "not found" outcome?

Answering these questions helps reduce the need to catch-and-swallow or wrap errors solely because of signature mismatches.

### Changing a public contract requires compatibility evaluation

Narrowing `throws` on a specific override usually creates no new checked obligations for callers, but **changing `throws` on an interface or superclass method** can affect other implementations. If you remove `throws IOException` from an interface, implementing classes that still declare `throws IOException` risk failing to compile after that change.

Therefore, distinguish between:

- **Narrowing in a subclass override:** usually a valid choice within the bounds of the existing superclass contract.
- **Changing the contract on the superclass/interface:** a broader API change that requires reviewing all implementers/callers and library compatibility.

Do not apply the subclass-override narrowing rule to conclude that removing checked `throws` from an interface is always safe for the entire system.

## Conclusion

When overriding a method in Java, a subclass may **keep**, **narrow**, or **completely omit** the checked exceptions permitted by the superclass/interface, but **must not widen to a new or broader checked exception type**. This rule protects callers using the supertype: a new implementation cannot introduce additional checked exception obligations that the original contract did not advertise.

Always distinguish between the **caller's static type contract**, the **runtime type of the exception**, and the **exceptions that actually escape the override's body**. Reducing a `throws` list should reflect genuine handling behavior, not swallowing errors or arbitrarily wrapping them into unchecked exceptions. With multiple interfaces sharing a signature, an implementation must satisfy **all** checked exception constraints simultaneously, while constructors, overloads, and unchecked exceptions each have their own rules to apply in context.