# Precise Rethrow and Inferring a Narrower Set of Checked Exceptions in Java

**Precise rethrow** is an exception-analysis capability of the Java compiler, introduced in **Java 7**, that allows a method to **catch an exception using a broad type** (for example, `catch (Exception e)`), yet when executing `throw e;`, the compiler can determine **the specific checked exception types that can actually be rethrown** from the corresponding `try` block. As a result, the method signature does not always have to declare an overly broad `throws Exception`.

This mechanism is important when code needs to record an incident at the current layer while still **rethrowing the exact original exception object** to the caller. It is especially useful when a `try` block contains multiple operations that can throw different checked exceptions, and the program wants to keep a common handler without losing the precision of the `throws` contract.

A key point to remember from the start: **precise rethrow is a compile-time analysis; it does not transform the exception object at runtime, does not automatically add a `catch`, does not retry the operation, and does not convert a checked exception into an unchecked exception**.

## 1. The Problem Precise Rethrow Solves

Consider two operations: reading a file may throw `IOException`, and writing to a database may throw `SQLException`. A service needs to perform one of the two, record the error, and let the caller decide.

Before considering precise rethrow, learners often write:

```java
static void run(boolean fileMode) throws Exception {
    try {
        if (fileMode) {
            readFile();   // throws IOException
        } else {
            queryDb();    // throws SQLException
        }
    } catch (Exception e) {
        System.out.println("Ghi nhận lỗi");
        throw e;
    }
}
```

This is an **illustrative snippet**: `readFile()` and `queryDb()` are not yet defined, and the `throws Exception` signature is intentionally written broadly. If the API actually only exposes those two checked exception types, `throws Exception` forces the caller to handle an overly general type. The caller can no longer clearly see the specific contract from the signature.

On Java 7+, when the `catch` parameter satisfies the *final/effectively final* condition, Java allows writing this more precisely:

```java
static void run(boolean fileMode)
        throws IOException, SQLException {
    try {
        if (fileMode) {
            readFile();   // throws IOException
        } else {
            queryDb();    // throws SQLException
        }
    } catch (Exception e) {
        System.out.println("Ghi nhận lỗi");
        throw e;
    }
}
```

This is also a **non-standalone illustrative snippet**, requiring `import java.io.IOException; import java.sql.SQLException;` and the two corresponding methods. What is notable is that **the variable `e` is declared as `Exception`**, yet the compiler still accepts the signature `throws IOException, SQLException` without requiring `throws Exception`.

Why? Because the compiler analyzes **the checked exception types that can arise from the `try` block, are caught by this handler, and are rethrown**. The parameter `e` is not reassigned, so the set of error types used to check the `throw e` statement can be narrower than the declared type `Exception`.

## 2. Complete Java 17 Example: One `catch`, Two Checked Exception Types

Save the following program as **`PreciseRethrowDemo.java`**:

```java
import java.io.IOException;
import java.sql.SQLException;

public class PreciseRethrowDemo {
    static void readFile() throws IOException {
        throw new IOException("Không đọc được tệp");
    }

    static void queryDb() throws SQLException {
        throw new SQLException("Không truy cập được DB");
    }

    static void execute(boolean fileMode)
            throws IOException, SQLException {
        try {
            if (fileMode) {
                readFile();
            } else {
                queryDb();
            }
        } catch (Exception e) {
            System.out.println("Service bắt: "
                    + e.getClass().getSimpleName());
            throw e;
        }
    }

    public static void main(String[] args) {
        try {
            execute(true);
        } catch (IOException | SQLException e) {
            System.out.println("Caller: " + e.getMessage());
        }

        try {
            execute(false);
        } catch (IOException | SQLException e) {
            System.out.println("Caller: " + e.getMessage());
        }
    }
}
```

Compile and run with Java 17+:

```bash
javac -encoding UTF-8 --release 17 PreciseRethrowDemo.java
java PreciseRethrowDemo
```

**Exact stdout** on a UTF-8-capable console:

```text
Service bắt: IOException
Caller: Không đọc được tệp
Service bắt: SQLException
Caller: Không truy cập được DB
```

Analysis:

1. `readFile()` declares checked `IOException`; `queryDb()` declares checked `SQLException`.
2. `execute` can call either one. The compiler analyzes both paths from the signatures and the `try` body.
3. `catch (Exception e)` catches both types because they inherit from `Exception`.
4. `e` is never reassigned. Therefore, `throw e` is **precisely analyzed**: the two checked exception types that must be accounted for are `IOException` and `SQLException`.
5. The signature `throws IOException, SQLException` is sufficient. `main` still catches according to the declared types.
6. At runtime, `throw e` rethrows **the exact object** that was caught, without creating a new instance and without changing its runtime type.

`Exception` in the handler is a **broad static type**; the actual object is `IOException` the first time and `SQLException` the second time. Precise rethrow does not turn those two types into a new `Exception`.

## 3. Core Rule: The `catch` Parameter Must Be `final` or *Effectively Final*

Precise rethrow applies when the thrown object is the **parameter of the `catch` clause**, provided that the parameter is declared `final` or is **effectively final**.

- `final`: the variable is declared with the `final` keyword, so it cannot be reassigned.
- *Effectively final*: `final` is not written, but the program **does not reassign** the parameter after it receives its initial value.
- `throw e;`: the expression throwing the handler's parameter. The compiler can trace the sources of exceptions caught by this handler from the `try` block.

Example:

```java
catch (Exception e) {
    log(e);
    throw e; // e is effectively final, if log does not reassign e.
}
```

This is an **illustrative handler body** assuming `log(e)` is defined. Calling methods and reading properties of `e` **do not break** effective finality. Conversely, an assignment `e = other;` breaks that property.

Writing `final` explicitly is also valid:

```java
catch (final Exception e) {
    throw e;
}
```

The `final` keyword constrains the **reference variable**, not making the entire exception object immutable. APIs that allow mutating data on `Throwable` (such as `addSuppressed` or `setStackTrace`) still have their own rules. Precise rethrow cares about **whether the parameter can be switched to another reference**, not equating it with object immutability.

## 4. Why Reassigning `e` Breaks Narrower Type Inference

Consider the following method. This is an **intentional counterexample that does not compile** on Java 17:

```java
import java.io.IOException;

class ReassignCatchParameter {
    static void read() throws IOException {
        throw new IOException("Lỗi I/O");
    }

    static void relay() throws IOException {
        try {
            read();
        } catch (Exception e) {
            e = new IOException("Đã thay lỗi"); // Reassign e.
            throw e; // Compiler must consider the broad Exception type.
        }
    }
}
```

Because `e` is declared with type `Exception` and has been **reassigned**, the compiler is not allowed to apply the precise rethrow rule to this parameter as before. `throw e` can throw an `Exception` according to its broad static type, so a signature with only `throws IOException` is insufficient. The error typically appears as **unreported exception java.lang.Exception; must be caught or declared to be thrown**.

This does not mean every reassignment of `e` is forbidden in Java. For a **single-catch parameter** without `final`, reassignment can be syntactically valid, but it changes the referenced object and the checked-exception analysis.

The right choices depending on your goal:

- If you need to **keep the same object**, do not reassign `e` and use `throw e;`.
- If you want to **create a new exception** with a different contract, create a new variable/object, preserving the original error via `cause` if appropriate.
- If you genuinely allow throwing any `Exception`, declaring `throws Exception` is valid, though you should consider the breadth of the API.

Do not replace `e` with a new instance and call that an "original rethrow": the caller will receive a new object rather than the exception that originated from the original operation.

## 5. Precise Definition: Inferred from Which `try`?

When a `catch` catches multiple types that can be thrown from `try`, the compiler does not look only at **the type name of the `catch` parameter**. It examines the exceptions that can be thrown by the **corresponding `try` block**, and the types that the current handler can catch, after accounting for preceding handlers.

You can picture the analysis process for a `throw e` in a final/effectively final handler:

1. Identify the **`try` block associated with the handler containing `e`**.
2. Determine the exception types that can arise according to static analysis from `try`, including method calls and valid constructs inside it.
3. Determine which of those types **are caught by the current handler**, not already caught by an earlier handler in the same `catch` chain.
4. Use the corresponding types when checking the **checked exceptions** of `throw e`.
5. Types that are **unchecked** do not require `throws` in the signature under the catch-or-declare rule.

This is a **practical mental model**, not a step-by-step sequence of the JVM engine. The Java language specifies the checking conditions at **compile time**, while the JVM still receives a single exception object at runtime.

Do not assume the compiler "trial-runs" `if` branches with real data to know a specific runtime exception for sure. It analyzes **possibilities** from types and structure, without knowing all future input values.

## 6. An Earlier Handler Already Caught a Type: The Remaining Set Can Be Narrower

Precise rethrow takes into account that specific exceptions have already been handled by **preceding** `catch` clauses.

Complete Java 17 example, save as **`EarlierCatchDemo.java`**:

```java
import java.io.IOException;
import java.sql.SQLException;

public class EarlierCatchDemo {
    static void execute(boolean ioFailure)
            throws IOException, SQLException {
        if (ioFailure) {
            throw new IOException("Tệp lỗi");
        }
        throw new SQLException("DB lỗi");
    }

    static void relay(boolean ioFailure) throws SQLException {
        try {
            execute(ioFailure);
        } catch (IOException e) {
            System.out.println("I/O đã xử lý: " + e.getMessage());
        } catch (Exception e) {
            System.out.println("Lỗi còn lại: "
                    + e.getClass().getSimpleName());
            throw e;
        }
    }

    public static void main(String[] args) {
        relaySafely(true);
        relaySafely(false);
    }

    static void relaySafely(boolean ioFailure) {
        try {
            relay(ioFailure);
        } catch (SQLException e) {
            System.out.println("Caller: " + e.getMessage());
        }
    }
}
```

Commands:

```bash
javac -encoding UTF-8 --release 17 EarlierCatchDemo.java
java EarlierCatchDemo
```

**Exact stdout**:

```text
I/O đã xử lý: Tệp lỗi
Lỗi còn lại: SQLException
Caller: DB lỗi
```

Explanation:

- `execute` can throw `IOException` or `SQLException`.
- The first `catch (IOException e)` handles the I/O path and **does not rethrow**.
- The subsequent `catch (Exception e)` no longer receives `IOException` from that `try` block, because that type was already caught by the earlier handler.
- Because `e` in the later handler is effectively final, `throw e` is checked precisely; among the checked exceptions of `try` in the example, only **`SQLException`** remains.
- Therefore, `relay` only needs to declare `throws SQLException`, without needing `throws Exception` or `throws IOException`.

Do not confuse this with the case where the `catch (IOException e)` handler **throws a new exception**: an exception thrown from an earlier `catch` body is not caught by the subsequent `catch (Exception e)` handler in the same `try-catch` construct. It propagates to an enclosing scope or the caller according to propagation rules.

## 7. How Are Multi-Catch and Precise Rethrow Related?

Java 7 also introduced **multi-catch**: a single handler can list multiple exception types using `|`, for example:

```java
catch (IOException | SQLException e) {
    throw e;
}
```

With multi-catch:

- The parameter `e` of a multi-catch is **implicitly final**: it cannot be reassigned.
- The handler receives only **one exception object** per execution, belonging to one of the listed types.
- On `throw e`, the actual object is rethrown; no new object is created.
- The compiler can keep the checked exception types distinct in its analysis, instead of forcing an overly broad supertype to be declared.
- Types listed in the same multi-catch **must not have a subtype relationship with each other**; for example, `IOException | Exception` is invalid.

Complete example, save as **`MultiCatchPreciseDemo.java`**:

```java
import java.io.IOException;
import java.sql.SQLException;

public class MultiCatchPreciseDemo {
    static void task(boolean io) throws IOException, SQLException {
        if (io) {
            throw new IOException("Lỗi tệp");
        }
        throw new SQLException("Lỗi DB");
    }

    static void relay(boolean io) throws IOException, SQLException {
        try {
            task(io);
        } catch (IOException | SQLException e) {
            System.out.println("Relay: " + e.getClass().getSimpleName());
            throw e;
        }
    }

    public static void main(String[] args) {
        for (boolean io : new boolean[] {true, false}) {
            try {
                relay(io);
            } catch (IOException | SQLException e) {
                System.out.println("Caller: " + e.getMessage());
            }
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 MultiCatchPreciseDemo.java
java MultiCatchPreciseDemo
```

**Exact stdout**:

```text
Relay: IOException
Caller: Lỗi tệp
Relay: SQLException
Caller: Lỗi DB
```

In a multi-catch, you cannot write `e = new IOException("x");` because the parameter is implicitly `final`. **Multi-catch** and **precise rethrow** work well together, but they are two distinct concepts:

- Multi-catch allows **combining the handling syntax** for multiple exception types that have no subtype relationship.
- Precise rethrow allows **precise checking of checked exceptions on the rethrow statement** when the condition on the parameter is met.

You do not need multi-catch to get precise rethrow: the `catch (Exception e)` example with an effectively final `e` earlier proved the opposite.

## 8. `catch (Exception e)` Still Catches Types Other Than Checked Exceptions

`Exception` is the superclass of `RuntimeException`. Therefore, a `catch (Exception e)` can also catch unchecked exceptions such as `IllegalArgumentException` and `NullPointerException` thrown inside `try`. However, that **does not require** the method to declare `throws RuntimeException` or `throws NullPointerException`.

Example:

```java
static void run(String text) throws IOException {
    try {
        readFile();                   // throws IOException
        Integer.parseInt(text);       // May throw NumberFormatException
    } catch (Exception e) {
        throw e;
    }
}
```

This is an **illustrative method**, requiring `readFile()` to be defined and `IOException` to be imported. The signature `throws IOException` is sufficient with respect to checked exceptions because `NumberFormatException` is an unchecked subclass of `RuntimeException`. At runtime, the handler may receive either one and rethrow the exact object; the caller must decide whether to catch those unchecked exceptions according to the contract.

**`catch (Exception e)` does not catch `Error` classes**, because `Error` is a sibling branch of `Exception` under `Throwable`. You should not change it to `catch (Throwable e)` just to "catch everything" in business code: many `Error`s are severe and not suitable for normal continuation.

A Java snippet that compiles **does not guarantee** that all error paths have been handled safely. Precise rethrow only addresses the precision of the checked exception contract when the compiler checks it.

## 9. The Static Type of Called Methods Sets a Limit on Precision

The compiler analyzes **visible method signatures and code structure**, and does not infer exception types from what you *know* about the runtime implementation.

Suppose an API declares:

```java
static void externalApi() throws Exception {
    throw new IOException("Lỗi I/O");
}
```

This is an **illustrative method**, requiring `IOException` to be imported. Even though the illustrative body only throws `IOException`, the **caller** sees the signature `throws Exception`; the compiler must account for the possibility of a checked exception of type `Exception` from the published contract.

Therefore, the following **intentionally non-compiling** snippet cannot rely on precise rethrow to declare only `IOException`:

```java
static void caller() throws IOException {
    try {
        externalApi();  // Declared throws Exception
    } catch (Exception e) {
        throw e;        // May have to declare throws Exception
    }
}
```

Because `externalApi()` is declared `throws Exception`, at the call site, the checked exception type that can arise according to analysis is `Exception`, not just `IOException`. Even though parameter `e` is effectively final, it cannot make the caller's signature more precise than the information available from the called API.

Fix according to the **actual contract**:

- If you own `externalApi` and are sure the contract only has I/O errors, change its signature to `throws IOException` so callers have accurate information.
- If the API intentionally allows any checked `Exception`, the caller can declare `throws Exception` or catch/translate the corresponding cases.
- If you change abstraction layers with a new wrapper, proactively design the contract and preserve the cause; do not treat it as a precise rethrow of the original object.

Do not "cast" exceptions just to get past the compiler when there is no guarantee about the actual runtime type. A `ClassCastException` during error handling only makes the situation worse.

## 10. Resource Checked Exceptions Are Also Included in the `try` Analysis

A `try-with-resources` block can throw a checked exception **when closing a resource**, even if the `try` body throws no checked exceptions. Therefore, precise rethrow does not look only at the business statements between the curly braces: it must also include the close operations performed by the language construct.

Standalone Java 17 example **`ResourcePreciseDemo.java`**:

```java
import java.io.IOException;

public class ResourcePreciseDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("Đang đóng");
            throw new IOException("Không đóng được");
        }
    }

    static void use() throws IOException {
        try (Resource resource = new Resource()) {
            System.out.println("Trong try");
        } catch (Exception e) {
            System.out.println("Catch: "
                    + e.getClass().getSimpleName());
            throw e;
        }
    }

    public static void main(String[] args) {
        try {
            use();
        } catch (IOException e) {
            System.out.println("Caller: " + e.getMessage());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 ResourcePreciseDemo.java
java ResourcePreciseDemo
```

**Exact stdout**:

```text
Trong try
Đang đóng
Catch: IOException
Caller: Không đóng được
```

`close()` declares `throws IOException`. Even though the `try` body only prints to the console, exiting the scope calls `close()`, which throws `IOException`. The broad handler `catch (Exception e)` receives the error, then `throw e`; the compiler allows `use() throws IOException` because checked exception analysis includes errors that can arise when closing the resource.

If **both the `try` body and `close()` throw an exception**, `try-with-resources` typically keeps the body's error as the primary exception and attaches the close error as a **suppressed exception**. `throw e` preserves the primary object and the existing suppressed list; it does not automatically erase the close error. Do not carelessly use a `finally` block with a new `throw` that masks the original error.

## 11. Precise Rethrow and Rethrowing the Exact Object

`catch (Exception e) { throw e; }` **does not call `new Exception(...)`**. At runtime, `throw e` uses the exact reference to the caught object. Precise rethrow is the *compiler calculating checked exception obligations*, not creating a new object or stripping the stack trace.

Identity verification example in **`IdentityPreciseDemo.java`**:

```java
import java.io.IOException;

public class IdentityPreciseDemo {
    static IOException original;

    static void relay() throws IOException {
        original = new IOException("Lỗi gốc");
        try {
            throw original;
        } catch (Exception e) {
            System.out.println("Trong catch: " + (e == original));
            throw e;
        }
    }

    public static void main(String[] args) {
        try {
            relay();
        } catch (IOException e) {
            System.out.println("Tại caller: " + (e == original));
            System.out.println("Message: " + e.getMessage());
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 IdentityPreciseDemo.java
java IdentityPreciseDemo
```

**Exact stdout**:

```text
Trong catch: true
Tại caller: true
Message: Lỗi gốc
```

The purpose of the `original` field is only to check identity, not a pattern for sharing exceptions via a `static` variable in multithreaded programs. In real code, let the throw-and-catch mechanism carry error information.

A normal `throw e` also does not create a new stack trace just because it rethrows. If you need to change the error type due to an abstraction layer, use a wrapper with `cause` (for example, `new IllegalStateException("Không nạp được", e)`); that is a **new object**, no longer having the same identity, and differs from an original precise rethrow.

## 12. Combining with Nested Handlers

An inner `try` can catch and resolve `IOException`; the outer `try` only sees the exceptions that actually propagate upward according to flow analysis.

Skeleton example:

```java
static void dispatch() throws SQLException {
    try {
        try {
            readFile();  // throws IOException
        } catch (IOException e) {
            System.out.println("Đã xử lý I/O");
        }

        queryDb();       // throws SQLException
    } catch (Exception e) {
        throw e;
    }
}
```

This is an **illustrative snippet**, requiring both `readFile` and `queryDb` methods along with imports for the exception types. If the inner I/O handler completes normally and does not rethrow, the outer `try` does not let that `IOException` escape. `throw e` in the outer handler can be checked against the remaining checked exception, `SQLException`.

Conversely, if the inner `catch (IOException e)` handler writes `throw e;`, then `IOException` can propagate to the outer scope. In that case, it must be declared or handled; precise rethrow does not automatically "erase" an exception that can actually escape.

Note: placing separate `catch` clauses also makes code easier to read. Do not nest multiple levels just to achieve a narrower signature if a simple handler organization already clearly expresses handling responsibilities.

## 13. Cases That Are Not Precise Rethrow

It is easy to confuse the following cases as being the same mechanism:

### 13.1. Throwing an Exception Variable That Is Not a `catch` Parameter

```java
static void rethrowVariable(Exception saved) throws Exception {
    throw saved;
}
```

This is a **valid method without `main`**. `saved` is a method parameter, **not a `catch` parameter associated with a `try`**. Even if you do not reassign `saved`, the compiler does not apply the precise rethrow rule from a `try` block as it does with a catch parameter. Because the static type of `saved` is `Exception`, the signature `throws Exception` is appropriate.

### 13.2. Creating a New Exception Object

```java
catch (Exception e) {
    throw new Exception("Lỗi mới", e);
}
```

This is an **illustrative handler snippet**. The statement throws the expression `new Exception(...)`, not `throw e`. The new exception has checked type `Exception`; the method must catch/declare it according to the contract. The precise rethrow mechanism for catch parameters does not make the new exception's type become `IOException` just because its `cause` is `IOException`.

### 13.3. Only Having a Specific `catch`

```java
catch (IOException e) {
    throw e;
}
```

This handler rethrows the declared type `IOException`; even without discussing precise rethrow, the signature `throws IOException` is obviously valid. The most notable effect of precise rethrow is in situations where you **catch a broad type** without being forced to declare all checked exceptions belonging to that broad type.

### 13.4. Wrapping a Checked Exception into an Unchecked One

```java
catch (IOException e) {
    throw new IllegalStateException("Tầng dịch vụ lỗi", e);
}
```

This snippet creates a new **unchecked exception**, preserving `IOException` via `getCause()`; it does not require declaring checked `IOException` from throwing the wrapper. However, this is **changing the contract**, not precise rethrow. This option should only be used when the new layer's contract requires an appropriate application exception.

## 14. Precise Rethrow Does Not Remove Error-Handling Responsibility

A concise signature does not mean every failure has been recovered from. When rethrowing:

- The current method still **terminates abnormally** if the exception escapes.
- The caller still needs to know whether to try a fallback, return an error to the user, abort the request, or propagate further.
- `finally` and `try-with-resources` still participate in cleanup according to the rules; they do not automatically roll back data or undo all side effects.
- Unchecked exceptions can propagate upward even though they do not appear in `throws`.
- A more precise static type helps **callers read the API and use specific `catch` clauses**; it does not guarantee the system has no runtime errors.
- If there is nothing to do at an intermediate layer, you can **omit a `catch` that only rethrows**, letting the exception propagate naturally.

A suitable place to use a broad-catching handler that rethrows is a layer that needs to add context **without altering the checked exception contract**. Still, consider whether specific catches or multi-catch would be clearer; do not use `catch (Exception e)` unconditionally, because it also catches many `RuntimeException`s that may be bugs.

## 15. Common Mistakes

| Misconception | Correct Understanding |
| --- | --- |
| "`catch (Exception e)` followed by `throw e` must always `throws Exception`." | Java 7+ has precise rethrow when `e` is final/effectively final; narrower checked exceptions can be declared. |
| "Precise rethrow converts checked into unchecked." | No; it only analyzes the set of checked exceptions that can be rethrown more precisely. |
| "Only multi-catch has precise rethrow." | No; a broad single-catch `catch (Exception e)` can also be analyzed precisely. |
| "`catch (Exception e)` only catches checked exceptions." | It also catches `RuntimeException`, though it does not catch `Error`. |
| "`throw e` creates a new exception object." | It rethrows the same object that `e` references, if `e` has not been reassigned. |
| "A later handler still receives types already caught by an earlier handler." | No; handlers are evaluated in order, and a type caught earlier is not passed to a later handler. |
| "The compiler knows for sure that at runtime only `IOException` is thrown even if the callee declares `throws Exception`." | The compiler checks the static contract; the broad `Exception` type must still be considered. |
| "Writing `throws IOException` is enough just because the original exception has an IOException cause." | A new checked wrapper may be `Exception`; the cause does not change the checked type of the wrapper. |
| "Reassigning `e` still preserves precise rethrow as before." | Reassigning a single-catch parameter breaks the effectively final condition; multi-catch even forbids reassignment. |
| "Precise rethrow handles cleanup and retry automatically." | No; those are separate concerns regarding execution flow, resources, and policy. |

## 16. Self-Check Scenarios

**Question 1.** A `try` body can throw `IOException` and `SQLException`; the handler `catch (Exception e) { throw e; }` does not reassign `e`. Is `throws Exception` required?  
**Answer:** Not necessarily. `throws IOException, SQLException` can be sufficient under precise rethrow, if those are the checked exceptions that can escape and no other checked types arise in the handler.

**Question 2.** In `catch (Exception e)`, if you add `e = new IOException("khác");` before `throw e;`, does precise rethrow still apply?  
**Answer:** Not under the mechanism for final/effectively final catch parameters, because `e` has been reassigned. If the signature only says `throws IOException`, the compiler may require the broader type `Exception`.

**Question 3.** Can `e` be reassigned in `catch (IOException | SQLException e)`?  
**Answer:** No. A multi-catch parameter is implicitly final.

**Question 4.** A `try` body has `IOException` and `SQLException`, but the first handler catches `IOException` and finishes handling it. The next handler is `catch (Exception e) { throw e; }`. What is the set of checked exceptions to consider for the second handler?  
**Answer:** As in the standard example, `SQLException` remains; `IOException` was already caught by the earlier handler, provided the earlier handler does not throw an additional checked error that must be accounted for separately.

**Question 5.** Why cannot precise rethrow narrow the type when calling an API that declares `throws Exception` even though you know the current version only throws `IOException`?  
**Answer:** The compiler must examine the static contract of the call, in which `Exception` is still a checked type that can be thrown.

**Question 6.** Does `throw e` modify the message, cause, or stack trace of the original exception?  
**Answer:** The statement itself does not create a new object or modify those properties. Data may be modified by other code or special JVM mechanisms, but not because of a simple rethrow action.

**Question 7.** If a resource's `close()` declares `throws IOException` but the `try` body throws no checked exceptions, can `catch (Exception e) { throw e; }` cause the method to require `throws IOException`?  
**Answer:** Yes. Exception analysis for `try-with-resources` includes errors that can be thrown when closing the resource.

**Question 8.** Is a handler `catch (Exception e) { throw new IOException("mới"); }` an example of precise rethrow?  
**Answer:** No. It throws a new object of checked type `IOException`; the checking rules for throwing a new type apply, not the `throw e` analysis of a catch parameter.

**Question 9.** Can a method with `throws IOException, SQLException` still throw `NullPointerException`?  
**Answer:** Yes. This is an unchecked exception, which is not required to be declared.

**Question 10.** Why shouldn't you write `catch (Exception e)` everywhere just to take advantage of precise rethrow?  
**Answer:** Because an overly broad catch scope can accidentally include programming bugs; you should only catch when the current layer genuinely needs to do meaningful work before passing the error along.

## 17. Checklist for Reviewing a Precise Rethrow Snippet

When reviewing a method containing `throw e`, check the following in order:

1. **Is `e` a `catch` parameter?** An ordinary method parameter does not receive this rule in the same way.
2. **Is `e` final or effectively final?** There must be no reassignment.
3. **Which checked exceptions can the corresponding `try` block throw?** Check the signatures of called methods, internal constructs, and resource `close()` methods.
4. **Has any earlier handler already caught some types?** Only exceptions that can still reach the current handler are relevant to its precise rethrow.
5. **Is a new exception thrown from the handler?** Account for it separately; do not treat it as an original rethrow.
6. **Does the `throws` signature accurately describe the set of checked exceptions that can escape?** Do not write it narrower than the rules allow, and avoid unnecessarily broad types.
7. **Are there unchecked exceptions?** They do not have to be declared, but risks must still be managed according to the contract.
8. **Is the `catch` actually needed?** If the handler only does `throw e` without adding value, letting the exception propagate naturally may be simpler.
9. **Does the caller have an appropriate final handling action?** A precise signature helps the caller handle errors; it does not replace a recovery policy.
10. **Have the examples been run on the Java version used in the project?** Precise rethrow has existed since Java 7; other APIs and syntax in examples may require a newer version.

## 18. Conclusion

**Precise rethrow** helps Java infer a **narrower set of checked exceptions** when a handler catches a broad type but rethrows **the final/effectively final catch parameter itself** via `throw e;`. The compiler relies on the checked exceptions that can arise from the corresponding `try` block, taking into account preceding handlers and resource constructs, rather than simply forcing the signature to be `throws Exception` just because `e` has declared type `Exception`.

Multi-catch works well with precise rethrow because its parameter is implicitly `final`, but it is not a prerequisite for precise rethrow to work. Do not reassign `e`, do not confuse `throw e` with `throw new ...`, and do not expect the compiler to infer a narrower type than the static signature of a called API.

The practical rule is: **let the current layer handle the error when it can recover; if it needs to record and propagate, preserve the exception and declare the most accurate set of checked exceptions the language allows**.
