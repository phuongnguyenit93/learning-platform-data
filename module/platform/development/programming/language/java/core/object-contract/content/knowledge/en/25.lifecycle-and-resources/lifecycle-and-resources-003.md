# Distinguishing `final`, `finally`, and `finalize()` in Java

These three names look similar, yet belong to **three completely different mechanisms**: `final` constrains assignment/overriding/inheritance at the language level; `finally` is an execution block when leaving a `try` construct; and `finalize()` is a legacy object cleanup mechanism, now **deprecated for removal**. They cannot be used interchangeably.

| Aspect | `final` | `finally` | `finalize()` |
| --- | --- | --- | --- |
| Nature | Keyword (modifier) | Keyword marking a block of `try` | Method inherited from `java.lang.Object` |
| Where is it placed? | Variables, parameters, fields, methods, classes | After `try`/`catch`; can also follow `try-with-resources` | Overridden definition in legacy classes |
| Purpose | Restricts reassignment, overriding, or inheritance | Performs final actions when leaving `try`, even on `return`/`throw` | Formerly used as a hook before GC reclaims an object |
| Timing | Rules checked at compile time (for variables, methods, classes) | In control flow when `try` finishes | If the JVM runs it at all, timing is nondeterministic via the finalization machinery |
| Guarantees resource cleanup? | No | Useful in normal exit flow, though not for every way the JVM stops | **No**; no guarantee it will be called |
| Modern Java practice | Use when explicit constraints are needed | Use to restore state, while preferring `try-with-resources` to close resources | Avoid using; prefer `AutoCloseable` and `try-with-resources` |

## 1. `final` — Compile-Time Declaration Constraints

### 1.1. `final` with Variables, Parameters, and Fields

A `final` variable **can only be assigned once** once its value is determined. That restriction applies to the **variable/reference**, and does not mean the entire object the variable points to is immutable.

```java
final int maxRetries = 3;
// maxRetries = 4; // Compile error: cannot reassign.

final StringBuilder message = new StringBuilder("Hello");
message.append(" Java"); // Valid: mutating object state.
// message = new StringBuilder("Other"); // Error: reassigning reference.

final int[] numbers = {1, 2};
numbers[0] = 99; // Valid: array elements can be modified.
// numbers = new int[] {3, 4}; // Error: reassigning array variable.
```

Common cases:

- **`final` local variable**: must be assigned before being read and cannot be reassigned. `final int value; value = 10;` is valid if every path using the variable initializes it and never assigns it a second time.
- **`final` parameter**: the parameter name cannot be reassigned inside the method body; the state of the passed object can still be mutated if its API allows it.
- **`final` instance field**: must be assigned at declaration, in an initializer, or along every normally completing path of the appropriate constructor. After the object finishes construction, the field cannot be reassigned via normal Java code.
- **`static final` field**: initialized only once for the class, commonly used for constants. Not every `static final` is a compile-time constant: `static final int LIMIT = 10` is a constant expression, whereas `static final List<String> ITEMS = new ArrayList<>()` holds a single reference to a list that can still be mutated.
- **Variables captured by lambdas/local classes**: must be `final` or *effectively final* (not reassigned after initialization). Writing the keyword is optional if the variable never changes anyway.

```java
static final int DEFAULT_PORT = 8080; // Constant value of a primitive type.

private final String id;

public Example(String id) {
    this.id = id; // Assign the object's final field.
}
```

The snippet above only illustrates declarations inside a class named `Example`; it is not a standalone runnable file.

**`final` does not by itself make an object immutable.** For example, `final List<String> list = new ArrayList<>();` still allows `list.add(...)`. To design an immutable object, combine state encapsulation, avoiding setters, copying mutable data appropriately, and not exposing mutable references. `List.copyOf(...)` creates a list that prohibits modification through the list API, but if the elements inside are mutable, that is still only *shallow* immutability.

`final` fields also carry special visibility rules for state after initialization in the Java Memory Model when the object is properly constructed (without letting `this` escape during the constructor). However, `final` alone **does not** make a mutable object safe for concurrent modification by multiple threads.

### 1.2. `final` with Methods and Classes

- **A `final` method** cannot be *overridden* by subclasses. Subclasses can still call the inherited method (if visible), and methods with the same name but different parameters can still be *overloaded*.
- **A `final` class** cannot be extended (`extends`). This does not forbid creating instances or having the class implement interfaces.
- `final` and `abstract` cannot both be placed on the same class or on the same method: one locks extension, while the other requires implementation in a subclass.
- For a class marked `final`, instance methods eligible for overriding already cannot be overridden by subclasses, because no subclass can exist.

```java
class Parent {
    final void identity() {
        System.out.println("Parent");
    }
}

class Child extends Parent {
    // void identity() {} // Compile error: cannot override final method.

    void identity(String label) { // Valid: overload with different parameter.
        System.out.println(label);
    }
}

final class Token {
}

// class SpecialToken extends Token {} // Error: cannot extend final class.
```

**Correct understanding:** `final` locks a specific capability to change; it does not replace validation, access control, immutable design, or synchronization.

## 2. `finally` — Block Executed When Leaving `try`

A common structure:

```java
try {
    // Operation that may succeed or throw an exception.
} catch (RuntimeException e) {
    // Handle the exception if appropriate.
} finally {
    // Execute when exiting the try/catch construct.
}
```

In normal JVM operation, `finally` executes after the `try` or `catch` branch finishes, whether it ends by reaching the end of the block, `return`, `break`, `continue`, or an exception. If an exception is uncaught, `finally` still runs **before** the exception continues propagating to the caller. With `return`, the return expression is evaluated before the `finally` block runs; the method only actually returns control to the caller afterward.

**Do not treat this as absolute in all situations:** if the process is abruptly terminated, the JVM halts/crashes, or execution cannot continue, `finally` may not run. For instance, `System.exit(...)` terminates the JVM without guaranteeing execution of pending `finally` blocks.

### 2.1. Runnable Java 17 Example: `final` and `finally`

Create the file **`FinalFinallyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class FinalFinallyDemo {
    private static final class Session {
        private final List<String> events = new ArrayList<>();

        void add(String value) {
            events.add(value);
        }

        int count() {
            return events.size();
        }
    }

    private static int parsePort(String input) {
        try {
            System.out.println("try: " + input);
            return Integer.parseInt(input);
        } catch (NumberFormatException ex) {
            System.out.println("catch: invalid number");
            return -1;
        } finally {
            System.out.println("finally: input checked");
        }
    }

    public static void main(String[] args) {
        final Session session = new Session();
        session.add("started");
        System.out.println("event count=" + session.count());

        System.out.println("port=" + parsePort("8080"));
        System.out.println("port=" + parsePort("oops"));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac FinalFinallyDemo.java
java FinalFinallyDemo
```

Exact output:

```text
event count=1
try: 8080
finally: input checked
port=8080
try: oops
catch: invalid number
finally: input checked
port=-1
```

Explanation: `Session` is a `final` class, and the `events` field is a `final` reference, yet elements can still be added to the list. `parsePort` returns `8080` from `try` in the first case and `-1` from `catch` in the second; both print the `finally` line before the caller prints `port=...`.

### 2.2. Pitfall: `return`/`throw` Inside `finally` Masks Prior Results

```java
static int misleading() {
    try {
        return 1;
    } finally {
        return 2; // Overrides returning 1.
    }
}
```

`misleading()` returns `2`. Similarly, if `try` threw an exception and `finally` throws another exception, the later exception can replace the original one, making root-cause analysis difficult. Therefore **avoid unnecessary `return`, `break`, `continue`, or `throw` inside `finally`**. If cleanup must run and can throw errors, decide explicitly how to record/propagate errors so you do not accidentally mask the primary error.

`finally` is suited for actions that must run when leaving a block of logic, such as resetting a state flag to its previous value or properly releasing an acquired lock. Specifically for closing `InputStream`, `Connection`, files, sockets, and `AutoCloseable` resources, prefer **`try-with-resources`**.

## 3. `try-with-resources` and Its Relationship with `finally`

The `try (Resource r = ...) { ... }` construct automatically calls `close()` on resources when leaving the block. Resources must implement `AutoCloseable`; resource variables must be final or effectively final. When multiple resources are declared, Java closes them **in reverse order of opening**. With an accompanying `finally`, closing the resources declared in the `try` header occurs before that `finally` block.

Standalone runnable file **`ResourceDemo.java`** for Java 17:

```java
public class ResourceDemo {
    private static final class Probe implements AutoCloseable {
        private final String name;

        Probe(String name) {
            this.name = name;
            System.out.println("open " + name);
        }

        @Override
        public void close() {
            System.out.println("close " + name);
        }
    }

    public static void main(String[] args) {
        try (Probe first = new Probe("A");
             Probe second = new Probe("B")) {
            System.out.println("work");
        } finally {
            System.out.println("finally");
        }
    }
}
```

```bash
javac ResourceDemo.java
java ResourceDemo
```

```text
open A
open B
work
close B
close A
finally
```

**Why is this approach preferred?** Resource closing is tied to the `try` scope, even upon `return` or throwing an exception, and Java manages *suppressed exceptions*: if the `try` body throws a primary error and then `close()` also throws an error, the close error is attached via `Throwable.getSuppressed()` instead of masking the primary error by default. Secondary errors can be observed and logged during debugging.

Some practical notes:

1. The resource must truly be **owned** by the code being written and allowed to be closed; do not arbitrarily close an object managed by the caller.
2. Closing order is the reverse of opening order, so initialize dependent resources in a sensible order.
3. `try-with-resources` does not guarantee business operations succeed; `close()` can also throw exceptions.
4. `finally` still has its place for restoring state not modeled as a resource; do not use it merely to write a sequence of manual `close()` calls.

Classic stream example:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

class ReadFirstLine {
    static String read(Path path) throws IOException {
        try (BufferedReader reader = Files.newBufferedReader(path)) {
            return reader.readLine();
        }
    }
}
```

`ReadFirstLine` is an API-illustration class without a `main` method. `BufferedReader` is automatically closed when leaving scope, even if reading fails. The return value can still be `null` if the file is empty; `final` and `finally` are unrelated to this result.

## 4. `finalize()` — Historical Callback, Not `finally`

`Object.finalize()` is a legacy method considered for execution by the JVM when an object becomes eligible for finalization; both its timing and whether it runs before the application terminates are **not guaranteed**. The API was deprecated in Java 9 and deprecated for removal under JEP 421 (JDK 18). Do not write new finalizers to close files, sockets, or perform mandatory business work.

The easily confused distinction lies in the question **who decides the timing**: `finally` is tied to exiting `try`, whereas `finalize()` depends on the GC mechanism and may never run. `final` only constrains declarations and does not manage resource lifecycles. When cleanup is needed, the owner calls `close()` or uses `try-with-resources`; `Cleaner` (if needed for native handles) is only a fallback and also has no deadline. Preceding and following lessons cover finalization timing, migrating legacy code, and explicit closing APIs separately.

## 5. Choosing the Right Tool in Real Situations

| Situation | Right Choice | What Not to Infer |
| --- | --- | --- |
| Prevent a config variable from being reassigned after initialization | `final` | Does not guarantee the object in the field is immutable |
| Prevent subclasses from changing an important algorithm | `final` on the method; or `final` on the class to prevent inheritance | Does not prevent all ways of mutating data |
| Need to log/restore state when leaving `try` | `finally` | Must not use `return` here to alter the result |
| Need to close a file after reading | `try-with-resources` | Do not rely on GC or `finalize()` |
| Legacy code closing a socket via `finalize()` | Migrate to `AutoCloseable`/`close()` called by the owner | Do not treat finalization as a reliable cleanup mechanism |
| Lambda using a local variable declared outside the lambda | Variable must be `final` or effectively final | Not mandatory to add the `final` keyword if the variable is never reassigned |

## 6. Common Mistakes and How to Check

**Mistake 1 — Thinking `final` makes the whole object immutable.** Ask clearly whether you want to lock the **reference** or lock the **state**. To lock state, examine mutating APIs, collection aliases, and defensive copying.

**Mistake 2 — Thinking a `final method` cannot be called from subclasses.** Subclasses can inherit/call the method given appropriate visibility, but cannot override it. Overloading is a separate matter.

**Mistake 3 — Thinking `finally` only runs when an exception occurs.** It runs both on success and on early `return` during normal execution. Place logging in the `parsePort` example to observe the exact order.

**Mistake 4 — Writing `return` or throwing a new error inside `finally`.** This can discard the return value or mask the preceding exception. Keep cleanup concise and account for suppressed exceptions if multiple errors occur.

**Mistake 5 — Using `finalize()` to close files/database connections.** There is no deadline or invocation guarantee. Shift resource-closing ownership to `try-with-resources` or explicit `close()`.

**Mistake 6 — Calling `System.gc()` and waiting for `finalize()`.** `System.gc()` is only a suggestion and does not guarantee finalization occurs; it is neither a correctness strategy nor a reliable test.

**Self-check:** (1) Does `final List<String> names` allow `names.add("A")`? Yes, if the list supports modification. (2) Does `finally` run before the caller receives the `return` value? Yes, in normal completion flow. (3) Can you rely on `finalize()` to close a socket on time? No. (4) Which API should be used to close resources when exiting a block? `AutoCloseable` with `try-with-resources`.

**Key takeaway:** `final` is a declaration constraint; `finally` is a processing step when exiting `try`; `finalize()` is a legacy finalization mechanism unsuitable for modern Java resource management.
