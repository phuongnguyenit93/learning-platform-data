# Checked Exceptions in Overridden Methods (`override`) in Java

## 1. Learning Objectives

When a subclass **overrides a method** of a superclass or a class **implements an interface method**, Java checks more than just the name, parameters, access modifier, and return type: it also checks the **checked exception contract**. An overriding method **must not arbitrarily declare a new or broader checked exception** than those permitted by the overridden declaration.

For example, if the superclass declares `read() throws IOException`, the subclass may keep `IOException`, narrow it to `FileNotFoundException`, or omit the checked exception. The subclass **cannot** change it to `throws Exception` or `throws SQLException`, because the caller relies on the existing contract and does not have to prepare for checked exceptions outside that contract.

After this lesson, you will be able to:

- Understand the `throws` rules when using `@Override` for classes, abstract classes, and interfaces.
- Distinguish the three valid options: **keeping**, **narrowing**, or **omitting** checked exceptions.
- Recognize cases where **broadening** or **adding a checked exception from a different branch** causes a compile error.
- Know why a checked exception still must be handled if the call has a **static type of the superclass/interface**, even when the implementation does not throw that error.
- Distinguish checked exception checking from `RuntimeException` and `Error` (unchecked).
- Understand the constraints when a class implements **two interfaces** with methods having the same signature but different `throws` clauses.
- Properly understand the roles of `throws`, `throw`, `try/catch`, `instanceof`, and generic type parameters in the exception contract.
- Design APIs that preserve object *substitutability* without forcing unexpected changes on callers.

Examples are compatible with Java 17+, featuring complete programs with file names, `javac`/`java` commands, and deterministic `stdout` output.

## 2. Core Rule: Overriding Methods Do Not Broaden Checked Exceptions

Consider the superclass contract:

```java
class BaseReader {
    String read() throws java.io.IOException {
        return "data";
    }
}
```

An overriding method in a subclass must be compatible with that contract. Regarding checked exceptions, the following declarations are **valid when considering the `throws` condition alone**:

```java
class SameReader extends BaseReader {
    @Override
    String read() throws java.io.IOException {
        return "same";
    }
}

class SpecificReader extends BaseReader {
    @Override
    String read() throws java.io.FileNotFoundException {
        return "specific";
    }
}

class CachedReader extends BaseReader {
    @Override
    String read() {
        return "cached";
    }
}
```

The three classes above are **illustrative declaration snippets**, without a `main` method. Validity conditions:

- `IOException` is the exact checked exception type permitted by `BaseReader.read()`.
- `FileNotFoundException` is a **subclass of `IOException`**, so it narrows the contract.
- Declaring no checked exceptions is valid as long as the method body does not propagate any disallowed checked exception out of the method.

Conversely, the following two declarations are **invalid** if used to override `BaseReader.read()`:

```java
class TooBroadReader extends BaseReader {
    @Override
    String read() throws Exception {
        return "invalid"; // COMPILE ERROR: Exception is broader than IOException.
    }
}

class WrongBranchReader extends BaseReader {
    @Override
    String read() throws java.sql.SQLException {
        return "invalid"; // COMPILE ERROR: SQLException is not a subtype of IOException.
    }
}
```

These two classes are only used to explain errors; **do not include them in a project intended to build successfully**. Both `Exception` and `SQLException` are checked exceptions, but they are not covered by the contract of `BaseReader.read()`.

### A Question to Ask Yourself

If the caller only knows an object by the type `BaseReader`, the compiler has already forced it to handle or declare `IOException`. If a subclass were suddenly allowed to throw `SQLException` or the broader `Exception`, the caller could encounter a checked exception that the superclass signature did not warn about. Java prevents this situation at **compile time**.

The rule can be visualized as:

```text
BaseReader.read() throws IOException
                  |
                  v
        allowed overrides:
          IOException
          FileNotFoundException
          no checked exception
                  |
                  x
        disallowed overrides:
          Exception
          SQLException
          ParseException
```

This diagram illustrates representative exception types. The exact rule must evaluate the **inheritance type relationship**, not merely the exception name.

## 3. How Do Checked and Unchecked Exceptions Differ?

Java classifies exceptions as follows:

```text
Throwable
├── Error                    (unchecked)
└── Exception
    ├── IOException          (checked)
    │   └── FileNotFoundException (checked)
    ├── SQLException         (checked)
    ├── ParseException       (checked)
    └── RuntimeException    (unchecked)
        ├── IllegalArgumentException
        └── IllegalStateException
```

This is a **simplified** diagram. Checked exceptions are `Throwable` types that do not belong to `RuntimeException` or `Error` (and their subclasses).

For **checked exceptions**, an overriding method must not add types outside the permitted scope of the overridden declaration. For **unchecked exceptions**, the compiler does not require overrides to impose a similar restriction. This means:

```java
class BaseService {
    void execute() {
        // Does not declare a checked exception.
    }
}

class StrictService extends BaseService {
    @Override
    void execute() throws IllegalStateException {
        throw new IllegalStateException("invalid state");
    }
}
```

These are valid illustrative classes. `IllegalStateException` extends `RuntimeException`, so even though the superclass method does not declare it, the subclass is still allowed to `throw` it and optionally declare it in `throws`.

However, **being syntactically valid does not mean the API design is good**: adding unexpected unchecked exceptions can still cause runtime failures and violate business expectations. The rule only states that the compiler does not apply the corresponding checked exception restriction.

### Why Is `Error` Not Checked Like Checked Exceptions?

`Error` types (for example `OutOfMemoryError`) belong to the unchecked branch and can occur even when not listed in `throws`. Do not write `catch (Throwable)` to "fix" an override contract or attempt to treat every `Error` as a recoverable failure. Checked/unchecked handling rules and recovery policies are two separate topics.

## 4. Runnable Example: Subclass Omits the Checked Exception

Create the file **`OverrideNoCheckedDemo.java`**:

```java
import java.io.IOException;

class ParentReader {
    String read() throws IOException {
        return "parent";
    }
}

class MemoryReader extends ParentReader {
    @Override
    String read() {
        return "memory";
    }
}

public class OverrideNoCheckedDemo {
    public static void main(String[] args) throws IOException {
        ParentReader parentView = new MemoryReader();
        MemoryReader childView = new MemoryReader();

        System.out.println("parent type=" + parentView.read());
        System.out.println("child type=" + childView.read());
    }
}
```

Compile and run:

```bash
javac OverrideNoCheckedDemo.java
java OverrideNoCheckedDemo
```

Exact `stdout`:

```text
parent type=memory
child type=memory
```

Explanation:

1. `ParentReader.read()` declares `throws IOException`.
2. `MemoryReader.read()` overrides it validly because it **does not declare a checked exception**.
3. At runtime, both `parentView.read()` and `childView.read()` run `MemoryReader`'s implementation due to dynamic dispatch.
4. However, `parentView` has the **static type `ParentReader`**, so the compiler treats that call as potentially throwing `IOException` according to the superclass contract. `main` declares `throws IOException` to satisfy this condition.
5. `childView` has the static type `MemoryReader`; considering only this call, the compiler does not require catching `IOException` because the method in the visible type does not declare that checked exception.

**Important distinction:** the method that actually runs is selected by the **runtime type**, whereas the checked exception obligation at the call site is based on the **static type and the method declaration selected by the compiler**.

### Do Not Omit the Obligation Just Because You Know the Real Object Is a Subclass

Consider this code snippet:

```java
ParentReader reader = new MemoryReader();
System.out.println(reader.read());
```

If placed inside a method **without `throws IOException` and without `try/catch`**, it will **not compile**. Knowing the runtime implementation does not erase the `throws IOException` contract of the `ParentReader` type at compile time.

Conversely:

```java
MemoryReader reader = new MemoryReader();
System.out.println(reader.read());
```

This is a valid illustrative snippet that can be used without a checked handler for `IOException` from that `read()` call, because the signature of `MemoryReader.read()` declares no checked exceptions.

## 5. Runnable Example: Narrowing from `IOException` to `FileNotFoundException`

Create the file **`OverrideNarrowThrowsDemo.java`**:

```java
import java.io.FileNotFoundException;
import java.io.IOException;

class FileProvider {
    void open() throws IOException {
        throw new IOException("base IO failure");
    }
}

class MissingFileProvider extends FileProvider {
    @Override
    void open() throws FileNotFoundException {
        throw new FileNotFoundException("missing.txt");
    }
}

public class OverrideNarrowThrowsDemo {
    public static void main(String[] args) {
        FileProvider parentView = new MissingFileProvider();
        MissingFileProvider childView = new MissingFileProvider();

        try {
            parentView.open();
        } catch (IOException failure) {
            System.out.println("parent catch="
                    + failure.getClass().getSimpleName());
        }

        try {
            childView.open();
        } catch (FileNotFoundException failure) {
            System.out.println("child catch="
                    + failure.getClass().getSimpleName());
        }
    }
}
```

```bash
javac OverrideNarrowThrowsDemo.java
java OverrideNarrowThrowsDemo
```

Output:

```text
parent catch=FileNotFoundException
child catch=FileNotFoundException
```

- When viewed through `FileProvider`, the caller must prepare for `IOException`.
- When viewed through `MissingFileProvider`, the caller can specifically catch `FileNotFoundException`.
- In both calls, the actual implementation is `MissingFileProvider.open()` and throws the same `FileNotFoundException` type.
- `FileNotFoundException` has an inheritance relationship with `IOException`, so the subclass contract does not surprise callers of the superclass with an out-of-scope checked exception.

**Note:** `catch (IOException)` can also catch `FileNotFoundException`. However, with `childView.open()`, `catch (FileNotFoundException)` allows more specific handling based on the narrowed signature.

## 6. Broadening Checked Exceptions: Compile Error Even If the Body Does Not `throw`

A common misconception is: "The subclass only **declares** `throws Exception`, but the body doesn't actually throw an error, so it should be valid." That is incorrect.

An example that **intentionally does not compile**, if placed in the appropriate package/class:

```java
import java.io.IOException;

class Parent {
    void run() throws IOException {
    }
}

class InvalidChild extends Parent {
    @Override
    void run() throws Exception {
        System.out.println("always succeeds");
    }
}
```

The compiler rejects `InvalidChild.run()` because `Exception` is broader than `IOException`, regardless of whether the body throws anything or not.

The reason is the **method declaration contract**, not statistics of a single execution. When designing an overriding method, read the `throws` clauses of the relevant superclass/interface methods instead of looking only at the operations occurring in the current implementation.

### How to Fix Depending on Your Goal

If the subclass does not throw a checked exception, remove `throws Exception`:

```java
@Override
void run() {
    System.out.println("always succeeds");
}
```

If it genuinely needs to throw `FileNotFoundException`:

```java
@Override
void run() throws java.io.FileNotFoundException {
    throw new java.io.FileNotFoundException("missing");
}
```

Both snippets are **illustrative method fragments** for overriding `Parent.run()`.

If the actual failure belongs to a checked type on a **different branch** (such as `SQLException`), you must choose a valid contract strategy:

- Handle the SQL error directly in the implementation if recovery is possible.
- Meaningfully translate it into a **checked type permitted by the superclass contract**, while preserving the original SQL exception as the `cause`.
- Design a different API if the nature of the operation has changed so much that it no longer satisfies the original contract.
- Only wrap into an unchecked exception when it fits the semantics and application policy; do not do it merely to "bypass" compile-time checks.

There is no way to write `throws SQLException` directly on an override when the parent only permits `IOException`.

## 7. Superclass Declares No Checked Exceptions

If the superclass has:

```java
class AccountService {
    void update() {
        // ...
    }
}
```

Then a subclass **cannot** override it as follows:

```java
class CheckedAccountService extends AccountService {
    @Override
    void update() throws java.io.IOException {
        // Invalid: adds checked IOException.
    }
}
```

This is an example that **intentionally does not compile**. No checked exceptions are declared in `AccountService.update()`, so the override cannot arbitrarily broaden it to `IOException`.

However, the subclass can throw an unchecked exception:

```java
class ValidatingAccountService extends AccountService {
    @Override
    void update() throws IllegalArgumentException {
        throw new IllegalArgumentException("account invalid");
    }
}
```

This is a valid illustrative class. `IllegalArgumentException` belongs to `RuntimeException`, so it is not constrained by the checked exception rules of overriding.

### When You Need to Call an API with Checked Exceptions Inside an Override Body

Suppose you must call an I/O API inside `update()`, while the superclass method declares no checked exceptions. You cannot propagate the checked `IOException` directly via `throws`; you must **catch and handle** it or **translate** it according to the chosen contract.

Do not silently log and return success if a required update operation has failed. When a new failure mode is genuinely needed, you may have to change the interface design at a higher abstraction layer rather than just modifying the subclass.

## 8. Overriding in Interfaces: Same Rules

An interface can declare checked exceptions:

```java
interface DataSource {
    String load() throws java.io.IOException;
}
```

An implementing class can keep, narrow, or omit the checked exception. A **runnable** example:

Create the file **`InterfaceOverrideDemo.java`**:

```java
import java.io.IOException;

interface DataSource {
    String load() throws IOException;
}

class InMemoryDataSource implements DataSource {
    @Override
    public String load() {
        return "cached data";
    }
}

public class InterfaceOverrideDemo {
    public static void main(String[] args) throws IOException {
        DataSource source = new InMemoryDataSource();
        InMemoryDataSource direct = new InMemoryDataSource();

        System.out.println("interface=" + source.load());
        System.out.println("concrete=" + direct.load());
    }
}
```

```bash
javac InterfaceOverrideDemo.java
java InterfaceOverrideDemo
```

`stdout`:

```text
interface=cached data
concrete=cached data
```

Two additional points:

- The interface-implementing method `public String load()` must retain `public` visibility per Java rules. Omitting `throws IOException` remains valid.
- `source` has static type `DataSource`, so `main` must catch/declare `IOException`. `direct` has the concrete class static type, which declares no checked exception.

### The Same Applies to Abstract Classes

An abstract class can declare:

```java
abstract class Task {
    abstract void execute() throws java.io.IOException;
}

class PureTask extends Task {
    @Override
    void execute() {
        System.out.println("no IO");
    }
}
```

These are valid illustrative classes. There is no body for the abstract method, yet the `throws IOException` signature is still a **contract**. The subclass may narrow or omit the checked exception, but may not broaden it to other checked types.

## 9. Overriding a Method That Declares **Multiple** Checked Exceptions

When a superclass declares:

```java
void process()
        throws java.io.IOException, java.text.ParseException {
    // ...
}
```

The subclass method can keep both, keep one of the two, use valid subtypes, or omit checked exceptions. The key condition: **every checked exception declared by the subclass method must be covered by at least one compatible type in the superclass method's exception set**.

Relationship example:

```text
Parent: throws IOException, ParseException
  |
  +-- Child A: throws IOException
  +-- Child B: throws FileNotFoundException
  +-- Child C: throws ParseException
  +-- Child D: throws FileNotFoundException, ParseException
  +-- Child E: no checked exception
  |
  x-- Child F: throws SQLException
  x-- Child G: throws Exception
```

`FileNotFoundException` is a subclass of `IOException`. `SQLException` is not a subclass of either `IOException` or `ParseException`. `Exception` is broader than both branches, so it is invalid to add as a checked type for the override.

**There is no requirement that the subclass keep the same number of error types.** The permitted exception set can be much smaller when the implementation uses a cache, in-memory data, or handles errors internally.

### Runnable Example with Two Checked Types

Create the file **`MultipleCheckedOverrideDemo.java`**:

```java
import java.io.FileNotFoundException;
import java.io.IOException;
import java.text.ParseException;

class Importer {
    void load(String source) throws IOException, ParseException {
        throw new ParseException("bad data", 0);
    }
}

class FileImporter extends Importer {
    @Override
    void load(String source) throws FileNotFoundException {
        if ("missing".equals(source)) {
            throw new FileNotFoundException(source);
        }
        System.out.println("loaded " + source);
    }
}

public class MultipleCheckedOverrideDemo {
    public static void main(String[] args) {
        Importer parentView = new FileImporter();
        FileImporter childView = new FileImporter();

        try {
            parentView.load("missing");
        } catch (IOException | ParseException failure) {
            System.out.println("parent="
                    + failure.getClass().getSimpleName());
        }

        try {
            childView.load("ok");
        } catch (FileNotFoundException failure) {
            System.out.println("child error");
        }
    }
}
```

```bash
javac MultipleCheckedOverrideDemo.java
java MultipleCheckedOverrideDemo
```

`stdout`:

```text
parent=FileNotFoundException
loaded ok
```

Analysis:

- `Importer.load(...)` declares two checked types: `IOException` and `ParseException`.
- `FileImporter.load(...)` only declares `FileNotFoundException`, which is a valid subtype of `IOException`, and does not throw `ParseException`.
- `parentView` is viewed through the `Importer` type, so the handler may need to cover **both types**.
- `childView` is viewed through the concrete class, so the handler can focus on `FileNotFoundException`.
- The subclass method actually only throws a file error on the `missing` path or prints success on the `ok` path; it is not forced to throw every type from the superclass.

Do not use `|` in `throws`: declaring multiple types uses commas. `|` is used in `multi-catch`, such as `catch (IOException | ParseException e)`.

## 10. A Class Implementing **Two Interfaces** with the Same Method but Different `throws`

This case often surprises developers. Suppose:

```java
interface FileAction {
    void run() throws java.io.IOException;
}

interface SqlAction {
    void run() throws java.sql.SQLException;
}
```

A class implementing both `FileAction` and `SqlAction` must provide a single `run()` method compatible **with both contracts simultaneously**.

If you write:

```java
class InvalidCombined implements FileAction, SqlAction {
    @Override
    public void run() throws java.io.IOException {
        // ERROR: SqlAction's SQLException contract does not allow IOException.
    }
}
```

This class **intentionally does not compile**: even though `IOException` is allowed by `FileAction`, it is not covered by `SqlAction`. Similarly, declaring only `SQLException` is incompatible with `FileAction`.

In cases where the two branches `IOException` and `SQLException` **have no common checked exception subtype**, the implementation cannot declare a checked exception from either branch; however, it can still **declare no checked exception**.

### Complete Example: Same Implementation, Three Reference Types

Create the file **`MultipleInterfacesThrowsDemo.java`**:

```java
import java.io.IOException;
import java.sql.SQLException;

interface FileAction {
    void run() throws IOException;
}

interface SqlAction {
    void run() throws SQLException;
}

class CombinedAction implements FileAction, SqlAction {
    @Override
    public void run() {
        System.out.println("run");
    }
}

public class MultipleInterfacesThrowsDemo {
    public static void main(String[] args)
            throws IOException, SQLException {
        CombinedAction direct = new CombinedAction();
        FileAction asFile = direct;
        SqlAction asSql = direct;

        direct.run();
        asFile.run();
        asSql.run();
    }
}
```

```bash
javac MultipleInterfacesThrowsDemo.java
java MultipleInterfacesThrowsDemo
```

`stdout`:

```text
run
run
run
```

Note:

- `CombinedAction.run()` declares no checked exceptions; it is compatible with **both interfaces**.
- `direct.run()` is viewed through the concrete class, so it incurs no checked `IOException`/`SQLException` obligation from the signature.
- `asFile.run()` is viewed through `FileAction`, and can still throw `IOException` under the static contract.
- `asSql.run()` is viewed through `SqlAction`, and can still throw `SQLException` under the static contract.
- Because `main` calls all three, the signature `main throws IOException, SQLException` is valid.

**Key concept:** when a method overrides/implements multiple parent methods, the checked exception constraint must be compatible with **each overridden declaration individually**, rather than taking the union of the `throws` lists and freely throwing any type in them.

### What If Two Interfaces Declare Types with a Common Supertype?

For example, `A.run() throws IOException` and `B.run() throws Exception`: an implementation `run() throws IOException` can be valid regarding exceptions, because `IOException` falls within the scope of both `IOException` and `Exception`. The condition is that the override's checked exception types must satisfy all relevant contracts simultaneously.

## 11. `RuntimeException` Can Still Appear Even If the Interface Declares No Errors

For example, the `Runnable` interface has the method:

```java
public abstract void run();
```

In Java, `Runnable.run()` declares no checked exceptions. Therefore, an implementation cannot add `throws IOException`:

```java
// Invalid if used to implement Runnable.run():
@Override
public void run() throws java.io.IOException {
    // ...
}
```

This is a **snippet that intentionally does not compile**. A common scenario is a worker that needs to call an I/O API with checked exceptions. The author can **catch and handle** the I/O error inside the worker, or **wrap it into an unchecked exception** while preserving the cause per the application contract.

### Runnable Example: Wrapping Checked Exceptions for `Runnable`

Create the file **`RunnableOverrideDemo.java`**:

```java
import java.io.IOException;

public class RunnableOverrideDemo {
    static class TaskFailure extends RuntimeException {
        TaskFailure(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static void readData() throws IOException {
        throw new IOException("source unavailable");
    }

    static class ReaderTask implements Runnable {
        @Override
        public void run() {
            try {
                readData();
            } catch (IOException original) {
                throw new TaskFailure("task failed", original);
            }
        }
    }

    public static void main(String[] args) {
        Runnable task = new ReaderTask();

        try {
            task.run();
        } catch (TaskFailure failure) {
            System.out.println("outer=" + failure.getMessage());
            System.out.println("cause="
                    + failure.getCause().getClass().getSimpleName());
        }
    }
}
```

```bash
javac RunnableOverrideDemo.java
java RunnableOverrideDemo
```

`stdout`:

```text
outer=task failed
cause=IOException
```

`ReaderTask.run()` does not declare checked `IOException`; it catches the I/O error and **wraps** it in `TaskFailure` (unchecked) while keeping the original exception object as the cause.

**Example limitation:** the program calls `task.run()` **directly on the `main` thread** to produce deterministic output. If you use `new Thread(task).start()`, an uncaught exception in the worker will follow that thread's uncaught exception mechanism and will **not automatically rethrow** into the `main` thread. With `ExecutorService.submit(...)`, task failures can be captured in the `Future` and observed via `get()`. Do not confuse cross-thread exception policies with `throws` override rules.

**Do not use unchecked wrappers just to hide errors:** this is an API decision. If the caller can recover from a read error, provide a functional interface or method with an appropriate checked exception contract instead of forcing all errors into `RuntimeException`.

## 12. Method Overriding Is Not Method Overloading

Overriding provides a new implementation for a matching inherited signature. Overloading means having methods with **different parameter lists**.

The following two methods do not form an overload merely because their `throws` clauses differ:

```java
void load() throws java.io.IOException { }
void load() throws java.sql.SQLException { }
```

This is **code that intentionally does not compile** if both are placed in the same class: the `throws` list does **not** create a distinct overload signature.

Conversely:

```java
void load(String key) throws java.io.IOException { }
void load(int id) throws java.sql.SQLException { }
```

These are two illustrative methods with **different parameters**, so they can be overloads. They do not override each other just because they share the same name. Each overloaded call has its own exception contract based on the method selected by the compiler.

### Do Not Confuse `static` Methods with Overriding

A `static` method with the same signature in a subclass **hides** the superclass's `static` method (*method hiding*) and does not participate in dynamic dispatch like overriding. The JLS still imposes appropriate checked exception constraints on static method hiding.

You cannot use `@Override` on a `static` method. When analyzing exceptions for a static call, examine the method selected by the compiler from the enclosing type/signature, and do not describe it as "runtime overriding".

### Constructors Are Not Overridden

A constructor can declare its own `throws` clause, and a `super(...)` call can throw checked exceptions. However, constructors are **not inherited or overridden**, so do not mechanically apply method `@Override` rules to constructors. Separate initialization/checked exception rules apply if a superclass constructor throws an error.

## 13. Generics and Exception Types in `throws`

Java allows some generic APIs to declare an exception type parameter. When implementing or binding a specific type argument, the `throws` contract is also specialized.

Example:

```java
interface CheckedTask<E extends Exception> {
    void execute() throws E;
}
```

An implementation with the type argument `IOException` can narrow it further, such as `FileNotFoundException`. This follows the same principle as regular superclasses: the checked type thrown must fall within the scope permitted by the generic contract after type parameter substitution.

### Runnable Example: Generic Checked Exception

Create the file **`GenericThrowsOverrideDemo.java`**:

```java
import java.io.FileNotFoundException;
import java.io.IOException;

interface CheckedTask<E extends Exception> {
    void execute() throws E;
}

class FileCheckTask implements CheckedTask<IOException> {
    @Override
    public void execute() throws FileNotFoundException {
        throw new FileNotFoundException("missing resource");
    }
}

public class GenericThrowsOverrideDemo {
    public static void main(String[] args) {
        CheckedTask<IOException> task = new FileCheckTask();

        try {
            task.execute();
        } catch (IOException failure) {
            System.out.println(
                    failure.getClass().getSimpleName());
        }
    }
}
```

```bash
javac GenericThrowsOverrideDemo.java
java GenericThrowsOverrideDemo
```

`stdout`:

```text
FileNotFoundException
```

`CheckedTask<IOException>` is viewed through the interface type that has `execute() throws IOException` after specializing the type parameter. The implementation only throws the subtype `FileNotFoundException`, so it is valid. `catch (IOException)` at the caller is sufficient to handle the exception.

**Advanced note:** When using generic methods, type erasure, or multiple inherited declarations with the same signature, the JLS specifies in detail how checked exception compatibility is evaluated (including erasure conditions). Before designing a complex generic API, consult the official rules rather than relying on a simple textual comparison of `throws` lists.

## 14. Common Compile Errors and How to Fix Them

| Superclass/Interface Declaration | Override or Implementation | Valid? | Explanation |
| --- | --- | --- | --- |
| `throws IOException` | `throws IOException` | Yes | Keeps the same checked type |
| `throws IOException` | `throws FileNotFoundException` | Yes | Narrows to a subtype |
| `throws IOException` | No `throws` | Yes | Omits the checked exception |
| `throws IOException` | `throws Exception` | **No** | `Exception` is broader than `IOException` |
| `throws IOException` | `throws SQLException` | **No** | Different checked branch |
| `throws IOException` | `throws IOException, SQLException` | **No** | Adds `SQLException` outside scope |
| No checked exception | `throws IOException` | **No** | Adds a checked exception |
| No checked exception | `throws IllegalStateException` | Yes | Unchecked |
| `throws Exception` | `throws IOException` | Yes | Narrows from `Exception` |
| `throws FileNotFoundException` | `throws IOException` | **No** | Broadens the checked type |
| `throws IOException, ParseException` | `throws FileNotFoundException` | Yes | Covered by `IOException` |
| `throws IOException, ParseException` | `throws SQLException` | **No** | Not within the two permitted types |

This table examines **only the checked exception rules for overriding**, assuming the rest of the declaration (return type, parameters, access modifier, inheritance) is valid. An override can still fail to compile for other reasons: reduced visibility, mismatched name/parameters, incompatible return type, or attempting to override a `final` method.

### Three Common Fixes

**Approach 1 — Narrow `throws` to the exact subtype:** If the subclass API actually throws `FileNotFoundException`, declare this type instead of `Exception`.

**Approach 2 — Catch and handle in the subclass:** If the subclass calls an API with a checked exception outside the contract, handle it with a recoverable policy before exiting the method.

**Approach 3 — Translate the error meaningfully and preserve the cause:** When crossing layers, use an error type permitted by the contract or an unchecked exception with clear semantics, and preserve the original `cause`. Do not discard source error details by merely printing `getMessage()` and returning a false success.

Do not arbitrarily modify the superclass by adding `throws Exception` if it is a public API that already has callers. Broadening the superclass contract can force **all callers** to catch or declare a broader error, affecting *source compatibility*.

## 15. API Design: Do Not Turn `throws` into a Catch-All List

### 15.1. Declare the Most Specific Type Useful to Callers

If a method only reads files, `IOException` is usually more meaningful than `Exception`. A subclass can narrow it to `FileNotFoundException` if the nature of its operation allows. For an interface with multiple implementations, choose a contract suitable for **all valid implementations** that callers need to support.

### 15.2. Do Not Abuse `throws Exception` for "Coding Convenience"

`throws Exception` permits many checked exception types, but makes selective handling difficult for callers. During overriding, it is also invalid if the superclass only declares a narrower type. Declaring a broad exception in the initial interface should be a deliberate API decision, not the default.

### 15.3. Do Not Throw Exceptions for Normal Control Flow

If "value not found" is a normal outcome, consider `Optional` or a specialized result type instead of an exception (depending on the API). However, if an I/O error genuinely prevents the operation from completing, do not pretend it succeeded just to omit `throws` in the subclass.

### 15.4. Preserve the Cause When Changing Exception Types

Example snippet:

```java
try {
    readFromDatabase();
} catch (java.sql.SQLException original) {
    throw new IllegalStateException(
            "Cannot load current configuration", original);
}
```

`readFromDatabase()` here is an undeclared illustrative method. `IllegalStateException` is unchecked, so it does not violate the compile-time checked exception rule of overriding. Still, the application must have a policy for handling the failure when it occurs; do not treat the wrapper as having "resolved" the incident.

When the wrapper is a checked exception, it must still belong to the set of types permitted by the superclass/interface method.

### 15.5. Ensure Subclass Substitutability for the Superclass

A caller using `BaseReader` should not have to be rewritten just because the runtime object is `SomeSubclass`. Restricting checked exceptions on `@Override` ensures that implementations do not break the checked exception catch/declare contract that callers rely on.

## 16. Self-Check Questions

1. **Parent declares `throws IOException`; can Child declare `throws FileNotFoundException`?** Yes, because it is a subtype.
2. **Parent declares `throws IOException`; is Child declaring `throws Exception` valid?** No, because it is broader.
3. **Parent declares no checked exceptions; is Child adding `throws IOException` valid?** No.
4. **Parent declares no checked exceptions; can Child throw `IllegalStateException`?** Yes under checked exception rules, because it is unchecked.
5. **Child no longer declares `IOException`; must a caller referencing the Parent type still catch `IOException`?** Yes, if Parent's declaration at the call site still has `throws IOException`.
6. **Two interfaces both have `run()`, one throws `IOException`, one throws `SQLException`: can the implementation throw `IOException`?** No, because it is incompatible with the second interface.
7. **Can an implementation of `Runnable.run()` declare `throws IOException`?** No.
8. **If you need to call an I/O API inside `Runnable.run()`, what should you do?** Catch and handle it, or translate it into an unchecked wrapper with a cause per the contract.
9. **How do `throw` and `throws` differ?** `throw` actually throws an exception object; `throws` declares the error types allowed to propagate out.
10. **Does changing the order of types in a `throws` list fix an override error?** No. The rule is based on type relationships, not order.
11. **Can you overload two methods that differ only by `throws`?** No.
12. **Are constructors subject to method `@Override` rules?** No, constructors are not overridden.
13. **An implementation is memory-only and cannot produce an `IOException`: must it keep the interface's `throws IOException`?** No; it can omit it.
14. **Is a subclass method with `throws IOException` valid when the parent has `throws FileNotFoundException`?** No, because it broadens from a subtype to a supertype.
15. **When parent has `throws IOException, ParseException`, is a child with only `throws FileNotFoundException` valid?** Yes.
16. **If a child must report `SQLException` but the parent only allows `IOException`, can it declare `SQLException` directly?** No; you need to design appropriate handling or translation.
17. **What selects the override at runtime, and what does the compiler check checked exceptions against?** Runtime dispatch selects the implementation; the compiler checks against the method declaration corresponding to the static type at the call site.
18. **What is the purpose of `@Override`?** It helps the compiler verify that the method actually overrides/implements a matching signature; it does not relax the `throws` contract.
19. **If a call through an interface type throws an undeclared unchecked exception, will Java allow it to run?** It can happen at runtime; checked exception checking does not prevent unchecked exceptions.
20. **What should you do before changing `throws` on a public API?** Review existing callers and implementations, source compatibility requirements, and error-handling policies.

## 17. Official Java Documentation

- [Java Language Specification 17 — `8.4.6 Method Throws](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.6): throws clauses, checked exceptions, and exception type parameters.
- [Java Language Specification 17 — `8.4.8.3 Requirements in Overriding and Hiding](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8.3): checked exception restrictions when overriding and hiding methods.
- [Java Language Specification 17 — `9.4.1 Interface Method Body](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.4.1): rules related to interface methods.
- [Java Language Specification 17 — `11.2 Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2): obligation to catch or declare checked exceptions.
- [Java Language Specification 17 — `15.12 Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12): call checking, compile-time types, and selected methods.
- [Java SE 17 API — IOException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html), [FileNotFoundException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/FileNotFoundException.html): parent–child exception relationship.
- [Java SE 17 API — Runnable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runnable.html): interface with `run()` declaring no checked exceptions.
- [Java SE 17 API — RuntimeException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/RuntimeException.html): unchecked branch not subject to the same checked `throws` override restrictions.

**Takeaway:** With `@Override`, a subclass method may **keep, narrow, or omit** checked exceptions from the superclass/interface method contract, but **must not add or broaden** checked exception types beyond that scope. `RuntimeException` and `Error` belong to the unchecked branch and are not subject to the same compile-time check. The `try/catch` or `throws` obligation at the call site depends on the **static type of the reference**; the actual implementation is still chosen by dynamic dispatch.