# Multiple catch Blocks and Specific-to-General Ordering in Java

> Java Core – Exception · Group: **Try and catch** · Standalone examples use **Java 17+**.

## 1. Problem to Solve

A Java operation can fail in multiple ways: a missing file, a read error, invalid data types, or an invalid application state. When different situations require different responses, you can place **multiple `catch` blocks sequentially after the same `try`**:

```java
try {
    // Perform an operation that may throw multiple exception types.
} catch (SpecificException ex) {
    // Handle the specific type.
} catch (GeneralException ex) {
    // Handle the broader type.
}
```

This is **illustrative syntax**, not a standalone program: `SpecificException` and `GeneralException` are placeholder names.

**Key rule:** Java checks `catch` branches in **top-to-bottom order**; when an exception is thrown, the **first matching block** is selected. Therefore, exception classes with an inheritance relationship must be ordered **from specific (subclass) to general (superclass)** so that the specific handler still has a chance to execute.

After this lesson, you will be able to:

1. Use the exception inheritance hierarchy to determine valid `catch` ordering.
2. Explain why placing `catch (IOException)` before `catch (FileNotFoundException)` causes a compilation error.
3. Accurately predict which handler runs for checked or unchecked exceptions.
4. Distinguish between **multiple sequential `catch` blocks** and **multi-catch** (the `|` syntax) and know the non-overlapping type requirement.
5. Write behavioral tests, avoid overly broad `catch (Exception)` blocks, and understand the role of `finally`.

## 2. How catch Selection Works According to the JLS

According to the [Java Language Specification 17, Section 14.20.1](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.1), if the `try` body throws an exception object, Java looks for the **first `catch` whose catchable type is compatible with the runtime type of the thrown object**. Then:

- The exception object is assigned to the selected `catch` parameter.
- Only the **selected handler block** is executed; the remaining `catch` blocks of the same construct are not run.
- If the handler completes normally, the entire `try/catch` construct can also complete normally, and control continues after the construct.
- If no branch matches, the exception continues propagating outward; an associated `finally` block is still evaluated according to its rules.
- If the handler itself throws an exception, the new exception can propagate further; sibling `catch` blocks below **do not automatically catch** the new exception thrown from an earlier handler.

When a `finally` block is present, see also JLS Section 14.20.2: normally `finally` executes after the `try` body or after the handler, even when exiting the scope due to an exception. If `finally` itself completes abruptly, the reason for the transfer of control may change.

### 2.1. What Does “Matching” Mean?

Example hierarchy:

```text
java.lang.Throwable
├── java.lang.Error
└── java.lang.Exception
    ├── java.io.IOException
    │   └── java.io.FileNotFoundException
    └── java.lang.RuntimeException
        ├── java.lang.IllegalArgumentException
        │   └── java.lang.NumberFormatException
        └── java.lang.IllegalStateException
```

A `FileNotFoundException` can be caught by a parameter of type `FileNotFoundException`, `IOException`, `Exception`, or `Throwable`, because all of those are compatible supertypes. A `NumberFormatException` can be caught by `IllegalArgumentException` or `RuntimeException`. However, `IOException` has no parent–child relationship with `IllegalArgumentException`, so those two `catch` blocks **have no ordering conflict due to inheritance alone**.

**Do not misunderstand:** Java does not automatically pick “the most specific type among all `catch` blocks” while ignoring source order. Precisely because it looks for the **first matching `catch`**, if a superclass `catch` is placed first, a subclass `catch` after it can never receive the subclass exception. The compiler detects this case and rejects the code.

### 2.2. Ordering Is a Compile-Time Constraint

**Valid:**

```java
try {
    openFile();
} catch (java.io.FileNotFoundException ex) {
    System.out.println("File does not exist");
} catch (java.io.IOException ex) {
    System.out.println("Other I/O failure");
}
```

This is an illustrative snippet inside a method; assume `openFile()` is declared as capable of throwing `IOException`.

**Invalid (intentionally written to recognize the compiler error):**

```java
try {
    openFile();
} catch (java.io.IOException ex) {
    System.out.println("I/O failure");
} catch (java.io.FileNotFoundException ex) {
    System.out.println("Missing file"); // Unreachable catch block.
}
```

Reason: the first `catch` already covers `IOException` and all of its subclasses, including `FileNotFoundException`. The second `catch` cannot receive any case that the first `catch` would not already receive; this is a **compile-time error**, not a branch that runs and simply evaluates to false at runtime.

Similar relationships:

- `catch (NumberFormatException)` must appear before `catch (IllegalArgumentException)` if both are present.
- `catch (IllegalStateException)` must appear before `catch (RuntimeException)` if both are present.
- `catch (RuntimeException)` must appear before `catch (Exception)` if they are in the same construct.
- `catch (Exception)` placed before `catch (IOException)` completely shadows the `IOException` catch.
- `catch (Exception)` does not catch `Error`, because `Error` is a separate branch directly under `Throwable`.

## 3. Complete Java 17 Program: Multiple catch Blocks, Ordering, and Multi-catch

Create the file **`CatchOrderDemo.java`**. The program uses standard exceptions with clear inheritance relationships, prints the exact handler selected, and also runs a multi-catch example at the end.

```java
import java.io.FileNotFoundException;
import java.io.IOException;

public class CatchOrderDemo {
    private static void process(String action) throws IOException {
        switch (action) {
            case "missing" -> throw new FileNotFoundException("data.csv");
            case "io" -> throw new IOException("read failed");
            case "bad-number" -> throw new NumberFormatException("invalid integer");
            case "bad-state" -> throw new IllegalStateException("service unavailable");
            case "ok" -> System.out.println("processed ok");
            default -> throw new IllegalArgumentException("unsupported action");
        }
    }

    private static void runOne(String action) {
        System.out.println("== " + action + " ==");
        try {
            process(action);
            System.out.println("try completed");
        } catch (FileNotFoundException ex) {
            System.out.println("file handler: " + ex.getMessage());
        } catch (IOException ex) {
            System.out.println("io handler: " + ex.getMessage());
        } catch (IllegalArgumentException ex) {
            System.out.println("argument handler: "
                    + ex.getClass().getSimpleName());
        } catch (RuntimeException ex) {
            System.out.println("runtime handler: " + ex.getMessage());
        } finally {
            System.out.println("finally");
        }
        System.out.println("after");
    }

    private static void runMultiCatch(String action) {
        System.out.println("== multi " + action + " ==");
        try {
            if (action.equals("file")) {
                throw new FileNotFoundException("missing.txt");
            }
            if (action.equals("number")) {
                throw new NumberFormatException("not a number");
            }
            System.out.println("normal");
        } catch (FileNotFoundException | NumberFormatException ex) {
            System.out.println("group handler: "
                    + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        runOne("missing");
        runOne("io");
        runOne("bad-number");
        runOne("bad-state");
        runOne("ok");
        runOne("unknown");
        runMultiCatch("file");
        runMultiCatch("number");
        runMultiCatch("other");
    }
}
```

Compile targeting the Java 17 language level, then run:

```bash
javac --release 17 -encoding UTF-8 CatchOrderDemo.java
java CatchOrderDemo
```

**Exact stdout** after running the program:

```text
== missing ==
file handler: data.csv
finally
after
== io ==
io handler: read failed
finally
after
== bad-number ==
argument handler: NumberFormatException
finally
after
== bad-state ==
runtime handler: service unavailable
finally
after
== ok ==
processed ok
try completed
finally
after
== unknown ==
argument handler: IllegalArgumentException
finally
after
== multi file ==
group handler: FileNotFoundException
== multi number ==
group handler: NumberFormatException
== multi other ==
normal
```

This output has been verified using `javac --release 17` and `java` on a JDK supporting Java 17. The messages are intentionally constructed from deterministic strings in code, independent of the operating system's I/O message locale.

## 4. Walking Through the Program by Exception

### 4.1. Case `missing`: Subclass Appears Before Superclass

`process("missing")` throws `FileNotFoundException` with the message `data.csv`. Even though both the `FileNotFoundException` catch and the `IOException` catch could accept this exception type, the **first catch** is selected. The program prints only `file handler: data.csv`, then executes `finally` and `after`.

Practical benefit: when a file is missing, you can suggest checking the file name or location, while other I/O errors require separate handling.

### 4.2. Case `io`: More General Handler Receives the Remaining Error

`process("io")` throws `IOException` itself, not `FileNotFoundException`. The first catch does not match, so Java selects the next `IOException` catch.

You do not need to write `catch (FileNotFoundException)` for every file-reading feature if the business logic has no distinct handling for it; when differentiation is needed, parent–child ordering is mandatory.

### 4.3. Case `bad-number`: Unchecked Branches Still Participate in Selection

`NumberFormatException` extends `IllegalArgumentException`, so it is caught by `catch (IllegalArgumentException)` in the program. The `RuntimeException` catch after it does not run. The fact that an exception is unchecked only affects the mandatory `throws`/`catch` requirement at compile time; it **does not change the runtime-type handler lookup rules**.

If you need a specific message for numeric input errors, you can add `catch (NumberFormatException)` **before** `catch (IllegalArgumentException)`.

### 4.4. Case `bad-state`: General RuntimeException Handler

`IllegalStateException` is not in the `IllegalArgumentException` branch, so the I/O and argument catches do not match. The final `RuntimeException` catch receives the error. The program prints the message `service unavailable`.

This does not imply that catching every `RuntimeException` is good design: the example is intentionally structured to demonstrate ordering. In a real application, a `NullPointerException` caused by a programming bug is also a `RuntimeException` and could be caught too broadly.

### 4.5. Case `ok`: No catch Executes

`process("ok")` prints `processed ok` and returns normally. The statement following the call inside `try` prints `try completed`. Because no exception occurs, all `catch` branches are skipped; `finally` still runs, followed by `after`.

### 4.6. Case `unknown`: Not Every IllegalArgumentException Is a NumberFormatException

An unsupported value hits the `default` branch and throws `IllegalArgumentException`. The corresponding catch receives it directly, and the program prints the class name `IllegalArgumentException`. This shows that catching a superclass can cover multiple subclasses without declaring a separate catch for each subclass when the handling is the same.

### 4.7. `multi file` and `multi number`: One Block Handles Multiple Types

The block:

```java
catch (FileNotFoundException | NumberFormatException ex) {
    System.out.println("group handler: "
            + ex.getClass().getSimpleName());
}
```

uses the *multi-catch* syntax introduced in Java 7. The two types separated by `|` have no parent–child relationship. When either exception is thrown, Java runs the **same handler**; `ex.getClass().getSimpleName()` still reveals the specific runtime type.

`runMultiCatch("other")` throws no exception, so it only prints `normal`.

## 5. Inheritance Relationships Determine Valid Ordering

### 5.1. Do Not Place a Superclass catch Before a Subclass catch

Example that intentionally **does not compile**:

```java
try {
    riskyIo();
} catch (IOException ex) {
    recoverIo();
} catch (FileNotFoundException ex) {
    recoverMissingFile();
}
```

`riskyIo()`, `recoverIo()`, and `recoverMissingFile()` are illustrative placeholders, not methods provided to be executed. The compiler does not need to know whether a file actually exists at runtime: it only checks that the first catch covers every instance of the subclass. Therefore, the code fails **at compile time** because the `FileNotFoundException` branch is completely shadowed by the `IOException` catch.

Correct version:

```java
try {
    riskyIo();
} catch (FileNotFoundException ex) {
    recoverMissingFile();
} catch (IOException ex) {
    recoverIo();
}
```

### 5.2. Two Unrelated Types Can Be Reordered

If a method can throw `IOException` (checked) and `IllegalArgumentException` (unchecked):

```java
try {
    riskyOperation();
} catch (IOException ex) {
    handleIo();
} catch (IllegalArgumentException ex) {
    handleBadInput();
}
```

Swapping the order of those two catches does not cause an error **due to inheritance shadowing**, because an `IOException` is not an `IllegalArgumentException` and vice versa. This snippet is illustrative and not standalone (the methods are placeholders); the separate requirement that a **checked exception can be thrown from the `try` block** still must be satisfied.

Therefore, the precise rule is: **for types with a subsumption relationship, place the narrower type before the broader type**, rather than forcing all exceptions from every package into a meaningless global “specificity” table.

### 5.3. Runtime Type Determines the Handler, While the Compiler Checks Code Validity

If a call is declared `throws IOException`, the actual object at runtime might be a `FileNotFoundException`. The compiler inspects the signature when checking checked exceptions; at runtime, the JVM compares the **thrown instance's type** against the `catch` blocks in order.

Do not assume that a method declared `throws Exception` will only trigger `catch (Exception)`, nor that a method without a `throws` clause cannot throw a `RuntimeException`.

## 6. Multi-catch Is Not Multiple Sequential catch Blocks

Java provides two distinct mechanisms:

**Multiple sequential catch blocks:** each type has its own code block, suitable when the responses differ.

```java
try {
    readAndParse();
} catch (IOException ex) {
    reportReadFailure(ex);
} catch (NumberFormatException ex) {
    reportInvalidNumber(ex);
}
```

**A single multi-catch:** groups exceptions that share the same handling.

```java
try {
    readAndParse();
} catch (IOException | NumberFormatException ex) {
    reportFailure(ex);
}
```

The two snippets above only illustrate the design idea; `readAndParse`, `reportReadFailure`, `reportInvalidNumber`, and `reportFailure` are not defined here.

### 6.1. Alternatives in the Same Multi-catch Must Not Overlap in Type

Incorrect, **intentionally fails to compile**:

```java
catch (FileNotFoundException | IOException ex) {
    // Error: FileNotFoundException is a subtype of IOException.
}
```

Correct:

```java
catch (FileNotFoundException | NumberFormatException ex) {
    // The two branches have no direct inheritance relationship.
}
```

Java rejects the combination `FileNotFoundException | IOException` because one alternative is a subtype of another. If two types have a parent–child relationship and share the same handling, simply catch the **appropriate supertype**, such as `catch (IOException ex)`. If they need different handling, write separate `catch` blocks in the proper order.

### 6.2. The Multi-catch Parameter Is Treated as final

In:

```java
catch (FileNotFoundException | NumberFormatException ex) {
    System.out.println(ex.getMessage());
    // ex = new RuntimeException(); // Invalid.
}
```

the parameter `ex` is *implicitly final*, so it cannot be reassigned. When you need different behavior per type, it is usually better to use separate `catch` blocks to avoid heavy `instanceof` checks inside a grouped catch.

The type of a multi-catch parameter is also inferred from its alternatives (so common methods can be called safely); you cannot assume it always exposes APIs specific to each individual alternative. Common `Throwable` methods such as `getMessage()` and `getCause()` are always available.

### 6.3. Combining Multi-catch and General catch

```java
try {
    operation();
} catch (FileNotFoundException | NumberFormatException ex) {
    handleKnownCase(ex);
} catch (IOException ex) {
    handleOtherIo(ex);
}
```

In this illustrative example, if `operation()` can throw `IOException`, the ordering is valid: the first branch catches `FileNotFoundException` or `NumberFormatException`; the second catches any remaining `IOException` instances. A `FileNotFoundException` enters the first branch and does not fall through to the second.

## 7. Broad catch: When to Use It and What Are the Risks?

### 7.1. catch Exception

`catch (Exception ex)` catches `IOException`, `IllegalArgumentException`, `NullPointerException`, and many other failures under `Exception`. It does not catch `Error` types such as `OutOfMemoryError`, because `Error` does not extend `Exception`.

Using `catch (Exception)` at an application boundary (such as a job runner) is sometimes appropriate to aggregate errors, log details, and report a final status, but there must be a **clear policy**. A broad catch can accidentally swallow programming bugs and turn serious failures into normal return data.

In business logic, prefer catching only the types that the current layer **knows how to recover from**, such as a malformed line during parsing or a missing file. If there is no valid recovery path, let the exception propagate to an appropriate handling layer.

### 7.2. catch RuntimeException and Error

`catch (RuntimeException)` covers many code-level bugs such as `NullPointerException`, `IndexOutOfBoundsException`, and `IllegalStateException`. When this handler appears before `catch (IllegalArgumentException)` or `catch (IllegalStateException)`, the compiler reports that the later specific handler is unreachable.

`catch (Throwable)` is even broader because it also includes `Error`. Most programs should not catch `Throwable` just to keep running, because many `Error` conditions represent problems from which the application cannot safely recover. Special low-level frameworks may have exceptions to this, but that is a controlled design decision.

### 7.3. Preserving the Cause and Stack Trace Across Layers

If a handling layer needs to create a more meaningful domain exception, preserve the original cause:

```java
try {
    readConfiguration();
} catch (IOException ex) {
    throw new IllegalStateException("Cannot load configuration", ex);
}
```

This is illustrative code inside a method with an appropriate `readConfiguration()`. The `IllegalStateException(String, Throwable)` constructor preserves the `IOException` as the cause. Writing only `throw new IllegalStateException("failed");` discards the original cause chain unless it was recorded separately.

If you only want the same exception to continue propagating, you can use `throw ex;` (rethrow), subject to the checked exception requirements on the method signature or surrounding caller. Handling inside one `catch` does not give sibling `catch` blocks of the same `try` a chance to run next.

## 8. catch and finally: Execution Order Seen on stdout

In the main example, every call to `runOne` prints `finally` and then `after`, both when an exception occurs and when the operation succeeds.

When no exception occurs:

```text
try completes → skip all catch blocks → finally → statements after try/catch/finally
```

When an exception has a matching handler:

```text
throw → first matching catch → finally → statements after try/catch/finally
```

When an exception is not caught in the current construct:

```text
throw → no matching catch → finally → continue propagating to caller
```

In the last case, **statements immediately following the `try` construct on the same execution path will not run normally**. If `finally` itself throws another exception, that exception can replace the one currently propagating; avoid placing `return` or `throw` arbitrarily inside `finally`.

**Another note:** `try-with-resources` closes resources according to its own rules before transferring control to any outer `catch`/`finally` of the extended construct. Errors from `close()` can become suppressed exceptions; this does not bypass `catch` ordering rules.

## 9. Compiler Constraints Beyond Parent–Child Ordering

Ordering is not the only compilation rule.

### 9.1. A Caught Checked Exception Must Be Reachable from try

**Invalid** example:

```java
try {
    int number = Integer.parseInt("123");
} catch (IOException ex) {
    System.out.println("I/O failed");
}
```

The compiler can prove that this `try` block cannot throw the checked `IOException` or a related type, so the `IOException` catch is rejected (per exception analysis rules). `NumberFormatException` is different: it is unchecked, so it can be caught without a corresponding `throws` declaration.

Do not overuse `catch IOException` “just to be safe”: catch the types the code can actually throw, or design error propagation clearly in the API.

### 9.2. Duplicate catch Blocks of the Same Type Are Forbidden

The following snippet also fails to compile:

```java
try {
    possiblyFail();
} catch (IllegalArgumentException ex) {
    handleA(ex);
} catch (IllegalArgumentException ex) {
    handleB(ex);
}
```

The first catch already covers every exception that could reach the second catch. The code is illustrative only; the methods are not defined.

### 9.3. Do Not Confuse Two Kinds of “Unreachable”

- **A branch shadowed by an earlier catch**: because the supertype already catches all instances of the subtype, Java rejects it at compile time.
- **A valid branch not triggered by current test data**: it is still a usable handler in another run, so it is not an error just because today's test did not trigger that exception.

For example, `catch (FileNotFoundException)` before `catch (IOException)` is completely valid when the operation can also throw a general `IOException`. In a run that throws `FileNotFoundException`, the `IOException` catch does not execute, but it is **not** considered invalid by the language.

## 10. Design Patterns and Practical Verification Workflow

When designing multiple `catch` blocks for an operation:

1. **List possible failures**: inspect the API's `throws` clauses for checked exceptions; identify unchecked exceptions that carry domain meaning.
2. **Map the inheritance relationships** among the types you plan to catch; use Javadoc or your IDE to confirm parent–child links.
3. **Choose distinct recovery policies**: for example, missing file → report the path; other I/O error → report a read failure; invalid data → prompt for correction.
4. **Order handlers that have inheritance relationships** from subtype to supertype.
5. **Combine into a multi-catch** if the types are not in a subtype relationship and genuinely share the same handling.
6. **Choose cleanup boundaries** using `try-with-resources` or `finally` as appropriate.
7. **Compile and test each branch**: one input triggering the specific error, one triggering the parent error, and one succeeding; verify that only the intended handler is selected.
8. **Test the propagation path** when no catch matches; verify that the exception is not swallowed and that post-error state remains consistent.

Decision table for the lesson's example:

| Runtime exception | First matching catch | Why |
| --- | --- | --- |
| `FileNotFoundException` | `FileNotFoundException` | First specific branch |
| `IOException` | `IOException` | Not a `FileNotFoundException` |
| `NumberFormatException` | `IllegalArgumentException` | `NumberFormatException` is a subtype |
| `IllegalStateException` | `RuntimeException` | Not in the `IllegalArgumentException` branch |
| `IllegalArgumentException` | `IllegalArgumentException` | Direct type match |
| No exception | None | `try` completes normally |

You can automate verification with JUnit/AssertJ if the project already uses them. For small console examples, checking stdout and comparing exception types is enough to demonstrate the rules without framework dependencies.

## 11. Common Mistakes and How to Fix Them

- **Catching a superclass before a subclass.** Fix the order: `FileNotFoundException` before `IOException`, `NumberFormatException` before `IllegalArgumentException`.
- **Mistakenly thinking Java picks “the most specific catch” regardless of position.** Java evaluates in order of appearance; the compiler forbids completely shadowed branches.
- **Assuming multiple catches can run for a single exception.** Only one `catch` in the same construct is selected.
- **Putting two parent–child types in the same multi-catch.** `IOException | FileNotFoundException` is invalid; use `IOException` alone or separate handlers.
- **Using `catch (Exception)` to hide all errors.** This easily swallows programming bugs; use it only at boundaries with a clear handling policy.
- **Failing to distinguish checked and unchecked exceptions.** Checked exceptions have dedicated compiler analysis; `RuntimeException` can still be caught and follows the same ordering rules.
- **Assuming `catch (Exception)` includes `Error`.** No; `Error` is a separate branch under `Throwable`.
- **Catching `IOException` when `try` cannot throw it.** This can cause a compile-time error; read the API contract first.
- **Losing `cause` when wrapping an exception.** Construct the new exception with a constructor that accepts `cause` when you need to preserve the original failure.
- **Thinking a handler automatically retries the failed operation.** `catch` only transfers control; retrying requires explicit code and careful consideration of side effects.
- **Forgetting `finally`/resource cleanup.** Resources may still need to be closed after a handler; `try-with-resources` is usually the best choice for `AutoCloseable`.
- **Comparing full OS-dependent exception messages.** Actual messages can vary across environments; check the exception type, handling policy, and application-defined strings.

## 12. Self-Check Questions

**Question 1.** For a `FileNotFoundException`, if you write `catch (IOException)` before `catch (FileNotFoundException)`, which handler runs?

*Answer:* The program **does not compile** because the more specific handler below is shadowed. Java does not run and pick one of the two at runtime.

**Question 2.** If a `NumberFormatException` is thrown but only `catch (IllegalArgumentException)` is present, will that branch catch it?

*Answer:* Yes. `NumberFormatException` extends `IllegalArgumentException`.

**Question 3.** Do `IOException` and `IllegalArgumentException` always have to follow a mandatory “inheritance order”?

*Answer:* No. The two types have no parent–child relationship; their relative order can be chosen based on code organization and business policy, as long as other compiler constraints are satisfied.

**Question 4.** Once a handler catches an exception and completes normally, do other `catch` blocks of the same `try` continue to run?

*Answer:* No. Java selects the first matching `catch`, executes that handler, and then moves to `finally` (if present) and the code after the construct.

**Question 5.** Why is `catch (IOException | FileNotFoundException ex)` invalid?

*Answer:* One alternative is a subtype of the other. If the handling is the same, use a single `IOException` catch; if different, split into separate catches ordered subclass before superclass.

**Question 6.** If the selected `catch` throws an `IllegalStateException`, will a `RuntimeException` catch below it in the **same `try`** catch it?

*Answer:* No. Sibling `catch` blocks only participate in selecting a handler for exceptions thrown from the **`try` body**, not new exceptions thrown inside a sibling `catch`. Only an enclosing `try/catch` can catch it.

**Question 7.** If `try` completes normally, does `finally` still run?

*Answer:* Yes, under normal Java execution, `finally` still executes according to the construct's rules. All `catch` blocks are skipped.

## 13. Official Reference Documentation

- [JLS Java SE 17 §14.20 – The try Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20): syntax for multiple `catch` blocks, multi-catch, and `finally`.
- [JLS Java SE 17 §14.20.1 – Execution of try-catch](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.1): the **first matching catch** rule based on runtime type.
- [JLS Java SE 17 §14.20.2 – Execution of try-catch-finally](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.2): execution flow after `catch` and `finally`.
- [JLS Java SE 17 §11.2.3 – Exception Checking](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2.3): reachable checked exceptions and errors when a `catch` is shadowed.
- [Java 17 API – FileNotFoundException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/FileNotFoundException.html) and [IOException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html): inheritance relationship of I/O exceptions.
- [Java 17 API – NumberFormatException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NumberFormatException.html) and [IllegalArgumentException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/IllegalArgumentException.html): inheritance relationship of unchecked exceptions.

**Takeaway:** In a `try` with multiple `catch` blocks, start with the narrower exceptions you need to handle specifically, then place broader supertypes afterward. Java selects the **first matching handler**, multi-catch only groups types that are not in a subtype relationship with each other, and the compiler catches shadowed branches before runtime.