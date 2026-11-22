# `finally` and Introduction to `try-with-resources` in Java

## 1. Why Is Cleanup Needed When Operations Can Fail?

A Java program can open files, network connections, streams, or other resources. Those operations may complete normally, throw an exception, or exit early via `return`. If cleanup is only placed at the end of the success path, a failure path can skip it.

Java provides two related mechanisms:

- **`finally`**: a code block that can be used to perform work when exiting a `try`/`catch` construct, even if `try` encounters an exception or `return`.
- **`try-with-resources`**: a specialized form of `try` for managing resources that implement `AutoCloseable`; Java automatically calls `close()` upon exiting the block, handling exception cases as well.

Do not equate the two: `finally` is a general-purpose mechanism; `try-with-resources` is the preferred choice for **closing resources** that expose a `close()` API.

## 2. Structure and Control Flow of `finally`

Syntax:

```java
try {
    // Operations that may fail
} catch (SomeException ex) {
    // Handle matching exception
} finally {
    // Work performed when exiting try/catch
}
```

You can write `try-finally` without `catch`:

```java
try {
    doWork();
} finally {
    cleanUp();
}
```

The names `doWork()` and `cleanUp()` above are **illustrative methods**, not a standalone program. For a standard `try` (without a resource declaration), Java requires at least one `catch` or `finally`.

### Common Execution Paths

| What Happens in `try` | `catch` | `finally` |
| --- | --- | --- |
| Completes normally | `catch` is skipped | Runs before continuing |
| Throws an exception handled by a matching `catch` | That `catch` block runs | Runs after `catch` |
| Throws an exception not caught here | No matching block | Normally still runs before the exception propagates out |
| `return`, `break`, or `continue` exits the construct | Depends on context | Normally runs before completing the exit |

Example with `return`:

```java
static int calculate() {
    try {
        System.out.println("Trong try");
        return 7;
    } finally {
        System.out.println("Trong finally");
    }
}
```

When `calculate()` is called, the program prints `Trong try`, then `Trong finally`, and only then returns `7` to the caller. Inside `finally`, variables still in scope can be accessed; however, **you should not alter control flow with `return` inside `finally`**.

### `finally` Is Not an Absolute Guarantee

Under normal Java execution conditions, `finally` runs when exiting `try` or `catch`. However, it cannot be guaranteed to run in **every** case: for example, if the process/JVM is terminated abruptly, `System.exit(...)` terminates the VM, or a thread never exits the running code block.

Therefore, do not rely on `finally` to guarantee data durability when a process might lose power or be killed. Depending on the problem, design dedicated persistence, transactions, and recovery mechanisms.

## 3. `finally` Can Mask Root Causes If Written Improperly

Here is a notable pitfall:

```java
static int misleading() {
    try {
        return 10;
    } finally {
        return 99; // AVOID: masks the previous return value
    }
}
```

Even though `try` has `return 10`, calling `misleading()` returns `99`. If `try` throws an exception and `finally` executes `return`, the original exception can also be lost. Similarly, if `finally` throws a new exception, that exception can replace the one propagating out of `try`.

When closing a resource where both the main operation and `close()` can fail, calling `close()` manually inside `finally` makes it harder to preserve the **original exception**. This is an important reason to use `try-with-resources`.

## 4. What Is `try-with-resources`?

Since Java 7, resources can be declared in parentheses after `try`:

```java
try (Resource resource = acquireResource()) {
    use(resource);
}
```

The names `Resource`, `acquireResource()`, and `use(...)` here represent a **syntax pattern**, not built-in APIs. In real runnable code, the resource type must implement `java.lang.AutoCloseable` (or a suitable subinterface such as `java.io.Closeable`).

When exiting the block, Java calls `close()` on each resource that was successfully initialized and is non-`null`, even when:

- The `try` block completes normally.
- The `try` block throws an exception.
- Control flow uses `return` or exits the block via normal language rules.

Example with standard APIs:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

class FirstLineReader {
    static String readFirstLine(Path path) throws IOException {
        try (BufferedReader reader = Files.newBufferedReader(path)) {
            return reader.readLine();
        }
    }
}
```

This is an **illustrative class** without `main`. `BufferedReader` implements `Closeable`, so it is automatically closed after reading, even if `readLine()` throws `IOException` or hits `return`. The method still declares `throws IOException`: automatic resource closing **does not mean I/O errors are automatically handled and vanish**.

Do not confuse this closing mechanism with the Garbage Collector. GC manages collectible Java objects, but is generally not a solution for closing files, sockets, or connections in a timely manner.

## 5. Multiple Resources: Closed in Reverse Order

Multiple resources can be declared, separated by semicolons:

```java
try (First first = new First();
     Second second = new Second()) {
    // Use both resources
}
```

Classes `First` and `Second` above are undefined; this is a syntax illustration. If both resources are created successfully, they are **closed in reverse order of initialization**: `second.close()` first, then `first.close()`. If creating the second resource fails, previously created resources are still closed according to try-with-resources rules.

This order works like cleaning up a resource stack. It is useful when a later-created resource depends on an earlier-created one.

Since **Java 9**, an existing resource variable can be placed in the parentheses if it is `final` or *effectively final*:

```java
BufferedReader reader = Files.newBufferedReader(path);
try (reader) {
    System.out.println(reader.readLine());
}
```

This is an illustrative snippet inside a method that handles/declares `IOException` and has the corresponding imports. `reader` is not reassigned after initialization in this case. Passing the variable into `try (reader)` does not duplicate the resource or create a new reader object: it manages that same object for closing when exiting the block.

## 6. Exceptions Thrown During Closing and `getSuppressed()`

`AutoCloseable.close()` **can throw exceptions**. Two scenarios must be distinguished.

### Only Closing Fails

If the `try` body completes normally but `close()` throws an exception, the close exception propagates out or is caught by a matching `catch`.

### Both the `try` Body and Closing Fail

Java prioritizes keeping the **primary exception from the `try` body** as the thrown exception. The exception from automatically closing the resource is attached to the primary exception as a **suppressed exception**, which can be read via:

```java
Throwable[] otherFailures = ex.getSuppressed();
```

This prevents a failure during `close()` from accidentally erasing the original cause. With multiple resources, there can be multiple suppressed exceptions; the count and order depend on which resources actually threw during closing.

Note: `getSuppressed()` returns an array that may be **empty**; do not access `getSuppressed()[0]` without checking the length. The program in the next section uses a fixed scenario to guarantee there is one secondary exception.

## 7. Standalone Java 17+ Example: `finally`, Close Order, and Suppressed Exceptions

Create a file named **`FinallyResourcesDemo.java`**:

```java
public class FinallyResourcesDemo {
    static class Tracked implements AutoCloseable {
        private final String name;
        private final boolean failOnClose;

        Tracked(String name, boolean failOnClose) {
            this.name = name;
            this.failOnClose = failOnClose;
            System.out.println("open " + name);
        }

        void work() {
            System.out.println("work " + name);
        }

        @Override
        public void close() throws Exception {
            System.out.println("close " + name);
            if (failOnClose) {
                throw new Exception("close failed " + name);
            }
        }
    }

    static int returnWithFinally() {
        try {
            System.out.println("try return");
            return 7;
        } finally {
            System.out.println("finally return");
        }
    }

    static void reverseCloseOrder() throws Exception {
        try (Tracked a = new Tracked("A", false);
             Tracked b = new Tracked("B", false)) {
            System.out.println("work pair");
        }
    }

    static void demonstrateSuppressed() {
        try (Tracked c = new Tracked("C", true)) {
            c.work();
            throw new IllegalStateException("body failed");
        } catch (Exception ex) {
            System.out.println("caught: " + ex.getMessage());
            System.out.println("suppressed: " + ex.getSuppressed().length);
            if (ex.getSuppressed().length > 0) {
                System.out.println("detail: "
                        + ex.getSuppressed()[0].getMessage());
            }
        }
    }

    public static void main(String[] args) throws Exception {
        try {
            System.out.println("try normal");
        } finally {
            System.out.println("finally normal");
        }

        System.out.println("result: " + returnWithFinally());
        reverseCloseOrder();
        demonstrateSuppressed();

        try (Tracked d = new Tracked("D", true)) {
            d.work();
        } catch (Exception ex) {
            System.out.println("caught close: " + ex.getMessage());
        }

        System.out.println("done");
    }
}
```

Open a terminal in the directory containing the file, using **JDK 17 or later**. Run on PowerShell/CMD (Windows) or bash/zsh (Linux/macOS):

```bash
javac -encoding UTF-8 FinallyResourcesDemo.java
java FinallyResourcesDemo
```

**Exact stdout** (successful `javac` compilation prints no message):

```text
try normal
finally normal
try return
finally return
result: 7
open A
open B
work pair
close B
close A
open C
work C
close C
caught: body failed
suppressed: 1
detail: close failed C
open D
work D
close D
caught close: close failed D
done
```

**Step-by-step explanation:**

1. `try normal` finishes normally, so `finally normal` runs next.
2. `returnWithFinally()` has `return 7` inside `try`; `finally` prints its message before `result: 7` appears at the caller.
3. Two resources `A` and `B` are opened in order `A`, `B`, and closed in reverse order: `B`, `A`.
4. Resource `C` throws inside `close()`, while the `try` body throws `IllegalStateException("body failed")`. The primary exception is caught with message `body failed`; `close failed C` is stored as a suppressed exception.
5. For resource `D`, the `try` body succeeds normally; **only `close()` fails**, so `catch` directly receives `close failed D`.
6. The program still prints `done` because both failure cases have `catch` handling; there is no empty `catch` or silent ignoring of errors.

For `Tracked`, the signature `close() throws Exception` is valid because `AutoCloseable.close()` permits declaring `Exception`. Thus `reverseCloseOrder()` declares `throws Exception`, and `main` also declares `throws Exception` to propagate any unhandled failure on that path. In this example, `A` and `B` do not throw, so the stdout shown above is deterministic.

## 8. `try-with-resources` Can Combine with `catch` and `finally`

Valid syntax:

```java
try (Resource resource = open()) {
    use(resource);
} catch (SomeException ex) {
    report(ex);
} finally {
    finish();
}
```

This is an illustrative diagram with placeholder names `Resource`, `open`, `use`, `report`, and `finish`, not a standalone program.

The effective execution order is:

1. Initialize resources from left to right.
2. Execute the `try` body.
3. Automatically close initialized resources in reverse order.
4. If an exception needs handling, execute the matching `catch` attached to that construct.
5. Execute `finally` if present, per language rules.

Thus, **resources are already closed before code in `catch` and `finally` attached to the `try-with-resources` executes**. If you want to use a resource to write more data inside `catch`, you must redesign its scope/lifecycle; you cannot assume the `try (...)` resource is still open.

A `try-with-resources` block can stand alone without `catch` or `finally`. In contrast, a regular `try` (with no resource specification) must have at least `catch` or `finally`.

## 9. When Should Each Mechanism Be Used?

| Need | Preferred Approach |
| --- | --- |
| Reading/writing files via `BufferedReader`, `InputStream`, `Writer` | `try-with-resources` because these resources support closing |
| Managing `java.sql.Connection`, `Statement`, `ResultSet` | `try-with-resources` when scoped closing is needed |
| Releasing a custom resource with `close()` | Implement `AutoCloseable` carefully, then use `try-with-resources` |
| Logging/recording metrics after a `try`/`catch` branch | Consider `finally` or an equivalently clear structure |
| Checking and handling input errors | `catch` the right exception type; `finally` does not replace `catch` |
| Returning a value from a method | Use `return` in the right place; do not place `return` in `finally` to override other paths |

`AutoCloseable` only provides the contract for a `close()` method; it **does not inherently guarantee** that a resource is thread-safe across threads or reusable after closing. Those properties depend on the actual API.

## 10. Common Mistakes and Self-Check

1. **Assuming `finally` catches exceptions.** `finally` only runs cleanup when exiting the construct; to handle exceptions, use a matching `catch` or let them propagate to another layer.
2. **Putting `return` in `finally`.** It can overwrite the return value or mask an exception; avoid this pattern.
3. **Closing resources manually in `finally` while ignoring `close()` exceptions.** This can lose original error details; use `try-with-resources` when supported.
4. **Assuming `try-with-resources` swallows `IOException`.** Checked exceptions must still be caught or declared with `throws`.
5. **Using an object that does not implement `AutoCloseable` in `try (...)`.** That is a compile-time error; a valid resource type is required.
6. **Reading `getSuppressed()[0]` without checking length.** Can throw `ArrayIndexOutOfBoundsException` if there are no suppressed exceptions.
7. **Assuming resources close in declaration order.** With multiple resources, closing happens in **reverse** order.
8. **Using a closed resource after leaving `try-with-resources`.** Many APIs will throw an exception or disallow operations; avoid relying on closed state.
9. **Relying on `finally` when the VM is killed or the machine shuts down.** There is no cleanup guarantee when Java execution stops abruptly.
10. **Confusing OS resources with Java memory.** The Garbage Collector is not a mechanism for timely closing of files or sockets.

**Remember:** `finally` is for steps that must run when leaving normal `try`/`catch` execution paths; `try-with-resources` is the specialized tool for closing `AutoCloseable` resources more safely, even when `try` throws. When both the main operation and `close()` fail, inspect `getSuppressed()` so secondary failures are not missed.