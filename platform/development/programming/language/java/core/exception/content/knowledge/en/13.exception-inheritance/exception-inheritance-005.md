# A Single Method Implementing Multiple Interfaces with Different `throws` Clauses in Java

> **Topic:** Java Core → Exception → Inheritance and Contracts. A Java class can `implements` multiple interfaces that contain **the same abstract method** (same name and parameter list) but declare **different checked exceptions** in their `throws` clauses. In that case, **a single implementation method must satisfy the contracts of all methods it overrides**. It cannot arbitrarily combine the exceptions into `throws A, B` if one interface does not allow the corresponding checked type.

## 1. The Core Problem: One Implementation, Multiple Contracts

Consider two interfaces:

```java
interface FileAction {
    void execute() throws java.io.IOException;
}

interface DatabaseAction {
    void execute() throws java.sql.SQLException;
}
```

Both declare the same method `void execute()`, but with different `throws` clauses:

- `FileAction.execute()` allows the checked `IOException`.
- `DatabaseAction.execute()` allows the checked `SQLException`.
- A class implementing **both** must have an `execute()` that is valid when called through **either interface**.

This is a valid implementation:

```java
final class CombinedAction implements FileAction, DatabaseAction {
    @Override
    public void execute() {
        System.out.println("Hoàn tất");
    }
}
```

Because the implementation **does not declare any checked exceptions**, it does not force callers of either interface to handle any additional checked exception types outside that interface's contract.

By contrast, this implementation is **invalid**:

```java
// INTENTIONALLY WRONG, DOES NOT COMPILE:
final class BadAction implements FileAction, DatabaseAction {
    @Override
    public void execute()
            throws java.io.IOException, java.sql.SQLException {
        // ...
    }
}
```

**Reason:** callers of `FileAction` are only promised the possibility of a checked `IOException`, not required to handle a checked `SQLException`. Likewise, callers of `DatabaseAction` must not unexpectedly receive `IOException` in the checked contract. The implementation must satisfy **both simultaneously**, not take the **union** of the two `throws` lists.

### 1.1. Rule to Remember

**For each checked exception declared by the implementation method, that type must be permitted by every overridden method declaration.** "Permitted" means it is the declared checked type, or a **subtype** of a checked type declared by the corresponding interface.

With the two independent interfaces above, `IOException` and `SQLException` lie in two different class branches. No ordinary checked exception class is simultaneously a subtype of both (Java allows only a single direct superclass), so the implementation **cannot declare any checked exception from either of those two branches**.

**Important exception:** this restriction rule applies to **checked exceptions**. The implementation method can still throw `RuntimeException`/`Error` and their subtypes even if the interface does not declare them; this is syntactically valid, though it does not guarantee that such handling is sound from a business-logic perspective.

## 2. Distinguishing `throws` from `throw` to Avoid Misunderstanding

`throws` appears in a declaration:

```java
void load() throws java.io.IOException;
```

It announces the **checked exception types that may escape from the method** and affects the caller's compile-time obligations.

`throw` is an executable statement:

```java
throw new java.io.IOException("Đọc lỗi");
```

If an implementation is restricted from declaring `throws IOException`, it also **cannot let a checked `IOException` escape** from that method body. It must actually handle the checked exception, or change the API structure. Removing the `throws` keyword from the signature **does not automatically handle** an I/O call that throws `IOException` in the body.

Keep three questions separate:

1. Which checked types does the interface announce?
2. Which checked types does the implementation want to let escape?
3. Which interface is the caller's static reference type at compile time?

The three questions are related but not identical. An interface's `throws` clause does not determine which exception will **definitely** occur in a given run.

## 3. Table of Basic Cases

Assume both interfaces have the same `void run()`:

| Interface A | Interface B | Valid `throws` on implementation | Notes |
| --- | --- | --- | --- |
| `throws IOException` | `throws SQLException` | No checked exceptions from either separate branch | Two unrelated types |
| `throws IOException` | `throws FileNotFoundException` | `throws FileNotFoundException` or a subtype of it | `FileNotFoundException extends IOException` |
| `throws Exception` | `throws IOException` | `throws IOException` or an appropriate checked subtype | `Exception` in A covers `IOException` |
| `throws IOException` | No checked exceptions declared | No checked exceptions declared | Interface B is stricter |
| `throws FileNotFoundException` | `throws EOFException` | No checked exceptions from both branches | Two different subtypes of `IOException` |
| `throws Exception` | `throws Exception` | `throws Exception` or an appropriate checked subtype | Two compatible contracts |
| No checked exceptions declared | No checked exceptions declared | No checked exceptions declared | Unchecked exceptions can still occur |

In this table, "no checked exceptions declared" does **not** mean the method can never fail; it only refers to the `throws` constraint for checked exceptions.

### 3.1. How to Evaluate a Specific Exception Type

Suppose the implementation wants to declare `throws FileNotFoundException`:

- Against interface A `throws IOException`: **valid**, because `FileNotFoundException extends IOException`.
- Against interface B `throws FileNotFoundException`: **valid**, because the types match.
- Since both allow it, the implementation may declare `throws FileNotFoundException`.

If the implementation wants to declare `throws IOException`, it fails against B: `IOException` is **broader** than `FileNotFoundException`, meaning it could include errors that B has not promised to the caller.

### 3.2. Why Is It Not a "Literal Intersection of Two Lists"?

A quick rule of thumb is that the implementation's valid checked exceptions must lie in the **common part of the contracts**, but do not interpret that as a string intersection of names:

```text
A: throws IOException
B: throws FileNotFoundException
```

The two lists of names are **not identical**, yet the implementation is still allowed to declare `throws FileNotFoundException` due to the **inheritance relationship**. You must consider the **set of subtypes covered by each contract**, rather than comparing the two `throws` texts literally.

## 4. Override Mechanism with Multiple Interfaces

In Java, two instance methods with the same name and the same parameter signature are implemented by a class using **a single** matching implementation if the rules for return type, accessibility, and exceptions are satisfied.

Example:

```java
interface First {
    String query() throws java.io.IOException;
}

interface Second {
    String query() throws java.sql.SQLException;
}

final class QueryService implements First, Second {
    @Override
    public String query() {
        return "OK";
    }
}
```

These are valid type declarations, though without `main`. A single `QueryService.query()` satisfies both:

- `public` is required because interface methods here are `public`.
- `String` is a return type compatible with both declarations.
- There is no checked `throws`, so neither contract is violated.
- `@Override` helps the compiler confirm this is an implementation of the overridden method.

**Do not create two methods distinguished only by `throws`:**

```java
// INTENTIONALLY WRONG: cannot overload by throws alone.
public void query() throws java.io.IOException { }
public void query() throws java.sql.SQLException { }
```

`throws` is not part of the **method signature used to distinguish overloads**. The two declarations above have the same name and parameter list, causing a duplicate method declaration error. If you want two independent behaviors with different checked exceptions, consider **renaming or adding meaningful parameters**, or designing two separate adapters/interfaces.

### 4.1. Same Name with Different Parameters Is Not This Scenario

```java
interface ById {
    void load(int id) throws java.io.IOException;
}

interface ByName {
    void load(String name) throws java.sql.SQLException;
}
```

These are two different signatures: `load(int)` and `load(String)`. A class can implement **two independent overloaded methods** with two different `throws` clauses, as long as each method satisfies its own contract. There is no need to force both `throws` lists onto a single implementation.

### 4.2. `@Override` Does Not "Merge" Exceptions

The `@Override` annotation only asks the compiler to verify a proper override/implementation. It **does not** allow bypassing checked exception rules. Even if you remove the annotation, a declaration with an incompatible `throws` clause is still rejected.

## 5. Complete Java 17 Example: Two Interfaces with Unrelated Checked Exceptions

This program demonstrates that an implementation declaring no checked exceptions can still be called through **two interfaces that announce different checked types**.

Save as **`DisjointThrowsDemo.java`**:

```java
import java.io.IOException;
import java.sql.SQLException;

public class DisjointThrowsDemo {
    interface FileAction {
        String execute() throws IOException;
    }

    interface DatabaseAction {
        String execute() throws SQLException;
    }

    static final class CombinedAction
            implements FileAction, DatabaseAction {
        @Override
        public String execute() {
            return "OK";
        }
    }

    static void fromFile(FileAction action) {
        try {
            System.out.println("File: " + action.execute());
        } catch (IOException e) {
            System.out.println("File lỗi: " + e.getMessage());
        }
    }

    static void fromDatabase(DatabaseAction action) {
        try {
            System.out.println("DB: " + action.execute());
        } catch (SQLException e) {
            System.out.println("DB lỗi: " + e.getMessage());
        }
    }

    public static void main(String[] args) {
        CombinedAction implementation = new CombinedAction();

        System.out.println("Impl: " + implementation.execute());
        fromFile(implementation);
        fromDatabase(implementation);
    }
}
```

Compile and run with JDK 17+:

```bash
javac -encoding UTF-8 DisjointThrowsDemo.java
java DisjointThrowsDemo
```

Stdout:

```text
Impl: OK
File: OK
DB: OK
```

**Points to note:**

1. `CombinedAction.execute()` does not declare `throws`, yet it still implements both interfaces.
2. `implementation.execute()` in `main` has receiver type `CombinedAction`, so it **does not need** to catch checked `IOException` or `SQLException` for that specific call.
3. `fromFile(FileAction action)` calls through static type `FileAction`; the compiler sees `throws IOException`, so it must be caught or declared.
4. `fromDatabase(DatabaseAction action)` calls through static type `DatabaseAction`; the compiler sees `throws SQLException`.
5. The **same runtime object** can be called through different receiver types, resulting in **different compile-time checked obligations** while the runtime output in this example is `"OK"` in all cases.

This point is crucial: `throws` on the **declaration visible at the call site** is part of the API contract; a narrower implementation does not cause callers using the interface to automatically know about it and drop their checked obligations.

## 6. When Two Interfaces Have Parent–Child Exception Types

This is the case where two contracts are **partially compatible**.

```java
interface GeneralReader {
    void open() throws java.io.IOException;
}

interface FileReaderContract {
    void open() throws java.io.FileNotFoundException;
}
```

`FileNotFoundException` is a subtype of `IOException`. The implementation can:

- Declare no checked exceptions; or
- Declare `throws FileNotFoundException` (or an appropriate checked subtype if one exists).

It **cannot** declare `throws IOException`, because `FileReaderContract.open()` does not allow such a broad type.

### 6.1. Complete Java 17 Example

Create **`CompatibleThrowsDemo.java`**:

```java
import java.io.FileNotFoundException;
import java.io.IOException;

public class CompatibleThrowsDemo {
    interface GeneralReader {
        void open() throws IOException;
    }

    interface NarrowReader {
        void open() throws FileNotFoundException;
    }

    static final class MissingReader
            implements GeneralReader, NarrowReader {
        @Override
        public void open() throws FileNotFoundException {
            throw new FileNotFoundException("Không thấy tệp");
        }
    }

    public static void main(String[] args) {
        MissingReader implementation = new MissingReader();

        try {
            implementation.open();
        } catch (FileNotFoundException e) {
            System.out.println("Concrete: " + e.getMessage());
        }

        GeneralReader broadReference = implementation;
        try {
            broadReference.open();
        } catch (IOException e) {
            System.out.println("General: "
                    + e.getClass().getSimpleName());
        }

        NarrowReader narrowReference = implementation;
        try {
            narrowReference.open();
        } catch (FileNotFoundException e) {
            System.out.println("Narrow: " + e.getMessage());
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 CompatibleThrowsDemo.java
java CompatibleThrowsDemo
```

Stdout:

```text
Concrete: Không thấy tệp
General: FileNotFoundException
Narrow: Không thấy tệp
```

Analysis:

- The implementation `MissingReader.open()` declares `throws FileNotFoundException`, which is valid for both interfaces.
- When called through `GeneralReader`, the caller must handle checked `IOException` per the interface signature, even though the runtime object throws `FileNotFoundException`.
- When called through `NarrowReader`, the caller sees the narrower checked contract.
- `getClass().getSimpleName()` reflects the **runtime type of the exception**; it is not converted into `IOException` when the call is made through `GeneralReader`.

**Common mistake:** thinking "`IOException` contains `FileNotFoundException`, so writing `throws IOException` in the implementation should be fine." The subtype direction here is the opposite: the narrower interface only allows **`FileNotFoundException`**, so the implementation cannot widen it to `IOException`.

## 7. When One Interface Declares No Checked Exceptions

```java
interface Alpha {
    void run() throws java.io.IOException;
}

interface Beta {
    void run();
}
```

For an implementation of both, `Beta.run()` is a contract that **allows no checked exceptions to escape**. Therefore:

```java
final class Both implements Alpha, Beta {
    @Override
    public void run() {
        System.out.println("Run");
    }
}
```

is valid, whereas:

```java
// INTENTIONALLY WRONG:
final class InvalidBoth implements Alpha, Beta {
    @Override
    public void run() throws java.io.IOException {
    }
}
```

is invalid because it conflicts with `Beta.run()`.

From the caller's perspective:

- `Alpha alpha = new Both();` → calling `alpha.run()` is subject to the checked `IOException` contract.
- `Beta beta = new Both();` → calling `beta.run()` does not need to catch checked `IOException` due to `Beta`'s declaration.
- `Both both = new Both();` → calling `both.run()` also does not need to catch checked `IOException` due to the implementation's declaration.

**This is not the compiler guessing the runtime instance everywhere.** It follows the method determined by the **static type of the receiver expression** at the call site.

## 8. Unchecked Exceptions Can Still Occur

The restriction on checked `throws` **does not** prevent the implementation from throwing:

- `IllegalStateException`;
- `IllegalArgumentException`;
- `NullPointerException`;
- other `RuntimeException` subtypes;
- `Error` subtypes (though `Error` should not be used for business errors).

This complete example shows how two unrelated interfaces can still be satisfied by a single implementation even when the method throws an unchecked error on a specific execution path.

Save **`UncheckedAcrossInterfacesDemo.java`**:

```java
import java.io.IOException;
import java.sql.SQLException;

public class UncheckedAcrossInterfacesDemo {
    interface FileStep {
        void process() throws IOException;
    }

    interface SqlStep {
        void process() throws SQLException;
    }

    static final class SharedStep implements FileStep, SqlStep {
        @Override
        public void process() {
            throw new IllegalStateException("Trạng thái không hợp lệ");
        }
    }

    public static void main(String[] args) {
        SharedStep implementation = new SharedStep();

        FileStep asFile = implementation;
        try {
            asFile.process();
        } catch (IOException e) {
            System.out.println("Checked I/O");
        } catch (IllegalStateException e) {
            System.out.println("File ref: "
                    + e.getClass().getSimpleName());
        }

        SqlStep asSql = implementation;
        try {
            asSql.process();
        } catch (SQLException e) {
            System.out.println("Checked SQL");
        } catch (IllegalStateException e) {
            System.out.println("SQL ref: "
                    + e.getClass().getSimpleName());
        }

        try {
            implementation.process();
        } catch (IllegalStateException e) {
            System.out.println("Concrete: "
                    + e.getClass().getSimpleName());
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 UncheckedAcrossInterfacesDemo.java
java UncheckedAcrossInterfacesDemo
```

Stdout:

```text
File ref: IllegalStateException
SQL ref: IllegalStateException
Concrete: IllegalStateException
```

**Two separate takeaways:**

1. `SharedStep.process()` declares no checked exceptions, so it is valid for both interfaces; unchecked `IllegalStateException` is not forbidden by checked `throws` override rules.
2. This is **not** a recommendation to turn every I/O/SQL failure into `IllegalStateException`. If you convert exception types, you need a contract policy, preserve `cause`, and avoid misleading callers into thinking the operation succeeded.

### 8.1. Why Is `catch (IOException)` Valid on the Call Through `FileStep`?

The variable `asFile` has static type `FileStep`, where the method announces `throws IOException`. The compiler accepts that checked handler even though the implementation `SharedStep.process()` never throws `IOException`.

If you change it to:

```java
SharedStep concrete = new SharedStep();
try {
    concrete.process();
} catch (java.io.IOException e) {
    // INTENTIONALLY WRONG if there is no other source of IOException in try.
}
```

then `catch(IOException)` is rejected because at compile time the compiler sees the implementation signature **does not declare checked `IOException`**. This is an effect of the **receiver type**, not the runtime value.

## 9. What If the Implementation Body Actually Needs to Call an API That Throws a Checked Exception?

This is the real engineering problem in projects. Suppose `CombinedAction.execute()` must call a configuration-reading function declared with `throws IOException`. Because the two interfaces only allow incompatible checked sets, it **cannot simply add `throws IOException` to the implementation**.

You have several options:

1. **Handle it in the implementation** when there is a genuine recovery path: try another source, record a meaningful failure result, or skip the operation according to the contract.
2. **Wrap into an appropriate unchecked exception** and preserve `cause`, but only when the API contract accepts that error-reporting style; callers still need to know it can fail.
3. **Redesign the interfaces** to avoid forcing a single method signature to carry two conflicting meanings/contracts.
4. **Split into adapters**: each interface has its own implementation, both sharing a common internal service, while each adapter decides how to handle checked exceptions.
5. **Use a result type** when failure is an expected outcome rather than a condition that must unwind via exceptions.

There is no single automatic fix that is right for every system. **Hiding errors or returning fake success** is not a valid option just because the compiler forbids a broader `throws` clause.

### 9.1. Java 17 Example: Wrapping a Checked I/O Exception into an Unchecked Exception with `cause`

`java.io.UncheckedIOException` is an unchecked wrapper specifically for `IOException`. In this example, the adapter is forced to keep a signature without checked exceptions, yet can still propagate the cause to the caller.

Create **`HandledCheckedInsideDemo.java`**:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.sql.SQLException;

public class HandledCheckedInsideDemo {
    interface FileTask {
        void perform() throws IOException;
    }

    interface DatabaseTask {
        void perform() throws SQLException;
    }

    static final class CombinedTask
            implements FileTask, DatabaseTask {
        @Override
        public void perform() {
            try {
                readConfiguration();
            } catch (IOException original) {
                throw new UncheckedIOException(
                        "Không nạp được cấu hình", original);
            }
        }
    }

    static void readConfiguration() throws IOException {
        throw new IOException("Nguồn cấu hình lỗi");
    }

    public static void main(String[] args) {
        CombinedTask task = new CombinedTask();

        try {
            task.perform();
        } catch (UncheckedIOException e) {
            System.out.println("Exception: "
                    + e.getClass().getSimpleName());
            System.out.println("Cause: "
                    + e.getCause().getClass().getSimpleName());
            System.out.println("Message: " + e.getMessage());
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 HandledCheckedInsideDemo.java
java HandledCheckedInsideDemo
```

Stdout:

```text
Exception: UncheckedIOException
Cause: IOException
Message: Không nạp được cấu hình
```

Explanation:

- `readConfiguration()` actually throws a checked `IOException`.
- `CombinedTask.perform()` **catches** that type and throws the unchecked wrapper `UncheckedIOException`.
- `perform()` does not declare `throws IOException` or `throws SQLException`, so it is valid for both interfaces.
- `getCause()` still retains the original `IOException` object.
- Converting a checked exception to unchecked **does not recover** from the configuration error and does not undo side effects that already occurred; it only changes the error-reporting contract at this boundary.

**Warning:** if the two interfaces represent two genuinely different meanings (reading a file vs. writing to a database), using one implementation for the same method name can be a misleading design. Do not turn every checked exception into unchecked just to "get past the compiler"; whenever possible, design two clearer, separate operations.

### 9.2. Why Is `throw new RuntimeException(e.getMessage())` Bad Practice?

It loses the original exception object and the linked `cause` stack trace. If wrapping is appropriate, use a constructor that preserves the cause (such as `new UncheckedIOException(message, e)` or a custom exception with `super(message, e)`). Also, do not log and swallow the error just to keep the method free of `throws`.

## 10. Callers See `throws` Through the Static Reference Type

This is one of the most important parts of the lesson, so examine each receiver type clearly.

Given:

```java
interface A {
    void run() throws java.io.IOException;
}
interface B {
    void run() throws java.sql.SQLException;
}
final class C implements A, B {
    @Override
    public void run() {
        System.out.println("OK");
    }
}
```

These are illustrative class/interface declarations without `main`. At the call site:

```java
C c = new C();
c.run(); // No checked exception handling required.

A a = c;
// a.run(); // Must catch or declare IOException.

B b = c;
// b.run(); // Must catch or declare SQLException.
```

Even though all three variables point to the same `C` instance, the compiler determines the called method via the **static type** of the receiver:

- `C.run()` declares no checked exceptions.
- `A.run()` declares `IOException`.
- `B.run()` declares `SQLException`.

**Do not confuse** "the implementation does not throw checked exceptions" with "a caller invoking through the interface does not need to handle checked exceptions." The caller is compiled against the **API it sees**, which keeps the code compatible if the implementation is later swapped for another class that is still valid for the same interface.

### 10.1. Catching the Wrong Checked Exception Source

The following snippet intentionally **does not compile**:

```java
A a = new C();
try {
    a.run();
} catch (java.sql.SQLException e) {
    System.out.println("SQL lỗi");
}
```

Assuming `try` contains only the call `a.run()`, checked `SQLException` has no compatible declared source. `A.run()` announces `IOException`, so you must handle or declare `IOException`.

Adding a multi-catch `catch (IOException | SQLException e)` also does not fix the missing source for checked `SQLException` in this `try` block. Multi-catch does not automatically expand the error-source contract.

### 10.2. `throws` Is a Contract for the Compiler, Not a List of All Runtime Errors

`A.run() throws IOException` does **not** guarantee that the method will never throw a `RuntimeException`. A `NullPointerException` or `IllegalStateException` can occur along a runtime path without being listed in `throws`. API users still need an appropriate policy for unexpected errors at system boundaries.

## 11. Implementing a Method Already Inherited from a Superclass

A class can `extends` a superclass while simultaneously `implements` multiple interfaces. In that case, a `public` method inherited from the superclass is sometimes enough to implement an interface — **but it must still satisfy all checked `throws` contracts**.

Consider:

```java
class BaseService {
    public void sync() throws java.io.IOException {
        System.out.println("Base");
    }
}

interface NetworkContract {
    void sync() throws java.io.IOException;
}

interface SqlContract {
    void sync() throws java.sql.SQLException;
}
```

`BaseService.sync() throws IOException` cannot be used as-is to satisfy `SqlContract.sync() throws SQLException` because the two checked types are incompatible. The subclass can **override and narrow** the contract:

```java
final class UnifiedService
        extends BaseService
        implements NetworkContract, SqlContract {
    @Override
    public void sync() {
        System.out.println("Unified");
    }
}
```

### 11.1. Java 17 — Superclass, Two Interfaces, One Override Example

Create **`InheritedThrowsDemo.java`**:

```java
import java.io.IOException;
import java.sql.SQLException;

public class InheritedThrowsDemo {
    static class BaseService {
        public void sync() throws IOException {
            System.out.println("Base");
        }
    }

    interface NetworkContract {
        void sync() throws IOException;
    }

    interface SqlContract {
        void sync() throws SQLException;
    }

    static final class UnifiedService extends BaseService
            implements NetworkContract, SqlContract {
        @Override
        public void sync() {
            System.out.println("Unified");
        }
    }

    public static void main(String[] args) {
        UnifiedService concrete = new UnifiedService();
        concrete.sync();

        BaseService asBase = concrete;
        try {
            asBase.sync();
        } catch (IOException e) {
            System.out.println("I/O: " + e.getMessage());
        }

        SqlContract asSql = concrete;
        try {
            asSql.sync();
        } catch (SQLException e) {
            System.out.println("SQL: " + e.getMessage());
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 InheritedThrowsDemo.java
java InheritedThrowsDemo
```

Stdout:

```text
Unified
Unified
Unified
```

Explanation:

1. `UnifiedService.sync()` overrides the method from `BaseService`, implements both interfaces, and removes checked `throws`.
2. When called through `UnifiedService`, the compiler requires no checked handling.
3. When called through `BaseService`, the compiler requires handling `IOException` because that is the parent signature.
4. When called through `SqlContract`, the compiler requires handling `SQLException`.
5. Runtime dispatch still calls **`UnifiedService.sync()`** in all three cases, so all three print `Unified`.

If you remove the override in `UnifiedService`, the method inherited from `BaseService` with `throws IOException` does not satisfy `SqlContract`'s contract; the class will not compile as a valid implementation.

## 12. Checked Exceptions Are Override Constraints, Not Overload Variants

Review this comparison table of rules:

| Scenario | Rule |
| --- | --- |
| Same name, same parameters, different `throws` | Does not create an overload; must satisfy override/implementation rules |
| Same name, different parameters | Can be an overload; each method is checked against its own signature's contract |
| One implementation of two interfaces with the same signature | Must satisfy all checked `throws` clauses simultaneously |
| Implementation declares **fewer** checked exceptions than the interface | Valid |
| Implementation declares a checked subtype of the type allowed by the interface | Valid |
| Implementation declares a checked exception broader than any involved interface | Invalid |
| Implementation throws unchecked `RuntimeException` | Not restricted by the interface's checked `throws` declaration |
| Caller invokes through an interface | Checked obligations are based on the method resolved at compile time through that interface |
| Caller invokes through the implementation class | Checked obligations are based on the corresponding method signature on the class |
| Interfaces have differing generic methods/return types | In addition to checked `throws`, must satisfy signature, type parameter, and return-type substitutability rules |

Do not assume that because two methods have different `throws` clauses, the compiler will generate two separate implementations. Java dispatch is based on method signature and receiver, not on the checked exception types listed in `throws`.

## 13. Intentionally Invalid Examples and How to Read Compiler Errors

### 13.1. Invalid Because Two Incompatible Checked Exceptions Were Added

```java
interface Readable {
    void process() throws java.io.IOException;
}
interface Writable {
    void process() throws java.sql.SQLException;
}
class Invalid implements Readable, Writable {
    @Override
    public void process()
            throws java.io.IOException, java.sql.SQLException {
    }
}
```

**Does not compile:** the implementation declares checked exceptions that **one of the corresponding interfaces does not allow**.

Solutions depending on context: remove the checked `throws` and handle errors inside the method; use an unchecked wrapper with `cause` when appropriate; or change the API design to separate the two contracts.

### 13.2. Invalid Because the Implementation Declares a Broader Type Than the Narrow Contract

```java
interface Narrow {
    void open() throws java.io.FileNotFoundException;
}
interface Broad {
    void open() throws java.io.IOException;
}
class TooBroad implements Narrow, Broad {
    @Override
    public void open() throws java.io.IOException {
    }
}
```

**Does not compile:** `Narrow.open()` only allows checked `FileNotFoundException`, not any `IOException`.

Change it to `throws FileNotFoundException` or declare no checked exceptions.

### 13.3. Invalid Because Only `throws` Was Removed Without Handling the Call

```java
interface A {
    void load() throws java.io.IOException;
}
interface B {
    void load() throws java.sql.SQLException;
}
class ForgotHandling implements A, B {
    @Override
    public void load() {
        java.nio.file.Files.readString(
                java.nio.file.Path.of("config.txt"));
    }
}
```

**Does not compile:** `Files.readString(...)` announces checked `IOException`, but `load()` neither catches nor declares it appropriately. Adding `throws IOException` to `load()` would conflict with `B`. You must handle the checked exception in the body or redesign the contracts.

### 13.4. Invalid Because of Insufficient Access Visibility

```java
interface PublicTask {
    void execute();
}
class Hidden implements PublicTask {
    void execute() {
    }
}
```

**Does not compile:** the implementation method must be `public`; it cannot reduce visibility from the interface's `public` method. Even though this lesson focuses on `throws`, do not forget this is **an independent override constraint**.

### 13.5. Do Not Overuse `throws Exception`

A class can declare `throws Exception` when both interfaces allow `Exception`. However, that is a broad contract that forces callers to handle many unspecified checked types. If the API can be expressed accurately with `IOException` or a narrow custom type, consider specifying it clearly so callers understand how they can recover.

Putting `throws Exception` on the implementation **does not fix** the case where interface A only allows `IOException` and interface B only allows `SQLException`; it makes the contract even broader and invalid.

## 14. Can You Merge Two Interfaces into One Subinterface?

An interface can `extends` multiple interfaces:

```java
interface FileStep {
    void process() throws java.io.IOException;
}

interface SqlStep {
    void process() throws java.sql.SQLException;
}

interface CombinedStep extends FileStep, SqlStep {
}
```

This is a **valid declaration** when the two inherited methods have the same signature and compatible return types. Extending both does not automatically create a "`throws IOException, SQLException`" method as a broader contract for implementations to use freely.

A class implementing `CombinedStep` must still satisfy **both** checked exception contracts. Typically it uses `public void process()` with no checked `throws`, just as when implementing `FileStep, SqlStep` directly.

### 14.1. Redeclaring in the Subinterface to Clarify the Contract

You can redeclare the method with an appropriate checked `throws` clause:

```java
interface CombinedStep extends FileStep, SqlStep {
    @Override
    void process();
}
```

This is an illustrative interface example. Redeclaring without checked `throws` helps readers see the contract of `CombinedStep.process()`. It **does not** alter the signatures of `FileStep.process()` or `SqlStep.process()`; calls through each original interface are still subject to the checked exceptions announced by that original interface.

If you put `throws IOException, SQLException` on `CombinedStep.process()` to widen it, that violates the override rules against the parent interfaces.

### 14.2. If You Only Want a Unified Policy

Instead of forcing two different meanings into the same `void process()`, consider:

```java
interface FileService {
    void readFile() throws java.io.IOException;
}

interface DatabaseService {
    void queryDatabase() throws java.sql.SQLException;
}
```

A class can implement **both**, with **two differently named methods** and two appropriate contracts. That is usually a cleaner design if one operation is reading a file and the other is querying a database.

## 15. Implications for Testing and Library Design

### 15.1. Testing Calls Through Each Static Type

An interface-level test should invoke through the interface actually used in production, not only through the implementation class. This verifies implementation substitutability and the contract callers expect.

With `DisjointThrowsDemo`, try writing two functions `fromFile(FileAction)` and `fromDatabase(DatabaseAction)` as in the example; each handles the checked exception according to the interface it knows. If the implementation is replaced later, caller code remains valid under that contract.

### 15.2. Testing Checked `throws` Is Not the Same as Testing Runtime Exceptions

A method `FileAction.execute() throws IOException` may never throw an error at runtime. That does **not** mean the signature is useless or that tests proved an `IOException` can never occur. It is simply a contract across multiple possible implementations.

Use tests to verify runtime behavior (success, conditional failures, post-error state), while the compiler verifies checked constraints at every call site. The "intentionally does not compile" examples above are for learning language rules and should not be placed in the source of runnable programs.

### 15.3. Do Not Infer That an Exception Is "Impossible" Because of the Current Implementation

If a variable is declared with type `FileAction`, the compiler must allow for the possibility that another valid implementation of `FileAction` could throw `IOException`. The fact that the current concrete object is `CombinedAction` does not exempt code using `FileAction` from compile-time checked obligations.

### 15.4. Library APIs Should Avoid Conflicting Contracts

If two interfaces you control describe the same operation but have incompatible `throws` clauses, ask whether they really should share **the same method signature**. Sometimes using different names, modeling failure as a shared result type, or separating into a clear functional interface is a better solution than converting all checked exceptions to unchecked.

## 16. Notes on Default Methods, Generics, and Other Rules

This lesson mainly examines **two abstract instance method declarations** with the same signature and compatible return types. Java also has independent rules:

- If multiple interfaces provide **conflicting default methods**, the class usually must override to resolve the conflict. That is an **implementation inheritance** issue, not just `throws`.
- When combining interface methods with **incompatible return types**, a valid implementation may not exist even if `throws` is valid.
- When generic methods or erasure cause multiple declarations to collide in signature, the compiler also checks type parameters, method subsignatures, and name clashes.
- `static`/`private` interface methods do not form abstract instance method contracts like the examples in this lesson; they should not be lumped into the `throws` comparison of a single override.
- If a class inherits a method from a superclass and also implements interfaces, the inherited method must satisfy the contracts; otherwise, the class must override it, as in `InheritedThrowsDemo`.

**Do not overuse `throws` rules to explain every compiler error when implementing multiple interfaces.** Read the specific error message and check each constraint: name/parameters, return type, access modifier, checked exceptions, default methods, and generic erasure.

## 17. Step-by-Step Problem-Solving Workflow

When faced with "a class implements multiple interfaces with different `throws` clauses," follow these steps:

1. **Confirm the exact same signature:** do the method name and parameter types actually match, or is it just an overload?
2. **Read each contract:** note the checked types declared on each interface. Ignore message differences and import aliases.
3. **Map the inheritance hierarchy:** for example, `FileNotFoundException <: IOException <: Exception`.
4. **Find checked types permitted by every contract:** check subtypes, not just the intersection of two lists of names.
5. **Choose the narrowest `throws` needed:** you can omit checked `throws` completely if the implementation handles them internally.
6. **Check what the method body can throw:** inspect I/O/SQL calls, constructors/resource closing, and direct `throw` statements.
7. **If checked exceptions cannot escape:** handle them meaningfully, wrap into an unchecked exception with `cause` when the contract allows, or redesign the API.
8. **Check callers:** calls through A, B, or the implementation class may have different checked obligations.
9. **QA:** ensure `public`, compatible return type, `@Override`, and no out-of-scope errors from default methods or generics.
10. **Runtime testing:** confirm errors are genuinely reported, not swallowed, do not return fake success, and do not corrupt data state.

This approach is usually much more effective than trying to put `throws Exception` everywhere until the compiler stops complaining.

## 18. Common Misconceptions

| Misconception | Fact |
| --- | --- |
| "The implementation can `throws IOException, SQLException` because A allows IO and B allows SQL." | **No**. Each checked exception must be compatible with **all** contracts the method overrides. |
| "Just keep the `throws` clause of the first interface." | You must check the other interface(s) as well. |
| "Different `throws` means two different overloads." | `throws` does not distinguish overloads; same name and parameters still form one signature. |
| "Declaring no checked exceptions means the method cannot fail." | It can still throw unchecked exceptions or handle checked ones internally. |
| "The implementation can throw `IOException` even if the other interface forbids it, because the body calls file APIs." | The compiler requires handling the checked exception internally or changing the design; it does not allow violating the interface. |
| "If A throws `IOException` and B throws `FileNotFoundException`, the implementation must drop all `throws`." | It can declare `FileNotFoundException` because it is a subtype of `IOException`. |
| "The implementation can write `throws IOException` because B allows `FileNotFoundException`." | Wrong subtype direction: `IOException` is broader. |
| "Calling through the class or either interface has the same `throws`." | Compile-time obligations depend on the method declaration visible through the receiver's **static type**. |
| "Catching `IOException` on a call through a class without `throws` is always valid." | A specific checked handler can be rejected by the compiler if the `try` block has no matching exception source. |
| "`@Override` lets you bypass checked exception conflicts." | `@Override` only asks the compiler to check the override relationship. |
| "Turning checked into unchecked is always good design." | Only reasonable with a clear contract and handling policy, preserving `cause`, and without hiding errors. |
| "You can catch `Exception` and ignore it to satisfy both interfaces." | This can hide business failures and side effects; catching must be paired with real handling. |
| "A class can only implement one interface that has a `run()` method." | It can implement multiple interfaces sharing a signature if the contracts are compatible. |
| "If the superclass already has the method, it definitely satisfies all interfaces." | The inherited method must still satisfy the checked `throws` of all interfaces; an override may be needed. |
| "Changing to `throws Throwable` will resolve the conflict." | It is even broader, will usually be rejected, and is an inappropriate contract. |
| "Default method/generic errors are all caused by `throws`." | There are several independent rules for return types, signatures, erasure, and implementation conflicts. |

## 19. Practice Exercises

### Exercise 1 — Conflict Between Two Unrelated Checked Exceptions

Given two interfaces:

```java
interface A {
    void run() throws java.io.IOException;
}
interface B {
    void run() throws java.sql.SQLException;
}
```

Write `class C implements A, B` with a valid `public void run()`. If the code inside must call an API with `throws IOException`, state two responsible options: handling I/O internally or wrapping into an unchecked exception with `cause` per the contract. Why is adding `throws IOException` directly wrong?

### Exercise 2 — Finding Valid Checked Types

A declares `throws IOException`; B declares `throws FileNotFoundException`. Evaluate an implementation with: (a) no `throws`, (b) `throws FileNotFoundException`, (c) `throws IOException`, (d) `throws Exception`. **Answer:** (a) and (b) are valid regarding the `throws` clause; (c) and (d) are invalid against B.

### Exercise 3 — Obligations When Upcasting

Run `DisjointThrowsDemo`. Replace the variable `CombinedAction implementation` in `main` with `FileAction implementation`, then try calling `implementation.execute()` without catching/declaring. What does the compiler report? Next, change the reference type to `DatabaseAction` and compare.

### Exercise 4 — Unchecked Exceptions Are Not Restricted by Interfaces

Run `UncheckedAcrossInterfacesDemo`. Why does `IllegalStateException` pass through both checked `throws` contracts? Should `IllegalStateException` be used for all I/O/SQL errors? **No**; choose exceptions based on semantics, recovery strategy, and `cause`.

### Exercise 5 — Superclass and Interfaces

In `InheritedThrowsDemo`, remove the `UnifiedService.sync()` override. Explain the compile-time error. Restore the override without `throws` and verify that calls through `BaseService`, `SqlContract`, and `UnifiedService` have different checked obligations.

### Exercise 6 — Changing the API to Reduce Conflict

Suppose two interfaces both have `void save()`, where one means "save file" and the other means "save database." Redesign them as `saveToFile() throws IOException` and `saveToDatabase() throws SQLException`. Analyze why two semantically distinct methods are easier to maintain than one `save()` that must convert error types.

### Exercise 7 — Handler Order Does Not Change `throws` Obligations

An implementation satisfies both interfaces by declaring no checked exceptions. Should a caller `FileAction file = implementation;` write a standalone `catch(SQLException)` around `file.execute()`? **No**, because the signature visible at the call site announces `IOException`. Write the correct handler and describe the runtime exception if the implementation throws `IllegalStateException`.

### Exercise 8 — Designing an Adapter

Write an internal service `StorageService.read() throws IOException`. Create an adapter implementing an interface `Task.run()` without `throws`: the adapter catches `IOException` and returns a structured failure status (if the interface allows), or throws an unchecked wrapper with `cause`. Ensure it does not return a fake success result and does not lose the original error.

### Exercise 9 — Parent and Child Exception Types

Interface A `throws Exception`, interface B `throws IOException`. Can the implementation `throws IOException`? **Yes**. Can it `throws SQLException`? **No**, because B does not allow it. Can it `throws FileNotFoundException`? **Yes**, because it is a subtype of `IOException`.

### Exercise 10 — Distinguishing Method Signatures from `throws`

Given two methods `load(int) throws IOException` and `load(String) throws SQLException`. Why is this a valid overload, whereas two `load(int)` methods differing only in `throws` are invalid? Explain the role of the parameter list and why return types/`throws` do not create independent overloads.

## 20. Pre-Completion Checklist

- [ ] Have I accurately identified methods with the same signature and confirmed whether they truly must share an implementation?
- [ ] Have I read **all** interfaces that the implementation method overrides?
- [ ] Have I distinguished checked `Exception` from unchecked `RuntimeException`/`Error`?
- [ ] Is every checked exception in the implementation's `throws` clause permitted by **every** contract?
- [ ] Have I checked subtype relationships, not just compared lists of exception names?
- [ ] When two interfaces allow unrelated `IOException` and `SQLException`, do I know the implementation cannot declare both?
- [ ] When one interface allows `IOException` and the other allows `FileNotFoundException`, did I choose the narrow `throws`?
- [ ] Have I checked checked exceptions thrown directly or indirectly in the implementation body?
- [ ] If handling inside the body is required, did I avoid swallowing errors and preserve `cause` when converting types?
- [ ] Do I remember that checked obligations at a call site are determined by the **static type of the receiver**?
- [ ] Do I know that an implementation declaring no checked exceptions can still throw unchecked exceptions?
- [ ] Did I give the interface implementation method `public` visibility and use `@Override`?
- [ ] Did I avoid trying to create overloads that differ only by `throws`?
- [ ] If there is a superclass, did I check the inherited method and add an override if needed?
- [ ] Have I distinguished `throws` errors from default method conflicts, generic erasure, and return-type errors?
- [ ] Do tests verify the success path, actual errors, and post-failure state?

**Conclusion:** When a single method implements multiple interfaces with different `throws` clauses, **the implementation must satisfy all checked exception contracts simultaneously**. With unrelated `IOException` and `SQLException`, the implementing method cannot declare checked exceptions from either branch; with `IOException` and `FileNotFoundException`, it can declare the narrower `FileNotFoundException`. Callers are still checked against their static reference type. If the implementation needs an operation whose checked exception falls outside the shared contract, handle it responsibly or redesign the API rather than just "adding `throws`" to get past the compiler.
