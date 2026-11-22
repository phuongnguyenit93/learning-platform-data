# Throwing Exceptions with Appropriate Messages and Context in Java

The `throw` statement signals that an operation **cannot continue as promised by its contract**. However, simply throwing the right exception type is not enough: if the message is too generic and lacks information about the operation and cause, log readers or API callers will have a hard time figuring out what needs to be fixed.

For example:

```java
throw new IllegalArgumentException("Invalid");
```

The reader only knows "invalid", without knowing **which parameter**, **which rule**, or **which operation was being performed**. A better message is:

```java
throw new IllegalArgumentException(
        "field=quantity: must be a positive integer");
```

These are **illustrative statements**, not a standalone program. For invalid input data, the second statement tells the handler the field name and the violated condition without exposing the input value.

The overarching principle: **choose an exception type that matches the nature of the failure; write an actionable failure message; add necessary context at the layer that has enough information; preserve the root cause when translating exceptions; restrict sensitive data**.

## 1. What does `throw` do and what role does the message play?

In Java, `throw` is a statement that throws a value of type `Throwable` or a subclass; in practice, we usually throw a specific `Exception` or `RuntimeException` object:

```java
static int requirePositive(int value) {
    if (value <= 0) {
        throw new IllegalArgumentException(
                "value must be greater than zero");
    }
    return value;
}
```

This is an **illustrative method** that needs to be placed inside a Java class to compile. When `value <= 0`:

1. An `IllegalArgumentException` object is created with the message `"value must be greater than zero"`.
2. `throw` causes the method to complete abruptly at this statement; `return` is not executed.
3. The JVM searches for a matching `catch` in the active call stack.
4. If the caller catches the exception, `ex.getMessage()` provides the message; `ex.getClass()` provides the type for classification.

**The message is not the exception type.** A string containing `"IOException"` inside an `IllegalArgumentException` does not turn that exception into an `IOException`. Handlers are selected by the actual runtime type of the object and inheritance hierarchy, not by the string content.

Distinguish the three components:

| Component | Meaning | Example |
| --- | --- | --- |
| Exception type | Category of failure and which `catch` branch can handle it | `IllegalArgumentException` |
| Message (`message`) | Brief description of the failed condition or operation | `"field=quantity: must be positive"` |
| Cause (`cause`) | Link to the original exception when an error is translated or enriched with context | `NumberFormatException` inside `IllegalArgumentException` |

In addition, a `Throwable` object usually carries a stack trace and may contain *suppressed* exceptions during resource cleanup. An error may have a **good message but a lost cause**, or a complete cause but a message lacking context; these two issues need to be addressed separately.

## 2. What questions should a good message answer?

A useful message typically helps identify:

- **What failed?** For example: parsing the `quantity` field, loading configuration, creating an order.
- **What condition was not met?** For example: must be a positive integer, a required file does not exist, the current state does not allow the transition.
- **What context helps identify the specific failure?** For example: a non-sensitive internal task ID, operation name, field name, configuration name.
- **What action can the recipient take?** For example: fix the input field, add the configuration, check the connection. Not every exception needs to include instructions for the end user.

Comparison examples:

| Vague message | More useful message | Reason |
| --- | --- | --- |
| `"Error"` | `"field=port: must be between 1 and 65535"` | States the field and condition |
| `"Bad input"` | `"field=quantity: expected a positive integer"` | Indicates the data rule |
| `"Cannot continue"` | `"order transition rejected: expected status DRAFT"` | States the expected status |
| `"Failed"` | `"configuration loading failed: resource=app-settings"` | States the operation and a safe resource identifier |
| `"null"` | `"required dependency 'paymentGateway' was not configured"` | Points out the missing dependency |

The examples above only illustrate message structure; field names, bounds, and statuses must reflect the application's **actual contract**. Do not invent a "1–65535" rule if the application uses a smaller set of ports, or state "does not exist" when the API only reports "cannot read".

### Describe *observed facts*

If `Files.readString(path)` throws `IOException`, the cause is not necessarily that the file does not exist. It could be missing permissions, a device error, or another I/O failure. Therefore, the message `"failed to read configuration"` is more accurate than `"file does not exist"` unless `NoSuchFileException` has been specifically identified.

Similarly, `NumberFormatException` indicates that the string could not be interpreted according to the required numeric syntax; `Integer.parseInt` can also throw it when the number exceeds the `int` range. The message `"must fit into a signed 32-bit integer"` should only be used when the contract requires that constraint.

### Use consistent, concise wording

The message should be short enough to read in logs and specific enough to analyze. You can consistently follow a pattern such as:

```text
operation=<operation>, field=<field>: <violated condition>
```

or write a clear natural sentence. The pattern is only a suggestion; Java does not enforce a `message` format. What matters more is **not changing the meaning of the error across layers**.

## 3. Throw where the error occurs; add information at the layer that has it

A function that parses a string into a number knows the data must be a positive integer; it **does not inherently know** which order the string is being used for. The business layer calling the function knows the order ID and field name. Separating responsibilities avoids passing too many parameters just to build error messages.

```text
submitOrder(orderId, rawQuantity)
  └── parseQuantity(rawQuantity)
       ├── knows the rule "data is required"
       ├── knows the rule "must be an integer"
       └── knows the rule "must be greater than 0"
  └── knows this is the quantity field of orderId
       └── adds context and preserves cause when translating the error
```

As a result:

- The lower layer throws an error describing the **violated rule**.
- The calling layer adds the **operational context** that it reliably knows.
- The presentation layer can translate the error into a user-friendly response; the logging layer can record diagnostic details according to policy.

It is not always necessary to wrap exceptions at every layer. If an exception is already clear enough and the caller has no useful information to add, letting it propagate is simpler.

## 4. Complete Java 17+ example: message, context, and cause

The program below simulates processing an order quantity without needing external files or services. The order ID in the example is a **mock identifier considered safe to include in messages**. In real applications, the sensitivity of each identifier must be evaluated.

Save as **`ThrowWithContextDemo.java`**:

```java
public class ThrowWithContextDemo {

    static final class OrderValidationException extends RuntimeException {
        OrderValidationException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static int parseQuantity(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException(
                    "quantity is required");
        }

        final int quantity;
        try {
            quantity = Integer.parseInt(raw);
        } catch (NumberFormatException cause) {
            throw new IllegalArgumentException(
                    "quantity must be an integer", cause);
        }

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }
        return quantity;
    }

    static void submitOrder(String orderId, String rawQuantity) {
        try {
            int quantity = parseQuantity(rawQuantity);
            System.out.println(
                    "OK order=" + orderId + ", quantity=" + quantity);
        } catch (IllegalArgumentException cause) {
            throw new OrderValidationException(
                    "order=" + orderId
                    + ", field=quantity: " + cause.getMessage(),
                    cause);
        }
    }

    static void runCase(String orderId, String rawQuantity) {
        try {
            submitOrder(orderId, rawQuantity);
        } catch (OrderValidationException ex) {
            System.out.println("ERROR " + ex.getMessage());

            Throwable root = ex;
            while (root.getCause() != null) {
                root = root.getCause();
            }
            System.out.println(
                    "ROOT " + root.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        runCase("A-1", "2");
        runCase("A-2", "abc");
        runCase("A-3", "0");
        runCase("A-4", null);
    }
}
```

Run with JDK 17 or newer:

```bash
javac -encoding UTF-8 ThrowWithContextDemo.java
java ThrowWithContextDemo
```

**Exact stdout**:

```text
OK order=A-1, quantity=2
ERROR order=A-2, field=quantity: quantity must be an integer
ROOT NumberFormatException
ERROR order=A-3, field=quantity: quantity must be positive
ROOT IllegalArgumentException
ERROR order=A-4, field=quantity: quantity is required
ROOT IllegalArgumentException
```

### Analysis of the three failure cases

**String `"abc"`:** `Integer.parseInt("abc")` throws `NumberFormatException`. `parseQuantity` catches that error and throws `IllegalArgumentException("quantity must be an integer", cause)`. `submitOrder` adds the context `order=A-2, field=quantity` using `OrderValidationException`, while preserving the entire cause chain. Outer layers can inspect the business-level message or follow `getCause()` for deeper analysis.

**String `"0"`:** numeric parsing succeeds, but `quantity <= 0` violates the contract. There is no `NumberFormatException`; the root error is `IllegalArgumentException` for a business rule. The message states "must be positive". Thus, relying solely on the root type `IllegalArgumentException` is not enough to distinguish every rule; the message and/or structured error attributes can provide additional semantics.

**`null`:** the condition `raw == null || raw.isBlank()` uses **short-circuit evaluation**, so when `raw == null`, `raw.isBlank()` is not called and no `NullPointerException` is thrown. The message clearly states the field is required. This is the contract choice of this example; another API might prefer `NullPointerException` for a required non-`null` parameter.

### Points to note when wrapping errors

`submitOrder` is responsible for adding the order identifier and field name, so it has a reason to wrap the error. In a large API, you generally should not create a new wrapper in *every* method, because an overly long `Caused by` chain can make diagnostics noisy.

The example also **does not print `rawQuantity` when data is invalid**. In real code, the input string may contain information that should not enter logs. If you need to identify a specific processing attempt, use an allowed request/task ID instead of putting the entire user input into the message.

## 5. How to preserve `cause` when using `throw new ...`

A method that catches a low-level error may want to translate it into an exception type suitable for the upper layer's contract.

### Approach that loses information

```java
try {
    readConfiguration();
} catch (java.io.IOException ex) {
    throw new IllegalStateException("Cannot initialize service");
}
```

This is **illustrative code inside a method**, assuming `readConfiguration()` is defined and can throw `IOException`. This code creates a new error but **does not preserve the `cause` link** to the caught `IOException`. When investigating the failure, the root cause may be lost from the exception chain.

### Approach that preserves the cause

```java
try {
    readConfiguration();
} catch (java.io.IOException cause) {
    throw new IllegalStateException(
            "Cannot initialize service: configuration loading failed",
            cause);
}
```

The `(String message, Throwable cause)` constructor of `IllegalStateException` allows creating an application-layer message while preserving `cause`. The caller can read:

```java
Throwable rootCause = failure.getCause();
```

This statement is illustrative only; `failure` must be an actual exception variable, and `getCause()` may return `null`. To follow the entire cause chain, you must traverse until there is no further cause; if an API receives untrusted data or custom exceptions, diagnostic code should also guard against abnormal cause chains.

**Each layer should have clear responsibility for an error:** the file-reading layer reports that the I/O operation failed; the application initialization layer can add "cannot initialize service"; the outer layer decides how to respond or shut down the application. Multiple consecutive wrappers all with the message `"failed"` do not improve diagnostics.

### Should checked exceptions always be converted to unchecked?

No. If the caller can recover from a configuration/file reading error, having the method declare `throws IOException` and propagate `IOException` may be more appropriate. Wrapping into `IllegalStateException` should only be done when the current layer genuinely treats missing configuration as a **system state unable to fulfill its contract**.

Checked exceptions must be handled or declared according to Java's rules; `throw new IOException(...)` from a method that neither declares nor catches the checked exception causes a compile-time error (except in special cases permitted by the language). `IllegalArgumentException` and `IllegalStateException` are unchecked exceptions, so declaring `throws` is not required.

## 6. Message and context: what goes where?

Not all context needs to live inside a single message string. As a system grows, information with different purposes should be separated:

| Type of information | Appropriate place | Example |
| --- | --- | --- |
| Actionable reason | Exception message | `"field=age: must be non-negative"` |
| Error category for programmatic branching | Exception type or structured code/attribute | `InvalidOrderException`, `ErrorCode.INVALID_QUANTITY` |
| Underlying error from another library | `Throwable cause` | `NumberFormatException`, `IOException` |
| Safe operational identifiers | Structured logs or request-scoped context | Internal task ID, correlation ID |
| Stack trace | The `Throwable` itself and the logging system | Creation/throw site call stack |
| End-user message | UI or API layer | `"Quantity must be greater than 0."` |

For example, an exception has the message `"Cannot finalize order: status must be PAID"`; the API layer can display a user-friendly Vietnamese message; the logging layer records the exception type, timestamp, operation name, request ID, and cause chain. You should not default to returning `ex.getMessage()` verbatim as the HTTP response body to clients.

### When programmatic handling is needed, create typed data fields

Do not rely on:

```java
if (ex.getMessage().contains("quantity")) {
    // Map to a data error code.
}
```

This is an illustrative snippet, not reliable classification logic. The message wording or language can change, and `getMessage()` can be `null`. If callers need to distinguish errors reliably, use a **specific exception type**, an **error code**, or a **dedicated attribute**.

Example of a custom exception (a class to be saved as `ValidationException.java`):

```java
public final class ValidationException
        extends IllegalArgumentException {

    private final String field;

    public ValidationException(
            String field, String message, Throwable cause) {
        super(message, cause);
        this.field = field;
    }

    public String getField() {
        return field;
    }
}
```

When catching the error, code can call `ex.getField()` instead of parsing strings. The field name is a **structured data value**. If a stable API error code is needed, you can add an `enum` or code constant according to your system's design. Avoid creating many exception classes that differ only in their message if they are handled identically.

## 7. Choose the right exception type before writing the message

A great message cannot fix a wrong exception type. Some common choices:

| Situation | Exception type to consider | What the message should focus on |
| --- | --- | --- |
| Parameter violates method precondition | `IllegalArgumentException` | Parameter name and expected condition |
| Parameter must not be `null` | `NullPointerException` or `IllegalArgumentException` per API contract | Required parameter |
| Object is in a state that disallows the operation | `IllegalStateException` | Current state and requirement |
| String cannot be parsed as a number | `NumberFormatException` or appropriate wrapper | Field name and expected format |
| Cannot read/write an I/O resource | `IOException` or subclass | Operation/resource and verified cause |
| Specific business condition callers must distinguish | Appropriately named application exception | Business rule, classification code/attribute |
| Not found in a lookup where absence is normal | Possibly `Optional.empty()` or an empty collection | `throw` may not be needed |

`Objects.requireNonNull(value, "field must not be null")` is a convenient way to check non-null preconditions; the message is used if the method throws `NullPointerException`. Use it only when the condition and exception type match the contract.

Do not use `Error` for business errors. `Error` represents serious system-level conditions by Java's design and should generally not be caught for recovery like an input error.

## 8. When should the invalid value be included in the message?

Input data can speed up investigation, but putting values directly into the message carries risks:

- Tokens, passwords, cookies, API keys, one-time verification codes, or connection strings containing credentials may be leaked.
- Personal data, identification numbers, or customer content may be written into long-lived logs replicated across many systems.
- Untrusted strings may contain newlines or control characters, making logs hard to read, causing **log injection**, or corrupting record structure.
- Very large data can overload logs; a message like `"invalid input=" + entirePayload` can inadvertently duplicate large payloads.
- Messages can surface in stack traces, telemetry, error-reporting systems, or API responses if an outer layer returns them verbatim.

For a sensitive field, instead of:

```java
throw new IllegalArgumentException(
        "invalid credential: " + credential);
```

use:

```java
throw new IllegalArgumentException(
        "credential validation failed");
```

These two statements are illustrative only; `credential` is a hypothetical variable. If root-cause investigation is needed, use an error code/event ID and log **selectively filtered** information in an access-controlled observability system. Do not assume that "not putting secrets in the message" means you can log raw secrets elsewhere.

When safe identifiers are included in a message, limit their length and sanitize characters, or use a parameterized logger/structured context. Do not write `"user=" + rawRequestBody` to save the effort of building proper context.

## 9. Do not use the message as a substitute for stack trace or `cause`

Some code catches an error and turns the entire error into a string:

```java
try {
    loadData();
} catch (java.io.IOException ex) {
    throw new IllegalStateException(ex.toString());
}
```

This is an illustrative snippet, assuming `loadData()` can throw `IOException`. `ex.toString()` typically includes the class name and message, but **does not preserve the `cause` object** if passed only to the `String` constructor.

A safer approach:

```java
try {
    loadData();
} catch (java.io.IOException cause) {
    throw new IllegalStateException(
            "Data loading failed", cause);
}
```

If a logger accepts a `Throwable` object, passing the error object via the dedicated parameter of the logger API ensures the stack trace and `cause` are recorded. Do not just print `ex.getMessage()` and assume enough diagnostic information has been saved.

### `throw ex;` or `throw new ...(..., ex);`?

- `throw ex;`: rethrows the **same caught object**, preserving its existing type and `cause`. Suitable when the current layer does not need to change the contract, though it may have performed an action such as cleanup.
- `throw new SomeException("context", ex);`: creates a **new exception** with an additional message and a `cause` pointing to the original error; suitable when representing the error at a different level of abstraction.
- `throw new SomeException("context");` after catching another error: risks losing the causal link if no other mechanism records it.

Some code calls `fillInStackTrace()` or creates a new exception solely to adjust where the stack trace points; do not do this to "hide" the error origin unless you have a special need and fully understand the consequences. The stack trace typically reflects when the exception object was created/initialized; the `Caused by` chain is what reveals the underlying causes beneath a wrapper.

## 10. Logging and responsibility at each layer

An error may pass through libraries, services, controllers, job schedulers, and the UI layer. If **every layer logs the full stack trace and rethrows**, the system can record a single incident as multiple nearly duplicate log entries.

A generally sensible model:

1. **Detection site:** throw the right exception type with a message clearly stating the condition.
2. **Business layer:** wrap the error only if new context is added or the contract changes; preserve `cause`. Do not catch just to log the exact same error and rethrow.
3. **Interface or task boundary:** translate the error into an appropriate failure result/HTTP/status; this can be the centralized place to log the error.
4. **Observability system:** attach correlation ID, timestamp, operation name, severity, and allowed fields.

HTTP status, user-facing messages, and exception message strings do not have to be identical. For instance, an internal permission error requires a public response with limited details, while access-controlled operational logs can contain deeper cause information.

At API boundaries, do not expose every exception message to the client. Besides leaking information, messages may be technical, unlocalized, or subject to change when library versions are updated.

## 11. How does a checked-exception method add context?

The following example is **only an illustrative method**, not a standalone program. It reads a file and adds the configuration's logical name to the message on failure, while preserving `cause`:

```java
static String readRequiredConfig(
        java.nio.file.Path path, String logicalName)
        throws java.io.IOException {
    try {
        return java.nio.file.Files.readString(path);
    } catch (java.io.IOException cause) {
        throw new java.io.IOException(
                "Cannot read required configuration: " + logicalName,
                cause);
    }
}
```

Key points:

- `Files.readString` can throw various `IOException` subtypes; the wrapper message only states **cannot read configuration**, without claiming the file does not exist.
- `logicalName` is assumed to be a **safe internal name**, not a path or user data containing secrets. If no safe identifier is available, omit it from the message.
- Deeper details such as `NoSuchFileException` or another I/O cause remain available via `getCause()`.
- Because it still throws checked `IOException`, the `throws IOException` signature remains appropriate; callers must continue to declare or catch it when using the method.
- If the API does not need to change the message to remain useful, you can let the original exception propagate and log context at the appropriate boundary.

**Do not replace the original exception type with an overly broad wrapper just to "have a nicer message"**. When callers need to distinguish `NoSuchFileException` from other I/O errors, wrapping everything in a new `IOException` can break direct `catch (NoSuchFileException)`, even though `cause` is intact. Weigh this before changing an API's type contract.

## 12. Common mistakes when writing `throw`

### A. Message is too short

```java
throw new IllegalStateException("Invalid state");
```

Usually lacks sufficient context. It is better to state **the current state and the required state** if both are known and allowed to be exposed, such as `"cannot submit order: expected DRAFT status"`.

### B. Message contains sensitive data

```java
throw new IllegalArgumentException(
        "bad password: " + password);
```

This is an **example of what not to do**. Never let passwords appear in exception messages, even if the object is only thrown in an internal layer; many frameworks automatically log stack traces for uncaught errors.

### C. Wrapping without `cause`

```java
catch (java.io.IOException ex) {
    throw new IllegalStateException("Startup failed");
}
```

If policy requires changing the type, use the constructor that passes `ex` as the cause; if no change is needed, let `IOException` propagate.

### D. Using the message as an error code

```java
if ("quantity must be positive".equals(ex.getMessage())) {
    // ...
}
```

This is **code that should not be used for business branching**. A wording tweak can change behavior. Use an exception type, error enum, or specific attribute.

### E. Adding a wrapper at every catch

Writing `throw new RuntimeException("Failed at A", ex)` in A, then `"Failed at B"` in B, then `"Failed at C"` in C makes the stack trace long while adding little meaning. Only wrap at a layer that has **new, real, and useful context**.

### F. Message asserts an unverified cause

If an API throws `IOException`, do not immediately write `"network is offline"` if you are not certain. Use `"remote operation failed"` and let `cause` provide technical details, or classify further using specific exceptions.

### G. Catching an error and turning it into a fake success

```java
try {
    return parseRequiredValue();
} catch (RuntimeException ex) {
    return 0;
}
```

This is an **anti-pattern snippet**, assuming the method returns `int`. If `0` is valid, the caller cannot distinguish success from failure. When the contract does not allow a fallback value, propagate a meaningful error; if `0` is a valid default by policy, document the contract clearly and restrict which error types may be substituted.

### H. Misleading message from conflating layers

For example, in the parsing layer, writing `"Database server is down"` just because the function is called during a data-saving flow is wrong when the actual error is invalid numeric input. The message must stick to **what was verified at the throw site**.

## 13. A process for designing maintainable exceptions

When about to write `throw`, you can apply the following sequence:

1. **Define the failure condition.** Is this a mandatory stop error, or a valid absent result? Do not throw an exception merely because a normal lookup returns no result.
2. **Choose the appropriate exception type.** For example, `IllegalArgumentException` for parameter preconditions, `IllegalStateException` for object state, `IOException` for failed I/O operations.
3. **Write an actionable message.** Name the field or operation and the violated condition. Avoid standalone `"error"` or `"failed"`.
4. **Add context at the right layer.** If a calling layer has a safe task ID that helps identify the failure, add it there or in structured logs. Do not guess information that the layer does not know.
5. **Preserve the root cause when changing exception types.** Use a constructor that accepts `cause`. Check the new type's contract: changing the type must not accidentally hide a needed `catch` branch.
6. **Review for sensitive data.** Messages, `cause`, stack traces, and logs can leave the process. Do not put secrets or raw payloads into them.
7. **Place handlers where recovery is possible.** Catch where you can recover or translate into an appropriate response; do not swallow errors in low layers.
8. **Test the failure path.** Verify the exception type, `cause`, and structured data; avoid asserting the entire message sentence if the exact wording is not part of the public contract.

## 14. Scenario exercises

**Scenario 1:** A method receives `retryCount = -2`, and the contract specifies non-negative. What should be thrown?

You can use:

```java
throw new IllegalArgumentException(
        "retryCount must be non-negative");
```

The error clearly states the parameter name and condition. There is no need to print the value itself if it adds no value or if policy restricts logging inputs.

**Scenario 2:** The file-reading layer throws `IOException`. The application initialization layer knows the file is a required configuration but does not know the technical cause. How should it report this?

It can wrap with `new IllegalStateException("Service startup failed: required configuration could not be read", cause)` if that layer decides initialization cannot proceed. Preserve `cause`; do not claim "file does not exist" without evidence.

**Scenario 3:** The caller needs to know whether the error was caused by `quantity` or `price` to return a field-specific error. Should it check `ex.getMessage().contains("quantity")`?

No. If the caller needs stable classification, provide a `field` property or an enum/error code on a dedicated exception. Messages are for human readers and diagnostics, not a machine protocol based on fragile keywords.

**Scenario 4:** An error from a library already has a very clear type and message, and the middle layer has no additional context. Should it wrap the error again for "completeness"?

Usually not. Allowing the exception to propagate preserves its type, reduces wrappers, and lets the responsible layer handle it.

**Scenario 5:** An exception message records a raw request containing an authentication token. The system only prints errors in the development environment. Is this safe?

Not recommended. Environments, loggers, and retention policies can change; secrets can be sent to telemetry or error-reporting systems. Choose safe context fields from the start and restrict sensitive data in both messages and logs.

**Key takeaways:** `throw` indicates **the operation failed**; the **exception type** indicates what kind of error it is; the **message** explains the failed condition and operation; **`cause`** preserves the deeper reason; **safe, structured context** helps trace the exact event. When these parts are designed consistently, errors are easy to handle, easy to test, and easy to investigate without exposing unnecessary data.
