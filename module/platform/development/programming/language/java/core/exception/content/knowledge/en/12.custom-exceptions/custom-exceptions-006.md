# Designing an Exception Hierarchy Around How the Caller Needs to Handle It

> **Java Core – Exception** · Group: **Custom exceptions** · Goal: design an exception hierarchy around the **caller's handling decisions**, not around internal system class names. Main example compatible with **Java 17+**.

## 1. Core Design Philosophy

A useful exception does not just say "what went wrong" — it also helps **the caller know what to do next**.

For example, in a payment/checkout feature, when a transaction fails, the caller may need one of several distinct actions:

- **Ask the customer to fix the input:** missing shipping address information, invalid data.
- **Retry later under a safe policy:** payment service temporarily unresponsive or overloaded.
- **Escalate for manual review:** the transaction requires verification by an administrator.
- **Report a technical error:** the application violated an invariant or has a bug, and should not be treated as a normal error for the customer to fix.

These actions are the basis for choosing **exception branches**. An exception hierarchy should represent differences that are meaningful to the error handler, rather than mirroring every internal technical layer.

**Principle:** *If two errors force the caller to handle them the same way, they probably do not need two different exception classes. If two errors require two different actions and the caller must distinguish them reliably, that is a strong signal to have two separate types or a clearly structured error code.*

### 1.1. Proposed Hierarchy for a Checkout API

~~~text
java.lang.Throwable
└── java.lang.Exception
    └── CheckoutException                  ← checked contract of the API
        ├── CorrectionNeededException      ← customer needs to fix data
        ├── RetryableCheckoutException     ← temporary error, conditional retry handling
        └── ManualReviewException          ← escalate to manual review

java.lang.RuntimeException
└── IllegalStateException                  ← technical error, not an expected Checkout error
~~~

This hierarchy is a **modeling example**, not a standard set of exceptions built into the JDK. The Checkout types will be fully defined in the runnable program in section 5.

The caller can organize handlers based on action:

~~~java
try {
    checkout(request);
} catch (CorrectionNeededException ex) {
    askCustomerToFix(ex);
} catch (RetryableCheckoutException ex) {
    scheduleSafeRetry(ex);
} catch (ManualReviewException ex) {
    sendToReviewQueue(ex);
} catch (CheckoutException ex) {
    reportGenericCheckoutFailure(ex);
}
~~~

This is a **sketch snippet** and cannot run standalone because the variables, types, and handler methods are placeholder names. It illustrates the exact intent: the caller chooses a branch by **handling capability**, without needing to know the package name containing the gateway or the type of network driver.

## 2. Do Not Classify Solely by Technical Error Source

A purely technical classification often looks like this:

~~~text
ServiceException
├── DatabaseException
├── HttpException
├── SocketException
├── JsonException
└── QueueException
~~~

If the caller of the ordering feature has no way to handle a database error differently from a socket error, forcing it to catch each type only couples the business layer to the infrastructure structure. Switching from JDBC to HTTP or replacing a JSON library can **break the exception contract** even though the caller's recovery strategy has not changed.

For example:

| Infrastructure Cause | Meaning to the Caller | Possible Business Error Branch |
| --- | --- | --- |
| Gateway signals temporary overload | Can schedule a retry **if safe** | `RetryableCheckoutException` |
| Timeout before knowing whether the transaction completed | Needs reconciliation/idempotency before retrying | Do not automatically assume every timeout is retryable |
| User submits an address with missing fields | Ask to fix the input | `CorrectionNeededException` |
| Fraud rules require approval | Route to a review queue | `ManualReviewException` |
| An operation on a null object outside the contract | Report a bug/infrastructure issue, do not pretend it was handled as a business case | `NullPointerException` or an appropriate technical error |

**Important:** the same technical exception type can lead to multiple business decisions depending on context. For example, an `IOException` could be a recoverable timeout, a corrupted configuration file requiring operations intervention, or a permission error that should not be retried. Therefore, do not map *every* `IOException` to `RetryableCheckoutException` out of habit. You must determine the **meaning and state of the operation**.

Conversely, two different technologies can cause errors that require the same handling. If in both cases the caller can only ask the customer to re-enter information, they can be grouped into the same business error branch with structured details.

## 3. Start from the Caller's Decision, Not from `extends`

Good design starts with an **action table**:

| Question the Caller Needs to Answer | Action After Catching | Is a Distinct Type Useful? |
| --- | --- | --- |
| Can the customer fix the input? | Show a specific error and allow re-entry | Yes, if distinct from retry/escalate |
| Can the system safely retry? | Schedule a bounded retry with idempotency | Yes, if a dedicated retry branch is needed |
| Is human review needed? | Route to a manual handling workflow | Yes, if handling differs significantly |
| Is this a programming bug? | Log, alert, and stop at the proper boundary | Should be separated from expected errors |
| Do all errors just return the same message? | Use a common handler at the boundary | A single class + error code may suffice |
| Can the caller not recover at all? | Let the error propagate or wrap to add context | No need to create meaningless subtypes |

Implementation process:

1. Write down the **valid reactions** the caller can actually perform.
2. Group scenarios with the same reaction together.
3. Identify which branches need to be distinguished **at compile time** (exception types) and which details are just **data** (codes, IDs, messages).
4. Choose a meaningful base exception as the API's common contract.
5. Choose the appropriate checked/unchecked policy for each layer.
6. Identify where infrastructure exceptions are translated into contract exceptions, preserving the cause.
7. Write a demo caller or test first to verify whether the exception hierarchy actually helps control the logic.

If the caller has to write many `instanceof` checks, parse `getMessage()` strings, or cast repeatedly to decide what to do, the current hierarchy probably does not reflect the action classification well.

## 4. Checked or Unchecked in a Custom Hierarchy?

Java has two basic groups:

- **Checked exception**: extends `Exception` but is **not** under the `RuntimeException` branch. The compiler requires handling it or declaring an appropriate `throws` clause.
- **Unchecked exception**: extends `RuntimeException` or `Error`. The compiler does not require declaring it in the signature.

The example below designs `CheckoutException extends Exception` because the three business scenarios are treated as **expected failure outcomes** for which the API caller should have a policy. The signature:

~~~java
static String checkout(String scenario) throws CheckoutException
~~~

forces callers of the method to handle or declare the checked exception according to Java rules.

This **does not mean every business error must always be checked**. A library may choose unchecked exceptions by API policy, especially if the calling layer cannot recover directly or the framework expects free propagation. When deciding, consider:

- **Can and should** the caller usually react in a useful way?
- Is it reasonable to force every caller to declare/catch this group?
- Would future API changes force source-code callers to make widespread edits?
- Does the system have a boundary layer that uses error information to translate into an HTTP response, retry job, or transaction state?

**Do not use `Error` as a base for business errors.** `Error` belongs to the branch reserved for serious conditions that applications typically do not expect to recover from. You should also not derive custom exceptions directly from `Throwable` without an extraordinary reason: doing so easily creates a group not covered by standard `catch (Exception)` handlers.

## 5. Complete Java 17 Program: Caller Chooses How to Handle

Save the code as **`CallerOrientedExceptionsDemo.java`**. To keep the program runnable in a single file, the exceptions are declared as **public static nested classes**. In a real library, public exceptions are typically placed in separate files to form a clean API.

~~~java
import java.io.IOException;

public class CallerOrientedExceptionsDemo {
    public static abstract class CheckoutException extends Exception {
        private static final long serialVersionUID = 1L;

        protected CheckoutException(String message) {
            super(message);
        }

        protected CheckoutException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static final class CorrectionNeededException
            extends CheckoutException {
        private static final long serialVersionUID = 1L;

        public CorrectionNeededException(String message) {
            super(message);
        }
    }

    public static final class RetryableCheckoutException
            extends CheckoutException {
        private static final long serialVersionUID = 1L;

        public RetryableCheckoutException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static final class ManualReviewException
            extends CheckoutException {
        private static final long serialVersionUID = 1L;

        public ManualReviewException(String message) {
            super(message);
        }
    }

    private static String checkout(String scenario)
            throws CheckoutException {
        switch (scenario) {
            case "invalid":
                throw new CorrectionNeededException(
                        "shipping address missing");
            case "temporary":
                IOException technical =
                        new IOException("gateway timeout");
                throw new RetryableCheckoutException(
                        "payment service temporarily unavailable",
                        technical);
            case "review":
                throw new ManualReviewException(
                        "risk review needed");
            case "unexpected":
                throw new IllegalStateException(
                        "internal invariant broken");
            case "ok":
                return "ORDER-100";
            default:
                throw new CorrectionNeededException(
                        "unknown request");
        }
    }

    private static void caller(String scenario) {
        System.out.println("== " + scenario + " ==");

        try {
            System.out.println("receipt=" + checkout(scenario));
        } catch (CorrectionNeededException ex) {
            System.out.println(
                    "action=ask-customer; reason=" + ex.getMessage());
        } catch (RetryableCheckoutException ex) {
            System.out.println(
                    "action=retry-later; reason=" + ex.getMessage());
            System.out.println("cause="
                    + ex.getCause().getClass().getSimpleName());
        } catch (ManualReviewException ex) {
            System.out.println(
                    "action=manual-review; reason=" + ex.getMessage());
        } catch (CheckoutException ex) {
            System.out.println(
                    "action=generic-checkout-failure; type="
                    + ex.getClass().getSimpleName());
        } catch (RuntimeException ex) {
            System.out.println(
                    "action=technical-alert; type="
                    + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        caller("invalid");
        caller("temporary");
        caller("review");
        caller("ok");
        caller("unexpected");
    }
}
~~~

Run from the directory containing the file, with JDK 17 or newer:

~~~bash
javac --release 17 -encoding UTF-8 CallerOrientedExceptionsDemo.java
java CallerOrientedExceptionsDemo
~~~

**Exact stdout, verified when compiling and running the program:**

~~~text
== invalid ==
action=ask-customer; reason=shipping address missing
== temporary ==
action=retry-later; reason=payment service temporarily unavailable
cause=IOException
== review ==
action=manual-review; reason=risk review needed
== ok ==
receipt=ORDER-100
== unexpected ==
action=technical-alert; type=IllegalStateException
~~~

The program uses deterministic simulated code and does not make real network calls or process real payments. Printing `action=retry-later` **only illustrates the caller's decision** and does not perform an automatic retry.

## 6. Why Does the Exception Hierarchy in the Example Make Sense?

### 6.1. A Checked Base Describing the API Contract

~~~java
public static abstract class CheckoutException extends Exception {
    private static final long serialVersionUID = 1L;

    protected CheckoutException(String message) {
        super(message);
    }

    protected CheckoutException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

The root class `CheckoutException` states that an **expected failure belonging to the checkout process** occurred. It does not specify a concrete action, but allows high-level code to declare a common contract: `throws CheckoutException`.

Making it `abstract` forces service authors to use a subtype (or create an additional subtype when genuinely needed) rather than throwing a vague base error in situations that require differentiation. The `protected` constructors allow subclasses to pass message/cause while preventing arbitrary instantiation from external code when enforcing the classification policy.

**Note:** Not every project needs an abstract base. If a system primarily has one kind of business error, a single concrete exception can be clearer than a hierarchy. Only create a base when it provides real value to caller methods and contract management.

### 6.2. CorrectionNeededException: User Needs to Fix Data

In the `invalid` branch, the service throws:

~~~java
throw new CorrectionNeededException(
        "shipping address missing");
~~~

The caller sees the `CorrectionNeededException` type and performs a specific action: displaying the error to the user / letting them re-enter data. There is no need to catch `IllegalArgumentException` for every failure and guess whether it is a customer input error or a bug in the system.

**Do not return internal messages directly to customers** if they contain private information or system structure. In a real API, the handler should map to a stable error code and curated, potentially internationalized UI text.

### 6.3. RetryableCheckoutException: Retryable Under Policy

In the `temporary` branch, an `IOException("gateway timeout")` is wrapped:

~~~java
throw new RetryableCheckoutException(
        "payment service temporarily unavailable",
        technical);
~~~

The caller catches the retry branch and sees that `getCause()` is `IOException`. This preserves the technical trail without forcing the caller to depend directly on the networking library's exception type.

**Especially important in payments:** "retryable error" does not mean "calling again immediately is safe." A timeout can occur **after the recipient has already recorded the transaction as successful**. Retries must be paired with status checks, an **idempotency key**, attempt limits, backoff, timeouts, and duplicate-charge prevention. If safety cannot be verified, classify it into a state requiring reconciliation/manual handling rather than labeling it retryable by guesswork.

The example only **indicates the caller's intended action** and does not provide a real financial transaction retry algorithm.

### 6.4. ManualReviewException: Human Handling Required

The `review` branch indicates that the transaction cannot be completed automatically yet. The caller can create a ticket or a pending-approval state, rather than treating it as a temporary error for infinite retries or an input error forcing the user to edit fields.

A real API may need a `PENDING_REVIEW` status as a **business result** instead of an exception, especially if waiting for review is part of the normal workflow. Use an exception when it is genuinely an **abnormal exit path** under the contract, not just to store every state in a `Throwable` class.

### 6.5. IllegalStateException: Error Outside the Expected Business Group

In the `unexpected` branch, the code intentionally creates an `IllegalStateException` to represent a broken internal invariant. It does not extend `CheckoutException`, and the sample caller catches it at the boundary with `catch (RuntimeException)` to print a **technical alert**.

This is a simulated structure for observability purposes. **Do not catch every `RuntimeException` and blindly continue business logic** as if recovery had occurred. In a real application, the boundary may log, return a server error, stop the job, or escalate the incident to operations. Logic bugs such as `NullPointerException` or `IndexOutOfBoundsException` should not be wrapped into "customer entered invalid data" just to hit a common handler.

## 7. Catch Ordering and Subtype Contracts

When both subtypes and the base appear in one structure:

~~~java
try {
    checkout("temporary");
} catch (CorrectionNeededException ex) {
    handleCorrection(ex);
} catch (RetryableCheckoutException ex) {
    handleRetryable(ex);
} catch (ManualReviewException ex) {
    handleReview(ex);
} catch (CheckoutException ex) {
    handleOtherCheckout(ex);
}
~~~

This is an **illustrative snippet**; the handler methods would need to be defined. Ordering **subtypes before the base** is mandatory to prevent the base catch from shadowing the specific catches. If `catch (CheckoutException)` is placed first, the subsequent child branches become **unreachable** and the compiler rejects the code.

The three sibling subtypes in the example do not inherit from one another, so the order **among those three subtypes** is not constrained by superclass/subclass relationships. They can be ordered in whatever way makes the handling flow clearest to readers.

### Why Keep a Base Catch at the End?

In the main program, `catch (CheckoutException ex)` is a **fallback branch** to handle another subtype that may be added later, or a path originating from a method with a general signature.

If the library releases a new subtype, older callers catching the base at the end still have a fallback policy. However, the fallback must also be **safe**: do not silently treat an unknown subtype as "retryable." Printing `generic-checkout-failure` demonstrates a conservative stance: report a generic error or escalate, rather than guessing a specific action.

**Warning:** catching the base too early defeats the purpose of the hierarchy. Having a base for API evolution is different from having every layer catch the base and ignore classification.

## 8. How Many Levels Should an Exception Hierarchy Have?

A deep tree may look "architectural" but becomes hard to read:

~~~text
ApplicationException
  └─ DomainException
      └─ CommerceException
          └─ CheckoutException
              └─ PaymentException
                  └─ GatewayException
                      └─ TimeoutException
~~~

If the caller has no policy at each level, most of those layers are cognitive and maintenance overhead. Nested catches for many generic types sometimes make code hard to follow and class names fail to convey actions.

A **shallow, action-clear** hierarchy is usually easier to use. You can apply these critical questions:

- Does the caller **actually catch** this intermediate type?
- If the intermediate level is removed, is any meaningful handling policy lost?
- Do two existing subtypes differ in **behavior** or only in message/cause?
- If a technical library change occurs, will custom names and hierarchy force callers to change?
- If a new subtype is released, do existing callers have a safe fallback?

Not every new scenario needs a subtype. If two failures both require the user to fix input, you can use the same `CorrectionNeededException` and add a structured reason code.

## 9. Use Structured Error Codes Instead of Creating a Class for Every Detail

Suppose a group of errors requiring data correction has multiple reasons: missing address, missing phone number, invalid postal code. If all reasons lead to one common action, creating three new exception classes may be unnecessary.

One way to model this:

~~~java
enum CorrectionCode {
    ADDRESS_MISSING,
    PHONE_MISSING,
    POSTAL_CODE_INVALID
}

final class CorrectionNeededException extends Exception {
    private final CorrectionCode code;

    CorrectionNeededException(CorrectionCode code, String message) {
        super(message);
        this.code = code;
    }

    CorrectionCode code() {
        return code;
    }
}
~~~

The snippet above contains **valid Java type declarations to illustrate the design**, without a `main` program. The caller can catch a single `CorrectionNeededException` type, handle the general flow of letting the user fix data, and map `code()` to the appropriate UI field.

However, **if error codes start driving completely different control flows**, an overly broad enum merely shifts the burden from catch blocks into a complex `switch`. In that case, consider using subtypes or a different business result model.

**Do not classify errors by comparing `getMessage()`**: messages are for human readers/logs and can change due to translation or wording edits. Class types, enum codes, and clear API contracts are far more reliable.

## 10. Preserve the Cause When Translating Infrastructure Errors to Business Errors

Custom exceptions often sit at **layer boundaries**. The technical layer may throw `IOException`, `SQLException`, or an HTTP client exception; the service layer translates it into an exception carrying contract meaning.

Pattern:

~~~java
try {
    gatewayCall();
} catch (IOException ex) {
    if (knownTransientCondition(ex)) {
        throw new RetryableCheckoutException(
                "Gateway temporarily unavailable", ex);
    }
    throw new IllegalStateException(
            "Gateway failure needs investigation", ex);
}
~~~

This is **illustrative code**; `gatewayCall()` and `knownTransientCondition()` are not defined. What matters is not always picking the exact two types shown above, but **only labeling as retryable after valid classification** and **preserving the cause** via a constructor taking `Throwable`.

Common mistakes:

- Catching every `Exception` and throwing `new CheckoutException("failed")`, losing the original error type and recovery options.
- Catching `IOException` and marking it retryable without knowing whether the request may have already been executed by the external system.
- Copying only the message into the new exception, dropping the `cause` and original stack trace.
- Exposing infrastructure exceptions as public API even though callers should not depend on that library.

When logging, a good logger records the **exception object**, including its cause and suppressed exceptions, not just the message. Be careful with private information in messages.

## 11. Designing Constructors and Error Information

Custom exceptions should consider providing appropriate constructors to store the message and cause. Base example from the main program:

~~~java
protected CheckoutException(String message) {
    super(message);
}

protected CheckoutException(String message, Throwable cause) {
    super(message, cause);
}
~~~

The actual constructors reside inside the `CheckoutException` class. A subclass can expose only the initialization forms that match its semantics; it is not mandatory to copy all four constructor overloads from `Exception` just for "completeness."

Additional information that can be useful:

| Data | How to Store It? | Notes |
| --- | --- | --- |
| Action type to perform | Subtype or result structure | Must be stable and meaningful to callers |
| Structured reason code | Contracted enum/string code | Do not use message as a code |
| Diagnostic message | `getMessage()` | Do not expose tokens, passwords, or sensitive data |
| Root error | `cause` | Keep the chain for debugging |
| Transaction/operation identifier | Typed field or external context | Do not expose unconditionally |
| Expected retry timing | Retry policy or standardized field | Does not guarantee every transient error is safe to retry |
| Secondary cleanup error | `getSuppressed()` | Do not conflate with cause |

If an exception class is a public API that may be serialized, consider cross-version compatibility. The exceptions in the main program declare `serialVersionUID` because `Throwable` implements `Serializable`; this field does not make exceptions safer, nor does it replace a versioning/serialization policy.

## 12. Checked Exceptions Cannot Automatically Catch RuntimeExceptions

In the main program, `checkout(String)` declares:

~~~java
private static String checkout(String scenario)
        throws CheckoutException
~~~

The method can still throw `IllegalStateException` because it is an unchecked exception. The caller catches each `CheckoutException` subtype, followed by a `RuntimeException` handler at the boundary layer to log an alert.

**Do not assume that because a method declares `throws CheckoutException`, every runtime failure must be a subtype of `CheckoutException`.** The compiler only enforces `throws` rules for checked exceptions; unchecked exceptions can arise from internal code regardless of the signature.

You should also avoid writing all business logic like this:

~~~java
try {
    doSomething();
} catch (Exception ex) {
    System.out.println("Handled");
}
~~~

This is an illustrative snippet missing the definition of `doSomething()`. It catches a wide range of exceptions under `Exception`, including `RuntimeException` caused by bugs, and turns all of them into a generic message. In many systems, this "swallows" errors and lets the program continue in an inconsistent state. A broad handler should only exist at a boundary with a clear response, logging, and stop/recovery policy.

## 13. Evolution Contract of a Public Library

An exception hierarchy can be part of a **public API**. Once real callers exist, changing the hierarchy is no longer just renaming a class.

### 13.1. Adding a New Subtype

Suppose a release adds `VerificationPendingException extends CheckoutException`. An existing caller with the three specific catches **and** a trailing base catch still handles it via the general fallback. A caller trying to list every subtype exhaustively without a fallback may need adjustments depending on signatures and code structure.

Do not let a new subtype silently default to being retried if it does not yet have a clear policy. Choose a conservative fallback at the boundary, while emitting metrics/logs so the development team can add handling when needed.

### 13.2. Changing Checked to Unchecked or Vice Versa

Changing `extends Exception` to `extends RuntimeException` can alter both compiler `throws`/catch requirements and the contract's meaning for callers. Changing the other way can break compilation at many call sites. Treat this as a **major API change**, not a cosmetic inheritance tweak.

### 13.3. Changing an Exception's Parent/Child Relationship

If a subtype currently handled by `catch (RetryableCheckoutException)` is later moved to another group, caller behavior changes even though the exception class keeps its name. Runtime handlers depend on the inheritance tree.

Therefore, organizing classes around **stable caller actions** has greater long-term value than tying them tightly to infrastructure that changes frequently.

### 13.4. Do Not Promise a Closed Class Set When Not Guaranteed

The subtypes are marked `final` in the sample program so arbitrary sub-branches are not created beneath each action. However, the base `CheckoutException` still allows adding subtypes in the future. Therefore, **do not** assume the current hierarchy has only three cases forever.

Java 17 provides sealed classes to restrict the subtype set when a closed, controlled classification is needed, but that is a separate design decision: a sealed hierarchy can fit when an API wants exhaustive modeling, whereas systems needing plugin/exception extensibility may not want to close the tree. Do not choose `sealed` merely because Java 17 supports it.

## 14. Testing the Hierarchy by Caller Behavior

A good test does not only verify "an exception was thrown," it also verifies **the caller chooses the right reaction**.

For the main example:

| Scenario | Exception or Return Value | Caller Action |
| --- | --- | --- |
| `invalid` | `CorrectionNeededException` | Ask to fix data |
| `temporary` | `RetryableCheckoutException` with cause `IOException` | Mark for later retry handling, do not retry blindly |
| `review` | `ManualReviewException` | Route to manual review |
| `ok` | `ORDER-100` | Handle success |
| `unexpected` | `IllegalStateException` | Technical alert at boundary |

Practical tests should check:

1. **Right exception type** when a scenario is classified.
2. **Whether the cause is preserved** when translating from infrastructure to business contract.
3. **Whether the caller's action** is right, avoiding bugs that turn input-correction errors into retries.
4. **Whether the fallback is safe** when encountering an unknown subtype.
5. **Not swallowing `RuntimeException`** and not returning a false success result.
6. **Not relying on the message** to choose branches; messages can change.
7. **Retry policy has idempotency/bounded retries** and does not duplicate operations with side effects.
8. **Technical errors have appropriate logs/metrics** without leaking sensitive data.

In the console program, verifying stdout per scenario demonstrates the catch mechanism and the meaning of the hierarchy. When moving into a project, you can use JUnit 5 (if already present) to write separate tests for the service and caller; there is no need to add a framework just to explain Java rules.

## 15. Comparing Design Options

| Option | When Appropriate | Risks |
| --- | --- | --- |
| Single `CheckoutException` class | All callers handle errors uniformly | No direct action differentiation by type |
| Base + action-based subtypes | Callers need to fix, retry, or review in distinct branches | Can lead to too many classes if overused |
| Single exception + reason enum | Same action but multiple detailed causes | Enum can turn into a complex `switch` |
| Technology-based exceptions (DB/HTTP/JSON) | Caller is actually the infrastructure layer and knows specific recovery | Leaks implementation details into the business layer |
| Custom unchecked exception | API policy does not force callers to catch every error | Callers may overlook expected errors |
| Result type like `Result/Status` instead of exceptions | Failure/pending is a common, normal state | Requires designing a result type and explicit handling |
| Wrapper exception + cause | Crossing layers to add context while preserving the original error | Can be overused with multi-layer wrapping and verbose logs |

**Decision criterion:** A sound model is not the one with the most subtypes, but the one that lets callers write **correct, easy-to-understand, low-coupling, and safe handling flows**.

## 16. Common Design Mistakes

1. **Creating a class for every error message.** If the recovery action does not change, use the same class with a structured reason code.
2. **Creating classes per driver/protocol name.** Easily breaks the contract when swapping technical libraries.
3. **Having every exception extend a very broad base and catching the base at every layer.** Destroys action classification.
4. **Using checked exceptions for every bug.** Forces developers to handle issues that cannot be reasonably recovered from.
5. **Using unchecked exceptions to hide expected failures without a policy.** Callers may unexpectedly lose the chance to handle them.
6. **Labeling every timeout as retryable.** Very dangerous for operations with side effects without idempotency and reconciliation.
7. **Constantly changing the hierarchy based on implementation.** Breaks existing callers even when functionality has not changed.
8. **Not preserving the cause.** Makes tracing the root error in logs difficult.
9. **Comparing messages by string.** Display language and wording should not control program flow.
10. **Showing infrastructure messages directly to users.** Easily leaks system structure or sensitive data.
11. **Creating an overly deep inheritance tree.** Causes maintenance overhead when no handler uses the intermediate layers.
12. **Using an exception for a normal business state.** For example, pending approval is often a valid state that can be modeled as a result.
13. **Wrapping all `RuntimeException`s into user-input errors.** Hides programming bugs.
14. **Not testing the fallback handler.** New types that appear may be handled with an unsafe action.
15. **Assuming that having a cause means the caller should catch the cause type.** Callers should use the current layer's contract exception; the cause is primarily for diagnostics or a clearly designed handling strategy.
16. **Calling something retryable without putting a retry policy in the system.** Exception classification is only part of the workflow; retries must be bounded and controlled.

## 17. Self-Check Questions

**Question 1.** Why are `PaymentHttpException` and `PaymentDatabaseException` not necessarily two good branches in a Checkout API?

*Answer:* If the caller handles both errors the same way and does not need to know the internal technology, this split exposes infrastructure details. Group by actual handling policy where appropriate.

**Question 2.** How can the three decisions "fix data," "conditional retry," and "manual review" be represented?

*Answer:* You can create distinct meaningful subtypes under a `CheckoutException` base, or model them with structured codes/statuses when appropriate. What matters is that the caller can distinguish the right action.

**Question 3.** If `CorrectionNeededException extends CheckoutException`, which catch must come first when both are present?

*Answer:* `catch (CorrectionNeededException)` must come before `catch (CheckoutException)`. Placing the base first shadows the subtype and causes a compile error.

**Question 4.** Is an `IOException` when calling a payment gateway always an error that should be retried?

*Answer:* No. You must classify the actual state, evaluate idempotency, and assess the possibility that the transaction was already executed before the timeout.

**Question 5.** Why is the `RetryableCheckoutException(String, Throwable)` constructor useful?

*Answer:* It allows preserving the infrastructure cause when throwing a stable business exception, helping the caller handle it by contract while still keeping technical traces for debugging.

**Question 6.** Can a method declaring `throws CheckoutException` throw `NullPointerException`?

*Answer:* Yes. `NullPointerException` is unchecked and does not have to be listed in `throws`.

**Question 7.** If two invalid data fields both require the customer to re-enter input, is it mandatory to create two exception subclasses?

*Answer:* No. You can use the same "correction needed" action class and a detailed enum/code, if that forms a stable, easy-to-use contract.

**Question 8.** Should adding a `VerificationPendingException` subtype default to being retried in the base catch?

*Answer:* No. The fallback must be conservative: record the unclassified error, return a general status, or escalate under a safe policy.

**Question 9.** If "pending review" is a frequent state rather than an abnormal error, what should you consider?

*Answer:* Use a status/result object or a result type with explicit branches, rather than throwing an exception by default to represent a normal state.

**Question 10.** How can you tell when an exception hierarchy is becoming too deep?

*Answer:* Check whether each level is actually caught by callers to decide real actions. If multiple levels have no distinct handling policy, simplify the tree.

## 18. References

- [Java SE 17 JLS – Exceptions, Chapter 11](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html): distinguishing checked and unchecked, exception analysis, and declaration requirements.
- [Java SE 17 JLS – try/catch, Section 14.20](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20): rules for selecting matching catch blocks and handler ordering.
- [Java SE 17 JLS – throw, Section 14.18](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.18): expression requirements and `Throwable` throwing semantics.
- [Java SE 17 API – Exception](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Exception.html): common checked root class.
- [Java SE 17 API – RuntimeException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/RuntimeException.html): unchecked branch for many errors not required to be declared.
- [Java SE 17 API – Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): cause, message, stack trace, and suppressed exceptions.
- [Java SE 17 API – IllegalStateException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/IllegalStateException.html): an example unchecked exception representing invalid application state.

**In summary:** Design the hierarchy **from the caller's side**: do they need to fix data, retry under control, escalate to a human, or report a technical error? Give each branch a **stable action contract**, rather than creating classes for every infrastructure detail. Preserve the cause, place specific catches before the base catch, choose checked/unchecked intentionally, and keep the fallback safe as the API evolves.
