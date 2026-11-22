# Relationship Between the Exception Type Declared in `throws` and the Subclass Actually Thrown in Java

A Java method can declare `throws IOException` yet at runtime throw a `FileNotFoundException` or `EOFException` object. This is completely valid because those types are **subclasses of `IOException`**. The `throws` clause describes the **checked exception contract that the caller must account for at compile time**, whereas the object thrown at runtime still has its own **actual type**.

Short example:

```java
static void load() throws java.io.IOException {
    throw new java.io.FileNotFoundException("config.txt");
}
```

This is an illustrative method and needs to be placed inside a Java class. `FileNotFoundException extends IOException`, so `throws IOException` is sufficient for the compiler to allow this checked exception to propagate outward. At the caller:

```java
try {
    load();
} catch (java.io.IOException ex) {
    System.out.println(ex.getClass().getSimpleName());
}
```

The printed output is `FileNotFoundException`, **not `IOException`**. The `catch (IOException)` handler catches the subclass object, but catching it does not turn the object into a plain `IOException`.

To understand this properly, separate three layers of information:

1. **Declared exception type:** the type that appears after `throws` in the method signature.
2. **Actual runtime exception type:** the class of the `Throwable` object coming out of the `throw` statement or called API.
3. **Catch parameter type:** the type in the caller's `catch` branch; the handler matches if the actual object is of that type or a subclass of it.

## 1. `throws` Is a Compile-Time Contract

A method declaration has the form:

```java
static String read(String path) throws java.io.IOException {
    return java.nio.file.Files.readString(
            java.nio.file.Path.of(path));
}
```

This is an illustrative method that depends on an actual file at runtime. The `throws IOException` part indicates that the method is allowed to let `IOException` or its checked subclasses propagate out. For a call that can throw `IOException`, the compiler requires the calling code to **catch (`catch`) or further declare (`throws`)** that checked exception.

Example of a valid caller:

```java
static String readAtService(String path)
        throws java.io.IOException {
    return read(path);
}
```

Or a caller with a handler:

```java
static void printFile(String path) {
    try {
        System.out.println(read(path));
    } catch (java.io.IOException ex) {
        System.out.println("Không đọc được tệp");
    }
}
```

These snippets are illustrative methods and must be placed in the same scope where `read` can be called.

**Key takeaway:** declaring `throws IOException` does not throw anything by itself. A call may return normally. This clause also does not promise that the runtime exception must have the **exact class** `IOException`; subclasses such as `NoSuchFileException` or `FileNotFoundException` can appear if the corresponding operation actually throws them.

At the same time, `throws` is **not an exhaustive list of every exception that can occur at runtime**: unchecked exceptions such as `IllegalArgumentException`, `NullPointerException`, and `Error` instances can escape without appearing in the `throws` clause.

## 2. Why Does Declaring a Supertype Cover Subclasses?

In Java, the inheritance relationship allows an object of a subclass to be used where a superclass is expected. This rule also applies to exceptions.

Part of a typical hierarchy:

```text
Throwable
├── Error
└── Exception
    ├── IOException
    │   ├── FileNotFoundException
    │   └── EOFException
    └── RuntimeException
        ├── IllegalArgumentException
        │   └── NumberFormatException
        └── IllegalStateException
```

The tree only lists a few classes; many other exception classes are not shown.

With this tree:

- `throws IOException` can cover `FileNotFoundException` and `EOFException`.
- `throws Exception` can cover `IOException` and many other checked exceptions under `Exception`; it is usually **too broad** if the API can only raise meaningful I/O errors.
- `throws FileNotFoundException` does **not** cover a general `IOException`, because `IOException` is the **supertype**, not a subtype of `FileNotFoundException`.
- `throws RuntimeException` is valid syntax, but unnecessary to satisfy checked exception rules because `RuntimeException` and its subclasses are unchecked.
- `throws Exception` **does not describe `Error`**: `Error` is a different branch of `Throwable`. Even so, an `Error` can still occur without being declared.

### Important Direction of the Relationship

Suppose `ChildException extends ParentException`:

```java
class ParentException extends Exception {}
class ChildException extends ParentException {}

static void childOperation() throws ParentException {
    throw new ChildException();
}
```

The code consists of illustrative declarations that need to be placed in a valid Java class or file structure. It compiles: the method declares the checked supertype and throws the subtype.

The reverse direction:

```java
static void invalidOperation() throws ChildException {
    throw new ParentException();
}
```

The snippet above **intentionally does not compile**: `ParentException` is not a `ChildException`, and the thrown checked supertype exception is not covered by a declaration that only allows the subtype. Fix it by changing the declaration to `throws ParentException`, or only throwing the subtype, or catching the error inside the method.

In other words, for checked exceptions **allowed to escape the method body**, the actual type produced along execution paths must be declarable/catchable under a compatible type. The fact that the caller sees the supertype in the contract **does not force** the runtime to create a supertype object.

## 3. Distinguishing Three Moments: Declaring, Throwing, and Catching

| Stage | Relevant code | What is determined? |
| --- | --- | --- |
| API declaration | `void load() throws IOException` | The checked exception type that the caller must prepare for based on the static type of the call |
| Actual operation | `throw new FileNotFoundException("...")` | The error object carries the runtime type `FileNotFoundException` |
| Caller handling | `catch (IOException ex)` | The handler is selected because `FileNotFoundException` is a subtype of `IOException` |

At runtime, Java does not convert a `FileNotFoundException` object into an `IOException` just because the signature declares the supertype. Therefore:

```java
if (ex instanceof java.io.FileNotFoundException) {
    // This is an actual FileNotFoundException.
}
```

You can use `instanceof` when you need to classify errors inside a general handler. If different error types require different actions, specific `catch` branches are usually easier to read:

```java
try {
    readDocument();
} catch (java.io.FileNotFoundException ex) {
    // Handle specifically when the operation actually throws FileNotFoundException.
} catch (java.io.IOException ex) {
    // Handle the remaining IOExceptions.
}
```

This is an illustrative structure: `readDocument()` needs to be a method with an appropriate declaration/call. `FileNotFoundException` must come **before** `IOException` because a supertype branch placed first would also catch the subtype error, making the subtype branch after it unreachable.

## 4. Complete Java 17+ Example: `throws IOException`, Multiple Types Thrown at Runtime

Save the file **`DeclaredVsActualExceptionDemo.java`**:

```java
import java.io.EOFException;
import java.io.FileNotFoundException;
import java.io.IOException;

public class DeclaredVsActualExceptionDemo {

    // A general checked contract for I/O failures.
    static void load(String scenario) throws IOException {
        switch (scenario) {
            case "missing" ->
                    throw new FileNotFoundException("settings.properties");
            case "short" ->
                    throw new EOFException("incomplete content");
            case "other" ->
                    throw new IOException("read failed");
            case "state" ->
                    throw new IllegalStateException("resource is closed");
            default ->
                    System.out.println("load: success");
        }
    }

    static void caller(String scenario) {
        System.out.println("CASE " + scenario);
        try {
            load(scenario);
            System.out.println("caller: completed");
        } catch (IOException ex) {
            System.out.println("caught as: IOException");
            System.out.println(
                    "actual type: " + ex.getClass().getSimpleName());
            System.out.println("message: " + ex.getMessage());
        } catch (IllegalStateException ex) {
            System.out.println(
                    "unchecked type: " + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        caller("ok");
        caller("missing");
        caller("short");
        caller("other");
        caller("state");
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 DeclaredVsActualExceptionDemo.java
java DeclaredVsActualExceptionDemo
```

**Deterministic stdout:**

```text
CASE ok
load: success
caller: completed
CASE missing
caught as: IOException
actual type: FileNotFoundException
message: settings.properties
CASE short
caught as: IOException
actual type: EOFException
message: incomplete content
CASE other
caught as: IOException
actual type: IOException
message: read failed
CASE state
unchecked type: IllegalStateException
```

### Result Analysis

**`missing`:** the method declares `throws IOException`, but the object created by `throw new FileNotFoundException(...)` has the actual class `FileNotFoundException`. The handler declaring `IOException` catches it due to the inheritance relationship. `getClass().getSimpleName()` still returns `FileNotFoundException`.

**`short`:** the same `throws IOException` signature, but the actual object is `EOFException`, another subclass of `IOException`. The caller does not need to know in advance **which exact** subclass will appear in order to compile and handle all I/O errors with an `IOException` handler.

**`other`:** in this case the object is actually an `IOException`; the declared type and runtime type happen to match.

**`state`:** `IllegalStateException` is not under `IOException`; it is an unchecked `RuntimeException`. Java still allows throwing it even though `load` only declares `throws IOException`. The `catch (IOException)` handler does not catch it; the `catch (IllegalStateException)` branch is selected.

**`ok`:** `load` does not throw an error and the caller prints `"completed"`. A `throws` declaration only describes a possibility, not a guarantee that an exception will occur.

The example simulates failures using direct `throw` statements so it does not depend on real file paths or OS-specific errors.

## 5. The Caller Must Handle Based on the Declared Type, and Can Branch on the Runtime Type

When writing a call, the compiler looks at the **static type of the called method** and the checked exceptions declared/analyzed according to language rules. Given:

```java
static void load() throws java.io.IOException {
    // May perform data reading and raise an I/O error.
}
```

An actual caller must handle or declare `IOException`, for example:

```java
static void operation() throws java.io.IOException {
    load();
}
```

If you remove `throws IOException` from `operation()` without adding a `catch`, the compiler reports an uncaught/undeclared checked exception error. It does not need to, and usually cannot, prove in advance which exact subclass will be thrown on every run of `load`.

### Should You Catch Subclasses Separately?

If the caller knows how to handle them differently, you can place handlers in subtype → supertype order:

```java
try {
    load();
} catch (java.io.FileNotFoundException ex) {
    // Can report missing resource or choose an alternative path.
} catch (java.io.IOException ex) {
    // Handle other I/O errors according to the general contract.
}
```

Here `load()` is assumed to be able to raise `IOException`. Even though the signature declares `IOException`, a separate `FileNotFoundException` branch still makes sense because that subclass may be thrown at runtime. The `catch` order is checked against the inheritance hierarchy; do not place `catch (IOException)` before the `FileNotFoundException` branch.

If all I/O errors are handled the same way, a single `catch (IOException)` is more concise. There is no need to create handlers for every subclass just because they exist in the JDK.

### Is Catching Only the Subclass Enough?

No, if the method can also throw other kinds of `IOException`. For example:

```java
static void tooNarrow() {
    try {
        load();
    } catch (java.io.FileNotFoundException ex) {
        System.out.println("File not found");
    }
}
```

This is an **example that intentionally does not compile** if `load()` has the `throws IOException` declaration above: another `IOException` besides `FileNotFoundException` can still propagate out, yet `tooNarrow()` neither catches nor declares it. To fix this, add `catch (IOException)` after the subtype branch or declare `throws IOException` on `tooNarrow`.

## 6. The Broader the Declared Type, the Broader the Caller Contract

Suppose the same method only really needs to report a missing-file error:

```java
static void precise() throws java.io.FileNotFoundException {
    throw new java.io.FileNotFoundException("missing.txt");
}
```

Here `throws FileNotFoundException` gives the caller a narrow checked contract. The caller can catch `FileNotFoundException` or declare a compatible supertype such as `IOException`.

Meanwhile:

```java
static void broad() throws Exception {
    throw new java.io.FileNotFoundException("missing.txt");
}
```

`throws Exception` is also valid, but forces the caller to consider a much broader range of checked exceptions. If the caller only has `catch (IOException)`, declaring `throws Exception` can even prevent the calling code from compiling because other checked `Exception` types are still considered possible to escape.

| Declaration style | Checked exception types allowed to escape | Impact on the caller |
| --- | --- | --- |
| `throws FileNotFoundException` | `FileNotFoundException` and its subclasses | Narrow contract, clear specialized error |
| `throws IOException` | `IOException` and its subclasses | Caller handles the I/O error family |
| `throws Exception` | Checked exceptions under `Exception` | Broad; caller has difficulty knowing the exact failure category |
| No checked exception declared | No checked exception may escape uncaught in the normal way | Caller is not forced to handle checked exceptions from this method |
| `throws IOException, SQLException` | Two independent checked exception branches | Caller accounts for both I/O and SQL errors |

The goal is not always to declare the **narrowest leaf class**. A configuration-reading API might throw several `IOException` subclasses; declaring `throws IOException` is often the right level of abstraction. Conversely, `throws Exception` loses much of the contract's value if the method only has I/O errors.

Choose the declared type based on the **error category that callers can reasonably handle**, the likelihood of implementation changes, and API stability.

## 7. Overriding (`override`): A Subclass Method May Declare a Narrower Checked Exception

The supertype/subtype relationship also constrains **the signature of overriding methods**. Suppose an interface describes a document source where I/O errors can occur:

```java
interface DocumentSource {
    String fetch(String name) throws java.io.IOException;
}
```

An implementing class may declare only a narrower exception:

```java
class LocalDocumentSource implements DocumentSource {
    @Override
    public String fetch(String name)
            throws java.io.FileNotFoundException {
        if (name.isBlank()) {
            throw new java.io.FileNotFoundException("name is blank");
        }
        return "document";
    }
}
```

These are illustrative declarations and must be placed in a valid Java package/file. `FileNotFoundException` is a subtype of `IOException`, so this override is allowed.

Checked exception rules when overriding:

- The overriding method may **declare no checked exceptions**, if the implementation handles all checked exceptions internally.
- It may declare a **narrower checked type** within the scope of exceptions allowed by the parent method/interface.
- It must not widen the contract with a new or broader checked exception that the parent method does not allow, such as changing from `throws IOException` to `throws Exception`.
- It may throw **unchecked exceptions** regardless of whether the parent method declares any; the constraint above applies to checked exceptions.
- If a class implements multiple interfaces that share the same method with different checked exception contracts, the implementation must satisfy all relevant contracts simultaneously; it cannot arbitrarily take the union of all checked exception types.

### Complete Java 17+ Example: Interface and Implementing Class

Save the file **`OverrideThrowsDemo.java`**:

```java
import java.io.FileNotFoundException;
import java.io.IOException;

public class OverrideThrowsDemo {

    interface DocumentSource {
        String fetch(String name) throws IOException;
    }

    static final class LocalDocumentSource implements DocumentSource {
        @Override
        public String fetch(String name)
                throws FileNotFoundException {
            if ("missing".equals(name)) {
                throw new FileNotFoundException(name + ".txt");
            }
            return "loaded:" + name;
        }
    }

    static void useInterface(DocumentSource source) {
        try {
            System.out.println(source.fetch("missing"));
        } catch (IOException ex) {
            System.out.println(
                    "interface caller catches: "
                    + ex.getClass().getSimpleName());
        }
    }

    static void useConcrete(LocalDocumentSource source) {
        try {
            System.out.println(source.fetch("missing"));
        } catch (FileNotFoundException ex) {
            System.out.println(
                    "concrete caller catches: "
                    + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws FileNotFoundException {
        LocalDocumentSource source = new LocalDocumentSource();
        useInterface(source);
        useConcrete(source);
        System.out.println(source.fetch("found"));
    }
}
```

Run:

```bash
javac -encoding UTF-8 OverrideThrowsDemo.java
java OverrideThrowsDemo
```

**Stdout:**

```text
interface caller catches: FileNotFoundException
concrete caller catches: FileNotFoundException
loaded:found
```

**Why do two callers with different contracts see the same exception type?**

- `useInterface` receives a `DocumentSource` variable. By the **static type of the call**, the interface's `fetch` signature has `throws IOException`; therefore, an `IOException` handler satisfies compile-time checking.
- `useConcrete` receives a `LocalDocumentSource` variable. The compiler sees the narrower override declaration `throws FileNotFoundException`, so catching just the subclass is sufficient for this checked exception.
- Both invoke the `LocalDocumentSource.fetch` implementation at runtime, and the thrown error object is `FileNotFoundException` in both cases. The difference lies in the **type information available at compile time**, not the runtime coercing the error into the supertype.
- `source.fetch("found")` returns `"loaded:found"` and does not throw a checked exception on this branch; however, the concrete signature still indicates the possibility of `throws FileNotFoundException`. In `main`, that final call is also checked by the compiler against the concrete `throws FileNotFoundException` signature, so `main` itself declares `throws FileNotFoundException` for the complete program to compile.

### Override Relationship Order: Invalid Example

```java
interface Reader {
    void read() throws java.io.IOException;
}

class InvalidReader implements Reader {
    @Override
    public void read() throws Exception {
        // ...
    }
}
```

The example above **intentionally does not compile** because `throws Exception` is broader than `throws IOException` in the parent contract. A caller receiving a `Reader` is only required to account for `IOException`; if an implementation were allowed to add any other checked `Exception`, the supertype contract would be broken.

An overriding class can use `throws FileNotFoundException` or have no checked `throws`, but it cannot arbitrarily increase the checked exception exposure published by the supertype.

## 8. Note: `throws` Does Not Determine the Actual Type of the Object in `catch`

In Java, the clause:

```java
catch (java.io.IOException ex) {
    // ...
}
```

defines the **reference type** of the variable `ex` at compile time. It does not change the class of the object. If the object is a `FileNotFoundException`, then:

```java
ex instanceof java.io.FileNotFoundException
```

is `true` inside that branch. The methods directly available on `ex` are still limited by its static type `IOException` unless you use pattern matching `instanceof` or a safe cast.

Java 17 example of runtime type checking (placed inside a handler):

```java
if (ex instanceof java.io.FileNotFoundException missing) {
    System.out.println("Missing file: " + missing.getMessage());
} else {
    System.out.println("Other I/O: " + ex.getMessage());
}
```

This is an illustrative snippet, requiring `ex` to be a caught `IOException`. Pattern matching for `instanceof` supports binding the variable `missing` when the actual object belongs to the subclass; this feature is available in Java 17.

Branch on a subtype when the caller **genuinely has a distinct way to handle it**. If the subclass does not change the response, a single `IOException` handler may be enough. Do not use `ex.getMessage().contains("file")` to infer a subtype because the message is not a type contract.

## 9. Can a Different Exception Type Than the Declared Supertype Be Thrown?

Yes, but you must distinguish between **checked** and **unchecked**.

Suppose:

```java
static void load(String path) throws java.io.IOException {
    if (path == null) {
        throw new IllegalArgumentException("path is required");
    }
    if ("missing".equals(path)) {
        throw new java.io.FileNotFoundException(path);
    }
}
```

This is an illustrative method:

- `FileNotFoundException` is checked and is covered by `throws IOException`.
- `IllegalArgumentException` is unchecked, so it may be thrown without being listed in `throws`.
- A checked exception from a **different branch**, such as `java.sql.SQLException`, would require adding `throws SQLException` or being caught and handled inside the method. `throws IOException` does not cover `SQLException`.
- `Error` is also not required to be declared, though it should not be treated as a normal recoverable application failure.

Therefore, the statement "the method declares `throws IOException`, so it can only throw `IOException`" is **false**. A more accurate phrasing is: **checked exceptions allowed to propagate out in normal Java code must satisfy the declared contract**, while unchecked exceptions can still occur.

## 10. Wrapping a Subclass Exception Changes the Outer Type

Sometimes an upper-layer caller needs an error at a different level of abstraction. For example:

```java
static void loadRequiredConfiguration() {
    try {
        loadFile();
    } catch (java.io.FileNotFoundException cause) {
        throw new IllegalStateException(
                "Required configuration is missing", cause);
    } catch (java.io.IOException cause) {
        throw new IllegalStateException(
                "Required configuration cannot be read", cause);
    }
}
```

This is an **illustrative method**, assuming `loadFile()` can throw `IOException`. When wrapping:

1. The original exception may be `FileNotFoundException`, under the `IOException` branch.
2. The current layer creates **a new object** of type `IllegalStateException` and passes the original exception as `cause`.
3. The outer caller receives the **actual type of the new exception**, which is `IllegalStateException`, and will not automatically enter `catch (IOException)`.
4. If it needs to inspect the underlying I/O error, the caller or logging system inspects `ex.getCause()` and the cause chain. Do not assume `catch` automatically traverses `cause` to match the original type: `catch` only checks the object currently being thrown.

Wrapping can be appropriate when an application layer deliberately translates an I/O error into a state where a service cannot be initialized. However, do not wrap at every layer just to add a "failed" message; it alters the API contract and can prevent specialized handlers in callers from catching the error by its direct type.

### What About Rethrowing the Same Exception?

`throw ex;` rethrows the **same object** that was caught. Normally, the runtime type remains the original type; no new wrapper is created. For checked exceptions, the declaration of the method containing the rethrow must still satisfy compiler checking rules. Java has a more precise type analysis mechanism for certain cases of rethrowing an unmodified `catch` parameter (*precise rethrow*), but you should not conclude that any checked type can be rethrown without declaring it.

## 11. Declaring Multiple Checked Exceptions and Their Subclasses

A method can advertise multiple error categories:

```java
static void process()
        throws java.io.IOException, java.sql.SQLException {
    // May access files or a database.
}
```

This is an example of a **method signature**; the body does not implement real operations yet.

- `throws IOException, SQLException` indicates that both checked exception categories can escape.
- A `FileNotFoundException` is covered by `IOException`.
- A subclass of `SQLException` is covered by `SQLException`.
- The caller can choose two separate `catch` blocks if different actions are needed, or `catch (IOException | SQLException ex)` if the handling policy is the same.
- `IOException` and `SQLException` are not in a direct supertype/subtype relationship, so they can be combined in a multi-catch.

There is no need to list both `throws IOException` and `throws FileNotFoundException` to allow the subclass; the supertype already covers it. Adding subclass names sometimes serves documentation purposes, but is usually redundant in the signature; Javadoc's `@throws` can describe more precisely the conditions under which a subclass exception is raised.

## 12. `throws`, Polymorphism, and Implementation Substitutability

If a library exposes:

```java
interface Storage {
    byte[] read(String key) throws java.io.IOException;
}
```

multiple implementations can throw different specific `IOException`s on failure. A caller using the `Storage` type can still catch an `IOException` and work with new implementations without being forced to recompile subclass-specific handling logic. This is the benefit of an **exception contract at a stable abstraction level**.

However, choosing an overly broad supertype like `throws Exception` just for "flexibility" can push too much responsibility onto the caller and obscure recovery paths. Design APIs around **error categories that callers can reasonably handle**, rather than exposing all implementation details.

Nor should you assume that "declaring the supertype in `throws`" means "the caller never needs to know the subtype." The caller can still inspect the runtime type or catch a subclass when it has a specific recovery strategy for that case.

### `throws` Does Not Create a New Overload

Java does not allow two methods to differ only by their `throws` clause:

```java
// Intentionally invalid if both are placed in the same class:
void load() throws java.io.IOException {}
void load() throws java.io.FileNotFoundException {}
```

Both declarations have the same name and the same parameter list, so they are not valid overloads. Checked exceptions in `throws` affect contract checking and overriding, not method resolution for overloading.

## 13. Common Misconceptions and Programming Mistakes

| Misconception | What is actually true |
| --- | --- |
| `throws IOException` always produces an `IOException` | `throws` only declares a possibility; the method may succeed or throw a subclass |
| If the caller catches `IOException`, a `FileNotFoundException` object becomes an `IOException` | The runtime type does not change; `getClass()` is still `FileNotFoundException` |
| `throws FileNotFoundException` allows throwing any `IOException` | No; declaring a subtype does not cover its supertype |
| With `throws IOException`, you cannot throw `IllegalStateException` | You can, because `IllegalStateException` is unchecked |
| Catching `FileNotFoundException` is enough for any `throws IOException` method | Not if other `IOException`s remain possible; the caller must handle or declare the rest of the checked contract |
| An override can widen `throws IOException` to `throws Exception` | No, because that widens the checked exception contract |
| `catch` matches by `getCause()` | No; only the type of the object being thrown is used to select the handler |
| `throws Exception` is the best way to avoid worrying about error types | Being too broad makes the API harder to understand and forces callers to handle too many cases |
| To raise `NumberFormatException`, you must declare `throws NumberFormatException` | Not required; it is an unchecked exception |
| `throws` only exists in the implementing class and does not affect callers through an interface | The caller is checked against the signature on the **static type** it calls through |

### Wrong `catch` Order

Given:

```java
try {
    load();
} catch (java.io.IOException ex) {
    // ...
} catch (java.io.FileNotFoundException ex) {
    // ...
}
```

This is an **intentionally invalid example** if both branches are on the same `try`: the `IOException` handler already catches `FileNotFoundException`, so the subclass handler is shadowed and the code does not compile. Reverse the order to check the subclass first.

### Confusing the Declared Type with Reliable Runtime Diagnostics

Having `throws IOException` does not by itself tell you whether the actual failure came from a missing file, permissions, a connection, or a read error. Do not infer a single technical root cause from the supertype. Use the actual subtype, message, cause, stack trace, and operation context to diagnose, and report only what has been verified.

## 14. Self-Check Exercises

**Exercise A.** Is `static void f() throws IOException { throw new FileNotFoundException(); }` valid?

**Yes.** `FileNotFoundException` extends `IOException`; the actual checked type is covered by the declared supertype.

**Exercise B.** Is `static void f() throws FileNotFoundException { throw new IOException(); }` valid?

**No.** `IOException` is broader than `FileNotFoundException`; to let it propagate out, you must declare `throws IOException` or an appropriate supertype, or catch and handle it internally.

**Exercise C.** A method declares `throws IOException` but throws `EOFException`. Can `catch (IOException)` handle it?

**Yes.** The runtime type is `EOFException`, a subclass of `IOException`. The supertype handler matches.

**Exercise D.** An interface declares `throws IOException`; an implementing class overrides it and declares `throws FileNotFoundException`. Is this valid?

**Yes.** The override narrows the checked exception type. Callers through the interface variable are still checked against the interface's `throws IOException`; callers through the concrete class see the narrower declaration.

**Exercise E.** A method declares `throws IOException` and contains `throw new IllegalArgumentException("bad input")`. Does it need to add `throws IllegalArgumentException`?

**No.** `IllegalArgumentException` is an unchecked exception. It can still be caught at runtime by an appropriate handler.

**Exercise F.** A caller catches `IOException` and receives a `FileNotFoundException`. What does `ex.getClass().getSimpleName()` return?

**`FileNotFoundException`.** Catching through a supertype does not change the dynamic type.

**Exercise G.** A middle layer catches `FileNotFoundException` and then executes `throw new IllegalStateException("cannot start", ex)`. Can an outer layer with only `catch (IOException)` catch the wrapper?

**No.** The exception being thrown out is `IllegalStateException`; `FileNotFoundException` is inside `cause`. You need a handler compatible with the wrapper type or a change in the contract design.

## 15. Checklist When Reading a Call with `throws`

1. **Read the signature:** which checked exceptions are declared? Are they supertypes or specific types?
2. **Trace execution paths:** which `throw` statements or APIs can throw subtypes of the declared type?
3. **Check the caller:** has it caught or declared all checked exceptions according to the static type of the call?
4. **Read the handlers:** are subclass `catch` branches placed before superclass ones? Are the handlers addressing the right error types and policies?
5. **Check overriding:** does the implementing class narrow or preserve the checked exception contract of the parent class/interface?
6. **Consider runtime:** is the actual exception the expected subtype? Are there unchecked exceptions or wrappers changing the type at outer layers?
7. **Preserve diagnostic information:** if you must wrap, pass `cause`; if there is no reason to change the contract, consider letting the original exception propagate.

**Remember:** `throws` tells the compiler and callers **the category of checked exceptions a method may let escape**; `throw`/APIs at runtime determine **the concrete exception object**. A supertype declaration covers checked subclasses, while `catch` is selected by the actual type of the object and the inheritance hierarchy. In an overriding method, the checked exception contract may only stay equivalent or be narrowed, never widened in a way that breaks caller expectations.
