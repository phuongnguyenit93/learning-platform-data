# Effects of `final`, *Effectively Final*, and Reassigning the `catch` Parameter in Java

In Java, a `catch` parameter variable is not only used to read the exception message. **Whether that parameter can be reassigned** also affects its usability in lambdas/anonymous classes and, in particular, how the compiler analyzes checked exception types when writing `throw ex;` (*precise rethrow*).

Three core rules:

1. A **single-catch** parameter (e.g., `catch (IOException ex)`) can normally **be reassigned** if it is not declared `final`. If the code does not actually reassign it, the parameter can be **effectively final**.
2. A **multi-catch** parameter (e.g., `catch (IOException | SQLException ex)`) is **implicitly `final`**. It cannot be reassigned, even without writing the `final` keyword.
3. A single `catch` parameter with a broad type like `Exception` can be analyzed by the compiler to **rethrow more precisely than its declared type** if it is `final` or *effectively final*. Reassigning the parameter can lose that precision and lead to checked exception compile errors.

Therefore, we must distinguish between the **static type of the `catch` parameter**, the **runtime type of the exception object**, **variable reassignability**, and the **method's `throws` contract**. They are related, but not identical.

## 1. Recap: What is a `catch` parameter?

A `catch` clause declares a parameter representing the exception object received by the handler:

```java
try {
    Integer.parseInt("abc");
} catch (NumberFormatException ex) {
    System.out.println(ex.getClass().getSimpleName());
}
```

Output:

```text
NumberFormatException
```

- `NumberFormatException` is the **declared type** of the parameter.
- `ex` is the **reference variable** pointing to the exception object being handled.
- `ex.getMessage()`, `ex.getCause()`, and `ex.getStackTrace()` allow inspecting diagnostic information, depending on the situation.
- The scope of `ex` is the corresponding **`catch` handler body**; this variable does not exist in sibling `catch` branches or after the `try-catch` construct.

Normally, you **do not need to reassign `ex`**. Code reads the exception, handles it, or rethrows it. However, Java allows reassigning certain `catch` variables, and that is where differences arise between single-catch and multi-catch.

## 2. What does `final` actually mean for a `catch` parameter?

`final` on a reference variable forbids changing **that variable's reference value** after it is initialized. It **does not make the referenced object immutable**.

Illustrative example inside a method:

```java
try {
    throw new IllegalArgumentException("bad input");
} catch (final IllegalArgumentException ex) {
    System.out.println(ex.getMessage());
    // ex = new IllegalArgumentException("other"); // Compile error.
}
```

This is illustrative code; if the commented line is uncommented, it intentionally fails to compile because `ex` is declared `final`.

What is **not** allowed with a `final` variable:

```java
// Invalid if ex is declared final:
ex = new IllegalArgumentException("replacement");
ex = null;
```

What **can** be done:

```java
System.out.println(ex.getMessage());
Throwable cause = ex.getCause();
```

`final` does not remove the ability to call methods on the object. The object's methods can mutate state if its API allows; `final` only controls reassignment of the **reference variable**.

**Distinction:** `final` does not prevent `throw ex;`. The `throw` statement only uses the reference to throw the object; it is not an assignment to the variable `ex`.

## 3. What is *effectively final*?

A variable or parameter is called **effectively final** when the code obeys the language's relevant non-reassignment rules, even though the **`final` keyword is not explicitly written**. For a single `catch` parameter, the practical understanding is: after the parameter receives the exception object, the code does not reassign a value to that parameter.

Example:

```java
try {
    Integer.parseInt("abc");
} catch (NumberFormatException ex) {
    System.out.println(ex.getMessage());
    // No assignment ex = ...
}
```

`ex` is not declared `final`, yet it is still **effectively final**.

Conversely:

```java
try {
    Integer.parseInt("abc");
} catch (NumberFormatException ex) {
    ex = new NumberFormatException("custom description");
    System.out.println(ex.getMessage());
}
```

The second snippet **compiles** because this is a **single-catch** without `final` declared. However, the parameter `ex` is no longer *effectively final*.

Points to note:

- `ex = ex;` is still **an assignment**, so it does not count as preserving *effectively final*.
- An assignment inside a conditional `if` branch can also break this property; the compiler does not ignore a branch just because it rarely runs.
- Calling `ex.getMessage()` is not an assignment to `ex`.
- Assigning **another** variable, such as `Exception original = ex;`, does not affect whether `ex` is *effectively final*.
- Changing the `ex` reference does not modify the original exception object; it only makes the variable name `ex` point to a new object.

An interesting point: *effectively final* is not a new data type, does not exist at runtime, and does not make the JVM "lock" the object. It is a concept for the **compiler** to check and analyze the program.

## 4. Single-catch: reassignment is allowed, but understand the consequences

`catch (IOException ex)` is a **single-catch** with one exception type:

```java
try {
    readData();
} catch (java.io.IOException ex) {
    java.io.IOException original = ex;
    ex = new java.io.IOException("higher-level context", original);
    System.out.println(ex.getMessage());
}
```

This is an **illustrative snippet**, assuming `readData()` can throw `IOException`. If `final` is not declared, the assignment `ex = ...` is valid.

However, there are two objects to distinguish:

- `original` continues to reference the initially caught exception.
- `ex` after the assignment points to the new exception. If the code simply finishes the handler normally, the new exception is **not automatically thrown** to the caller.

Therefore, **reassigning `ex` is not a way to propagate an exception**. If you need to wrap an error and send it outward, throw the new object:

```java
try {
    readData();
} catch (java.io.IOException cause) {
    throw new java.io.UncheckedIOException(
            "Cannot load required data", cause);
}
```

This is an illustrative snippet, requiring an actual `readData()`; `UncheckedIOException` is a `RuntimeException` subclass dedicated to wrapping `IOException`. The constructor preserves `cause` for tracing.

**Best practice:** use a new variable such as `cause` or `wrapped` when transforming context; do not reassign the `catch` parameter itself just to change the message. Reassigning makes code harder to read and, for a broad-typed `catch`, can also affect *precise rethrow* analysis.

## 5. Multi-catch: parameter is implicitly `final`

Java supports catching multiple unrelated error types in a single handler:

```java
try {
    perform();
} catch (java.io.IOException | java.sql.SQLException ex) {
    System.out.println(ex.getClass().getSimpleName());
}
```

This is an illustrative structure. To compile as-is, `perform()` must have a matching contract, such as `throws IOException, SQLException`.

In a multi-catch:

- The types in the `|`-separated list must not have a **superclass–subclass** relationship with each other.
- All alternatives share the same variable `ex`.
- The variable `ex` is **implicitly final**, meaning it is treated as `final` even without the keyword.
- `ex` cannot be reassigned to a new exception or to `null`.
- You can read `ex`, inspect its actual type, print its message, pass it as `cause`, or `throw ex;` if the checked exception contract allows.
- The static type used to access members of `ex` is inferred from the multi-catch alternatives; you cannot directly call methods that exist only on one branch without appropriate type checking.

Example that **intentionally does not compile**:

```java
try {
    perform();
} catch (java.io.IOException | java.sql.SQLException ex) {
    ex = new java.io.IOException("replacement"); // Error: ex is implicitly final.
}
```

Similarly, `ex = ex;` is still disallowed. If you need a new reference to manipulate, declare **another variable** inside the handler; `ex` continues to hold the caught object.

Another syntax/type error:

```java
// Invalid: NumberFormatException is a subclass of IllegalArgumentException.
catch (NumberFormatException | IllegalArgumentException ex) {
    // ...
}
```

The snippet above **intentionally does not compile** because the second alternative already subsumes the first. Use `catch (IllegalArgumentException ex)` or separate specific handlers if the handling logic differs.

## 6. Accurate comparison table

| Aspect | Single-catch `catch (IOException ex)` | Single-catch `catch (final IOException ex)` | Multi-catch `catch (IOException | SQLException ex)` |
| --- | --- | --- | --- |
| Has `final` keyword? | No | Yes | Not needed |
| Can the variable be reassigned? | **Yes**, unless another rule applies | **No** | **No**, because implicitly `final` |
| Can it be effectively final? | **Yes**, if not reassigned | Explicitly `final` | Implicitly `final` |
| Can a lambda capture `ex`? | Yes, if effectively final | Yes | Yes |
| Is `throw ex;` valid? | Yes, if checked exception rules are satisfied | Yes, if checked exception rules are satisfied | Yes, if checked exception rules are satisfied |
| Can precise rethrow apply? | Yes, when type analysis conditions are met | Yes, when conditions are met | Yes, according to the corresponding type analysis rules |
| Does `final` change the runtime type? | No | No | No |

**Do not confuse:** `final` is a rule for the **variable**, not a prohibition on throwing exceptions. Nor should one claim that every `throw ex;` in a single-catch throws precisely the exceptions raised inside `try`: that depends on the analysis conditions and whether the variable is reassigned.

## 7. Why does *effectively final* matter for lambdas?

Local variables and parameters **captured** from an enclosing scope into a lambda must be `final` or *effectively final*.

Valid single-catch example:

```java
try {
    Integer.parseInt("abc");
} catch (NumberFormatException ex) {
    Runnable printer = () ->
            System.out.println(ex.getClass().getSimpleName());
    printer.run();
}
```

Stdout:

```text
NumberFormatException
```

There is no reassignment to `ex`, so the lambda is allowed to use that reference.

If an assignment to `ex` is added in the handler:

```java
try {
    Integer.parseInt("abc");
} catch (NumberFormatException ex) {
    ex = new NumberFormatException("changed");
    Runnable printer = () -> System.out.println(ex.getMessage());
    printer.run();
}
```

This snippet **intentionally does not compile**: the variable `ex` is no longer *effectively final*, so it cannot be captured by the lambda. The error is not caused by `Runnable` or `NumberFormatException`, but by reassigning a variable referenced by a lambda.

A clearer solution is **not to reassign the exception**, or to create a separate variable:

```java
try {
    Integer.parseInt("abc");
} catch (NumberFormatException ex) {
    String description = "invalid number";
    Runnable printer = () -> System.out.println(description);
    printer.run();
}
```

Here `description` is an *effectively final* local variable. The lambda reads it validly. If you need to pass the exception itself into an asynchronous task, you must also consider data lifetime, threads, and security/logging policies; *effectively final* does not automatically guarantee thread safety of an object's internal state.

With multi-catch, the parameter `ex` is implicitly `final`, so capturing does not run into issues from reassigning that variable. This **does not mean** every object used by the lambda is immutable or safe for concurrent use.

## 8. Complete Java 17+ example: single-catch reassignment and multi-catch capture

Save as **`CatchParameterDemo.java`**:

```java
import java.io.IOException;
import java.sql.SQLException;

public class CatchParameterDemo {

    static void perform(String mode) throws IOException, SQLException {
        switch (mode) {
            case "io" -> throw new IOException("disk unavailable");
            case "sql" -> throw new SQLException("database unavailable");
            default -> System.out.println("task: ok");
        }
    }

    static void single(String mode) {
        try {
            perform(mode);
        } catch (IOException ex) {
            IOException original = ex;

            // Non-final single-catch: reassignment is valid.
            ex = new IOException("context added", original);

            System.out.println("single: rebound=" + ex.getMessage());
            System.out.println("single: source=" + original.getMessage());

        } catch (final SQLException ex) {
            // ex = new SQLException("another"); // Intentionally invalid.
            System.out.println("single: sql=" + ex.getMessage());
        }
    }

    static void multi(String mode) {
        try {
            perform(mode);
        } catch (IOException | SQLException ex) {
            // ex = new IOException("another"); // Intentionally invalid.
            Runnable printer = () ->
                    System.out.println(
                            "multi: " + ex.getClass().getSimpleName()
                            + ": " + ex.getMessage());
            printer.run();
        }
    }

    static void capture(String text) {
        try {
            Integer.parseInt(text);
        } catch (NumberFormatException ex) {
            // Do not reassign ex => effectively final.
            Runnable printer = () ->
                    System.out.println(
                            "captured: " + ex.getClass().getSimpleName());
            printer.run();
        }
    }

    public static void main(String[] args) {
        single("io");
        single("sql");
        multi("io");
        multi("sql");
        multi("ok");
        capture("abc");
    }
}
```

Run with JDK 17 or later:

```bash
javac -encoding UTF-8 CatchParameterDemo.java
java CatchParameterDemo
```

**Exact stdout:**

```text
single: rebound=context added
single: source=disk unavailable
single: sql=database unavailable
multi: IOException: disk unavailable
multi: SQLException: database unavailable
task: ok
captured: NumberFormatException
```

### Reading the behavior in the example

**`single("io")`:** `perform` throws `IOException`. In the single handler, `original` keeps a reference to the original error; `ex` is reassigned to a new object. Because the handler just prints and finishes, the new object **does not become an exception thrown out of `single`**. This example demonstrates that the assignment is legal, not a recommendation to handle errors this way.

**`single("sql")`:** the `SQLException` error is caught by the handler with parameter `final SQLException ex`. Reading the message works; uncommenting the reassignment line causes a compile error.

**`multi("io")` and `multi("sql")`:** the same multi-catch handles two checked exception types with no superclass/subclass relationship. The variable `ex` has a static type inferred to suit both alternatives, while `ex.getClass().getSimpleName()` still reflects the **actual runtime type**. The lambda is allowed to capture `ex`; the code does not and cannot reassign it.

**`multi("ok")`:** no exception occurs; the handler does not run, only printing `task: ok`.

**`capture("abc")`:** the single-catch parameter does not write `final` but is not reassigned, so it is *effectively final* and can be used by the lambda.

## 9. What is precise rethrow?

This is a point easily overlooked when learning about `final` in `catch`.

Normally, if you have a reference variable `Exception ex` and write `throw ex;`, checked exception checking might be assumed to require accounting for the broad `Exception` type. Under certain conditions, however, Java can analyze that this `catch` parameter can only receive **the checked exceptions that can actually be thrown from the corresponding `try` block**, after accounting for preceding handlers. That is **precise rethrow**, introduced in Java 7.

Example:

```java
static void risky(String mode)
        throws java.io.IOException, java.sql.SQLException {
    if ("io".equals(mode)) {
        throw new java.io.IOException("disk error");
    }
    if ("sql".equals(mode)) {
        throw new java.sql.SQLException("query error");
    }
}

static void relay(String mode)
        throws java.io.IOException, java.sql.SQLException {
    try {
        risky(mode);
    } catch (Exception ex) {
        // ex is not reassigned => effectively final.
        throw ex;
    }
}
```

These are **illustrative methods**. `risky` can throw `IOException` or `SQLException`, and `relay` **only declares those two checked exception types**. Even though the `catch` parameter is declared as `Exception ex`, the code compiles because Java precisely analyzes the rethrow when the parameter is not reassigned.

Without precise rethrow, a reader might think `relay` must declare `throws Exception`. That is not required in this situation.

### Conditions to understand

To benefit from precise rethrow analysis for a broad-typed `catch` parameter:

1. The exceptions originating from the execution paths of the corresponding `try` can be analyzed under Java's exception checking rules.
2. `ex` is the parameter of the `catch` catching those exceptions.
3. The parameter is not reassigned in a way that breaks the `final`/*effectively final* condition.
4. The remaining checked exception types that can be thrown must be caught or declared in the method containing `throw ex;`.

If a `catch (Exception ex)` also catches unchecked exceptions, checked exception analysis still follows the language rules; having `catch (Exception)` does not automatically allow every method to declare arbitrary types.

**Important:** precise rethrow is a **compile-time check**; it does not "turn" an `IOException` object into a `SQLException` or change `getClass()` at runtime.

## 10. Complete Java 17+ example: precise rethrow with an effectively final parameter

Save as **`EffectivelyFinalRethrowDemo.java`**:

```java
import java.io.IOException;
import java.sql.SQLException;

public class EffectivelyFinalRethrowDemo {

    static void risky(String mode) throws IOException, SQLException {
        if ("io".equals(mode)) {
            throw new IOException("storage unavailable");
        }
        if ("sql".equals(mode)) {
            throw new SQLException("database unavailable");
        }
    }

    static void relay(String mode) throws IOException, SQLException {
        try {
            risky(mode);
        } catch (Exception ex) {
            System.out.println(
                    "relay: " + ex.getClass().getSimpleName());

            // ex is effectively final, so precise rethrow applies.
            throw ex;
        }
    }

    static void runCase(String mode) {
        System.out.println("mode=" + mode);

        try {
            relay(mode);
            System.out.println("result=ok");
        } catch (IOException ex) {
            System.out.println("io: " + ex.getMessage());
        } catch (SQLException ex) {
            System.out.println("sql: " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        runCase("io");
        runCase("sql");
        runCase("ok");
    }
}
```

Run commands:

```bash
javac -encoding UTF-8 EffectivelyFinalRethrowDemo.java
java EffectivelyFinalRethrowDemo
```

**Exact stdout:**

```text
mode=io
relay: IOException
io: storage unavailable
mode=sql
relay: SQLException
sql: database unavailable
mode=ok
result=ok
```

### Analyzing each execution path

- `risky("io")` throws `IOException`. `relay` catches it via the broad `Exception` parameter, prints the actual type, and throws **the same object** via `throw ex;`. `runCase` catches `IOException`.
- `risky("sql")` behaves similarly with `SQLException`, and the caller selects the `SQLException` handler.
- `risky("ok")` does not throw; the `catch` in `relay` does not run, so `runCase` prints `result=ok`.
- The signature `relay(String mode) throws IOException, SQLException` is valid, **without needing to change to `throws Exception`**, because `ex` was never reassigned and the compiler can determine the checked exception types from `try`.

This example shows the difference between **catching with a supertype to perform a common action** and **preserving the contract's checked exception types when rethrowing**.

In real projects, a handler that only does `throw ex;` is usually redundant. Precise rethrow is valuable when the handler needs to do purposeful work before propagating the error: recording task state, adding a monitoring event, or enforcing a local policy.

## 11. Reassigning the `catch` parameter can break precise rethrow

Consider the following version that **intentionally does not compile**:

```java
static void relayBad(String mode)
        throws java.io.IOException, java.sql.SQLException {
    try {
        risky(mode);
    } catch (Exception ex) {
        ex = new Exception("replacement");
        throw ex; // Compile error: checked Exception is not declared.
    }
}
```

This is **intentionally invalid code**, assuming the `risky` method from the previous example exists and declares `throws IOException, SQLException`.

Reason:

1. A single `catch (Exception ex)` without `final` allows **reassigning** the parameter.
2. After the assignment `ex = new Exception(...)`, the parameter `ex` is **no longer effectively final**.
3. The compiler can no longer apply precise rethrow analysis as before. The expression `throw ex` must now be checked against the broad static type `Exception`.
4. The signature `throws IOException, SQLException` does not cover every checked `Exception`, so it reports an error.

Ways to fix depending on intent:

- **Do not reassign `ex`** if you only want to forward the original error as-is; keep `throw ex;`.
- **Declare `final Exception ex`** so that an accidental reassignment is flagged immediately at the assignment.
- If you genuinely want to **throw a new exception** of type `Exception`, declare/catch accordingly per the contract, or choose a meaningful specific type and keep the original exception as `cause`.
- **Do not widen the signature to `throws Exception` just to hide unclear error design**, if the caller only needs to handle `IOException` and `SQLException`.

Subtle note: reassigning a `catch (IOException ex)` parameter also loses *effectively final*, yet `throw ex;` can still be valid in a method with `throws IOException`, because **the static type of `ex` is already `IOException`**. The precise rethrow issue surfaces most clearly when the handler uses a **declared type broader than the checked exceptions that can actually arise from `try`**.

## 12. How does explicit `final` in single-catch help?

Instead of:

```java
catch (Exception ex) {
    throw ex;
}
```

you can write:

```java
catch (final Exception ex) {
    throw ex;
}
```

In a matching `try` and signature context, both can benefit from precise rethrow analysis. The main differences are:

- Explicit `final` causes **any reassignment to `ex` to be reported as an error immediately**.
- Omitting `final` while keeping it *effectively final* is still sufficient for the related rules.
- Using `final` expresses clear intent that the reference variable should not be changed.
- `final` does **not** by itself make a broad-typed handler good practice: it does not decide recovery policy, protect sensitive data, or replace choosing appropriate error types.

In modern Java, you can choose a project style: declare `final` on important parameters, or rely on *effectively final*. However, **do not reassign a catch parameter just because the syntax allows it**.

## 13. Broad-typed `catch`, handler order, and limits of precise rethrow

Suppose `try` can throw both `IOException` and `SQLException`. A specific handler can handle part of it, while a subsequent handler rethrows the rest:

```java
static void caller() throws java.sql.SQLException {
    try {
        performDatabaseAndFileOperation();
    } catch (java.io.IOException ex) {
        System.out.println("I/O issue has been handled");
    } catch (Exception ex) {
        throw ex;
    }
}
```

These are **illustrative declarations**, assuming `performDatabaseAndFileOperation()` has `throws IOException, SQLException` and no other checked exceptions. Once the earlier `IOException` handler has handled the I/O group, the subsequent `catch (Exception ex)` handler only needs to rethrow the remaining checked group `SQLException`, so `caller`'s `throws SQLException` declaration can suffice under precise rethrow rules.

Do not reverse the order to put `catch (Exception)` before `catch (IOException)`: the superclass handler in front would make the subclass handler unreachable.

**Why does this matter?** The compiler does not just look at a single `throw ex;` line; it analyzes the checked exception types inside `try` and the handlers that caught them earlier. That is why precise rethrow should not be oversimplified into "`catch (Exception)` always requires `throws Exception`" or "`catch (Exception)` can always declare anything".

If you are unsure which types can escape, compile a standalone example and check the signature, rather than randomly changing all `throws` types to `Exception`.

## 14. Multi-catch and rethrowing

A multi-catch can rethrow the object:

```java
static void relayMulti(String mode)
        throws java.io.IOException, java.sql.SQLException {
    try {
        risky(mode);
    } catch (java.io.IOException | java.sql.SQLException ex) {
        throw ex;
    }
}
```

This snippet is an **illustrative method**, assuming `risky(mode)` is defined with the same checked exception contract. `IOException` and `SQLException` are two classes with no superclass/subclass relationship, so the multi-catch is valid. `ex` is implicitly `final`; `throw ex;` preserves the actual error object and allows the contract to list both checked exception types.

Differences to remember:

- In **multi-catch**, you cannot reassign the parameter even if you **do not** write `final`. This is a direct language rule.
- In **single-catch**, to prevent reassignment you can write `final`; if you omit it and do not reassign, the variable remains effectively final.
- Both forms can rethrow the error; whether it is allowed at compile time still depends on the checked exception contract.
- `throw ex;` does not create a wrapper, so it does not automatically add a message/context. If you need to change the exception type, create a new object with `cause` and handle the contract according to the new exception type.

### Multi-catch does not change the runtime type

If `risky` throws `SQLException`, the `ex` parameter in the multi-catch references an **actual `SQLException` object**. `ex.getClass().getSimpleName()` returns `SQLException`, even though the handler is shared with `IOException`.

Do not confuse the parameter's common static type with converting the object at runtime. `ex` being implicitly `final` also only restricts changing the **reference**, not making the exception immutable.

## 15. Common programming mistakes

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Thinking every `catch` parameter is automatically `final` | Single-catch without `final` allows reassignment | Distinguish between single-catch and multi-catch |
| Thinking multi-catch allows reassigning `ex` because `final` is not written | Multi-catch parameters are implicitly `final` | Create a new variable if you need to work with a different value |
| Assigning `ex = new Exception(...)` then `throw ex` in `catch (Exception)` while only declaring `throws IOException, SQLException` | Loses *effectively final*, breaking precise rethrow | Do not reassign or use an appropriate checked contract |
| Catching an error and only reassigning `ex` to a new object | Does not throw the new exception to the caller | `throw new SomeException("context", ex)` if you want to propagate a new error |
| Using a reassigned `catch` variable in a lambda | The variable is no longer *effectively final* | Keep the parameter unassigned or capture another value |
| Thinking `final` makes the `Throwable` object immutable | `final` only locks reference reassignment | Distinguish between reference and object state |
| Using `catch (IOException | FileNotFoundException)` | Superclass/subclass relationship between alternatives | Use `catch (IOException)` or separate handlers |
| Placing `catch (Exception)` before a subtype handler | Subsequent handler is shadowed | Place specific types before supertypes |
| Thinking `throw ex;` automatically creates a new stack trace/cause | It rethrows the same object | Create a wrapper with `cause` if you truly need added context |
| Catching `Exception` at every layer just to log and rethrow | Creates noise and blurs responsibility boundaries | Catch at the layer that has a useful action |

### Avoid confusing "caught" with "handled"

A `catch` can do three very different things:

```java
// A. Intentional recovery and normal completion.
catch (KnownRecoverableException ex) {
    useVerifiedFallback();
}

// B. Rethrow the same object.
catch (KnownRecoverableException ex) {
    throw ex;
}

// C. Wrap with new context and preserve the cause.
catch (KnownRecoverableException ex) {
    throw new HigherLevelException("operation failed", ex);
}
```

The snippets above are **illustrative only**, requiring types/methods to be defined for a real application; they are not standalone Java files. In case A, the caller receives no exception if the fallback succeeds. In B, the caller receives the same object. In C, the caller receives a new object and can trace the origin via `getCause()`.

This choice is about **error policy and handling boundaries**, not whether the `catch` parameter is `final`.

## 16. Checklist when using `final` and precise rethrow

When reading or modifying a `catch` block, check:

1. **Is this single-catch or multi-catch?** Multi-catch has an implicitly `final` parameter; single-catch is only `final` if explicitly declared.
2. **Is the exception variable reassigned?** Look for `ex = ...`, including inside conditional branches. If so, a single-catch is no longer *effectively final*.
3. **Does a lambda/anonymous class capture this parameter?** Captured variables must be `final` or *effectively final*.
4. **Is there a `throw ex;` in a broad-typed handler?** If so, check precise rethrow and the checked exception types analyzed from the `try` block.
5. **Does the `throws` signature accurately cover the checked exceptions?** Do not arbitrarily widen to `throws Exception` when the `try` block actually only has `IOException` and `SQLException`.
6. **Which exception is actually being thrown?** Reassigning the parameter does not transform the old object; rethrowing has a different meaning from creating a wrapper.
7. **Does `cause` need to be preserved?** When converting to a new exception, pass the original error through a cause-accepting constructor if appropriate.
8. **Does a multi-catch have overlapping superclass/subclass types?** If so, split or simplify the alternatives.
9. **Can it be simplified?** If a handler only does `throw ex;` and performs no meaningful work, letting the exception propagate naturally is usually clearer.
10. **Have the critical error paths been test-compiled?** Especially examples with parameter reassignment and methods declaring narrow checked exceptions.

## 17. Self-check questions

**Question 1.** Does `catch (IOException ex)` allow `ex = new IOException("other");`?

**Yes**, if this is a single-catch and the parameter is not declared `final`. However, the assignment makes `ex` no longer *effectively final*, and does not automatically throw the new exception.

**Question 2.** Does `catch (IOException | SQLException ex)` allow reassigning `ex`?

**No.** Multi-catch has an implicitly `final` parameter.

**Question 3.** Does `catch (Exception ex) { throw ex; }` necessarily force the method to declare `throws Exception`?

**No.** When `ex` is not reassigned and precise rethrow conditions are met, the compiler can determine a narrower set of checked exceptions from the `try` block, such as `IOException` and `SQLException`.

**Question 4.** What happens if you write `ex = new Exception("new"); throw ex;` in a `catch (Exception ex)` handler?

The parameter is no longer *effectively final*. For a method that only declares `throws IOException, SQLException`, the broader checked `Exception` type can cause a compile error. To throw a new object, design the contract appropriately rather than relying on precise rethrow.

**Question 5.** Can a `catch` parameter without the `final` keyword that is never reassigned be used by a lambda?

**Yes.** It is *effectively final* under Java's rules.

**Question 6.** Does `final IOException ex` prevent code from calling `ex.getMessage()` or `throw ex;`?

**No.** `final` forbids reassigning the `ex` variable; it does not forbid reading the reference or throwing the same object.

**Question 7.** Does assigning `ex = new IOException("context", original)` automatically make the caller receive the new error?

**No.** If the handler completes normally without `throw`, the caller does not receive a new exception merely because of the assignment.

**Question 8.** Can a multi-catch contain `NumberFormatException | IllegalArgumentException`?

**No.** The two alternatives have an inheritance relationship; `NumberFormatException` is a subclass of `IllegalArgumentException`.

**Conclusion:** a **single-catch** parameter can be reassigned if not declared `final`; a **multi-catch** parameter is implicitly `final`. A single-catch parameter that is **not reassigned** is *effectively final*, can be captured by lambdas, and enables the compiler to apply **precise rethrow** in appropriate situations. When you need to propagate an error, choose an explicit action—handle, rethrow, or wrap with `cause`—instead of confusingly reassigning the exception variable.