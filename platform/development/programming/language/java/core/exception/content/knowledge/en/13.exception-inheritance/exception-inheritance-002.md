# Do Not Broaden the Set of Checked Exceptions Permitted to Be Thrown When Inheriting and Overriding in Java

When a subclass **overrides** a method of its superclass, Java does not allow it to arbitrarily declare **new or broader checked exceptions** compared to the `throws` contract of the overridden method. This rule also applies when a class implements an interface method, and when a method must satisfy multiple inheritance contracts simultaneously.

Superclass example:

~~~java
class Parent {
    void read() throws java.io.IOException {
        // Operation that may fail with an I/O error.
    }
}
~~~

The subclass **is allowed** to narrow to `FileNotFoundException` (a subclass of `IOException`), or omit the checked exception declaration completely:

~~~java
class Child extends Parent {
    @Override
    void read() throws java.io.FileNotFoundException {
        // Valid: FileNotFoundException extends IOException.
    }
}
~~~

However, the subclass **is not allowed** to switch to `SQLException` or broaden to `Exception`:

~~~java
// DOES NOT COMPILE with @Override.
class InvalidChild extends Parent {
    @Override
    void read() throws java.sql.SQLException {
        // SQLException is not a subclass of IOException.
    }
}
~~~

Key takeaway: **an overriding method must not broaden the set of checked exception types that the caller may have to handle compared to the contract declared through the superclass/interface**. This rule is a *compile-time* constraint, not a runtime mechanism prohibiting all kinds of exceptions from occurring; **unchecked exceptions** (`RuntimeException` and `Error` along with their subclasses) are not subject to the same restriction.

This lesson focuses on the validity conditions of the `throws` clause in overriding, interfaces, multiple interfaces, and calls through a supertype; how to handle cases where a new checked error needs to be raised; distinguishing overriding from overloading, constructors, and unchecked exceptions; and Java's design rationale. The complete programs run with Java 17+.

## 1. Recap of checked and unchecked exceptions

Relevant hierarchy:

~~~text
java.lang.Throwable
├── java.lang.Error                         unchecked
│   └── ...
└── java.lang.Exception
    ├── java.io.IOException                 checked
    │   ├── java.io.FileNotFoundException   checked
    │   └── java.io.EOFException            checked
    ├── java.sql.SQLException               checked
    └── java.lang.RuntimeException          unchecked
        ├── IllegalArgumentException       unchecked
        ├── IllegalStateException          unchecked
        └── ...
~~~

**Checked exceptions** consist of `Throwable` types that do not belong to the `RuntimeException` or `Error` branches. For example, `IOException`, `SQLException`, `FileNotFoundException`, and `InterruptedException` are checked; `IllegalStateException` and `NullPointerException` are unchecked.

For checked exceptions, the compiler enforces the **catch-or-declare** rule: a method with an execution path that can let a checked exception escape must handle it appropriately or declare it as permitted in `throws`.

~~~java
import java.io.IOException;

// Illustrated within a class.
static void read() throws IOException {
    throw new IOException("không đọc được");
}
~~~

If the caller does not catch `IOException`, the method containing the call itself may need `throws IOException`. That obligation arises from the **checked exception type and execution path**.

When overriding, there is a second constraint: **the overriding signature must be compatible with the `throws` of the superclass method**. Therefore, simply adding `throws SomeCheckedException` will not always compile.

## 2. Why does Java forbid broadening checked exceptions in a subclass method?

Consider code used through the superclass type:

~~~java
class ReaderService {
    String load() throws java.io.IOException {
        return "data";
    }
}

class FileReaderService extends ReaderService {
    @Override
    String load() throws java.io.FileNotFoundException {
        return "file-data";
    }
}
~~~

A caller can write:

~~~java
ReaderService service = new FileReaderService();
try {
    System.out.println(service.load());
} catch (java.io.IOException ex) {
    System.err.println(ex.getMessage());
}
~~~

The **static type** of the `service` variable is `ReaderService`, so the compiler checks the call against the contract `ReaderService.load() throws IOException`. At runtime, the actual method may be `FileReaderService.load()` due to dynamic dispatch.

If the subclass could arbitrarily declare a checked `SQLException` that is completely absent from the superclass contract, the valid caller written above would **not be required by the compiler to handle** the SQL error. This would break the catch-or-declare guarantee that the superclass API provided.

Therefore, Java requires that a subclass method not broaden the checked exceptions permitted to escape through the overriding signature.

**Design implication:** a subclass object must be usable in places expecting the superclass, at least with respect to the compile-time guarantees about checked exception types. This is part of the substitutability contract, though it does not guarantee that all other behaviors of the subclass are automatically correct.

## 3. Quick rules for a superclass and a subclass

Suppose the superclass method is:

~~~java
public void execute() throws IOException;
~~~

In this example, `IOException` is the declared checked exception. For the corresponding override:

| Declaration in subclass | Valid? | Reason |
| --- | --- | --- |
| `void execute()` | Yes | Declares no checked exceptions. |
| `void execute() throws FileNotFoundException` | Yes | `FileNotFoundException` is a subclass of `IOException`. |
| `void execute() throws EOFException` | Yes | `EOFException` is a subclass of `IOException`. |
| `void execute() throws IOException` | Yes | Same checked type as the superclass. |
| `void execute() throws FileNotFoundException, EOFException` | Yes | Each type is covered by `IOException`. |
| `void execute() throws SQLException` | No | `SQLException` does not belong to the `IOException` branch. |
| `void execute() throws Exception` | No | `Exception` is broader than `IOException`. |
| `void execute() throws Throwable` | No | `Throwable` is checked under this classification and is broader. |
| `void execute() throws IOException, SQLException` | No | Adds a new `SQLException`, not permitted by the superclass. |
| `void execute() throws IllegalStateException` | Yes | `IllegalStateException` is unchecked. |
| `void execute() throws IOException, IllegalStateException` | Yes | The checked `IOException` part is valid; unchecked exceptions are not similarly restricted. |

The table only evaluates the **checked exception constraint in overriding**; complete code must also satisfy other conditions such as visibility, return type, static/instance, and accessibility of the types.

In particular, `throws FileNotFoundException, EOFException` is not "broadening" merely because there are more types in the list. What matters is **whether each declared checked type lies within the type range covered by the superclass contract**.

## 4. Narrowing, keeping, or omitting checked `throws`

An overriding method has three common strategies:

### 4.1. Keeping the permitted checked type

~~~java
// Illustrative snippet in a subclass of a class with method load() throws IOException.
@Override
String load() throws java.io.IOException {
    return java.nio.file.Files.readString(path);
}
~~~

This is valid if the superclass has the corresponding contract, `path` is a `Path` variable, and the rest of the code satisfies compilation requirements.

### 4.2. Narrowing to a specific subtype

~~~java
// Illustrative snippet in a subclass.
@Override
String load() throws java.io.FileNotFoundException {
    if (missing) {
        throw new java.io.FileNotFoundException("không thấy tệp");
    }
    return "OK";
}
~~~

Here `missing` is a hypothetical condition. Narrowing makes the subclass method's contract more specific. However, if the implementation calls an API that can throw a general `IOException`, you still must handle that broader error inside the body; you cannot use `throws FileNotFoundException` to declare every `IOException`.

### 4.3. Omitting the checked exception declaration

~~~java
// Illustrative snippet of an implementation reading from memory.
@Override
String load() {
    return cachedValue;
}
~~~

This is valid if the code in the body does not let an unhandled checked exception escape. In practice, a cache implementation may not need I/O and thus does not need to declare `IOException`.

**Core rule:** a subclass may **make fewer checked-error promises** than the superclass (declaring fewer types or more specific subtypes), but it must not arbitrarily add a checked exception group that callers of the superclass were not informed about.

## 5. Complete Java 17+ program: valid override

Save the file `OverrideCheckedDemo.java`:

~~~java
import java.io.FileNotFoundException;
import java.io.IOException;

public class OverrideCheckedDemo {
    static class Loader {
        String load(String name) throws IOException {
            throw new IOException("Lỗi đọc " + name);
        }
    }

    static final class LocalLoader extends Loader {
        @Override
        String load(String name) throws FileNotFoundException {
            if (!"known".equals(name)) {
                throw new FileNotFoundException("Thiếu " + name);
            }
            return "OK";
        }
    }

    static final class CachedLoader extends Loader {
        @Override
        String load(String name) {
            return "cache:" + name;
        }
    }

    public static void main(String[] args) {
        Loader first = new LocalLoader();
        try {
            first.load("missing");
        } catch (IOException ex) {
            System.out.println("Lỗi qua kiểu cha: " + ex.getClass().getSimpleName());
        }

        Loader second = new CachedLoader();
        try {
            System.out.println("Dữ liệu: " + second.load("x"));
        } catch (IOException ex) {
            System.out.println("Không chạy");
        }

        CachedLoader concrete = new CachedLoader();
        System.out.println("Trực tiếp: " + concrete.load("y"));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 OverrideCheckedDemo.java
java OverrideCheckedDemo
~~~

Exact stdout:

~~~text
Lỗi qua kiểu cha: FileNotFoundException
Dữ liệu: cache:x
Trực tiếp: cache:y
~~~

### Why does `main` have two different call styles?

- `LocalLoader.load()` declares `FileNotFoundException` (a checked subtype), which is valid because `Loader.load()` declared `IOException`.
- `CachedLoader.load()` declares no checked exceptions; this is a completely valid **narrowing of the declared exception set**.
- `first` has static type `Loader`, so the call `first.load(...)` is checked against `Loader.load()`'s `throws IOException`; `catch (IOException)` can handle `FileNotFoundException`.
- `second` also has static type `Loader`, even though the actual object is `CachedLoader`; the compiler still requires handling `IOException` when calling `second.load("x")` through the supertype.
- The variable `concrete` has static type `CachedLoader`, so the call `concrete.load("y")` **does not need `try/catch IOException`**, because `CachedLoader.load` itself declares no checked exceptions.
- The fact that `catch` in `second` does not execute is a runtime characteristic of the example, not a reason for the compiler to skip the checked exception rule when calling through a supertype.

This is where **compile-time reference type** must be distinguished from **the implementation selected at runtime**. Dynamic dispatch decides which method body runs; the checked exception checking rule at a call site is based on the signature permitted by the static type and context.

## 6. Invalid example: changing `IOException` to `SQLException`

Save the following file as `InvalidOverride.java`. It is written **intentionally wrong to observe the compilation error**:

~~~java
import java.io.IOException;
import java.sql.SQLException;

class InvalidOverride {
    static class Parent {
        void execute() throws IOException { }
    }

    static class Child extends Parent {
        @Override
        void execute() throws SQLException { }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 InvalidOverride.java
~~~

JDK 17's `javac` produces the core message:

~~~text
execute() in Child cannot override execute() in Parent
overridden method does not throw SQLException
~~~

The path, line number, column number, and caret position in the message may vary. The reason does not change: `SQLException` is a checked exception **not permitted by `Parent.execute()`**, because it is not a subclass of `IOException`.

**There is no fix by adding `@Override` or changing the order in the `throws` clause.** The `@Override` annotation helps the compiler verify overriding intent; it does not change the exception contract.

If you change the subclass to:

~~~java
// Illustrative replacement for Child above.
static class Child extends Parent {
    @Override
    void execute() throws java.io.FileNotFoundException { }
}
~~~

then the checked exception constraint alone will be valid. If the code truly needs to perform database operations and may fail with `SQLException`, you must choose one of the approaches in the next section.

## 7. What if the implementation actually calls an API that can throw a new checked exception?

Suppose the supertype defines:

~~~java
interface Processor {
    void process() throws java.io.IOException;
}
~~~

The implementation wants to call a database library that can throw `SQLException`:

~~~java
// INVALID if the subclass method directly declares SQLException.
@Override
public void process() throws java.sql.SQLException {
    databaseOperation();
}
~~~

This is only illustrative: `databaseOperation()` needs to be defined, and if the implementation lets `SQLException` escape, the compiler will reject it because the interface does not declare that type.

There are several design approaches, depending on the layer's responsibility:

### 7.1. Catch the SQL error and genuinely handle it in the implementation

~~~java
@Override
public void process() throws java.io.IOException {
    try {
        databaseOperation();
    } catch (java.sql.SQLException ex) {
        recoverDatabaseOperation(ex);
    }
}
~~~

The snippet above depends on `databaseOperation()` and `recoverDatabaseOperation(...)`. It is only valid if `recoverDatabaseOperation` properly resolves the problem without letting an incompatible checked exception escape. **Do not swallow the error** and pretend to succeed if the data or state is no longer valid.

### 7.2. Translate the error into a type already permitted by the contract, preserving the cause

~~~java
@Override
public void process() throws java.io.IOException {
    try {
        databaseOperation();
    } catch (java.sql.SQLException ex) {
        throw new java.io.IOException("Không thể xử lý dữ liệu", ex);
    }
}
~~~

In terms of types, `IOException` is permitted by the interface, so the compile-time constraint is satisfied. However, this mapping should only be applied if `IOException` **genuinely makes sense in the contract**. Do not wrap every SQL error as an "I/O error" just to get past the compiler when the API abstraction does not consider it a reasonable case.

### 7.3. Wrap in a custom unchecked exception at the right abstraction

~~~java
@Override
public void process() {
    try {
        databaseOperation();
    } catch (java.sql.SQLException ex) {
        throw new ProcessingUnavailableException(
                "Không thể thực hiện thao tác", ex);
    }
}
~~~

This example requires defining `ProcessingUnavailableException extends RuntimeException` with a constructor taking `(String, Throwable)`. Because it is unchecked, it does not violate the `throws` restriction of overriding.

**However, unchecked is not automatically the best approach.** Converting checked to unchecked means callers are no longer forced by the compiler to handle it; if the error genuinely requires mandatory recovery, you should revisit the interface contract itself.

### 7.4. Update the supertype contract if you control the API

If the `Processor` contract is designed for both I/O and SQL, you can update it to declare a shared checked exception that makes sense for the abstraction, or define a domain exception to serve as the common contract. Such a change may force existing callers to update their `catch`/`throws`; evaluate compatibility before modifying a public API.

You should not simply broaden `throws Exception` for the convenience of every implementation. That makes the contract vague and pushes unnecessary handling obligations onto callers.

## 8. Checked exceptions and unchecked exceptions follow different rules

The `throws` restriction on overriding in this lesson **targets only checked exceptions**. A subclass method may declare new unchecked types:

~~~java
class Parent {
    void execute() throws java.io.IOException { }
}

class Child extends Parent {
    @Override
    void execute() throws IllegalStateException {
        throw new IllegalStateException("không hợp lệ ở trạng thái hiện tại");
    }
}
~~~

This is a valid illustration regarding the `throws` constraint: the subclass declares no new checked exceptions, and `IllegalStateException` is unchecked.

Even if the supertype method has no `throws`:

~~~java
interface Greeter {
    String greet(String name);
}

class StrictGreeter implements Greeter {
    @Override
    public String greet(String name) throws IllegalArgumentException {
        if (name == null) {
            throw new IllegalArgumentException("name không được null");
        }
        return "Xin chào " + name;
    }
}
~~~

Java still allows this checked/unchecked policy, because `IllegalArgumentException` is unchecked. However, **what the language permits does not mean the behavioral contract is always good**: an implementation should not arbitrarily tighten preconditions in ways that surprise callers of the interface.

Subclasses of `Error` are also unchecked according to the language, but **you should not use `Error` to represent ordinary business errors**. Do not interpret "not checked during overriding" as advice to declare `throws Error` to bypass constraints.

## 9. An interface is also a checked exception contract

An interface can declare:

~~~java
import java.io.IOException;

interface DataReader {
    String read() throws IOException;
}
~~~

Implementation:

~~~java
class InMemoryReader implements DataReader {
    @Override
    public String read() {
        return "memory";
    }
}
~~~

Completely valid: the implementation throws no checked exceptions, even though the interface permits `IOException`.

Another implementation:

~~~java
class FileDataReader implements DataReader {
    @Override
    public String read() throws java.io.FileNotFoundException {
        throw new java.io.FileNotFoundException("không thấy dữ liệu");
    }
}
~~~

Also valid: `FileNotFoundException` is in the `IOException` family. Conversely, an implementation cannot directly declare `throws SQLException` on the same method because the interface does not allow it.

**An interface method may have no body**, yet its `throws` clause is still a real constraint on implementing classes. If an interface has a `default` method, an implementing class overriding the default method must still obey the checked exception contract of the overridden method.

Java does not force an implementation to list the **exact same** `throws` list as the interface. The number or order of types matters less than the **subtype relationship** of the declared checked exceptions.

## 10. When a method must implement two interfaces with different contracts

An advanced but very practical case:

~~~java
import java.io.IOException;
import java.sql.SQLException;

interface TextFromFile {
    String load() throws IOException;
}

interface TextFromDatabase {
    String load() throws SQLException;
}
~~~

A class can `implements TextFromFile, TextFromDatabase` if it provides **one shared implementation** of `load()`. However, that implementation must satisfy **both contracts**.

Complete program `TwoInterfacesDemo.java`:

~~~java
import java.io.IOException;
import java.sql.SQLException;

public class TwoInterfacesDemo {
    interface TextFromFile {
        String load() throws IOException;
    }

    interface TextFromDatabase {
        String load() throws SQLException;
    }

    static class Combined implements TextFromFile, TextFromDatabase {
        @Override
        public String load() {
            return "kết quả chung";
        }
    }

    public static void main(String[] args) {
        Combined x = new Combined();
        System.out.println("Gọi implementation: " + x.load());

        TextFromFile fileView = x;
        try {
            System.out.println("Gọi interface: " + fileView.load());
        } catch (IOException ex) {
            System.out.println("Không chạy");
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 TwoInterfacesDemo.java
java TwoInterfacesDemo
~~~

Exact stdout:

~~~text
Gọi implementation: kết quả chung
Gọi interface: kết quả chung
~~~

### Why must checked `throws` be omitted in this implementation?

`IOException` is not a subtype of `SQLException`, and `SQLException` is not a subtype of `IOException`. Because the single method `Combined.load()` must satisfy both interfaces, it **cannot declare `throws IOException` or `throws SQLException`**. Omitting the checked exception declaration satisfies both contracts.

Diagram:

~~~text
TextFromFile.load()       throws IOException
          \                    /
           \                  /
            Combined.load()  declares no checked exceptions
           /                  \
          /                    \
TextFromDatabase.load()   throws SQLException
~~~

This example illustrates two checked branches without a suitable common subtype. In general, an implementation **can declare a specific checked type if it satisfies all contracts simultaneously** (for example, a special subtype if the system has an appropriate type hierarchy). You should not assume that every method implementing multiple interfaces is forbidden from declaring any checked exception.

**When calling through `fileView`**, the compiler still uses the signature `TextFromFile.load() throws IOException`, so `main` must handle the appropriate checked exception, even though the actual implementation `Combined.load()` does not throw that type. When calling directly through a `Combined` variable, no `catch` is needed.

## 11. Invalid example when combining two interfaces

The file `InvalidIntersection.java` below **intentionally does not compile**:

~~~java
import java.io.IOException;
import java.sql.SQLException;

class InvalidIntersection {
    interface A {
        void execute() throws IOException;
    }

    interface B {
        void execute() throws SQLException;
    }

    static class Both implements A, B {
        @Override
        public void execute() throws IOException { }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 InvalidIntersection.java
~~~

The key part of the Java 17 `javac` message:

~~~text
execute() in Both cannot implement execute() in B
overridden method does not throw IOException
~~~

Class `Both` satisfies interface A regarding exceptions, but **does not satisfy interface B**. The compiler checks every contract that the same method must fulfill, not just the first contract you think of.

The simple fix for an example that does not need checked exceptions is to remove `throws IOException` from `Both.execute()`. If the body calls an API that actually throws `IOException`, you must handle it internally, wrap it in an appropriate exception, or intentionally redesign the interfaces.

**Do not fix it with `throws Exception`.** `Exception` is broader than both `IOException` and `SQLException`, and resolves neither contract's constraint.

## 12. Which checked exceptions are allowed when the superclass declares multiple types

Suppose:

~~~java
class Parent {
    void operate() throws java.io.IOException, java.sql.SQLException {
        // ...
    }
}
~~~

The subclass can declare:

~~~java
class Child extends Parent {
    @Override
    void operate() throws java.io.FileNotFoundException {
        // ...
    }
}
~~~

Because `FileNotFoundException` is a subtype of `IOException`, it only needs to be covered by **at least one checked branch permitted by the superclass**, provided all other relevant overriding contracts are also satisfied.

It is also possible to keep both `IOException` and `SQLException`, or only `SQLException` if the implementation suits it. The subclass is not required to declare all the types present in the superclass.

However:

~~~java
// Invalid if the superclass method only permits IOException and SQLException.
@Override
void operate() throws java.text.ParseException {
    // ...
}
~~~

`ParseException` is a different checked exception, belonging to neither `IOException` nor `SQLException`, so it cannot be added in the override declaration.

In summary, for a typical single-supertype contract, **each checked type listed by the override must be covered by a checked type in the supertype's `throws`**. With multiple inheritance contracts, compatibility must be checked against each contract individually, rather than merely merging the `throws` lists of all supertypes into one arbitrary allowed set.

## 13. Can an overriding method without `throws` throw a checked exception internally?

**It can create or receive a checked exception in the body**, but it **cannot let an incompatible checked exception escape**. For example, an implementation can catch `IOException` completely:

~~~java
import java.io.IOException;

// Illustrated inside a class that implements a suitable interface.
@Override
public String load() {
    try {
        return readData();
    } catch (IOException ex) {
        return "giá trị dự phòng";
    }
}
~~~

`readData()` must be defined with `throws IOException`; this snippet is not standalone. If returning fallback data is valid according to the contract, the implementation can complete normally without `throws IOException`.

Conversely, the following is invalid when the supertype does not declare `IOException`:

~~~java
@Override
public String load() {
    throw new java.io.IOException("lỗi đọc"); // Compilation error.
}
~~~

The message typically involves **unreported exception IOException; must be caught or declared to be thrown**. Yet if you add `throws IOException` to the override while the superclass/interface does not allow it, you hit an **overriding constraint error**.

Two compile-time requirements exist simultaneously:

1. **The body must handle or declare any checked exception that can escape.**
2. **The `throws` clause of the override must not broaden checked exceptions beyond the supertype contract.**

You cannot "bypass" these two requirements merely by changing keywords without altering the handling or design.

## 14. `throw` and `throws` are different

`throw` is a statement that **throws an actual Throwable object**:

~~~java
throw new java.io.FileNotFoundException("missing");
~~~

`throws` in a signature **declares the exception types that may propagate out of the method**:

~~~java
void read() throws java.io.IOException {
    throw new java.io.FileNotFoundException("missing");
}
~~~

In the method above, the actual type thrown is `FileNotFoundException`; `throws IOException` is valid because it covers the subtype.

In the overriding constraint, the compiler checks the **declared checked types** and the exceptions the body can throw. The fact that you only throw `FileNotFoundException` in one branch does not allow broadening the declaration to `throws Exception` if the superclass only declares `throws IOException`.

**Overly broad declarations can also prevent the program from compiling**, even if the actual implementation never throws that broader type. Therefore, choose a `throws` list that accurately reflects the contract and inherited limits.

## 15. Constructor inheritance is not like method overriding

Constructors **are not overridden like instance methods**. A subclass can have its own constructor declaring checked exceptions needed for object creation, though when calling the superclass constructor it must obey the checked exception checking of the `super(...)` call.

Example:

~~~java
import java.io.IOException;
import java.sql.SQLException;

class Parent {
    Parent() throws IOException {
        // ...
    }
}

class Child extends Parent {
    Child() throws IOException, SQLException {
        super();
        // May have its own step requiring SQLException.
    }
}
~~~

This snippet is valid with respect to constructor checked exception constraints: `Child()` does not "override `Parent()`"; it is an independent constructor of the subclass, declaring both `IOException` from `super()` and its own `SQLException` if appropriate.

Key point to remember: **do not apply the method overriding `throws` rule directly to constructors**. Constructors are checked according to invocation and initialization rules, not same-signature overriding relationships.

## 16. Overloading is not overriding either

Consider:

~~~java
class Parent {
    void save(String value) throws java.io.IOException { }
}

class Child extends Parent {
    void save(int value) throws java.sql.SQLException { }
}
~~~

`Child.save(int)` is an **overloaded** method, because its parameter list differs from `Parent.save(String)`. It does not override `save(String)`, so it is not constrained by the other method's `throws IOException`.

However, if you change it to `Child.save(String) throws SQLException`, that is an overriding candidate with the matching signature and violates the checked exception rule.

**Use `@Override` to verify intent.** If you accidentally change the method name or parameter type so that it becomes an overload, the compiler will report an error when the annotation does not point to a valid overridden method. This helps avoid subtle bugs when you think you have replaced superclass logic.

Similarly, `static` methods participate in **method hiding**, not dynamic overriding like instance methods, yet Java still has signature compatibility constraints, including checked exceptions, for static methods with an applicable hiding relationship. Do not use `static` as a way to evade the contract.

## 17. What else do overriding rules involve?

`throws` is only **one part** of the overriding conditions. A subclass method must also satisfy:

- **Valid signature:** same name and parameters according to overriding rules, including generic/subsignature cases defined by the JLS.
- **Compatible return type:** Java supports **covariant return types** under appropriate conditions; return type rules are separate from checked exception rules.
- **No illegal narrowing of visibility:** for example, you cannot override a `public` method with a `private` method.
- **`final`:** a `final` instance method cannot be overridden.
- **Static vs instance:** you cannot arbitrarily turn an instance method into a static one to override it.
- **Generic throws/type variables:** with parameterized types and type variables, the JLS has detailed rules on substitution, erasure, and potential unchecked warnings.

In basic cases with `IOException`, `SQLException`, and their subclasses, the principle "checked exceptions no broader than the supertype contract" is the primary tool. When building complex generic APIs, do not apply a simple type-name string comparison in place of full JLS type checking.

You may encounter legacy code using raw types or generic relationships that produce an **unchecked warning** about `throws`. A type warning does not mean Java allows an override to arbitrarily throw any checked exception; consult the exact JLS rules and fix the generic structure when needed.

## 18. When calling via an interface vs. a concrete class, `catch` can differ

Notice:

~~~java
interface Service {
    void run() throws java.io.IOException;
}

class FastService implements Service {
    @Override
    public void run() {
        System.out.println("OK");
    }
}
~~~

If the calling code is:

~~~java
Service service = new FastService();
try {
    service.run();
} catch (java.io.IOException ex) {
    // Valid: the Service type declares IOException.
}
~~~

the compiler uses `Service.run() throws IOException`, because the variable has static type `Service`.

If the calling code is:

~~~java
FastService concrete = new FastService();
concrete.run(); // Does not need try/catch IOException.
~~~

the compiler uses `FastService.run()`, which declares no checked exceptions. This is important behavior when an API is designed so that implementations can offer different capabilities, while general callers must handle a consistent contract.

Do not explain this as the compiler "inspecting the real object's class at runtime to know which exceptions need to be caught." The checked exception rule is **checked at compile time**, whereas Java selects the instance method implementation at runtime.

## 19. Do not automatically broaden a contract by changing `throws` in an override

Sometimes you want to add a new failure path after changing an implementation—for example, a later version switches from reading a cache to calling a database. If the interface method has the signature:

~~~java
String find() throws java.io.IOException;
~~~

you **cannot just edit the implementation** to:

~~~java
@Override
public String find() throws java.sql.SQLException {
    // ...
}
~~~

That breaks the compile-time constraint. A decision must be made at the **API design boundary**:

1. Can the SQL error be handled/retried locally in the implementation so it does not escape?
2. Is there an exception type belonging to the existing contract that is semantically appropriate to wrap the SQL error?
3. Should the API be publicly updated so callers receive a new error abstraction?
4. If the public checked exception changes, how are existing callers and source compatibility affected?
5. Should the interface be split when implementations have fundamentally different error contracts?

For library code, adding `throws Exception` to the supertype is not a default solution because it forces every caller to handle an overly broad type. Changing a contract requires documentation, tests, and a clear upgrade plan.

## 20. Connection to the substitutability principle and API design

A subclass used in place of its superclass can guarantee that it "does not introduce additional checked error types that must be handled." This allows callers to write code against the abstraction while the compiler verifies exception obligations.

However, Java's rule **does not solve the entire substitutability problem**:

- A subclass can still throw a new unchecked exception and the compiler will accept it.
- A subclass can alter results, input conditions, or side effects in ways that break caller expectations.
- A method that declares no checked exceptions can still fail at runtime due to environment errors, bugs, or logic issues.

Therefore, when designing an override, consider the **semantic contract** alongside `throws`: preconditions, postconditions, state after failure, and how the application recovers.

A subclass should not use unchecked exceptions as a tool to **systematically bypass** a checked exception that callers actually need to handle. If every valid implementation needs to declare a new error, the issue may lie in the abstraction design.

## 21. Common compilation errors and how to fix them

| Error or misconception | Why it happens | How to fix |
| --- | --- | --- |
| Overriding with `throws SQLException` while supertype only has `throws IOException` | Adds a checked exception outside the supertype contract | Catch it, wrap it in the right abstraction, or adjust the API design |
| Overriding with `throws Exception` when supertype only has `throws IOException` | Broader checked type | Keep `IOException` or an appropriate subtype |
| Overriding with `throws IOException` when supertype has no checked `throws` | No corresponding checked exception is permitted | Handle internally or choose another error mechanism fitting the contract |
| Thinking any subclass can add any checked type | Breaks the contract for callers using the supertype | Every overridden checked exception must be permitted by the contract |
| Thinking omitting `throws` means the body cannot use checked APIs | The body can call them and catch the error | Handle completely before the method finishes |
| Two interfaces declare different checked exceptions, implementation picks one | Must satisfy **both**, not just one | Omit/catch checked exceptions if there is no valid common subtype |
| Caller via supertype does not catch `IOException` because it knows the real object is a cache class | Compiler checks against the **static type** of the call | Catch/declare according to the static type's contract |
| Thinking unchecked exceptions must also be subtypes of the supertype's checked ones | Unchecked exceptions are not similarly restricted | Still ensure sound semantic design |
| Changing signature to `throws RuntimeException` to pass the compiler | May hide a real error path callers need to handle | Reconsider the contract instead of bypassing with unchecked |
| Confusing `throw` with `throws` | One throws an object, the other declares potential error types | Distinguish statement from method declaration |
| Confusing constructor inheritance with overriding | Constructors are not overridden methods | Apply constructor-specific rules |
| Changing parameters to an overload and thinking it overrides | A method with a different signature does not replace the old one | Use `@Override`, verify the signature |
| Fixing compiler errors solely by removing `throws` | Checked exceptions may still escape from the body | Fix the handling path or propagate a valid error |

## 22. Checklist before declaring `throws` on an override

When reviewing a subclass or implementation, go through these steps in order:

1. **Identify the exact superclass/interface method being overridden**, without confusing it with an overload.
2. **Read the list of declared checked exceptions** on each relevant supertype method.
3. **Classify each type listed in the subclass's `throws`**: checked or unchecked?
4. For **each checked exception in the subclass**, verify that it is permitted by the relevant supertype contracts according to subtype relationships and JLS rules.
5. If there are multiple interfaces, **check each contract individually**; do not simply merge the lists.
6. Read the **actual body** to identify checked exceptions that can escape from called APIs or `throw`.
7. If there is a new checked exception, decide whether to handle/recover, wrap with a cause, or change the abstraction.
8. Verify that **calls through the supertype** are caught/declared properly by callers.
9. Keep `@Override` to avoid signature mistakes and check visibility, static/instance, and return type.
10. Compile at least one **success** path and one **failure** path; for public APIs, add tests using interface/superclass-typed variables.
11. Document necessary `@throws` conditions; do not use Javadoc as a substitute for a required checked exception signature.
12. Avoid wrapping errors into unchecked exceptions just to silently change caller obligations.

## 23. Self-check

**Question 1.** Parent declares `void read() throws IOException`. Can Child declare `throws FileNotFoundException`?

**Answer:** Yes. `FileNotFoundException` is a checked subtype of `IOException`.

**Question 2.** With the same parent, is it valid for Child to declare `throws Exception`?

**Answer:** No. `Exception` is broader than `IOException`.

**Question 3.** Is it valid for Child to omit `throws` completely?

**Answer:** Yes, provided the body does not let an unhandled checked exception escape.

**Question 4.** Is it valid for Child to declare `throws IllegalStateException` when Parent declares no checked exceptions?

**Answer:** Yes with respect to the checked `throws` constraint, because `IllegalStateException` is unchecked.

**Question 5.** If a variable has static type `Parent` but holds a `Child` object that omitted `throws IOException`, how must the caller of `variable.read()` handle `IOException`?

**Answer:** According to `Parent`'s signature during compile-time checking; the caller must still catch or declare `IOException` if the superclass method declares that type.

**Question 6.** Two interfaces both have `load()`; interface A has `throws IOException` and B has `throws SQLException`. Is an implementation with no checked `throws` valid?

**Answer:** Yes, as long as the body does not let a checked exception violating the contracts escape and other overriding rules are satisfied.

**Question 7.** In the two-interface example above, is an implementation declaring `throws IOException` valid?

**Answer:** No; it does not satisfy contract B because `IOException` is not a subtype of `SQLException`.

**Question 8.** If the override body calls an API throwing `SQLException` while the superclass only allows `IOException`, can you omit `throws SQLException` and let the exception escape on its own?

**Answer:** No. A checked exception must be caught or declared with a permitted type; it cannot be allowed to escape unhandled merely by omitting the declaration.

**Question 9.** Does this rule apply identically to subclass constructors?

**Answer:** No. Constructors do not override; they have their own signatures and checked exception obligations when calling `super(...)` or performing operations inside the constructor.

**Question 10.** If a subclass defines a method with the same name but different parameters, is that overriding?

**Answer:** Usually that is overloading; `@Override` helps the compiler check whether it is truly a valid override.

**Question 11.** Why shouldn't you convert every `SQLException` into an `IOException` just to compile?

**Answer:** Because language-level type compatibility does not replace abstraction correctness; an improper mapping misleads callers about the nature of the error. Only wrap when the target type makes contractual sense, and preserve the `cause`.

**Question 12.** An interface method declares `throws Exception`. Can an implementation use `throws IOException`?

**Answer:** Yes, because `IOException` is a checked subtype of `Exception` (assuming no stricter overriding contract applies).

## 24. References

- [Java Language Specification 17 — §8.4.8.3, Requirements in Overriding and Hiding](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8.3): checked exception restrictions in overriding/hiding methods, along with return and signature conditions.
- [Java Language Specification 17 — §8.4.6, Method Throws](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.6): meaning of the `throws` clause and exception classification.
- [Java Language Specification 17 — §9.4.1, Inheritance and Overriding](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.4.1): interface method relationships and inheritance rules.
- [Java Language Specification 17 — §11.2, Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2): catch-or-declare and exceptions that can be thrown from a body.
- [Java SE 17 API — `IOException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html) and [`FileNotFoundException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/FileNotFoundException.html): reference for subtype relationships.
- [Java SE 17 API — `SQLException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLException.html): checked exception in a different branch from `IOException`.

**Conclusion:** when a method **overrides** a superclass/interface method, its `throws` list must not declare new or broader checked exceptions beyond the inherited contract. You can **narrow, keep, or omit** permitted checked exceptions; unchecked exceptions are not similarly restricted. If an implementation needs to raise a different checked exception, **handle it, wrap it in the right abstraction with a cause, or revisit the API contract**, rather than merely changing the signature to get past the compiler.
