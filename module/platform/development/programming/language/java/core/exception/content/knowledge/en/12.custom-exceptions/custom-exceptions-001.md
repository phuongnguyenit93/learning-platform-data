# When Should You Define a Custom Exception Type in Java?

A **custom exception** is an application-defined class that extends `Exception`, `RuntimeException`, or another appropriate exception class. Its goal is not merely to rename an error: a good exception type must express **a distinct failure meaning**, help the caller handle it properly, protect an abstraction boundary, or carry structured diagnostic data.

For example, an ordering system might distinguish:

- The caller passes an empty `orderId`: this is an **invalid argument**, and the built-in `IllegalArgumentException` can usually be used.
- The order is not yet in a state that allows payment: this may be a **domain invariant/state error** requiring a dedicated `InvalidOrderStateException` if different callers handle it differently.
- The payment gateway cannot be reached: this is an **infrastructure error**; the business layer can wrap `IOException` into `PaymentGatewayUnavailableException` so the public API does not depend on low-level I/O error types.
- A card is declined according to a valid bank decision: many systems should return a **business result** such as `PaymentDecision.DECLINED` instead of throwing an exception, because this can be an expected outcome of the workflow.

**There is no rule that "every error message needs an exception class."** The right question is: *does this error type need a distinct handling contract or information that existing exceptions do not already express clearly?*

This lesson belongs to Java Core – Exception, topic **Custom Exceptions**, focusing on the decision criteria for when you should or should not create a custom exception type; including checked/unchecked, constructor structure, cause, error data, API boundaries, hierarchy design, and a standalone Java 17+ example.

## 1. What Problem Do Custom Exceptions Solve?

Suppose a method in the payment layer throws:

~~~java
throw new RuntimeException("Payment gateway unavailable");
~~~

This is an illustrative Java snippet. The caller receives a generic `RuntimeException`. If it wants to handle payment gateway failures specifically without accidentally catching other programming errors, the caller might have to inspect the message:

~~~java
catch (RuntimeException e) {
    if (e.getMessage().contains("gateway")) {
        // Retry or enqueue for later processing.
    }
}
~~~

This is a **design anti-pattern**, not a recommended approach: `getMessage()` can be `null` (causing a `NullPointerException` when calling `contains`), message text can change due to localization or refactoring, and catching `RuntimeException` broadly easily sweeps up unrelated bugs.

If the payment gateway error has a distinct meaning and the caller needs a dedicated handling branch:

~~~java
public final class PaymentGatewayUnavailableException
        extends RuntimeException {
    public PaymentGatewayUnavailableException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

This is a **standalone Java class**, which can be saved in `PaymentGatewayUnavailableException.java`. The caller can catch by the specific type:

~~~java
catch (PaymentGatewayUnavailableException e) {
    // Payment gateway error handling policy.
}
~~~

An error type carries more stable semantics than message text. When applying a custom type, the application can add fields for an error code, operation identifier, or necessary attributes, as long as it does not expose sensitive information.

**Main benefit:** turning an error into part of the **typed contract** of the API, instead of forcing callers to infer meaning from unstable text strings.

## 2. Five Signals to Consider Creating a Custom Exception

### 2.1. The Caller Needs to Distinguish This Error for Different Handling

If calling layers need different actions for different failure scenarios, a separate exception type is a strong signal.

For example:

| Scenario | Potentially Appropriate Action | Is a Custom Type Needed? |
| --- | --- | --- |
| Order is not in a payable state | Reject operation, report current state | May be useful if part of the domain contract |
| Payment gateway is temporarily unavailable | Bounded retry, alert, or enqueue | May be useful if the caller needs to identify it |
| Negative `age` in a simple function | Fix input argument | Usually use `IllegalArgumentException` |
| Integer parser failure | Handle `NumberFormatException` directly when appropriate | Not necessarily |
| An operation produces an expected `DECLINED` outcome | Return `PaymentDecision` | Usually no exception needed |

If the caller **never handles it differently**, a new type may only increase the class count without bringing any benefit.

### 2.2. There Is an Abstraction Boundary to Protect

A business module should not force every caller to know whether the storage layer uses files, JDBC, or HTTP. Instead of exposing countless infrastructure errors, the module can translate them into a public error type:

~~~java
static Account loadAccount(String accountId)
        throws AccountRepositoryException {
    try {
        return readFromDatabase(accountId);
    } catch (java.sql.SQLException cause) {
        throw new AccountRepositoryException(
                "Unable to load account", cause);
    }
}
~~~

This is **non-standalone illustrative code**, assuming `Account`, `AccountRepositoryException`, and `readFromDatabase` are declared appropriately.

Meaning:

- The caller receives a stable `AccountRepositoryException` contract.
- The module can replace JDBC with another API without forcing callers to understand all implementation details.
- `cause` preserves the original exception for investigation.

However, not every layer needs a new wrapper. If a layer adds neither context nor a handling policy, letting an appropriate error propagate can be clearer.

### 2.3. The Error Carries Structured Data Useful for Handling

When the caller needs to retrieve an error code or domain information in a **type-safe** way, a custom class with dedicated fields is better than parsing a message.

~~~java
public final class OrderConflictException
        extends IllegalStateException {
    private final String orderId;

    public OrderConflictException(String orderId) {
        super("Order is not in a valid state");
        this.orderId = orderId;
    }

    public String getOrderId() {
        return orderId;
    }
}
~~~

This is a standalone Java class if saved in `OrderConflictException.java`. The caller reads `getOrderId()` instead of extracting the order ID from `getMessage()`.

**Privacy note:** do not automatically put the entire order, card details, or user data into the exception. Exceptions may be logged or pass through multiple layers. Only keep fields that are truly necessary and permitted to be stored.

### 2.4. An Error Is Part of a Library's Public Contract

In a library API or a widely used module, a custom exception can clearly express **a set of failures that clients are allowed to rely on**.

API example:

~~~java
public Receipt issueReceipt(String orderId)
        throws ReceiptGenerationException
~~~

This is an **illustrative signature**, not a standalone program. It indicates that the caller needs to account for a group of receipt issuance failures. If that is meaningful to clients, `ReceiptGenerationException` can be part of the versioned contract.

Once an exception type is made public, do not change or remove it arbitrarily: calling code may `catch` that type, configure retries based on it, or map HTTP status codes based on the exception type.

### 2.5. Wanting to Distinguish Abnormal States from Programming Errors

Some errors should be clearly separated from `NullPointerException`, `IndexOutOfBoundsException`, or `IllegalArgumentException` commonly seen in code because their causes and remedies differ.

For example, `LeaseExpiredException` in a temporary access management module can be more meaningful than a generic `IllegalStateException`, if the caller is designed to request a lease renewal.

Even so, be careful: **"having a business name" is not enough**. A small system may work fine with standard exceptions plus clear messages. Only create a type when there is a concrete benefit for the API, branching, or expressiveness.

## 3. When to Use Standard Exceptions Instead of Defining Your Own

The JDK already provides a rich set of meaningful exceptions:

| Built-in Exception | Typically Appropriate Scenario |
| --- | --- |
| `IllegalArgumentException` | Argument value violates a precondition |
| `NullPointerException` | Null reference is not accepted |
| `IllegalStateException` | Current state does not allow the operation |
| `UnsupportedOperationException` | Operation is not implemented/supported |
| `NoSuchElementException` | No element exists per the access contract |
| `NumberFormatException` | String cannot be parsed into a valid number |
| `IOException` | I/O failure |
| `SQLException` | Error per the JDBC API |

If the error is a **common technical precondition violation**, `IllegalArgumentException` or `IllegalStateException` with a clear message is usually sufficient.

For example:

~~~java
static int positive(int value) {
    if (value <= 0) {
        throw new IllegalArgumentException(
                "value must be positive");
    }
    return value;
}
~~~

This is a valid Java method when placed in a class. There is no need for a separate `NotPositiveValueException` if the caller only needs to fix the argument and does not distinguish multiple domain error classes.

### Do Not Create a Custom Exception Just to Change the Message Text

Compare:

~~~java
throw new IllegalArgumentException("quantity must be > 0");
~~~

and:

~~~java
throw new InvalidQuantityException("quantity must be > 0");
~~~

The second snippet assumes a custom class exists. If callers still handle both in the exact same way and do not need extra data, the new class may add no value.

Standard exceptions reduce API size, reduce code to maintain, and leverage the shared knowledge of Java developers.

## 4. Exceptions Are Not the Way to Represent Every Unfavorable Business Outcome

An **unaccepted** result is not always an **abnormal program failure**.

For example, a payment service responds that the card is not accepted. If that is a common outcome of the workflow, an explicit result type can be easier to use:

~~~java
enum PaymentStatus {
    APPROVED, DECLINED
}

record PaymentDecision(PaymentStatus status, String reason) {}
~~~

These are two Java 17+ declarations that can reside in a class. The caller branches on `status` without needing an exception mechanism for an expected outcome.

| Criterion | Return Explicit Result | Throw Exception |
| --- | --- | --- |
| Outcome occurs frequently and is a valid choice | Usually clear | Can feel like an abnormal error |
| Caller must always consider multiple business branches | `enum`/`record`/sealed result fits well | Easy for branches to be missed if unchecked |
| Cannot complete operation due to infrastructure or broken invariant | Error result can be used per API | Exception is usually appropriate |
| Needs to propagate across many layers without immediate handling | Requires passing results through each layer | Exception supports propagation |
| Wants to convey rich user-facing information | Result is usually convenient | Must avoid leaking internal stack traces |

There is no absolute rule for every domain. One API might choose an exception for a missing object; another might choose `Optional.empty()` or a `NOT_FOUND` result. What matters is **contract consistency** and fit with caller behavior.

### Do Not Use Exceptions as Normal Control Flow in Loops

~~~java
try {
    return Integer.parseInt(text);
} catch (NumberFormatException e) {
    return 0;
}
~~~

This is an illustrative snippet. If the requirement is simply "try parsing once," this approach can be reasonable. But if invalid data appears continuously as an expected protocol state, consider a parsing API that returns an explicit status or appropriate format validation instead of abusing exception creation to drive hot loops.

Do not optimize by guesswork: the decision also depends on simplicity, correctness, and actual performance measurements.

## 5. Choosing Checked or Unchecked for a Custom Exception?

Before creating a custom error class, you need to choose **the contract the caller will see**:

| Approach | Compile-Time Obligation | When to Consider |
| --- | --- | --- |
| `extends Exception` (not via `RuntimeException`) | Caller must `catch` or declare `throws` if the checked exception can escape | The API intentionally requires callers to account for a declared failure condition |
| `extends RuntimeException` | Caller is not forced to `catch` or `throws` | State/precondition violation, or the contract intentionally leaves error handling to a boundary |

**Recoverable** does not mean **must be checked**: an unchecked `NumberFormatException` can still be handled by the UI; a checked `IOException` may be unrecoverable. Consider the impact on API signatures, method overriding, and library consumers. Choose the kind based on handling responsibility, not on a subjective feeling of how "severe" the error is.

## 6. Defining Constructors: Message and Cause

A custom exception should preserve a **clear description** and the **root cause** when wrapping an error from another layer. At a minimum, expose the overloads that callers actually need:

~~~java
public final class RepositoryAccessException extends Exception {
    public RepositoryAccessException(String message) {
        super(message);
    }

    public RepositoryAccessException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

This is a standalone class if saved in `RepositoryAccessException.java`. When catching `SQLException` and converting it to `RepositoryAccessException`, use the `(message, ex)` constructor so that `getCause()` retains the exact **original Throwable**. Merely concatenating `ex.getMessage()` into a new sentence loses the cause chain and the stack trace of `ex`.

Java does not automatically inherit constructors from the superclass, so to allow callers to pass `cause`, the subclass must provide the appropriate overload. There is no need to add all four standard constructors just to follow a mechanical template.

## 7. Adding Structured Fields When There Is a Real Need

If callers need to branch on an error code or query an ID, put them in **typed fields** rather than requiring callers to parse `getMessage()`. For example:

~~~java
enum OrderFailureCode { ALREADY_PAID, STOCK_INSUFFICIENT }

final class OrderOperationException extends RuntimeException {
    private final OrderFailureCode code;
    private final String orderId;

    OrderOperationException(OrderFailureCode code, String orderId) {
        super("order operation rejected");
        this.code = java.util.Objects.requireNonNull(code);
        this.orderId = java.util.Objects.requireNonNull(orderId);
    }

    OrderFailureCode code() { return code; }
    String orderId() { return orderId; }
}
~~~

Java 17 declaration example; the types can be placed in appropriate files in the same package. Only add a field if it serves an actual caller decision or investigation. Avoid storing the same ID in multiple fields, storing entire mutable entities, or putting secrets into an exception. Enum codes and IDs can be used for safe classification/logging per policy; the message remains descriptive prose.

## 8. Standalone Java 17+ Example: When to Use a Custom Type and When Not To

The program below intentionally uses **three different ways of representing failure**:

1. Built-in `IllegalArgumentException` for an invalid `orderId`.
2. `InvalidOrderStateException` (unchecked, custom) for a state invariant error with domain meaning and an `orderId` field.
3. `GatewayUnavailableException` (checked, custom) for an infrastructure failure that needs to preserve `IOException` as its cause.
4. `PaymentDecision` as a `record` for a declined card — **a valid business outcome**, without throwing an exception.

Create the file **`CustomExceptionDecisionDemo.java`**:

~~~java
import java.io.IOException;

public class CustomExceptionDecisionDemo {

    record PaymentDecision(boolean approved, String reason) {}

    static final class InvalidOrderStateException
            extends IllegalStateException {
        private final String orderId;

        InvalidOrderStateException(
                String orderId, String message) {
            super(message);
            this.orderId = orderId;
        }

        String orderId() {
            return orderId;
        }
    }

    static final class GatewayUnavailableException
            extends Exception {
        private final String code;

        GatewayUnavailableException(
                String code, String message, Throwable cause) {
            super(message, cause);
            this.code = code;
        }

        String code() {
            return code;
        }
    }

    public static void main(String[] args) {
        show("O-1", true, true, true);
        show("O-2", true, false, true);
        show("O-3", false, true, true);
        show("O-4", true, true, false);

        try {
            charge("", true, true, true);
        } catch (IllegalArgumentException e) {
            System.out.println(
                    "invalid argument: " + e.getMessage());
        } catch (GatewayUnavailableException e) {
            System.out.println("unexpected gateway error");
        }
    }

    static void show(
            String orderId,
            boolean ready,
            boolean approved,
            boolean gatewayOnline) {
        try {
            PaymentDecision decision =
                    charge(orderId, ready, approved, gatewayOnline);

            String status = decision.approved()
                    ? "APPROVED"
                    : "DECLINED";
            System.out.println(
                    orderId + " decision=" + status
                            + " reason=" + decision.reason());
        } catch (InvalidOrderStateException e) {
            System.out.println(
                    orderId + " state-error=" + e.getMessage()
                            + " order=" + e.orderId());
        } catch (GatewayUnavailableException e) {
            System.out.println(
                    orderId + " gateway-error=" + e.code());
            System.out.println(
                    "cause=" + e.getCause().getClass().getSimpleName()
                            + ": " + e.getCause().getMessage());
        }
    }

    static PaymentDecision charge(
            String orderId,
            boolean ready,
            boolean approved,
            boolean gatewayOnline)
            throws GatewayUnavailableException {

        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException(
                    "orderId must not be blank");
        }

        if (!ready) {
            throw new InvalidOrderStateException(
                    orderId, "order is not ready");
        }

        try {
            callGateway(gatewayOnline);
        } catch (IOException cause) {
            throw new GatewayUnavailableException(
                    "GATEWAY_OFFLINE",
                    "payment gateway unavailable",
                    cause);
        }

        if (!approved) {
            return new PaymentDecision(false, "card declined");
        }

        return new PaymentDecision(true, "accepted");
    }

    static void callGateway(boolean online) throws IOException {
        if (!online) {
            throw new IOException("connection refused");
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac CustomExceptionDecisionDemo.java
java CustomExceptionDecisionDemo
~~~

**Exact stdout:**

~~~text
O-1 decision=APPROVED reason=accepted
O-2 decision=DECLINED reason=card declined
O-3 state-error=order is not ready order=O-3
O-4 gateway-error=GATEWAY_OFFLINE
cause=IOException: connection refused
invalid argument: orderId must not be blank
~~~

### Tracing the Success Flow

`show("O-1", true, true, true)` calls `charge` with a valid argument, a ready order, and an online gateway. `callGateway` does not throw; `charge` returns `PaymentDecision(true, "accepted")`. The caller prints `APPROVED`.

### Card Declined: No Custom Exception Created

`show("O-2", true, false, true)` still calls the gateway successfully. The business decision is `DECLINED`, so `charge` returns `PaymentDecision(false, "card declined")`. This is an important example showing that **not every unsuccessful outcome needs an exception**.

If the system has different rules, payment decline can be represented by a richer result type; the goal is to make clear to the caller that this is an **expected** state.

### Invariant Violation: Custom Unchecked Exception

`show("O-3", false, true, true)` encounters an order that is not ready. `charge` throws `InvalidOrderStateException` containing the specific order ID. `show` catches this exact error type and reads `orderId()` without parsing the message.

`InvalidOrderStateException extends IllegalStateException` is a reasonable choice if this error **truly represents a state that does not permit the operation** and multiple handling layers need to recognize it. In a very small application, the built-in `IllegalStateException` may also suffice.

### Infrastructure Error: Custom Checked Exception and Cause

`show("O-4", true, true, false)` causes `callGateway` to throw `IOException("connection refused")`. `charge` catches it and wraps it into `GatewayUnavailableException` containing:

- `code = "GATEWAY_OFFLINE"` as a stable classification code for the caller;
- `message = "payment gateway unavailable"` describing the payment layer operation;
- `cause` as the original `IOException` itself.

Because `GatewayUnavailableException extends Exception`, `charge` declares `throws GatewayUnavailableException`. Callers are forced to handle or propagate that checked exception type per the contract.

### Blank Argument: Standard Exception Suffices

`charge("", ...)` throws `IllegalArgumentException` because `orderId` violates a precondition; the example does not create a separate `BlankOrderIdException`. This is a simple, clear choice that fits when the caller only needs to fix the input data.

**Note:** This program simulates logic; `boolean approved` and `boolean gatewayOnline` are mock inputs, not a real payment protocol. Do not use this example to infer security implementation, idempotency/deduplication, or retry policies for a real payment system.

## 9. Designing a Custom Exception Hierarchy: Start Simple

A base class like `BillingException extends Exception` is useful if callers actually want to `catch (BillingException)` for a whole group of errors. When callers need two different actions, you can create subtypes like `PaymentDeclinedException` and `PaymentProviderUnavailableException`, if they belong to the same family.

However, **do not create a deep tree just to mirror a system diagram**. If all errors are handled the same way, a single exception with a typed reason code may be better than dozens of subtypes. Callers should branch on **the action they can take**, not on the name of an internal driver, HTTP client, or database. Infrastructure details should be preserved via `cause` when crossing abstraction boundaries.

## 10. Checked Exception Design and API Compatibility

A custom checked exception becomes a part with significant impact on calling code:

~~~java
public Receipt generate(String orderId)
        throws ReceiptGenerationException
~~~

This is an illustrative API signature. Callers must choose `try/catch` or declare `throws`. If you add a new checked exception to a public signature, client source code may need to change.

Considerations:

- Does the checked exception **truly** help the caller handle or recover?
- Does it describe an expected kind of failure from the operation or merely a programming error?
- Is it possible to swap the underlying infrastructure while keeping the contract?
- Does catching/declaring it repeatedly across many layers complicate the API?
- Would a `Result`/`Optional`-style outcome be clearer for an expected missing-data state?

Once you create a public API, document **when the exception is thrown, what the caller can do, and whether the exception preserves a cause**. Do not merely publish a type name and leave users guessing.

### `throws` Does Not Mean Every Call Fails

The method:

~~~java
static String readConfig(boolean available)
        throws java.io.IOException {
    if (!available) {
        throw new java.io.IOException("unavailable");
    }
    return "ready";
}
~~~

This is a valid Java method inside a class. `throws IOException` declares the possibility of throwing a checked exception as part of the contract. With `readConfig(true)`, the normal result is `"ready"`.

The same applies when a custom checked exception appears in `throws`: the declaration does not cause the exception to happen; only execution paths that actually throw it terminate abnormally.

## 11. When Using a Custom Unchecked Exception, Can the Caller Ignore It?

With a custom unchecked exception, the compiler does not require callers to write `catch` or `throws`. But that does not turn the error into a harmless event.

~~~java
static void verifyState(boolean ready) {
    if (!ready) {
        throw new InvalidOrderStateException(
                "O-7", "order is not ready");
    }
}
~~~

This is an illustrative method using the nested class from the runnable example; if written outside, it needs proper access to the class. When `ready = false`, the exception is still thrown and can cause a request or task to fail if there is no handler.

There must be an appropriate boundary layer to handle it, such as translating a domain error into HTTP 409 per API policy, reporting a CLI command error, rolling back a transaction, or logging in a controlled manner.

**Do not catch `RuntimeException` or `Exception` broadly just so the application "doesn't crash."** Doing so can hide programming bugs and continue execution in an unreliable state. Only catch at boundaries with specific responsibilities.

## 12. Do Not Classify Retries Solely by Exception Name

A custom error type can assist retry classification, but "network error" does not automatically mean **safe to retry**.

For example, a payment request may have already been processed by the provider, and then the connection drops before the response is received. Blindly retrying can create duplicate transactions.

When designing infrastructure-related exceptions, distinguish:

- Can you determine whether the operation has **not** yet been executed on the service side?
- Is the operation **idempotent**?
- Is there an idempotency key or deduplication mechanism?
- Are there reasonable retry limits, backoff, and timeouts?
- Is there a structured error code or metadata indicating retryability per the contract?

A name like `GatewayUnavailableException` only states **the kind of failure**; it is not enough to confirm that a write operation can be safely retried. If retry policy matters, design it independently or through contract-verified data.

## 13. When Should You Avoid a Hierarchy per Error Code?

A system with dozens of failure codes does not necessarily need dozens of `Exception` classes. You can use one exception type for a semantic group, paired with an error code enum:

~~~java
enum ImportFailureCode {
    INVALID_FORMAT,
    UNSUPPORTED_VERSION,
    SOURCE_UNAVAILABLE
}

final class ImportException extends Exception {
    private final ImportFailureCode code;

    ImportException(
            ImportFailureCode code,
            String message,
            Throwable cause) {
        super(message, cause);
        this.code = code;
    }

    ImportFailureCode code() {
        return code;
    }
}
~~~

These are valid Java 17+ declarations in the same package or an appropriate enclosing class.

This solution can fit well if callers handle the import error group uniformly, while needing detailed error codes for display or logging. Conversely, if a few codes have very different recovery paths and are caught directly in many places, separate subtypes may be clearer.

### Trade-off: Separate Types vs. Error Code Enum?

| Approach | Pros | Trade-offs |
| --- | --- | --- |
| One separate subtype per scenario | Type-based `catch`, clear semantics, easy IDE discovery | Many classes, larger API surface |
| One group exception + enum error code | Fewer classes, stable error code data | Callers may need to `switch` on the code |
| Standard exception + message | Simple, minimal boilerplate | Less machine-readable domain semantics |
| Stateful business result | Clear expected branches and typed data | Must pass result through call layers |

There is no universally optimal choice for every project. Start with a simple structure, and increase the number of types when real contracts and needs emerge.

## 14. Cause and Suppressed Exceptions in Custom Exceptions

A custom exception should not lose the root cause when wrapping an error:

~~~java
catch (java.io.IOException cause) {
    throw new GatewayUnavailableException(
            "GATEWAY_OFFLINE",
            "gateway unavailable",
            cause);
}
~~~

This is an illustrative snippet inside a class with access to `GatewayUnavailableException`. The custom class constructor calls `super(message, cause)`, so `getCause()` returns the original `IOException`.

### Cause vs. Suppressed

- `getCause()`: an exception that is the **direct cause** of the outer error.
- `getSuppressed()`: secondary exceptions that should not replace the primary error, commonly encountered when closing resources in try-with-resources.

For example:

~~~java
Exception main = new Exception(
        "work failed",
        new java.io.IOException("read failed"));

main.addSuppressed(new java.io.IOException("close failed"));
~~~

This is an illustrative snippet. The cause is `"read failed"`, and the suppressed exception is `"close failed"`. They are not consecutive links in `getCause()`.

### Note on Constructors and Subclasses

If a custom exception does not define an overload taking a cause, you can consider `initCause(...)` when the class permits it and the cause has not been initialized yet. For new code, however, it is usually best to **provide a constructor accepting a cause from the start**. Constructors are not inherited automatically.

## 15. Messages, Error Codes, and Sensitive Data

Exceptions often appear in logs, tracing, and operational error reports. Therefore, the data fields of a custom exception must have a clear policy.

Do:

- Write messages that describe **the operation and failure condition**, not just `"error occurred"`.
- Use stable error codes for handling branches; avoid parsing messages.
- Preserve the cause when crossing abstractions to aid investigation.
- Keep only necessary metadata (e.g., non-sensitive internal operation IDs).
- Separate technical messages in logs from user-facing messages.

Avoid:

- Storing passwords, access tokens, full connection strings, or card data.
- Attaching entire request bodies containing sensitive data to an exception.
- Using `getMessage()` as a stable machine-to-machine protocol.
- Returning raw `printStackTrace()` or the entire chain to a public API.

A good exception type must also align with the application's observability and security strategy.

## 16. Do Exception Classes Need `serialVersionUID`?

`Throwable` implements `Serializable`, so a custom exception may trigger IDE warnings regarding `serialVersionUID`. **Not every exception needs a serialization format commitment.** If a system actually persists or exchanges Java-serialized `Throwable` instances across versions, define a UID, ensure class/field compatibility, and test reading old data with new versions; merely adding `serialVersionUID = 1L` does not guarantee compatibility.

For HTTP, message queues, or public APIs, it is usually better to expose an **error DTO with a controlled schema, error code, and context** rather than serializing the entire `Throwable` graph, which can carry causes, suppressed exceptions, and sensitive information.

## 17. Should Everything Inherit from a `BaseApplicationException`?

A common parent class can be useful when a framework or application needs a boundary handler:

~~~java
public class ApplicationException extends RuntimeException {
    public ApplicationException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

But if every error inherits from it, a caller catching `ApplicationException` receives a very broad set of errors with no guarantee of a common recovery strategy. A large hierarchy also easily becomes a dumping ground for unrelated error codes.

**A base exception is only useful if it truly represents a shared contract.** For example, a billing module whose error group shares the same logging or boundary error-mapping mechanism. There is no need to create a base exception for every new project just to follow an OOP template.

If exception types across modules are completely different, using built-in JDK types or small independent groups can be easier to maintain.

## 18. Testing Custom Exceptions

A custom exception should be tested at **two levels**.

### Class Level: Constructors and Metadata

Verify:

- `getMessage()` receives the expected message.
- `getCause()` retains the **exact cause instance** (using `==` or `assertSame` in a test framework).
- Metadata getters such as `code()` or `orderId()` return the right values.
- The checked/unchecked kind matches the inheritance relationship.
- Whether there is any unintended data leakage through the message.

A simple check without a framework:

~~~java
java.io.IOException root =
        new java.io.IOException("unavailable");

GatewayUnavailableException e =
        new GatewayUnavailableException(
                "GATEWAY_OFFLINE", "gateway down", root);

if (e.getCause() != root) {
    throw new AssertionError("cause was lost");
}
if (!"GATEWAY_OFFLINE".equals(e.code())) {
    throw new AssertionError("wrong code");
}
~~~

This is a test snippet that can be placed in the class containing `GatewayUnavailableException` from the full example.

### Behavior Level: Right Scenario Throws the Right Type

For example:

- `charge` with a blank `orderId` must throw `IllegalArgumentException`.
- `charge` with a non-ready state must throw `InvalidOrderStateException`.
- `charge` with an offline gateway must throw `GatewayUnavailableException` and preserve `IOException` as the cause.
- `charge` with a validly declined card must **return `DECLINED`**, not throw an exception.

Testing by type and structured data is better than testing against fragile details like full stack traces, source line numbers, or `printStackTrace()` formatting.

## 19. Common Mistakes

### Mistake 1 — One Exception Type per Message String

Creating many classes that differ only in wording bloats the API without providing any real handling benefit.

### Mistake 2 — Catching `RuntimeException` and Comparing `getMessage()`

Messages are unstable and can be null. Use a specific error type or structured error code if the caller truly needs to branch.

### Mistake 3 — Creating a Custom Exception for Every Bad Input

Simple precondition errors already have `IllegalArgumentException` or `IllegalStateException`. Only create a separate type when there is a clear domain contract.

### Mistake 4 — Using Exceptions for Every Declined Outcome

If a decline is an expected business outcome, an explicit result type may be more appropriate.

### Mistake 5 — Choosing Checked for "Serious" Errors and Unchecked for "Minor" Errors

The checked/unchecked distinction is about compile-time contracts, not a severity scale.

### Mistake 6 — Forgetting to Pass `cause` in the Constructor

`super(message)` does not automatically preserve the cause. Use `super(message, cause)` when wrapping lower-layer exceptions.

### Mistake 7 — Forgetting to Declare `throws` for Custom Checked Exceptions

A class extending `Exception` (not `RuntimeException`) is generally checked. Methods throwing it must catch or declare it; callers must do the same per Java rules.

### Mistake 8 — Creating Deep Inheritance Trees with No Consumers

Overly granular hierarchies increase coupling and maintenance burden. Choose the number of classes that matches actual branching needs.

### Mistake 9 — Leaking Infrastructure into Business Contracts

Returning `SQLException` or `IOException` directly in every high-level API can couple callers to current technology; consider wrapping at module boundaries when helpful.

### Mistake 10 — Wrapping Every Error at Every Layer

Exceptions with long wrapper chains that add no new information make logs hard to read. Only wrap when changing abstraction or adding context.

### Mistake 11 — Assuming the Exception Name Determines Safe Retries

A gateway error can occur after a write request has already been executed. Retries also require idempotency, timeouts, backoff, and provider contracts.

### Mistake 12 — Abusing `catch (Exception)` or `catch (Throwable)`

Catching too broadly can hide programming errors or serious `Error` conditions. Only catch at layers with appropriate responsibility and handling strategies.

### Mistake 13 — Using Messages as Stable Error Codes

Changing message phrasing can break logic. Separate the code or subtype from the message when automated handling is needed.

### Mistake 14 — Adding Sensitive Data Fields to Exceptions

Errors may be logged, printed in stack traces, or sent through monitoring systems; avoid exposing secret information.

### Mistake 15 — Disabling Stack Traces to "Optimize" Without Measuring

Some advanced constructors can suppress stack trace collection or suppressed exceptions, but that trades away diagnosability. Do not make it the default for ordinary custom exceptions.

### Mistake 16 — Thinking All `Exception` Constructors Automatically Pass Down to Subclasses

Constructors **are not inherited**. Any public overload you want must be explicitly defined by the custom exception itself.

## 20. Checklist Before Creating a Custom Exception Type

Ask yourself the following questions:

1. **Is this truly an abnormal state or just an expected outcome?** Should you return an enum/record/result instead of throwing?
2. **Does the JDK already have an exception type that expresses this?** Are `IllegalArgumentException`, `IllegalStateException`, `IOException`, etc. sufficient?
3. **Does the caller need to catch this type separately?** If so, how will it act differently?
4. **Is there an abstraction boundary to protect?** Does the custom type keep the module independent of infrastructure?
5. **Checked or unchecked?** Do the compile-time rules match how clients need to recover?
6. **Is structured metadata needed?** Will a safe error code/status/ID actually be used?
7. **Is the cause preserved?** When wrapping errors, does the constructor call `super(message, cause)`?
8. **Is there a simpler option?** Is one class with an enum code, a standard type, or an explicit result clearer than many subclasses?
9. **Is there a logging/API policy protecting sensitive data?** Messages and causes can contain sensitive information.
10. **Are there tests for type, required message, cause, and metadata?** Rather than checking fragile stack trace strings.

If the answers show that the new error type will **change how callers understand and handle failures**, a custom exception may be a good choice. Otherwise, it is usually better to start with a standard type or result data.

## 21. Self-Check Exercises

1. When is a built-in `IllegalArgumentException` better than creating `InvalidAgeException`?
2. What advantages does a custom exception have over comparing `getMessage()` strings?
3. Must a "card declined" error always throw an exception?
4. Why might an order state error need a subtype of `IllegalStateException`?
5. When should `IOException` be wrapped in a business-layer exception?
6. How does `getCause()` help when creating a wrapper?
7. If you only call `super(message)`, is cause information automatically preserved?
8. If a custom exception extends `Exception` but not `RuntimeException`, what is the checked obligation?
9. Does extending `RuntimeException` mean an exception cannot cause a request to fail?
10. Must a custom exception have a no-arg constructor?
11. If the caller handles 12 error codes identically, is it necessary to create 12 classes?
12. When is an error code enum inside an exception useful?
13. How do error codes and messages differ in stability?
14. Should you extend `Throwable` directly for ordinary business exceptions?
15. Why should you not use `Error` as the parent class for ordinary business errors?
16. Can a custom exception hold an `orderId` field? How should that data be limited?
17. Why is the name `GatewayUnavailableException` not enough to decide to retry a payment command?
18. Does creating a separate subtype for every application layer always make chains easier to understand?
19. When adding a new custom checked exception to a public API, what might clients have to change?
20. Is `serialVersionUID` required for `throw/catch` to work?
21. How do you test that a constructor preserves the exact cause?
22. When should a caller handle a `DECLINED` outcome as a value instead of `catch`?
23. Is `catch (Throwable)` the default choice for handling all custom exceptions?
24. How can a custom exception hide JDBC details when a module migrates to another infrastructure?
25. Name the three most important questions to ask before creating a new exception class.

### Suggested Answers

1. When it is simply an ordinary argument violation with no distinct domain handling branch.
2. Callers branch on a stable type, which is more readable and safer than messages.
3. No; it can be represented with an explicit business result.
4. When it is a domain invariant that needs to be identified and handled separately.
5. When an API boundary needs to change abstraction or add useful context.
6. Preserves the original cause object and its diagnostic information.
7. No; call `super(message, cause)` if you want to preserve the cause.
8. Methods/callers must catch or declare it per checked exception rules.
9. No; unchecked exceptions are still thrown and can propagate to fail the operation.
10. No; only create overloads needed for the contract.
11. No; a group exception paired with an enum code can be clearer.
12. When machines need to classify errors without parsing messages.
13. Codes are for handling contracts; messages are for human readers and can change.
14. Usually no; prefer `Exception`/`RuntimeException` or a meaningful subtype.
15. `Error` is meant for serious environment/VM errors, not everyday business failure contracts.
16. Yes, if needed and safe; avoid overly detailed personal/secret data.
17. Because a call may have already had side effects; retries also require idempotency.
18. No; long chains that add no context can be harder to investigate.
19. They may need to add `catch` or `throws` and corresponding handling policies.
20. No; only consider serialization if the project requires it.
21. Check `getCause() == originalCause` and verify the metadata/message are correct.
22. When a decline is an expected protocol state and the caller needs to handle it as a normal branch.
23. No; catching too broadly can swallow `Error` and unrelated bugs.
24. Callers only know the module's public exception; the cause still retains technical info for logging.
25. Does the error have different semantics/handling? Is a standard type or result already enough? What do callers or API boundaries gain?

## 22. Key Takeaways

**Define a custom exception when you need distinct failure semantics, a typed handling contract, structured error data, or a clear abstraction boundary.** Do not create a new class just to change a message string or for every unfavorable state. Prefer standard exceptions for simple preconditions, explicit results for expected business branches, and custom exceptions when callers genuinely need to distinguish them. Choose **checked or unchecked** based on the API contract, preserve the **cause** when wrapping errors, avoid unnecessary deep hierarchies, and test both data and throw/catch behavior.
