# Unreachable Catch Block Due to Being Covered by a Preceding Catch Block

## 1. Learning Objectives

In Java, the `catch` clauses of **the same `try` statement** are evaluated in top-to-bottom order when an exception occurs. If a preceding `catch` already catches **every object of the type that a subsequent `catch` intends to catch**, the subsequent `catch` has no chance of receiving the exception. Java detects this case at compile time and reports an error.

After this lesson, you will be able to:

- Explain why `catch` ordering is directly related to the inheritance relationship between exception classes.
- Recognize the error where a `catch` is unreachable because a preceding `catch` already covers its type.
- Order handlers from specific types to general types while preserving the intended handling semantics.
- Distinguish between **an ordering error due to coverage** and **an error caused by catching a checked exception that cannot be thrown from the `try` block**.
- Write `multi-catch` correctly and recognize cases where the alternatives in a multi-catch have a parent–child relationship.
- Understand the impact of `catch (Exception)`, `catch (Throwable)`, sibling branches, nested `try` blocks, and `finally`.
- Read `javac` errors, fix the right location, and verify again with a Java 17+ program.

## 2. Mechanism for Selecting a `catch` When an Exception Occurs

A `try` can have multiple consecutive `catch` clauses:

```java
try {
    riskyOperation();
} catch (SpecificException e) {
    handleSpecific(e);
} catch (GeneralException e) {
    handleGeneral(e);
}
```

This is an illustrative snippet; the corresponding exception types and methods need to be defined. In principle, Java examines the `catch` clauses in **source-code order**, selecting the first handler whose type is compatible with the **actual exception object**. The remaining `catch` clauses of the same `try` do not run for that object.

The compatibility condition can be understood in terms of reference type assignment: a handler of type `Exception` can accept an `IOException` object because `IOException` extends `Exception`; a handler of type `IOException` does not accept an arbitrary `Exception` object.

Example abbreviated diagram:

```text
java.lang.Throwable
├── java.lang.Error
│   ├── AssertionError
│   └── ...
└── java.lang.Exception
    ├── java.io.IOException
    │   ├── java.io.FileNotFoundException
    │   └── ...
    ├── java.sql.SQLException
    └── java.lang.RuntimeException
        ├── IllegalArgumentException
        │   └── NumberFormatException
        ├── NullPointerException
        └── ...
```

These are representative branches, not the entire `Throwable` hierarchy.

Two rules to remember:

1. **A superclass before a subclass in sibling `catch` clauses** is a covered case: `catch (Exception)` before `catch (IOException)` makes the latter branch unselectable.
2. **A subclass before a superclass** can be valid: `catch (FileNotFoundException)` followed by `catch (IOException)` allows handling file-not-found errors separately, while other I/O errors are received by the broader handler.

`catch` does not behave like independent `if` statements where every branch can run in turn. Only one handler of **the same `try`** is selected for the propagating exception; after that handler completes, there is no "fall-through" mechanism to the next handler.

## 3. Why Does Java Reject a Covered `catch`?

Consider the following example. **This is code intentionally written not to compile**; save it as `WrongCatchOrder.java` to observe the error:

```java
import java.io.IOException;

public class WrongCatchOrder {
    public static void main(String[] args) {
        try {
            throw new IOException("read failed");
        } catch (Exception failure) {
            System.out.println("general handler");
        } catch (IOException failure) {
            System.out.println("IO handler");
        }
    }
}
```

Verification command:

```bash
javac WrongCatchOrder.java
```

`javac` reports a compile-time error at the `catch (IOException failure)` handler. The English message on common JDKs has the equivalent meaning of **"exception IOException has already been caught"**; the exact position and detailed formatting may vary by version/compiler. There is no valid `java WrongCatchOrder` command because compilation did not produce a program.

Cause:

- The actual type `IOException` is assignable to `Exception`.
- The `catch (Exception)` handler comes first and already covers all `IOException` objects.
- Therefore, the `catch (IOException)` handler below can never be selected in the same `try`.
- The compiler detects this conflict even without running the program; this is a **compile-time language error**.

Placing `throw new IOException(...)` in the `try` block only gives the example a clear scenario. Even if the actual execution flow has never raised an error, **the type relationship and handler ordering** still make the two handlers above invalid.

### How to Fix

Place the specific handler first, and the broad handler after:

```java
import java.io.IOException;

public class CorrectCatchOrder {
    public static void main(String[] args) {
        try {
            throw new IOException("read failed");
        } catch (IOException failure) {
            System.out.println("IO handler: " + failure.getMessage());
        } catch (Exception failure) {
            System.out.println("general handler");
        }
    }
}
```

Save as **`CorrectCatchOrder.java`**, compile, and run:

```bash
javac CorrectCatchOrder.java
java CorrectCatchOrder
```

Exact `stdout` output:

```text
IO handler: read failed
```

`catch (IOException)` receives the object and prints the error information. `catch (Exception)` at the end does not run for this throw. The broad handler can serve other exceptions under the `Exception` branch that the `try` block might throw. In this simple example, the broad handler is not required just to handle `IOException` alone, but the **specific first, general later** structure is valid.

## 4. Coverage Is Based on Type, Not Variable Name

Compare these two code snippets side by side:

**Wrong, superclass before subclass:**

```java
try {
    load();
} catch (java.io.IOException ex) {
    // Covers every FileNotFoundException.
} catch (java.io.FileNotFoundException missing) {
    // Unreachable: FileNotFoundException is an IOException.
}
```

This is a **compile-error illustration snippet**, assuming `load()` is a call that can throw a checked `IOException`. Renaming the variable `missing` or `ex` does not change the inheritance relationship between the types.

**Correct ordering:**

```java
try {
    load();
} catch (java.io.FileNotFoundException missing) {
    // Handle the missing-file case specifically.
} catch (java.io.IOException ex) {
    // Handle other IOExceptions.
}
```

This is an **illustrative snippet**; `load()` needs to be defined appropriately. A parent-type handler placed afterward can catch types in the same branch not covered by the preceding handler.

Visualizing the set of caught types:

```text
catch (IOException)
    ├── IOException
    ├── FileNotFoundException
    └── other IOException subclasses

catch (FileNotFoundException)
    └── FileNotFoundException and its subclasses
```

If the type set of a later `catch` **is completely contained within** the type set of an earlier `catch`, the later handler is covered. If the two type sets are two non-overlapping branches, we do not conclude an ordering error merely because one handler is placed before or after another.

## 5. Runnable Example: Three Handler Layers by Specificity

Create the file **`CatchHierarchyDemo.java`**:

```java
import java.io.FileNotFoundException;
import java.io.IOException;

public class CatchHierarchyDemo {
    private static void load(String mode) throws IOException {
        if ("missing".equals(mode)) {
            throw new FileNotFoundException("missing.txt");
        }
        if ("io".equals(mode)) {
            throw new IOException("connection interrupted");
        }
        if ("bad".equals(mode)) {
            throw new IllegalArgumentException("invalid mode");
        }
    }

    private static void run(String mode) {
        try {
            load(mode);
            System.out.println(mode + ": success");
        } catch (FileNotFoundException failure) {
            System.out.println(mode + ": file not found");
        } catch (IOException failure) {
            System.out.println(mode + ": IO failure");
        } catch (IllegalArgumentException failure) {
            System.out.println(mode + ": invalid argument");
        }
    }

    public static void main(String[] args) {
        run("missing");
        run("io");
        run("bad");
        run("ok");
    }
}
```

```bash
javac CatchHierarchyDemo.java
java CatchHierarchyDemo
```

`stdout` output:

```text
missing: file not found
io: IO failure
bad: invalid argument
ok: success
```

Explanation:

- `load("missing")` creates a `FileNotFoundException`; the first handler receives the error because it is the most specific type.
- `load("io")` creates an `IOException` that is not a `FileNotFoundException`; the second handler receives it.
- `load("bad")` creates an `IllegalArgumentException`, which belongs to the `RuntimeException` branch; the two I/O handlers are incompatible and the third handler receives it.
- `load("ok")` completes normally and runs the success message line.

In this example, `IOException` and `IllegalArgumentException` do not have a parent–child inheritance relationship, so placing those two handlers in different positions does not by itself create a coverage issue. It is still good practice to order them for readability and based on the application's handling semantics.

## 6. Which Branches Can `catch (Exception)` and `catch (Throwable)` Shadow?

These two types are very broad, though not completely equivalent.

### 6.1. `catch (Exception)` Before Any `Exception` Subclass

Example that **does not compile**:

```java
try {
    int value = Integer.parseInt("abc");
    System.out.println(value);
} catch (Exception failure) {
    System.out.println("general");
} catch (NumberFormatException failure) {
    System.out.println("parse failed");
}
```

`NumberFormatException` extends `IllegalArgumentException → RuntimeException → Exception`. Because `Exception` comes first, the `NumberFormatException` handler is covered. Swap the order if you genuinely need to handle parse errors separately.

### 6.2. `catch (Throwable)` Is Even Broader Than `catch (Exception)`

`Throwable` is the superclass of both `Exception` and `Error`. Therefore:

```java
try {
    operation();
} catch (Throwable failure) {
    // Covers both Exception and Error.
} catch (Exception failure) {
    // Unreachable: already belongs to Throwable.
}
```

This is a **compile-error illustration snippet**; `operation()` must be defined in a real program. For the same reason, placing `catch (Throwable)` before `catch (Error)` also makes the `Error` branch afterward unselectable.

In ordinary applications, `catch (Throwable)` should not be used just to "catch everything", because it also includes serious `Error`s that the application is unlikely to be able to recover from.

### 6.3. What About `catch (Exception)` Before `catch (Error)`?

The two branches `Exception` and `Error` **are not in a parent–child relationship**. Therefore, considering type coverage alone, the following ordering is valid:

```java
try {
    operation();
} catch (Exception failure) {
    handleException(failure);
} catch (Error failure) {
    handleError(failure);
}
```

This is an **illustrative snippet**, not a recommendation to always catch `Error`. The methods must be defined. `catch (Exception)` does not catch objects belonging to the `Error` branch. However, certain `Error`s such as `OutOfMemoryError` and `StackOverflowError` can leave the JVM state or resources unsafe to continue, so an appropriate operational policy is needed.

## 7. `multi-catch` and Covered Cases

Since Java 7, you can write multiple exception alternatives in **a single `catch`** using the `|` operator:

```java
catch (IOException | SQLException failure) {
    // Handle two different exception branches together.
}
```

`IOException` and `SQLException` are two checked exception classes from different branches; they do not inherit from each other, so they can appear together in a multi-catch. The `failure` parameter of a multi-catch is restricted from reassignment; you cannot assign a new object to it.

### 7.1. Multi-catch Does Not Allow Alternatives With a Parent–Child Relationship

Example that **does not compile**:

```java
try {
    load();
} catch (java.io.FileNotFoundException
         | java.io.IOException failure) {
    System.out.println("IO failed");
}
```

`FileNotFoundException` already belongs to `IOException`, so the two alternatives in **the same multi-catch** have an inheritance relationship; Java rejects this construct. This is a specific rule of `multi-catch`, similar to the goal of avoiding redundant alternatives caused by type coverage.

Write it as a single broad handler:

```java
try {
    load();
} catch (java.io.IOException failure) {
    System.out.println("IO failed");
}
```

Or separate the specific/broad handlers in the right order if the handling differs:

```java
try {
    load();
} catch (java.io.FileNotFoundException missing) {
    System.out.println("Missing file");
} catch (java.io.IOException failure) {
    System.out.println("Other IO issue");
}
```

All snippets in this section are **illustrative snippets**; `load()` with an appropriate `throws` contract is needed and must be placed inside a valid method/class.

### 7.2. A Preceding `multi-catch` Can Shadow a Subsequent `catch`

Example that **does not compile**:

```java
try {
    process();
} catch (java.io.IOException | java.sql.SQLException failure) {
    handle(failure);
} catch (java.io.FileNotFoundException missing) {
    handle(missing);
}
```

The `FileNotFoundException` branch is covered by the `IOException` alternative in the preceding multi-catch. Even though `SQLException` is unrelated to `FileNotFoundException`, having just **one** preceding alternative that covers the entire type of the later handler is enough to cause an error.

This snippet illustrates the ordering rule; `process()` and `handle(...)` must be declared compatibly.

### 7.3. Valid, Runnable Multi-catch Example

Create the file **`MultiCatchDemo.java`**:

```java
import java.io.IOException;
import java.sql.SQLException;

public class MultiCatchDemo {
    private static void execute(String mode)
            throws IOException, SQLException {
        if ("io".equals(mode)) {
            throw new IOException("read error");
        }
        if ("sql".equals(mode)) {
            throw new SQLException("query error");
        }
    }

    private static void run(String mode) {
        try {
            execute(mode);
            System.out.println(mode + ": done");
        } catch (IOException | SQLException failure) {
            System.out.println(mode + ": "
                    + failure.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        run("io");
        run("sql");
        run("ok");
    }
}
```

```bash
javac MultiCatchDemo.java
java MultiCatchDemo
```

`stdout` output:

```text
io: IOException
sql: SQLException
ok: done
```

`throws IOException, SQLException` uses a **comma** to declare multiple types on a method; `catch (IOException | SQLException failure)` uses **`|`** to handle two types from different branches in one handler. These two syntaxes have different purposes and rules.

## 8. Two Easily Confused Compile-Time Errors

Not every "unreachable" or "never thrown" message related to `catch` has the same cause.

### 8.1. Covered by a Preceding `catch`

```java
try {
    throw new java.io.IOException("x");
} catch (Exception failure) {
    // Catches IOException as well.
} catch (java.io.IOException failure) {
    // Unreachable: covered by the preceding handler.
}
```

This snippet **does not compile** because of the order of caught types. Even though `try` throws `IOException`, the specific handler is still completely claimed by the general handler.

### 8.2. Catching a Checked Exception That the `try` Block Cannot Throw

```java
try {
    int x = 1 + 2;
    System.out.println(x);
} catch (java.io.IOException failure) {
    System.out.println("IO error");
}
```

This snippet **does not compile** because there is no operation in `try` that can throw checked `IOException` according to the compiler's analysis. There is no preceding `catch` shadowing it; the error lies in **reachability and exception checking from the `try` block**.

The two cases require different fixes:

| Error | Cause | How to Fix |
| --- | --- | --- |
| `IOException` after `Exception` | Type is covered by the preceding handler | Move `IOException` up, or remove the redundant handler |
| `catch (IOException)` in a `try` that only adds and prints | No matching path that throws checked `IOException` | Remove the unnecessary handler, or move it to a `try` block that actually calls an I/O API |
| `IOException` after `FileNotFoundException` where `try` can throw `IOException` | The broad handler can still receive other I/O types | Can be valid; keep the specific-first order |
| `catch (RuntimeException)` to receive possible unchecked errors | Checking rules differ from checked exceptions | Do not assume an error just because a test path has never thrown it |

In particular, a broad `catch` placed after several specific `catch` clauses can be completely valid, as long as it can still receive another exception type under Java's rules. You should not judge whether code compiles or not solely by how many times a handler ran in tests.

### 8.3. Can You Catch a Subtype After a Supertype by Writing an `if`?

No. Java checks the type relationships of the sibling handlers themselves. You cannot fix the error by adding a condition inside the preceding `catch`:

```java
try {
    load();
} catch (java.io.IOException failure) {
    if (!(failure instanceof java.io.FileNotFoundException)) {
        System.out.println("Other IO error");
    }
} catch (java.io.FileNotFoundException missing) {
    // Still unreachable.
}
```

This is a **snippet intentionally written not to compile**. Even if the preceding handler only executes an `if` branch for some exceptions, that handler still **catches** every `IOException` object. If you want to handle `FileNotFoundException` separately, put the specific handler first; if you want to branch inside a broad handler, do it **inside that same handler** and do not add a subtype `catch` afterward.

## 9. Difference Between Sibling `catch` Clauses and Nested `try` Blocks

The shadowing rule is evaluated for the `catch` chain of **the same `try`**. A `try` nested inside a `catch` or another `try` creates its own handling scope.

Runnable example **`NestedCatchDemo.java`**:

```java
import java.io.FileNotFoundException;
import java.io.IOException;

public class NestedCatchDemo {
    private static void read() throws IOException {
        throw new FileNotFoundException("config.txt");
    }

    public static void main(String[] args) {
        try {
            try {
                read();
            } catch (FileNotFoundException missing) {
                System.out.println("inner: missing file");
                throw new IOException("cannot recover", missing);
            }
        } catch (IOException failure) {
            System.out.println("outer: " + failure.getMessage());
        }

        System.out.println("done");
    }
}
```

```bash
javac NestedCatchDemo.java
java NestedCatchDemo
```

`stdout` output:

```text
inner: missing file
outer: cannot recover
done
```

Initially, the **inner** handler receives `FileNotFoundException`. That handler throws **a new `IOException` object** to signal that recovery is not possible; the **outer** `try` catches this new object. The two handlers are not in the same `catch` chain, so there is no "preceding handler covers later handler" error.

Remember: an exception **thrown from the body of a `catch` itself** is not caught again by sibling `catch` clauses of the same `try`. It exits to the corresponding enclosing scope, and can be handled by an outer `try`. This differs from multiple `catch` clauses in the same list running sequentially.

### `finally` Is Not a Replacement Handler

If `finally` is present, it participates when exiting the block normally or due to an exception. It does not make a `catch` already covered by a preceding type valid:

```java
try {
    read();
} catch (java.io.IOException failure) {
    System.out.println("read failed");
} finally {
    System.out.println("cleanup");
}
```

This is an **illustrative code snippet** with `read()` needing an appropriate declaration. The `catch` order must still be valid; `finally` does not change the compile-time handler checking rules. If `finally` itself throws an error, it can change the final propagating exception, but that is a different control-flow matter.

## 10. When Exceptions Are Siblings, Does Order Still Matter?

For example, `IOException` and `SQLException` both extend `Exception` but do not inherit from each other. Therefore, these two handlers do not shadow each other by type:

```java
try {
    process();
} catch (java.io.IOException io) {
    handleIo(io);
} catch (java.sql.SQLException sql) {
    handleSql(sql);
}
```

With `process()`, `handleIo()`, and `handleSql()` validly defined, swapping the positions of the two handlers can still compile. However, **the checked-exception condition from `try`** must be satisfied as explained in section 8.

Similarly, `NullPointerException` and `IllegalArgumentException` are two different branches under `RuntimeException`. A `RuntimeException` handler placed above would cover both; however, two specialized handlers placed next to each other do not shadow each other.

Do not confuse sharing a common ancestor with **one type being a subtype of the other**. Only a true coverage relationship makes a later handler incapable of receiving objects of its type.

## 11. Principles for Designing Maintainable Handlers

### 11.1. Catch a Sufficiently Specific Type Where It Can Be Handled

If `FileNotFoundException` requires prompting the user to choose another path, while other `IOException`s require a bounded retry, you have a reason to separate the handlers. If both cases use the exact same handling, a single `IOException` handler may be enough; there is no need to add `FileNotFoundException` just to make the code longer.

### 11.2. General Handlers Usually Go Last, If Truly Needed

`catch (Exception)` includes `RuntimeException`s such as `NullPointerException`. An overly broad handler can hide programming bugs if it only logs cursorily and then continues reporting success. Choose an appropriate boundary for handling and consider rethrowing when recovery is not possible.

`catch (Throwable)` also includes `Error`. Use it only in special infrastructure with a clear policy; do not abuse it to work around `catch` ordering errors.

### 11.3. Preserve the Cause When Wrapping Errors

If you want to convert `FileNotFoundException` into a business-layer exception, preserve `cause` via an appropriate constructor or `initCause`. Wrapping does not make an already-covered `catch` handler runnable; that is a change in **propagation path and exception type** that must be designed separately.

### 11.4. Verify Immediately by Compiling

For covered-handler errors, the `javac` command is enough to detect them. There is no need to try running the program to test an unreachable branch. Fix the order of types based on the hierarchy; only after compilation succeeds should you verify the output for each input case.

A short checklist:

1. List the types appearing in the `catch` chain.
2. Sketch the `extends` relationships between them or check Javadoc.
3. If a subtype appears after a superclass that already covers it, move the subtype handler up or remove the redundant handler.
4. For checked exceptions, ensure the `try` block can actually throw the corresponding type.
5. For multi-catch, check that the alternatives have no parent–child relationship.
6. Compile, then test at least one path for each meaningful handler.

## 12. Common Misconceptions

**"The later `catch` will run if the earlier `catch` prints nothing."** False. A handler still **catches** the object even if its body is empty or does not log. The next `catch` of the same `try` is not tried again.

**"`catch (Exception)` before `catch (IOException)` is valid if I only handle RuntimeException in the first handler."** False. The catch type of the first handler is still `Exception`, which includes `IOException`, regardless of any `if` inside the body.

**"Only checked exceptions fail when a child handler is placed after a parent handler."** False. `RuntimeException` before `NullPointerException` also causes shadowing. The same applies to `Throwable` before `Error`.

**"`catch (Exception)` covers every `Error`."** False. `Error` also extends `Throwable` but does not extend `Exception`.

**"Two types that share the parent `Exception` always shadow each other."** False. For example, `IOException` and `SQLException` do not inherit from each other.

**"`catch (FileNotFoundException | IOException e)` is a concise shorthand."** False. Alternatives in a multi-catch must not have a parent–child relationship; just use `catch (IOException e)` or separate handlers in the appropriate order.

**"`catch (IOException)` after `catch (FileNotFoundException)` is always wrong."** False. The broad handler can catch remaining `IOException`s if the `try` block can produce them according to checked-exception analysis.

**"If a `catch` never runs in unit tests, the compiler must report it as unreachable."** False. Never occurring in a test dataset is different from reachability under language rules.

**"Moving a `catch` to a nested `try` block still fails because of duplicate types."** False. Each `catch` chain is attached to its own `try` statement; handlers in different scopes can serve different exceptions.

**"`finally` fixes the compile error because it always runs."** False. `finally` does not change the ordering and type rules of `catch`.

## 13. Self-Check Exercises

### Exercise 1: Order of Two Types With an Inheritance Relationship

```java
try {
    read();
} catch (java.io.IOException e) {
    System.out.println("io");
} catch (java.io.FileNotFoundException e) {
    System.out.println("missing");
}
```

**Question:** Does it compile? **Answer:** No. `FileNotFoundException` is a subclass of `IOException`, so the handler below is covered. Move `FileNotFoundException` first. This is an illustrative snippet; `read()` must be declared.

### Exercise 2: Two Sibling Classes

```java
try {
    process();
} catch (java.io.IOException e) {
    System.out.println("io");
} catch (java.sql.SQLException e) {
    System.out.println("sql");
}
```

**Question:** Is there a coverage error due to ordering? **Answer:** No. The two checked exception types are in different branches. For the snippet to compile completely, `process()` must have a path that can throw the corresponding checked exceptions. This is an illustrative snippet, not a standalone program.

### Exercise 3: Runtime Exception

```java
try {
    System.out.println(Integer.parseInt("x"));
} catch (RuntimeException e) {
    System.out.println("runtime");
} catch (NumberFormatException e) {
    System.out.println("format");
}
```

**Question:** Can execution enter `catch (NumberFormatException)`? **Answer:** No. `NumberFormatException` is a `RuntimeException`. Move the specific handler up or keep only the broad handler when the handling contract is the same.

### Exercise 4: Exception Not Thrown From `try`

```java
try {
    System.out.println("hello");
} catch (java.io.IOException e) {
    System.out.println("io");
}
```

**Question:** Is this an error caused by coverage from a preceding `catch`? **Answer:** No. `try` cannot throw checked `IOException` from the operations shown, so the handler does not satisfy compile-time exception checking.

### Exercise 5: `Throwable` Then `Error`

```java
try {
    throw new AssertionError("assertion");
} catch (Throwable e) {
    System.out.println("anything");
} catch (Error e) {
    System.out.println("error");
}
```

**Question:** What happens? **Answer:** A compile-time error because the preceding `Throwable` already covers `Error`. Do not "fix" it by catching `Throwable` even more broadly; determine whether `Error` genuinely needs to be handled.

## 14. Java 17 References

- [Java Language Specification 17 — `14.20.1 Execution of try-catch](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.1): selecting a compatible handler in order of appearance.
- [Java Language Specification 17 — `11.2.3 Exception Checking](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2.3): compile-time rules for checked exceptions and handlers.
- [Java Language Specification 17 — `14.21 Unreachable Statements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.21): statement reachability.
- [Java Language Specification 17 — `14.20 The try Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20): syntax of `catch`, multi-catch, and `finally`.
- [Java SE 17 API — IOException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html), [FileNotFoundException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/FileNotFoundException.html): parent–child type relationship.
- [Java SE 17 API — RuntimeException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/RuntimeException.html), [Exception](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Exception.html): broad handler types.

**Lesson Takeaway:** When a `catch` of the same `try` already covers the entire exception type that a subsequent `catch` intends to receive, the subsequent handler is unreachable and Java reports a compile-time error. Check the inheritance relationships, place specific handlers before general handlers, verify the rules for checked exceptions and multi-catch separately, and only then run the program.
