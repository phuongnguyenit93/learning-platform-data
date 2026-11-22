# Avoid Extending `Throwable` or `Error` Directly When Inappropriate in Java

When creating a **custom exception**, the first question is not only *“what should the class be named?”* but also *“which branch in the `Throwable` hierarchy should this class extend?”*. The choice of superclass determines whether the error is checked at compile time, whether `catch` blocks can intercept it, what semantics the API communicates to callers, and how maintainable the codebase is.

**Practical rules for most Java applications:**

- For application errors that callers are **expected to catch or declare** under a checked exception contract, consider extending `Exception` or an appropriate checked subclass.
- For parameter, state, or application contract errors that use an **unchecked exception**, consider `RuntimeException` or a subclass such as `IllegalStateException`.
- **Do not extend `Throwable` directly** just to “create the most general error type”: this usually produces a checked exception outside the `Exception` branch and surprises callers.
- **Do not extend `Error`** for ordinary business, validation, I/O, or integration failures: this branch carries special semantics and should not be used as a workaround to avoid `throws`.

The last two choices are not always syntactically forbidden by Java. What matters is that they are usually **semantically or contractually wrong** for the error you are designing.

## 1. Reading the `Throwable` Inheritance Hierarchy Correctly

Simplified hierarchy:

~~~text
java.lang.Object
    |
    +-- java.lang.Throwable
          |
          +-- java.lang.Error
          |      +-- AssertionError
          |      +-- LinkageError
          |      +-- VirtualMachineError
          |             +-- OutOfMemoryError
          |
          +-- java.lang.Exception
                 |
                 +-- IOException
                 |
                 +-- RuntimeException
                        +-- IllegalArgumentException
                        +-- IllegalStateException
                        +-- NullPointerException
~~~

In Java:

- `Throwable` is the root class of objects that can be used with `throw` and caught via `catch`.
- `Exception` is the branch commonly used to represent exceptional conditions that an application may decide to handle.
- `RuntimeException` is the **unchecked** branch, typically used for conditions that do not require callers to catch or declare them at compile time.
- `Error` is also an **unchecked** branch, typically indicating serious VM issues, class linkage problems, system invariants, or conditions from which ordinary application code is not expected to recover.
- A class that **extends `Throwable` directly**, without belonging to `RuntimeException` or `Error`, is a **checked exception**.

Checked/unchecked status is determined by the **inheritance type**, not by the class name and not by how “dangerous” the author considers the error to be.

### Distinguishing “Can Be Written” from “Should Be Written”

A **syntactically valid** Java example:

~~~java
final class DirectFailure extends Throwable {
    DirectFailure(String message) {
        super(message);
    }
}
~~~

You can also define:

~~~java
final class BusinessFailureError extends Error {
    BusinessFailureError(String message) {
        super(message);
    }
}
~~~

However, both approaches have significant consequences that cannot be seen from the class name alone. This lesson analyzes why a different approach should be chosen in most business code.

## 2. Why Extending `Throwable` Directly Is Usually the Wrong Choice

A custom exception that directly extends `Throwable` sits **outside both the `Exception` and `Error` branches**. Java still allows throwing it, but many APIs and application handlers are designed around `Exception`, not the root `Throwable` class.

Example:

~~~java
final class DirectFailure extends Throwable {
    DirectFailure(String message) {
        super(message);
    }
}

static void work() throws DirectFailure {
    throw new DirectFailure("cannot complete work");
}
~~~

These are two illustrative declarations that can be placed in the same Java class.

`DirectFailure` here is **checked**. Therefore `work()` must catch or declare it as shown in the example. Callers also need to handle or propagate that checked type.

### 2.1. `catch (Exception)` Does Not Catch Direct Subclasses of `Throwable`

~~~java
static void caller() throws DirectFailure {
    try {
        work();
    } catch (Exception e) {
        System.out.println("Exception handler");
    }
}
~~~

This is an illustrative method that **compiles** when `work()` throws `DirectFailure`. `catch (Exception e)` does not catch `DirectFailure` because it does not extend `Exception`. Consequently, `caller()` must still declare `throws DirectFailure` or provide another appropriate handler.

Ordinary callers easily assume `catch (Exception)` handles all “exception-style” application errors, but for a direct subtype of `Throwable`, that assumption is false.

### 2.2. It Can Make `throws` Signatures Overly Broad

If a library uses `throws Throwable` to avoid listing individual errors:

~~~java
static void execute() throws Throwable {
    throw new DirectFailure("cannot complete work");
}
~~~

then callers may be forced to catch/declare `Throwable` or a type matching the declared error at the call site. That signature is so broad that it mixes ordinary situations with `Error`, making the contract unclear.

You should not use `throws Throwable` in a business API just to be “future-proof.” Broader does not mean better; it can force API users to handle an inappropriate set of error types.

### 2.3. It Does Not Fit Many `Exception`-Handling Boundaries

In real-world applications, generic error handlers, response mappers, or business error-handling code may intentionally catch `Exception`. A direct subtype of `Throwable` **does not belong to that group**.

This does not mean every framework fails to catch it: a framework may use `Throwable` or special mechanisms. However, choosing `Throwable` directly as the parent **increases the chance of unexpected behavior**, and requires a clear contract if you truly intend to do so.

**Conclusion:** Unless designing a framework or VM mechanism with a specific reason, ordinary custom errors should sit under `Exception` or `RuntimeException`, not directly under `Throwable`.

## 3. Why You Should Not Extend `Error` for Business Errors

`Error` is the unchecked branch of `Throwable`, but it is **not an alias for every severe error**.

Several standard classes illustrate its distinct semantics:

| Class | Typical Meaning |
| --- | --- |
| `OutOfMemoryError` | The JVM cannot allocate memory as requested |
| `StackOverflowError` | Deeply nested calls cause stack overflow |
| `LinkageError` | Class linkage/definition problem |
| `AssertionError` | An internal assertion is violated |
| `Error` | Common superclass for the special error group |

Not every `Error` instance in every environment has the exact same severity, and specialized programs may intentionally use `AssertionError` in tests. However, **the conventional meaning of `Error` is not a recoverable business error**.

### 3.1. `catch (Exception)` Does Not Catch `Error`

~~~java
try {
    throw new AssertionError("Unexpected invariant failure");
} catch (Exception e) {
    System.out.println("Exception caught");
} catch (AssertionError e) {
    System.out.println("AssertionError caught");
}
~~~

This is a valid Java snippet. The output is:

~~~text
AssertionError caught
~~~

`AssertionError` does not extend `Exception`, so the first branch does not match it. The second branch is used here solely to **demonstrate the type hierarchy**; you should not turn broad `Error` catching into normal recovery logic in production.

If you define `PaymentDeclinedError extends Error` for an expected payment outcome, handlers that catch `Exception` will not intercept it. The `Error` name also sends the wrong signal that the failure is an abnormal serious issue like a VM error or a broken system invariant.

### 3.2. Using `Error` to Avoid Checked Exceptions Is the Wrong Motivation

Some developers want to avoid `throws` and think:

~~~java
final class DatabaseUnavailableError extends Error {
    DatabaseUnavailableError(String message) {
        super(message);
    }
}
~~~

This is a **design anti-pattern**, even though the class compiles. `DatabaseUnavailableError` is unchecked because it sits under `Error`, but that does not turn a lost database connection into a virtual machine error. If you want an unchecked application error with proper semantics, you should usually use `RuntimeException` or an appropriate subclass.

### 3.3. Why Not “Catch `Throwable` and Continue”?

~~~java
try {
    performBusinessAction();
} catch (Throwable t) {
    logAndContinue(t);
}
~~~

This is an illustrative snippet with two hypothetical methods. Catching `Throwable` includes `Exception`, `RuntimeException`, `Error`, and direct subtypes of `Throwable`. If business logic simply continues after any `Error`, the system may operate in an unsafe state or without sufficient resources.

**Catching `Throwable` should only appear at special boundaries with a very explicit error policy**, such as execution frameworks that must record state before failing. It is not a default handler for requests, database operations, or input processing.

## 4. Choosing the Right Superclass: `Exception`, `RuntimeException`, or a Specialized Class?

A simple decision tree:

~~~text
Do you really need a custom exception type?
             |
     +-------+-------+
     |               |
     No             Yes
     |               |
Use a standard       Does the caller need a checked contract?
exception or              |
result data type      +---+----+
                      |        |
                     Yes       No
                      |        |
               extends Exception   extends RuntimeException
               (checked)           or an unchecked subclass
~~~

This diagram is a **practical guideline**, not a rigid formula. Some APIs choose unchecked exceptions for recoverable errors because callers are designed to handle them at a boundary layer; some APIs choose checked exceptions to force callers to consider failure.

### 4.1. Using `Exception` for a Checked Contract

~~~java
public final class ConfigurationLoadException extends Exception {
    public ConfigurationLoadException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

This is a standalone class in `ConfigurationLoadException.java`.

When used:

~~~java
static void initialize() throws ConfigurationLoadException {
    try {
        readConfiguration();
    } catch (java.io.IOException cause) {
        throw new ConfigurationLoadException(
                "Cannot initialize configuration", cause);
    }
}
~~~

This snippet assumes `readConfiguration()` is already defined. Because `ConfigurationLoadException` is checked, callers must catch or declare it appropriately.

**When useful:** the error has clear meaning in the contract, callers are expected to make a recovery or propagation decision, and compile-time enforcement provides value.

### 4.2. Using `RuntimeException` for an Unchecked Contract

~~~java
public final class DomainStateException
        extends RuntimeException {
    public DomainStateException(String message) {
        super(message);
    }
}
~~~

This is a standalone Java class. Callers are not required by the compiler to catch or declare it, yet it can still propagate and fail the operation.

**When useful:** a business invariant is violated, an invalid state occurs, or the API policy favors centralized error handling without imposing checked exceptions at every layer.

### 4.3. Extending a JDK Subclass When It Already Carries the Right Semantics

If the custom error genuinely represents an invalid state, you can use:

~~~java
public final class OrderNotReadyException
        extends IllegalStateException {
    public OrderNotReadyException(String orderId) {
        super("Order " + orderId + " is not ready");
    }
}
~~~

This is a standalone class. It can be caught specifically via `catch (OrderNotReadyException e)`, while also belonging to `IllegalStateException`.

However, do not extend a JDK class merely because its name sounds close. For example, a lost connection error is not an argument error; `extends IllegalArgumentException` would convey the wrong semantics.

**Selection tip:** consider the condition under which the error arises, how callers are expected to handle it, module boundaries, and whether the superclass truly matches the meaning.

## 5. Checked vs. Unchecked: The Exact Rules

Java categorizes exceptions for compile-time checking purposes:

**Unchecked:** `RuntimeException` and all of its subclasses; `Error` and all of its subclasses.

**Checked:** other subclasses of `Throwable` not in those two groups. Therefore, **`Throwable` itself and its direct subclasses** are checked.

| Class Declaration | Kind | Does the Caller Have a Checked Obligation? |
| --- | --- | --- |
| `class A extends Exception` | Checked, unless A actually extends RuntimeException — which is not the case with the declaration above | Yes |
| `class B extends IOException` | Checked | Yes |
| `class C extends RuntimeException` | Unchecked | No |
| `class D extends IllegalStateException` | Unchecked | No |
| `class E extends Error` | Unchecked | No |
| `class F extends Throwable` | Checked | Yes |

Important distinctions:

- **Checked** does not mean “minor” or “always fixable.”
- **Unchecked** does not mean “unhandleable” or “does not need logging.”
- **Error** does not mean every instance of it is thrown automatically by the JVM.
- **A `throws` contract** describes the possibility that a checked exception may propagate out; it does **not** guarantee every call throws an error.

When an API can encounter an `IOException` from reading a file, keeping `IOException` or defining an appropriate checked subclass is much more natural than creating an `Error` just out of fear of writing `throws`.

## 6. Practical Issues When Extending `Throwable` Directly

### Issue 1 — Callers Catch `Exception` Yet the Error Still Escapes

~~~java
final class DirectIssue extends Throwable {
    DirectIssue(String message) {
        super(message);
    }
}

static void throwDirect() throws DirectIssue {
    throw new DirectIssue("direct issue");
}

static void caller() throws DirectIssue {
    try {
        throwDirect();
    } catch (Exception e) {
        System.out.println("Caught as Exception");
    }
}
~~~

These declarations can be placed in a single Java class. `caller()` must still declare `throws DirectIssue` because `catch (Exception)` **does not cover** `DirectIssue`.

If `DirectIssue extends Throwable` is replaced with `DirectIssue extends Exception`, an appropriate `catch (Exception e)` can catch it. That is why the exception type hierarchy matters more than just looking at the `throw` keyword.

### Issue 2 — API Signatures Become Unusual

~~~java
public void save() throws Throwable
~~~

This is an illustrative signature. A public API requiring callers to account for `Throwable` is an overly broad contract. It suggests the method may throw categories that business code should not be expected to recover from normally.

If the error group is actually I/O or business storage failure, declare `throws IOException`, `throws StorageException`, or a specific architectural exception group.

### Issue 3 — Handlers and Tooling May Behave Unexpectedly

Error-handling code using `catch (Exception)` or handlers configured for `Exception` subclasses will not catch a direct `Throwable` subtype outside that branch. This creates a situation where a seemingly general handler misses an error intended as an “application exception.”

Do not infer that all frameworks will fail: systems that catch `Throwable` can catch it. Still, that is not a good reason to place an ordinary custom exception outside the `Exception` branch.

### Issue 4 — Harder Maintenance of Checked Contracts

A project with many classes extending `Throwable` directly easily leads to sprawling `throws Throwable` signatures. When clients later want to narrow responsibilities, changing the exception types and fixing catch blocks to match proper semantics can be costly.

For new business code, choosing a conventional superclass and expressing caller responsibilities accurately from the start is much better.

## 7. Practical Issues When Extending `Error` for Application Errors

An example of **a design to avoid**:

~~~java
public final class CustomerNotFoundError extends Error {
    public CustomerNotFoundError(String customerId) {
        super("Customer not found: " + customerId);
    }
}
~~~

Although this code compiles, “customer not found” is normally a business state or query outcome, not a failure in the `Error` branch.

Options to consider:

- If “not found” is a normal lookup outcome: consider `Optional<Customer>` or a result type with a `NOT_FOUND` code.
- If a missing customer violates a precondition or invariant: you can use `IllegalArgumentException`, `IllegalStateException`, or an appropriate unchecked subclass.
- If the API contract requires callers to catch it explicitly: consider a checked `CustomerNotFoundException extends Exception`.
- If the project consistently uses unchecked domain errors: consider `CustomerNotFoundException extends RuntimeException`.

Each option has its own meaning. There is no single answer for every application, but **`extends Error` is usually inappropriate**.

### Impact on `catch` Blocks

~~~java
try {
    findCustomer("C-100");
} catch (Exception e) {
    // Handler for Exception errors.
}
~~~

This is an illustrative snippet. If `findCustomer` throws `CustomerNotFoundError extends Error`, this handler will not catch that object. That usually contradicts the expectations of an application layer preparing a “customer not found” response.

If the custom type extends `RuntimeException` or `Exception`, a broad `catch (Exception)` handler can catch it, though **narrower catch blocks should still be used** when the current layer has specific handling.

## 8. When Might Creating a Subtype of `Error` Be Reasonable?

Saying “avoid when inappropriate” does not mean Java code **absolutely forbids** developers from creating an `Error` subclass.

There are very specialized situations in low-level libraries, internal tooling, or invariant-checking mechanisms where an author intentionally wants to signal a failure outside normal business exception contracts. Some testing libraries use `AssertionError` to report a failed check. `AssertionError` belongs to the `Error` branch by design.

However, before considering a custom `Error` subclass, answer these questions:

1. Does this error truly have semantics similar to a system/internal assertion issue that ordinary callers should not handle?
2. Are the consequences clear when `catch (Exception)` does not catch it?
3. Does the system need to continue operating after this error? If so, using `Error` can be misleading.
4. Can `AssertionError` or an appropriate standard exception be used instead of creating a new `Error` branch?
5. Do all handlers and observability tools understand this unusual contract?

For ordinary business services, web APIs, batch jobs, repositories, validation, and integrations, **there is almost always a better choice than subclassing `Error`**.

## 9. No Custom Exception Is Needed If a Standard Type Suffices

A simple system may only need:

~~~java
static int divide(int numerator, int denominator) {
    if (denominator == 0) {
        throw new IllegalArgumentException(
                "denominator must not be zero");
    }
    return numerator / denominator;
}
~~~

This is a valid Java method. There is no need to create `ZeroDenominatorThrowable extends Throwable` or `ZeroDenominatorError extends Error`; both would make the contract harder to understand.

Similarly:

- Invalid argument → `IllegalArgumentException`, or `NullPointerException` when a required reference must not be null.
- Invalid state → `IllegalStateException`.
- Unsupported operation → `UnsupportedOperationException`.
- I/O error → `IOException` or a subtype.
- JDBC failure → `SQLException` at the corresponding boundary.

If multiple clients must handle a specific domain error differently, **then** consider adding a dedicated class. A good custom type must bring clear value, not just a longer name.

## 10. Do Not Use Exceptions for Every Expected Business Outcome

An unsuccessful outcome is not always an exceptional error.

For example, looking up an item may not find the ID:

~~~java
static java.util.Optional<String> lookupItem(String id) {
    if ("SKU-1".equals(id)) {
        return java.util.Optional.of("Keyboard");
    }
    return java.util.Optional.empty();
}
~~~

This is a valid Java method. Callers can handle the `Optional.empty()` branch as an expected outcome, rather than creating `ItemNotFoundError` or `ItemNotFoundThrowable`.

Similarly, a declined payment can be represented by an `enum` or `record` containing a `DECLINED` status. Use exceptions only when the contract truly treats the situation as a failure that must propagate, rather than a result callers must always inspect.

Decision table:

| Situation | Usually Reasonable Option |
| --- | --- |
| Simple parameter error | Standard exception such as `IllegalArgumentException` |
| Domain state error needing distinct catching | Custom `RuntimeException` or appropriate subtype |
| Recoverable error under a compile-time contract | Custom checked `Exception` |
| Low-level I/O error | `IOException` or subclass |
| Data not found as an expected outcome | `Optional`/result type |
| VM error or very specialized low-level failure | Appropriately meaningful `Error` classes; do not turn into business errors |
| Wanting to “catch everything and keep processing” | Do not default to `catch (Throwable)`; design properly typed handling boundaries |

## 11. Standalone Java 17+ Example: Comparing Four Error Groups

The following program contains:

1. **A properly designed checked custom exception** extending `Exception`.
2. **A properly designed unchecked custom exception** extending `IllegalStateException`.
3. **A direct subclass of `Throwable`** to show it is checked yet outside `Exception`.
4. **Standard `AssertionError`** to show the `Error` branch bypasses `catch (Exception)`. This is a type-checking illustration, not a production `Error`-handling pattern.

Create the file **`ThrowableInheritanceDemo.java`**:

~~~java
import java.io.IOException;

public class ThrowableInheritanceDemo {

    static final class ConfigurationFailure extends Exception {
        ConfigurationFailure(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static final class OrderStateFailure
            extends IllegalStateException {
        OrderStateFailure(String message) {
            super(message);
        }
    }

    // Design anti-pattern: used only for hierarchy comparison.
    static final class DirectThrowableFailure extends Throwable {
        DirectThrowableFailure(String message) {
            super(message);
        }
    }

    public static void main(String[] args) {
        System.out.println("== checked ==");
        try {
            initializeConfig(true);
            System.out.println("configuration=ready");
        } catch (ConfigurationFailure e) {
            System.out.println("unexpected configuration failure");
        }

        try {
            initializeConfig(false);
        } catch (ConfigurationFailure e) {
            System.out.println(
                    "configuration=" + e.getClass().getSimpleName()
                            + ": " + e.getMessage());
            System.out.println(
                    "cause=" + e.getCause().getClass().getSimpleName()
                            + ": " + e.getCause().getMessage());
        }

        System.out.println("== unchecked ==");
        try {
            verifyOrder(false);
        } catch (IllegalStateException e) {
            System.out.println(
                    "state=" + e.getClass().getSimpleName()
                            + ": " + e.getMessage());
        }

        System.out.println("== direct Throwable ==");
        try {
            throwDirect();
        } catch (DirectThrowableFailure e) {
            System.out.println(
                    "direct=" + e.getClass().getSimpleName()
                            + ": " + e.getMessage());
        }

        System.out.println("== Error hierarchy ==");
        try {
            throw new AssertionError("illustrative assertion");
        } catch (Exception e) {
            System.out.println("caught by Exception");
        } catch (AssertionError e) {
            System.out.println(
                    "assertion=" + e.getClass().getSimpleName()
                            + ": " + e.getMessage());
        }

        System.out.println("app=completed");
    }

    static void initializeConfig(boolean available)
            throws ConfigurationFailure {
        try {
            readConfig(available);
        } catch (IOException cause) {
            throw new ConfigurationFailure(
                    "cannot initialize config", cause);
        }
    }

    static void readConfig(boolean available) throws IOException {
        if (!available) {
            throw new IOException("disk inaccessible");
        }
    }

    static void verifyOrder(boolean paid) {
        if (!paid) {
            throw new OrderStateFailure(
                    "cannot ship before payment");
        }
    }

    static void throwDirect() throws DirectThrowableFailure {
        throw new DirectThrowableFailure("direct root");
    }
}
~~~

Compile and run with Java 17 or later:

~~~bash
javac ThrowableInheritanceDemo.java
java ThrowableInheritanceDemo
~~~

**Exact expected stdout:**

~~~text
== checked ==
configuration=ready
configuration=ConfigurationFailure: cannot initialize config
cause=IOException: disk inaccessible
== unchecked ==
state=OrderStateFailure: cannot ship before payment
== direct Throwable ==
direct=DirectThrowableFailure: direct root
== Error hierarchy ==
assertion=AssertionError: illustrative assertion
app=completed
~~~

### Explaining the Checked Group

`initializeConfig(true)` completes normally. When `available=false`, `readConfig` throws `IOException("disk inaccessible")`. The configuration layer wraps it in `ConfigurationFailure` and preserves the `IOException` itself in `getCause()`. `main` catches the declared checked type; no `catch(Throwable)` is needed.

### Explaining the Unchecked Group

`OrderStateFailure extends IllegalStateException`, and `IllegalStateException extends RuntimeException`, so this exception is unchecked. Callers can `catch(IllegalStateException)` to handle states that disallow the operation. This is a reasonable example if order state errors have distinct meaning in the API.

### Explaining the Direct `Throwable` Group

`DirectThrowableFailure extends Throwable` is neither under `Exception` nor `Error`, so it is checked. `throwDirect()` must declare `throws DirectThrowableFailure`. `main` uses the narrow handler `catch(DirectThrowableFailure e)`. With only `catch(Exception e)`, this error type **would not be caught**.

### Explaining the `Error` Group

`AssertionError` belongs to the `Error` branch, not `Exception`. Therefore, in the final `try` block, `catch (Exception e)` does not run; `catch (AssertionError e)` runs. This is **an example testing inheritance hierarchy behavior**, not a recommendation to catch and ignore uncontrollable `Error`s.

The program does not intentionally trigger `OutOfMemoryError`, `StackOverflowError`, or terminate the JVM. Creating such failures for “testing” is unnecessary and can destabilize the runtime environment.

## 12. Anti-Pattern Code: Catching `Exception` Cannot Substitute for `Throwable` Subclass Semantics

Consider:

~~~java
static void demonstrate() throws DirectThrowableFailure {
    try {
        throwDirect();
    } catch (Exception e) {
        System.out.println("not reached for DirectThrowableFailure");
    }
}
~~~

This method can be placed in the same `ThrowableInheritanceDemo` class.

**Why is `throws DirectThrowableFailure` required?** Because the `catch(Exception)` handler does not accept a direct subtype of `Throwable`. The call can still propagate the checked `DirectThrowableFailure` outward.

If `throws DirectThrowableFailure` is removed without adding a matching handler, a **compile error** occurs because the checked exception is neither caught nor declared.

Fixing this according to the business goal does not always mean adding `catch(Throwable)`. Usually a better solution is to **redesign the custom error to extend `Exception`** from the beginning, if it is genuinely a checked application exception.

## 13. Can You Extend a Specialized Standard Exception?

Yes, if the error condition maintains a **meaningful “is-a” relationship** with the superclass.

Example:

~~~java
public final class InsufficientOrderStateException
        extends IllegalStateException {
    public InsufficientOrderStateException(String message) {
        super(message);
    }
}
~~~

This is a standalone Java class if saved in `InsufficientOrderStateException.java`.

Then:

- `catch (InsufficientOrderStateException e)` handles it specifically.
- `catch (IllegalStateException e)` can also catch it due to the subtype relationship.
- `catch (RuntimeException e)` is a broader handler, though it should not be used indiscriminately.

Conversely, a network connection error does not become an `IllegalArgumentException` just because a library wants to put it in the unchecked branch. Choose a superclass with the right semantics, not just the right compile-time characteristics.

## 14. Cause and Constructors of a Custom Exception

Choosing the right superclass is only the first step. When wrapping a low-level exception, a custom exception must **preserve the cause** via an appropriate constructor.

~~~java
public final class RepositoryUnavailableException
        extends Exception {

    public RepositoryUnavailableException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

This is a standalone class. Callers can instantiate it as:

~~~java
throw new RepositoryUnavailableException(
        "Repository is unavailable", sqlException);
~~~

This is an illustrative snippet that has a `sqlException` variable and requires handling the checked exception per contract. The `super(message, cause)` constructor ensures the wrapper’s `getCause()` retains a reference to the original error.

**Do not write only:**

~~~java
super(message + ": " + cause.getMessage());
~~~

in the error class constructor if the goal is to preserve the cause. Concatenating the message does not populate the wrapper’s `getCause()`.

### Constructors Are Not Automatically Inherited

Even though `Exception` provides a `(String, Throwable)` constructor, `RepositoryUnavailableException` must still **declare** the corresponding overload if callers should be able to invoke it. Java does not inherit constructors like instance methods.

### Do Not Disable Stack Traces or Suppression by Default

Some root classes like `Exception` and `RuntimeException` have a `protected` constructor that controls `enableSuppression` and `writableStackTrace`. Do not disable those two features merely for assumed performance gains: doing so can lose useful diagnostic data. Measure first and define a clear policy before using specialized configurations.

## 15. `Error` Does Not Mean “The Most Severe Error That Must Be Caught”

Many beginners think severe errors should extend `Error` while minor errors extend `Exception`. Java does not use such a simplistic criterion.

Examples:

- Failing to start a business system due to missing configuration can be **very severe** operationally, yet it can still be cleanly represented by an appropriate `Exception` or `RuntimeException`.
- An `AssertionError` intentionally thrown by a test may describe a violated invariant in a test environment, not that the entire JVM is broken.
- An `IOException` from a lost connection may require a retry/recovery policy, not an `Error` subclass.
- An `OutOfMemoryError` may leave the program without enough resources to continue safely, making catching and continuing very risky.

Choose the superclass based on **the nature of the contract and expected recovery**, not on whether someone feels the error is “severe.”

## 16. Do Not Create a `BaseApplicationThrowable`

An architecture sometimes starts with:

~~~java
public class BaseApplicationThrowable extends Throwable {
    public BaseApplicationThrowable(String message) {
        super(message);
    }
}
~~~

This is a **design anti-pattern** if intended for all business exceptions. It places every checked subclass in the system outside `Exception`, leading to the same issues with `catch(Exception)` and `throws` signatures.

If the project genuinely needs a base exception to group multiple error types:

~~~java
public class ApplicationException extends Exception {
    public ApplicationException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

or an unchecked base:

~~~java
public class ApplicationRuntimeException extends RuntimeException {
    public ApplicationRuntimeException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

These snippets are two **independent illustrative classes**, not a requirement to create both. Having a common superclass is only useful when there is a **genuine shared contract**; there is no need to build a deep hierarchy just to satisfy an OOP diagram.

## 17. When Should You Catch `Throwable` at a Special Boundary?

Some system environments want to record the failure of an execution unit, even when the error is not in the `Exception` branch. In such cases you may see:

~~~java
try {
    executePlugin();
} catch (Throwable failure) {
    recordFailure(failure);
    throw failure;
}
~~~

This is an **illustrative snippet**, where `executePlugin` and `recordFailure` are provided by the system; the enclosing method must satisfy checked exception rules and the rethrown type.

The key characteristic is that the handler **records and rethrows**, without implicitly claiming that every `Error` is recoverable.

In practice, if both `Error` and `Exception` must be handled at a framework boundary, there must be specific analysis of:

- Whether resources can still operate safely.
- The extent to which state can be reclaimed after `OutOfMemoryError` or `LinkageError`.
- How to avoid logging loops or secondary errors caused by low memory.
- Reporting the error once and deciding where to stop or restart.
- The library/framework’s contract in the real runtime environment.

**This is a special case, not a reason to create custom `Error`s for business logic.**

## 18. Differences with `finally` and Try-With-Resources

Some developers choose `Error` because they want errors to “fast-exit” past handlers. However, `Error` **does not automatically skip `finally` blocks** when Java exits a `try` construct via normal exception flow.

Example:

~~~java
try {
    throw new AssertionError("assertion failed");
} finally {
    System.out.println("cleanup");
}
~~~

This is an illustrative snippet. `finally` still executes before `AssertionError` continues propagating outward, as long as the Java thread can still perform the exit from `try`.

However, failures that prevent the JVM/process from continuing (forced kill, `Runtime.halt`, crash, power loss) are not guaranteed a chance to clean up. The difference here lies in **how the JVM/process terminates**, not that any `Error` subtype “skips finally.”

Try-with-resources also runs when Java code has a chance to exit scope; it does not become a mechanism to prevent data loss from a forced VM shutdown.

## 19. Designing APIs That Do Not Force Callers to Catch `Error` by Mistake

A good API distinguishes:

1. **Errors callers must handle by contract**.
2. **Programming errors or state violations**.
3. **Severe environmental failures** that the application cannot resolve per call.
4. **Expected business outcomes**.

For example, a configuration-reading API might choose:

~~~java
public Configuration read(String path)
        throws ConfigurationLoadException
~~~

This is an illustrative signature. It tells callers a clear checked failure exists: reading configuration can fail.

An API performing a stateful operation might choose unchecked `IllegalStateException` or a specific subtype to signal a violated invariant.

A lookup API that finds no data can return `Optional.empty()` instead of throwing an exception.

There is no need to advertise `throws Throwable` or make callers catch `Error` just to “cover all cases.” The more accurately scoped the API, the easier it is for callers to write valid code.

## 20. Questions to Answer Before Choosing a Superclass

| Question | Direction to Think |
| --- | --- |
| Should callers be required to handle/declare the error at compile time? | Choose checked `Exception` or an appropriate subtype |
| Is the error a state or precondition violation? | `RuntimeException` or an appropriate JDK subclass |
| Is a distinct type needed to differentiate actions? | Custom subtype in the appropriate branch |
| Is this an expected outcome rather than an exception? | Consider `Optional`, enum, record, or result type |
| Are you thinking of using `Throwable` to avoid picking a branch? | Stop and define the exact contract |
| Are you thinking of using `Error` because you dislike `throws`? | Use unchecked `RuntimeException` if the semantics fit |
| Is it truly a special VM/framework mechanism? | Only consider a special branch when you fully understand the consequences |
| Does the low-level cause need to be preserved? | `(String, Throwable)` constructor with `super(message, cause)` |

If you cannot state a concrete benefit of directly extending `Throwable` or `Error`, that is a strong signal they are **inappropriate**.

## 21. Common Misconceptions and Pitfalls

### 21.1. “`Throwable` is the parent of all errors, so extending it directly is more flexible”

It is true that `Throwable` is the root, but extending it directly places the custom type outside `Exception`, makes it checked, and prevents `catch(Exception)` from catching it. That usually **breaks compatibility with expectations** rather than increasing flexibility.

### 21.2. “A severe error must extend `Error`”

False. Business impact severity is not the criterion for branching in the `Throwable` hierarchy. A configuration error that prevents a service from starting can still be a custom `Exception`.

### 21.3. “`Error` is always thrown automatically by the JVM”

No. Code can explicitly `throw new AssertionError(...)`, and can also define `Error` subtypes. The issue lies in semantics and how the system handles it, not syntax.

### 21.4. “`Error` must never be caught”

Do not interpret this as an absolute rule. There are test cases or special system boundaries that catch a specific `Error`. However, **catching every `Error` and continuing business logic as normal is a dangerous practice**.

### 21.5. “`catch(Exception)` catches every `Throwable`”

False. It does not catch `Error` and does not catch other direct subtypes of `Throwable` outside `Exception`.

### 21.6. “`catch(Throwable)` is always better because it is general”

No. It can sweep up errors from which the application cannot safely recover. Use the narrowest handler appropriate for the layer’s responsibility.

### 21.7. “Extending `RuntimeException` means the error will not stop the program”

False. Unchecked exceptions are still thrown, propagate, and can terminate a task abnormally. Unchecked only means `catch`/`throws` is not enforced by checked-exception rules.

### 21.8. “`extends Throwable` is unchecked because `Throwable` is at the top”

False. Subtypes of `Throwable` that do not sit under `RuntimeException` or `Error` are checked.

### 21.9. “`throws Throwable` describes an API better than `throws IOException`”

Usually not. An overly broad signature makes it hard for callers to know which errors are genuinely part of a recoverable contract.

### 21.10. “A custom exception must extend `Exception` directly”

No. It can extend `RuntimeException` or a subclass such as `IllegalStateException`, or an appropriate specialized checked class. What matters is a semantically accurate superclass.

### 21.11. “Just change the superclass to `Error` to avoid adding `throws`”

Wrong direction. If you want unchecked semantics by contract, consider `RuntimeException`. `Error` carries different meaning.

### 21.12. “Having `Error` in the class name puts it in the `Error` branch”

No. Classification depends on `extends`, not the name. Even so, naming a `RuntimeException` subclass `SomethingError` can still be misleading, so choose names that reflect the role.

### 21.13. “Errors inside `finally` only happen with `Exception`”

No. Any `Throwable` can propagate through a `try/finally` construct; `finally` execution rules do not depend on the exception class name.

### 21.14. “Extending `Error` is how to represent a business rejection”

No. A valid rejection decision should be designed with a result/enum if appropriate; if it is an exceptional business error, use an exception in the proper branch.

### 21.15. “Superclass constructors are automatically inherited”

No. When a custom exception needs a message/cause, you must declare the constructors and call the appropriate `super(...)`.

### 21.16. “Wrapping an error with a new message already preserves the cause”

No. Simply copying `cause.getMessage()` does not create a cause link. Pass the original object to the constructor or a valid cause-setting mechanism.

## 22. Self-Check Questions

1. How does `Throwable` differ from `Exception` and `Error` in the inheritance hierarchy?
2. Is `class X extends Throwable` checked or unchecked? Why?
3. Is `class Y extends Error` checked or unchecked?
4. Can `catch (Exception e)` catch `DirectThrowableFailure extends Throwable`?
5. Can `catch (Exception e)` catch `AssertionError`?
6. Why is `throws Throwable` usually too broad a signature for a business API?
7. When should you choose `extends Exception` for a custom error class?
8. When should you choose `extends RuntimeException`?
9. Why should you not choose `extends Error` just to avoid `throws`?
10. Must a very severe configuration failure necessarily be an `Error`?
11. If an order state error has distinct domain meaning, which standard class can you extend?
12. If a user passes a simple invalid argument, is a custom exception always necessary?
13. Can `Optional.empty()` be used for an expected not-found state?
14. Choosing `Error` for a business error can cause which handler to miss it?
15. Does `throw new AssertionError("x")` skip `finally` under normal exception flow?
16. Does a custom checked exception need to be declared in `throws` when propagating to a caller?
17. If a custom unchecked exception is not caught, what can happen?
18. How does `getCause()` help when translating an infrastructure error into a business error?
19. When can a special `catch(Throwable)` reasonably exist?
20. When catching an `Error` at a special boundary, why should you not default to continuing work?
21. Why might a subtype of `IllegalStateException` be more suitable than a direct subtype of `RuntimeException` in some cases?
22. Do two errors that differ in message necessarily require two subclasses?
23. If a library defines `BaseApplicationThrowable extends Throwable` for all errors, what is the compile-time issue?
24. What should a `(String, Throwable)` constructor in a custom exception call?
25. Should business logic be embedded in the exception message for callers to parse?

### Suggested Answers

1. `Throwable` is the root class; `Exception` and `Error` are its two major direct branches.
2. Checked, because it does not sit under `RuntimeException` or `Error`.
3. Unchecked.
4. No.
5. No.
6. It forces callers to consider a very broad group, including types that do not fit the application contract.
7. When callers are expected to catch or declare handleable errors by contract.
8. When using an unchecked exception with proper semantics and not wanting to enforce checked handling at every layer.
9. `Error` has special semantics; choose `RuntimeException` if you genuinely need an unchecked business exception.
10. No; severity does not equate to the `Error` branch.
11. For example, `IllegalStateException`.
12. No; `IllegalArgumentException` may suffice.
13. Yes, if the contract treats it as an expected outcome.
14. For example, a `catch(Exception)` handler.
15. No, `finally` normally still runs if the Java thread exits `try`.
16. Yes, when uncaught and it is a checked exception.
17. It can still propagate outward and cause the task to fail.
18. It preserves the original cause and stack trace.
19. At certain framework/VM boundaries that need to record the failure and handle it under a special policy.
20. Because resources may be exhausted or the system may already be in an unsafe state.
21. Because it preserves the “invalid state” semantics while allowing broader handlers to catch by superclass.
22. No, if callers do not handle them differently and a standard type with a message suffices.
23. The subtypes are still checked yet outside `Exception`; `catch(Exception)` does not cover them.
24. `super(message, cause)` when supported by the superclass.
25. No; use structured error types or error codes.

## 23. Summary

**Extending `Throwable` or `Error` directly is not strictly forbidden, but it is usually the wrong tool for application custom exceptions.** A direct subtype of `Throwable` is checked yet outside the `Exception` branch, which easily surprises callers and handlers. An `Error` subtype is unchecked yet carries special error semantics, not a shortcut to replace `RuntimeException` when avoiding `throws`.

Choose **`Exception` for custom checked exceptions**, **`RuntimeException` or an appropriate specialized subclass for custom unchecked exceptions**, and **built-in exceptions or result types** when they already express enough. A good exception class should help callers understand, distinguish, or handle a situation better — not merely complicate the inheritance tree.