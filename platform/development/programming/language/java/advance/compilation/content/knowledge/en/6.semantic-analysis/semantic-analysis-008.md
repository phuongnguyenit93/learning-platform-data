# Checked exception analysis and handling branches in Java compilation

A Java program can be syntactically valid and have all types and methods resolved, yet still fail to compile because a code branch might throw a **checked exception** that is neither handled nor declared. This is part of the **semantic analysis** performed by `javac`: the compiler analyzes expressions, calls, `throw` statements, `try/catch/finally` blocks, and paths through the program to decide whether an exception has been handled or can still escape the method.

The goal of this lesson is to understand **why the compiler accepts or rejects an exception-handling structure**, while distinguishing what the compiler can verify from declared types versus what actually happens at runtime.

## 1. What is a checked exception?

Every exception in Java relates to the `Throwable` hierarchy:

~~~text
java.lang.Throwable
├── java.lang.Error
│   └── ... (system errors, normally should not be caught for recovery)
└── java.lang.Exception
    ├── java.lang.RuntimeException
    │   ├── IllegalArgumentException
    │   └── NullPointerException
    ├── java.io.IOException
    │   └── java.io.FileNotFoundException
    └── java.sql.SQLException
~~~

Under the language's exception-checking rules:

- **Checked exceptions** are subclasses of `Throwable` that are **not** under `RuntimeException` or `Error` (including `Throwable` and `Exception` directly). Familiar examples: `IOException`, `SQLException`, `ClassNotFoundException`, and custom business exceptions extending `Exception`.
- **Unchecked exceptions** are `RuntimeException` and its subclasses, or `Error` and its subclasses. The compiler does not force every call capable of causing a `NullPointerException` to write `catch`/`throws`.
- Whether an exception is checked or unchecked is based on **type inheritance relationships**, not on the class name, error description, or whether the program can recover.

Example:

~~~java
import java.io.IOException;

class StorageException extends IOException {
    StorageException(String message) {
        super(message);
    }
}

class InputProblem extends RuntimeException {
    InputProblem(String message) {
        super(message);
    }
}
~~~

`StorageException` is checked because it extends `IOException`; `InputProblem` is unchecked because it extends `RuntimeException`. The snippet above is an **illustration of type declarations** without `main`; it does not need to be run as a standalone program.

**Two ways to satisfy the compiler's check:** handle the checked exception with an appropriate `catch` branch (which may convert it into a result or throw another exception type), or declare that the exception can escape using a `throws` clause on the appropriate method/constructor. In certain contexts such as lambdas, the rules also depend on the target functional type.

## 2. Distinguishing throw, throws, try, and catch

| Construct | Meaning | What does the compiler check? |
| --- | --- | --- |
| `throw new IOException("x");` | **Throws** an exception object at the execution point | Is the checked exception handled or allowed to escape? Is the expression a subtype of `Throwable`? |
| `void read() throws IOException` | **Declares** the possibility that the method completes abruptly due to an exception | Every checked exception that can escape is compatible with the types in `throws` |
| `try { ... } catch (IOException e) { ... }` | Handles matching exceptions originating from the `try` region | Can the catch catch an allowed exception type? Does catch ordering create an unreachable branch? |
| `finally { ... }` | Performs the final action of `try` according to normal/abrupt completion rules | How can the final branches finish, and does any new checked exception escape? |
| `try (Resource r = ...) { ... }` | Automatically closes resources via `AutoCloseable` | Which checked exceptions can arise across creating, using, and closing the resource? |

A `throws` clause **does not catch** the exception on its own and does not guarantee the exception will actually occur. It establishes a static contract for callers: if a method's type declares `throws IOException`, callers must handle or declare `IOException`, even if a specific implementation rarely throws it.

Additionally, `throws` is allowed to list checked exceptions that the method does not actually throw in practice (subject to special constraints such as overriding). This is a contract permitting the exception to escape, not a log of every runtime scenario.

## 3. Java 17+ example: success and failure handling branches

Complete **`ExceptionBranchesDemo.java` file**:

~~~java
import java.io.IOException;

public final class ExceptionBranchesDemo {
    static String read(boolean shouldFail) throws IOException {
        if (shouldFail) {
            throw new IOException("read failed");
        }
        return "content";
    }

    static String execute(boolean shouldFail) {
        try {
            return read(shouldFail);
        } catch (IOException ex) {
            return "fallback:" + ex.getMessage();
        } finally {
            System.out.println("cleanup");
        }
    }

    public static void main(String[] args) {
        System.out.println(execute(false));
        System.out.println(execute(true));
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac -encoding UTF-8 ExceptionBranchesDemo.java
java ExceptionBranchesDemo
~~~

**Exact stdout:**

~~~text
cleanup
content
cleanup
fallback:read failed
~~~

**Why does it compile?**

1. `read` has an `if` branch throwing `IOException`; the method declares `throws IOException`, so that checked exception type is allowed to escape.
2. `execute` calls `read` inside `try`, and `catch (IOException ex)` can handle the exact declared exception type. Therefore `execute` does not need `throws IOException` if no other checked exception escape path exists.
3. When `shouldFail=false`, `read` returns `content`. Before `execute` completes `return`, `finally` prints `cleanup`. Then `main` prints `content`.
4. When `shouldFail=true`, `throw` transfers control to `catch` to build the string `fallback:read failed`; `finally` still executes before the return value reaches `main`.
5. The compiler checks both control possibilities based on the code and declared types; it does not need to run the program or know the passed values in advance.

**There is no requirement to catch every unchecked exception** such as `NullPointerException` that could arise from accessing a null object. Successful compilation does not prove all runtime paths will avoid errors.

## 4. Cases rejected by the compiler for missing handling

The following snippet is **intentionally invalid, not a runnable program**:

~~~java
import java.io.IOException;

class MissingHandling {
    static void read() throws IOException {
        throw new IOException("disk");
    }

    static void run() {
        read(); // Error: checked IOException has not been handled/declared.
    }
}
~~~

`run()` has neither `throws IOException` nor `try/catch`. `javac` may report something like:

~~~text
error: unreported exception IOException; must be caught or declared to be thrown
~~~

The reported location/line varies by filename, JDK, and coding style. There are three language-valid ways to resolve it, with different design meanings.

**Approach A – Handle right at the call site:**

~~~java
static void run() {
    try {
        read();
    } catch (IOException ex) {
        System.err.println("Read failed: " + ex.getMessage());
    }
}
~~~

**Approach B – Pass responsibility to the next caller:**

~~~java
static void run() throws IOException {
    read();
}
~~~

**Approach C – Convert into an unchecked exception preserving the cause:**

~~~java
static void run() {
    try {
        read();
    } catch (IOException ex) {
        throw new IllegalStateException("Cannot read", ex);
    }
}
~~~

These three snippets are **replacements for the body of method `run`** in `MissingHandling`, not three standalone programs. Approach C preserves the original exception in `cause` to aid diagnosis; it should be used only when the API genuinely intends to translate the error type. In real applications, logging and swallowing an exception may not suffice; handling must match business behavior, retry mechanisms, or the current layer's error policy.

## 5. Analyzing if, switch, and call branches

The compiler analyzes the possibility of exceptions arising from expressions and statements across branches. A method does **not** escape checked exception rules merely because an error branch “rarely happens”.

**Intentionally invalid** snippet:

~~~java
import java.io.IOException;

class BranchCheck {
    static String load() throws IOException {
        return "ok";
    }

    static String select(boolean fromDisk) {
        if (fromDisk) {
            return load(); // IOException not yet caught/declared.
        }
        return "memory";
    }
}
~~~

Even if runtime calls usually pass `false`, the parameter `fromDisk` can be `true`; `select` needs `throws IOException` or handling within the relevant branch. A fix keeping `select`'s contract without `throws`:

~~~java
static String select(boolean fromDisk) {
    if (!fromDisk) {
        return "memory";
    }
    try {
        return load();
    } catch (IOException ex) {
        return "fallback";
    }
}
~~~

**The fix is only a replacement method body inside class `BranchCheck`.** These snippets themselves do not yet include a `main` method.

Similar cases:

- `if/else`: checked exceptions that can escape from **any** involved branch must be handled or declared.
- `switch` and `switch expression`: cases may call methods declaring different exceptions. Both value-yielding cases and `throw` cases are subject to exception checking rules.
- Loops: the compiler still checks exceptions from the loop body and related expressions; do not treat `break`/`continue` as a way to exempt checked exception handling.
- Method parameters: a method's `throws` signature is evaluated at the call site, independent of assumptions that input data is always “good”.
- Early `return` branches: exceptions thrown **before** `return` still must be resolved; `finally` may run on that completion path.

Semantic analysis is not equivalent to a static analyzer proving every runtime condition. Do not rely on the compiler optimizing away conditions when designing exception-handling rules.

## 6. Catching by type: subtypes and branch ordering

A `catch` handles exception objects compatible with the caught type. When multiple catch clauses exist, the JVM chooses **the first matching branch in order of appearance**.

Valid example:

~~~java
try {
    performIO();
} catch (java.io.FileNotFoundException ex) {
    System.out.println("File missing");
} catch (java.io.IOException ex) {
    System.out.println("Other IO failure");
}
~~~

`performIO()` here is an **illustrative** call assumed capable of throwing `FileNotFoundException` or another `IOException`. The subtype `FileNotFoundException` is placed **before** the supertype `IOException` so each branch has a chance to handle the right exception.

Reversing the order is **intentionally invalid**:

~~~java
try {
    performIO();
} catch (java.io.IOException ex) {
    System.out.println("IO failure");
} catch (java.io.FileNotFoundException ex) {
    System.out.println("Missing file"); // Unreachable catch.
}
~~~

`FileNotFoundException` is a subclass of `IOException` and is already covered by the first catch. The compiler reports that the later catch branch is unreachable (typically “exception ... has already been caught”). Ordering principle: **more specific types first, broader types later**.

### Catching a checked exception that try cannot throw

This snippet is **intentionally invalid**:

~~~java
try {
    int answer = 40 + 2;
    System.out.println(answer);
} catch (java.io.IOException ex) {
    System.out.println("Cannot happen here");
}
~~~

The statements inside `try` neither declare nor throw `IOException`, so `javac` typically reports `exception IOException is never thrown in body of corresponding try statement`.

However, distinguish the case of catching `Exception` or unchecked exceptions: Java has special rules for types that can include unchecked exceptions, so do **not** generalize the example above into “every catch without an explicit throw is invalid”. If `try` calls a method declaring `throws IOException`, that catch can be valid even if the method's runtime implementation does not throw an exception on the specific call being considered.

### Do not catch by “same name”

If two libraries declare two exception classes with the same simple name but in different packages, they are still two distinct types. The compiler resolves type names in `catch` via packages/imports just like other types. Use fully qualified names when disambiguation is needed.

## 7. Multi-catch for branches with identical handling

Since Java 7, `catch (IOException | SQLException ex)` catches both types in one block. This is a more concise syntax when **the recovery/error-logging approach is the same**.

**`MultiCatchDemo.java` file:**

~~~java
import java.io.IOException;
import java.sql.SQLException;

public final class MultiCatchDemo {
    static String query(int mode) throws IOException, SQLException {
        if (mode == 1) {
            throw new IOException("disk");
        }
        if (mode == 2) {
            throw new SQLException("database");
        }
        return "ok";
    }

    public static void main(String[] args) {
        for (int mode = 0; mode <= 2; mode++) {
            try {
                System.out.println(query(mode));
            } catch (IOException | SQLException ex) {
                System.out.println(
                        ex.getClass().getSimpleName() + ":" + ex.getMessage()
                );
            }
        }
    }
}
~~~

Compile/run on Java 17+:

~~~bash
javac -encoding UTF-8 MultiCatchDemo.java
java MultiCatchDemo
~~~

**Exact stdout:**

~~~text
ok
IOException:disk
SQLException:database
~~~

Analysis:

- `query` has two branches throwing two checked exception types, so both `IOException` and `SQLException` are listed in `throws`.
- The multi-catch in `main` handles both types, so `main` does not need corresponding `throws`.
- The multi-catch parameter `ex` is **implicitly final**: it cannot be reassigned.
- Alternatives in the same multi-catch must not have a subclass/superclass relationship with each other.

**Intentionally invalid** example:

~~~java
catch (java.io.FileNotFoundException | java.io.IOException ex) {
    // Invalid: FileNotFoundException is a subtype of IOException.
}
~~~

The compiler reports the alternatives are invalid due to the subtype relationship. Choose `catch (IOException ex)` or separate the catch clauses in a valid order.

An important question: multi-catch does not mean the compiler ignores analyzing exceptions that may arise from **the catch body**. If inside the catch block a method throwing another checked exception is called, that exception still must be handled/declared.

## 8. Checked exceptions arising inside catch and finally

Handling one exception can cause a new exception. The compiler analyzes **every code region**, including `catch` and `finally` bodies, rather than only analyzing the initial `try` block.

**Intentionally invalid illustrative** snippet:

~~~java
import java.io.IOException;
import java.sql.SQLException;

class HandlerCheck {
    static void risky() throws IOException {
        throw new IOException("read");
    }

    static void persist() throws SQLException {
        throw new SQLException("save");
    }

    static void handle() {
        try {
            risky();
        } catch (IOException ex) {
            persist(); // SQLException not yet handled or declared.
        }
    }
}
~~~

`catch` resolves `IOException` from `risky`, yet `persist` declares `SQLException`. Because `handle` neither catches nor declares `throws` for the new type, the compiler rejects it.

A valid fix is adding `throws SQLException` to `handle` or catching `SQLException` in another `try/catch` inside the catch body. One should not mechanically switch to `catch (Exception)` if a data-write failure requires separate handling.

With `finally`, for example:

~~~java
static void cleanup() throws IOException {
    throw new IOException("close");
}

static void work() {
    try {
        System.out.println("work");
    } finally {
        cleanup(); // Intentionally invalid: IOException from finally is not handled.
    }
}
~~~

The methods in the second snippet are just **illustrative code inside a class**. Even though the `try` body throws no checked exception, `finally` can still throw `IOException`, so `work` must catch/declare it.

**Key takeaway:** `finally` normally still executes when the `try`/`catch` block prepares to `return` or `throw`; however, if the JVM terminates abnormally outside normal Java execution (for example, the process is terminated), cleanup actions are not guaranteed to run. If `finally` itself throws an exception or executes `return`, it can replace the result/exception being propagated outward. Avoid writing `return` or `throw` in `finally` to avoid accidentally masking the original error.

## 9. Try-with-resources and exceptions from close()

Use `try-with-resources` when an object implements `AutoCloseable`. This construct calls `close()` automatically when exiting the block, including upon `return` or an exception.

**`ResourceDemo.java` file:**

~~~java
import java.io.IOException;

public final class ResourceDemo {
    static final class TrackedResource implements AutoCloseable {
        String read(boolean fail) throws IOException {
            if (fail) {
                throw new IOException("read failed");
            }
            return "data";
        }

        @Override
        public void close() throws IOException {
            System.out.println("closed");
        }
    }

    static String execute(boolean fail) {
        try (TrackedResource resource = new TrackedResource()) {
            return resource.read(fail);
        } catch (IOException ex) {
            return "caught:" + ex.getMessage();
        }
    }

    public static void main(String[] args) {
        System.out.println(execute(false));
        System.out.println(execute(true));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 ResourceDemo.java
java ResourceDemo
~~~

**Exact stdout:**

~~~text
closed
data
closed
caught:read failed
~~~

In the example, both `read` **and** `close` declare `throws IOException`. The compiler must account for exceptions from both using the resource and closing the resource. `catch (IOException ex)` handles both potential sources, so `execute` does not need to declare a checked exception. The fact that `close` currently only prints to the console does not make the compiler automatically ignore the `throws IOException` signature.

If the resource has `close() throws Exception` (a broader type than `IOException`), a catch accepting only `IOException` may be insufficient; one must rely on the **declared type** of `close` to design the appropriate catch/throws.

### Suppressed exceptions: preserving the original error when close also fails

If the `try` body throws an exception and `close()` also throws, try-with-resources normally keeps the body's exception as the **primary exception** and attaches the exception from close to `getSuppressed()`.

**`SuppressedDemo.java` file:**

~~~java
import java.io.IOException;

public final class SuppressedDemo {
    static final class BrokenResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close");
        }
    }

    public static void main(String[] args) {
        try (BrokenResource resource = new BrokenResource()) {
            throw new IOException("body");
        } catch (IOException ex) {
            System.out.println(ex.getMessage());
            for (Throwable suppressed : ex.getSuppressed()) {
                System.out.println("suppressed:" + suppressed.getMessage());
            }
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 SuppressedDemo.java
java SuppressedDemo
~~~

**Exact stdout:**

~~~text
body
suppressed:close
~~~

This behavior differs from manually closing resources in `finally` and letting an exception from `close` accidentally mask an earlier error. When logging the primary exception, preserve suppressed information so secondary causes are not lost.

If multiple resources are declared in try-with-resources, they are closed in **reverse order of declaration**. Checked exceptions from initializing and closing those resources also participate in exception analysis.

## 10. Rethrow and more precise type analysis

Java has a **precise rethrow** mechanism: under certain conditions, the compiler infers that an exception variable caught with a broad type can actually hold only the specific checked exception types thrown from the `try` block.

**`RethrowDemo.java` file:**

~~~java
import java.io.IOException;

public final class RethrowDemo {
    static void action(boolean fail) throws IOException {
        try {
            if (fail) {
                throw new IOException("failed");
            }
        } catch (Exception ex) {
            throw ex;
        }
    }

    public static void main(String[] args) {
        try {
            action(true);
        } catch (IOException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 RethrowDemo.java
java RethrowDemo
~~~

Stdout:

~~~text
failed
~~~

Outwardly `ex` has type `Exception`, yet the compiler can infer that the checked exception thrown from `try` here is only `IOException`, so `action` declaring `throws IOException` suffices. This relies on the precise rethrow rule, not “every `catch (Exception)` is always equivalent to `catch (IOException)`”.

Precise rethrow has conditions, among which the `catch` parameter variable must not be reassigned (effectively final). If `ex` is reassigned before `throw ex`, exception type inference may differ and the `throws IOException` signature may be insufficient.

## 11. Checked exceptions in overriding and interface implementation

An overriding method **cannot arbitrarily widen the set of checked exceptions** compared to the overridden method. It can omit the `throws` clause, or declare narrower compatible checked exceptions per Java rules.

**`OverrideDemo.java` file:**

~~~java
import java.io.IOException;

interface TextReader {
    String read() throws IOException;
}

final class FixedReader implements TextReader {
    @Override
    public String read() {
        return "ready";
    }
}

public final class OverrideDemo {
    public static void main(String[] args) throws IOException {
        TextReader reader = new FixedReader();
        System.out.println(reader.read());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 OverrideDemo.java
java OverrideDemo
~~~

Stdout:

~~~text
ready
~~~

In the implementation `FixedReader.read`, `throws IOException` is not needed because no checked exception escapes. However, at the call `reader.read()`, the variable `reader` has **compile-time type `TextReader`**, and the interface signature declares `throws IOException`. Therefore `main` needs catch/throws `IOException` even though the runtime object is `FixedReader`.

**Intentionally invalid** snippet when replacing the implementation:

~~~java
final class InvalidReader implements TextReader {
    @Override
    public String read() throws Exception {
        return "ready";
    }
}
~~~

`Exception` is broader than `IOException`; the compiler rejects the override because the declared checked exception is broader than the interface contract. To declare a narrower checked exception type, an override can use `FileNotFoundException` (a subclass of `IOException`) if the method body matches.

Conversely, adding `throws IllegalArgumentException` (unchecked) is not restricted by this checked-exception narrowing rule, though the API should still have a clear contract.

For a method overriding multiple declarations from interfaces/superclasses, the valid set of checked exceptions must also be compatible with **every** contract the method implements.

## 12. Checked exceptions in lambdas and functional interfaces

A lambda is checked against its **target type** (a functional interface type) containing the abstract method signature. A lambda cannot add checked exceptions on its own if the target method does not allow them.

**Intentionally invalid** example:

~~~java
import java.io.IOException;

java.util.function.RunnableTask task = () -> {
    throw new IOException("disk");
};
~~~

The snippet above also uses an incorrect interface name: standard Java has `java.lang.Runnable`, not `java.util.function.RunnableTask`. Even after fixing to the right interface, there is **still** a checked exception error because `Runnable.run()` declares no checked exceptions:

~~~java
Runnable task = () -> {
    throw new java.io.IOException("disk"); // Intentionally invalid: Runnable.run does not declare throws IOException.
};
~~~

The right design if the task genuinely needs to throw a checked exception is choosing a functional interface with a matching signature or defining one yourself:

~~~java
@FunctionalInterface
interface IoAction {
    void run() throws java.io.IOException;
}

IoAction action = () -> {
    throw new java.io.IOException("disk");
};
~~~

The last two snippets only illustrate lambdas in **a context with variable declarations**, not a standalone `main` program. When calling `action.run()`, the caller in turn must catch or declare `IOException`.

Standard example: `java.util.concurrent.Callable<V>.call() throws Exception` allows a lambda body to declare/throw matching checked exceptions, whereas `Runnable.run()` does not. When using lambdas with `Stream.map` or `Function.apply`, read the functional interface signature instead of assuming arbitrary checked exceptions can be thrown.

## 13. Constructors, field initializers, and exceptions in other locations

Checked exceptions do not appear only in ordinary method calls. The compiler also checks other locations, for example:

- **Constructors**: if a constructor body or related initializer has a checked exception that can escape, the constructor contract must declare the corresponding exception; every caller invoking the constructor must handle/declare it.
- **Field initialization and instance initializers**: exception rules depend on the initializer and constructor context. A checked exception arising in instance initialization may require matching declarations on constructors; it cannot simply be “let escape” as in a method with `throws`.
- **Static initializers**: have no `throws` signature to propagate checked exceptions outward in the usual way. If a static initializer calls a method throwing a checked exception, it must be handled appropriately inside the block; runtime errors during class initialization are a separate issue.
- **Object creation expressions**: `new SomeType()` may need to handle checked exceptions declared by the constructor.
- **Method references**: are also checked for compatibility with the target functional interface, including escapable exception types.

**`ConstructorDemo.java` file:**

~~~java
import java.io.IOException;

final class ConnectionLike {
    ConnectionLike(boolean fail) throws IOException {
        if (fail) {
            throw new IOException("open failed");
        }
    }
}

public final class ConstructorDemo {
    public static void main(String[] args) {
        try {
            new ConnectionLike(true);
        } catch (IOException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 ConstructorDemo.java
java ConstructorDemo
~~~

Stdout:

~~~text
open failed
~~~

`new ConnectionLike(true)` is precisely an expression carrying a checked exception per the constructor declaration. `catch` in `main` handles that exception type; if the catch is removed without adding throws, the compiler will reject it.

## 14. Checked exceptions, compile-time checks, and runtime exceptions

Not every exception-related failure surfaces during compilation:

| Situation | Must the compiler detect it? | Example |
| --- | --- | --- |
| Calling a method with `throws IOException` without catch/throws | Yes | Checked exception error in source |
| `catch (FileNotFoundException)` after `catch (IOException)` | Yes | Specific catch branch already shadowed by parent catch |
| `catch (IOException)` when try cannot throw that checked type | Usually yes per catch reachability rules | Invalid catch error |
| `throw new RuntimeException()` without catch/throws | Catch/throws not required | Unchecked |
| Null receiver causing `NullPointerException` | Not always provable by the compiler | May throw at runtime |
| Resource close failure or unexpected I/O | Compiler checks declared types; runtime determines actual error | `IOException` while reading/closing |
| Runtime library version differs from compile version | Usually not detected at source compile time with older libraries | `NoSuchMethodError` / `NoClassDefFoundError` at runtime |

Just because a method declares `throws IOException` **does not mean** the runtime will always throw that exception. And a method **not declaring checked exceptions** can still throw unchecked exceptions. The compiler focuses on enforcing the source code's checked exception contract, not predicting every operational failure.

A caught exception handled improperly can also cause business bugs. Example:

~~~java
try {
    saveData();
} catch (Exception ignored) {
    // Swallowing all errors can hide unsaved data.
}
~~~

This is an illustrative snippet; `saveData` is assumed to be a call that can throw an exception. The syntax may be valid, which does not mean it is good handling. When catching to translate an error, preserve `cause` and log appropriate context.

## 15. Branch-checking rules: practical decision diagram

~~~text
Detect call/throw/resource creation that can throw E
                 |
                 v
        Is E a checked exception?
            /                 \
           No                 Yes
            |                  |
     Not required to     Can E escape
     catch/throws        the try block?
                             |
                            \/
                    Any compatible catch?
                        /           \
                      Yes            No
                       |              |
                Analyze catch     Does method/constructor
                & finally bodies  have throws covering E?
                       |              /      \
                       |            Yes       No
                       |             |         |
                 Can a new         Valid   Compile error
                 exception escape?   |
                       |        Next caller
                 Check next     is responsible
~~~

This is a **mental model**, not the exact internal algorithm of `javac`. The compiler analyzes syntax, types, and control flow together; a `catch` can be invalid due to ordering, type, or the possibility of the exception occurring. What matters is tracing a checked exception from **its origin** through **branches that can handle it** to **the method/constructor contract**.

A useful way to read errors:

1. **Identify the exact exception type** in the compiler message: `IOException`, `SQLException`, or another subtype?
2. **Find the origin**: `throw`, method/constructor `throws`, a call in catch/finally, or `close()` of a resource.
3. **Evaluate all possible paths**: does an `if` branch, `switch` case, loop body, cleanup, or nested catch block let the exception escape?
4. **Check catch order**: subtypes must come before supertypes, and the catch must make semantic sense for the exceptions the try region can throw.
5. **Inspect the current signature**: catch to recover here, or `throws` so the calling layer resolves it? If overriding, does the signature obey the parent/interface contract?
6. **Once compiled**, verify runtime handling logic: ensure errors are not swallowed, root causes are not masked, and resources are properly closed.

## 16. Self-check exercises with answers

### Exercise 1: undeclared throw branch

~~~java
static void run(boolean fail) {
    if (fail) {
        throw new java.io.IOException("disk");
    }
}
~~~

**Question:** Does the snippet above compile? **Answer:** No, because `IOException` is checked and can escape `run`. Fix with `throws IOException` (along with an import if you want the short name) or catch the appropriate exception type inside the method.

### Exercise 2: catch ordering

~~~java
try {
    readFile();
} catch (java.io.IOException ex) {
    recover();
} catch (java.io.FileNotFoundException ex) {
    reportMissing();
}
~~~

**Question:** Why is the second catch invalid? **Answer:** `FileNotFoundException` is a subtype of `IOException`; exceptions of this type are already caught by the first branch. Put the more specific catch first if the illustrative methods have matching signatures and handling.

### Exercise 3: overriding and calling through an interface

An interface declares `void load() throws IOException`; the implementation overrides `void load()` without throws. A variable of the **interface** type calls `load()`. Is catch/throws needed?

**Answer:** Yes, because the compiler examines the signature of the receiver's compile-time type. A concrete implementation without throws does not remove the interface's checked exception contract from that call.

### Exercise 4: close throwing IOException

A resource implements `AutoCloseable` with `close() throws IOException`, while the `try` body only prints to the console. Can catch/throws `IOException` be omitted?

**Answer:** No, if the checked exception from `close` can escape the try-with-resources construct. The compiler also inspects the `close()` signature, not just the `try` body.

### Exercise 5: multi-catch

Two exceptions `IOException` and `SQLException` have no parent-child relationship. Can `catch (IOException | SQLException ex)` be used? Yes, if they are exception types that can validly be caught from the `try` region; the variable `ex` cannot be reassigned.

### Exercise 6: finally overriding an exception

If the `try` body throws `IOException("read")`, yet `finally` throws `IllegalStateException("cleanup")`, which exception type escapes normally?

**Answer:** The exception from `finally` can replace/mask the exception propagating out from `try`. Avoid letting cleanup arbitrarily overwrite the primary cause; for resources, try-with-resources supports suppressed exceptions.

## Takeaways to apply

- Checked exceptions are a **compile-time type and control-flow rule**, not a runtime prediction.
- `throw` raises an exception; `throws` declares escape capability; `catch` handles compatible types; `finally` and `close()` can introduce additional exceptions into analysis.
- The compiler evaluates reachable branches in `if`, `switch`, loops, catch, and finally. An uncaught/undeclared checked-exception escape path is a compile error.
- Specific catch clauses precede broad catch clauses; multi-catch must not contain alternatives with a subtype relationship; catching checked exceptions must be valid for the `try` region.
- Try-with-resources checks exceptions from creating, using, and closing resources; suppressed exceptions help preserve errors from `close` when the `try` body already threw an exception.
- Overriding must not declare broader checked exceptions than the inherited contract; lambdas depend on the functional interface's exception signature.
- When encountering `unreported exception`, trace from the exception origin through all branches to the method signature, choosing catch to handle locally or `throws` to pass responsibility upward.