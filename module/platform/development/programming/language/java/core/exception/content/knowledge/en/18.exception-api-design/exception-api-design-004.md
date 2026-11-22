# Distinguishing Parameter Errors, State Errors, and Dependency Errors When Designing Java APIs

## 1. Why Classify Errors Correctly?

When a Java method fails, the caller needs to know whether **they passed invalid data**, **the object/system is in a state that does not allow the operation**, or **an external component failed to perform the work**. These three groups lead to different fixes and handling strategies:

- **Parameter error (invalid argument):** The input value violates the method's contract. The caller usually needs to fix the data or how they call the method.
- **State error (invalid state):** The parameters may be completely valid, but the current state of the object or resource does not allow the operation. The caller needs to change the sequence of operations or ensure the state condition.
- **Dependency error (dependency failure):** The inputs and the API's own state may be valid, but an operation on the network, file, database, another system, or a dependent library fails. It must be handled at the integration boundary: diagnostics, reporting, conditional retries, or fallback.

This classification describes **the cause and responsibility for recovery**, not three fixed branches of the `Exception` inheritance hierarchy. For example, both `IllegalArgumentException` and `IllegalStateException` are `RuntimeException`s; a dependency error may appear as a checked exception, an unchecked exception, or a business-domain exception.

## 2. Quick Decision Table

| Criterion | Parameter Error | State Error | Dependency Error |
| --- | --- | --- | --- |
| Core question | "Does the value the caller passed satisfy the contract?" | "Is this call valid **right now**?" | "Can a required component execute?" |
| Typical causes | Negative number when non-negative is required; malformed string; forbidden `null` reference | Using a service after closing it; calling `commit()` before `begin()`; reading an uninitialized resource | Lost connection, timeout, I/O error, DB unavailable |
| Common Java exceptions | `IllegalArgumentException`, `NullPointerException`, `IndexOutOfBoundsException` | `IllegalStateException`; sometimes an API-specific state exception | `IOException`, `SQLException`, `TimeoutException`, or an API-defined `...UnavailableException` type |
| What does the caller usually do? | Fix the arguments; fix the calling logic | Fix the call sequence or resource lifecycle | Inspect the cause, restore connection, retry if safe, report a transient error |
| Should the exact same call be retried immediately? | Usually no; parameters must be fixed | Usually no; state must be changed first | Only if the error is transient, the operation is safe to retry, and a bounded policy is in place |

**Key principle:** The same input string can lead to different types of errors at different stages. A syntactically valid currency code may still not be supported by the data provider, or the provider may lose its connection while processing that code. Classify based on **the API contract and the actual root cause**, not merely on the message or exception class name.

## 3. Parameter Errors: Violating Call Preconditions

A parameter is invalid when the caller can determine the error **from the method's public contract and the passed-in value**, independent of external state. For example:

- `transfer(amount)` requires `amount > 0` but receives `0` or a negative number.
- `parsePort(port)` requires a port in the range `1..65535` but receives `70000`.
- `findById(id)` requires `id` to be non-`null` but receives `null`.
- An API requires a string of three uppercase letters, and the caller passes a malformed string.

Choosing the exception:

- `IllegalArgumentException`: the parameter does not satisfy the API's value or format conditions.
- `NullPointerException`: usually appropriate when a reference parameter is forbidden from being `null`; `Objects.requireNonNull(value, "value")` is the JDK idiom. An API may also choose `IllegalArgumentException` per its own policy, but it must be consistent.
- `IndexOutOfBoundsException`: for an index outside the valid range of a string, list, array, or indexed-access structure. This is a more specific case of `RuntimeException`.

Validation pattern:

```java
Objects.requireNonNull(name, "name");
if (name.isBlank()) {
    throw new IllegalArgumentException("name must not be blank");
}
if (pageSize < 1 || pageSize > 100) {
    throw new IllegalArgumentException("pageSize must be between 1 and 100");
}
```

This is a **code snippet placed inside a method** that already declares the `name` and `pageSize` variables, not a standalone program. `Objects.requireNonNull` throws `NullPointerException` when it receives `null`; `String.isBlank()` has been supported since Java 11. Error messages should clearly state the parameter name and the violated rule, while avoiding printing sensitive data.

**Boundary to remember:** "Account not found by ID" is not automatically an invalid argument. The ID may be properly formatted, yet the account does not exist: that is a *resource not found* case in the business domain, which usually has its own exception or result value. Likewise, do not use `IllegalArgumentException` to mask a DB error simply because the DB call took a parameter.

## 4. State Errors: Valid Values, Wrong Timing

A state error occurs when a precondition depends on **the lifecycle, processing phase, or current state** of the object/resource:

- Calling `send()` after `close()`.
- Calling `commit()` when no transaction has started.
- Calling `next()` on an already-closed object, if the contract specifies it must not be used after closing.
- Calling `start()` a second time when the processor only allows starting once.

`IllegalStateException` expresses that **the call is inappropriate for the state of the object or application**. It is useful for internal synchronous APIs and object lifecycles:

```java
if (closed) {
    throw new IllegalStateException("service is closed");
}
```

This snippet assumes there is a `closed` state variable in the class owning the operation.

Important distinction: a valid parameter does not become an "invalid parameter" just because the object is closed. Nor does state mean "any error that happens at runtime"; a DB timeout is a dependency error, even if it occurs while the Java object is in a normal, usable state.

APIs that already define specialized exceptions must adhere to their own contracts. For example, `UnsupportedOperationException` typically indicates an unsupported operation, not necessarily a transient state; do not replace it with `IllegalStateException` just for superficial consistency.

## 5. Dependency Errors: External System Failures

A "dependency" is anything the method must call to complete its work: an HTTP client, database, file system, message broker, RPC service, library/native service, or a data source from another module. Distinguish three cases:

1. **Unreachable:** network loss, timeout, DNS resolution failure, connection refused.
2. **Reachable, but processing fails:** DB reports temporary overload, service returns a 5xx error, file cannot be read due to I/O.
3. **Dependency returns data/behavior violating the integration contract:** payload is missing a required field, response cannot be parsed, incompatible schema version.

In Java, `IOException` is the classic checked exception when an I/O operation fails; `SQLException` can come from JDBC. Specific HTTP/DB libraries may use unchecked exceptions, exceptions categorized as transient/permanent, or exception wrappers; there is no single Java class that covers every dependency error.

**Not every error thrown by a dependency belongs to the dependency failure category.** For example, an HTTP service returning `400` because the user entered a forbidden field may correspond to an input error of the public API; a `401` error may be due to the integrating application's credentials; a `404` response may mean a business object does not exist. You must accurately match the contract of each layer and determine who is able to fix the error.

For dependency errors, contract design should consider:

- **Preserving the original type** when callers need to distinguish `IOException`, `SQLException`, etc., and the API wants to allow fine-grained handling.
- **Using a domain or boundary exception** (e.g., `RateProviderUnavailableException`) when you want to avoid leaking internal technology; always preserve the original `cause`.
- **Distinguishing transient vs. permanent errors** based on reliable data: timeouts/dropped connections may be transient; misconfiguration or expired credentials usually require fixing the configuration.
- **Bounding retries:** have a maximum number of attempts/wait time, reasonable timeouts, backoff/jitter, and verify operation idempotency. Do not automatically retry a payment or data-write operation without deduplication mechanisms.
- **Not leaking secrets:** log with appropriate context, and mask tokens, passwords, private payloads, and connection details when returning errors to users.

## 6. Java 17+ Example: One API, Three Error Causes

The program below has **one public class in a single standalone file** and simulates an exchange-rate provider. It validates arguments first, then checks the service state, and finally calls the dependency. The code `EUR` intentionally triggers a simulated I/O error so the dependency branch is easy to see.

Create the file `ExceptionTaxonomyDemo.java`:

```java
import java.io.IOException;
import java.math.BigDecimal;
import java.util.Objects;

public class ExceptionTaxonomyDemo {
    @FunctionalInterface
    interface RateProvider {
        BigDecimal rateOf(String currency) throws IOException;
    }

    static final class QuoteService {
        private final RateProvider provider;
        private boolean closed;

        QuoteService(RateProvider provider) {
            this.provider = Objects.requireNonNull(provider, "provider");
        }

        BigDecimal quote(BigDecimal amount, String currency) throws IOException {
            Objects.requireNonNull(amount, "amount");
            Objects.requireNonNull(currency, "currency");
            if (amount.signum() < 0) {
                throw new IllegalArgumentException("amount must be >= 0");
            }
            if (!currency.matches("[A-Z]{3}")) {
                throw new IllegalArgumentException("currency must have 3 uppercase letters");
            }
            if (closed) {
                throw new IllegalStateException("service is closed");
            }
            return amount.multiply(provider.rateOf(currency));
        }

        void close() {
            closed = true;
        }
    }

    public static void main(String[] args) throws IOException {
        QuoteService service = new QuoteService(currency -> {
            if ("EUR".equals(currency)) {
                throw new IOException("exchange-rate endpoint unavailable");
            }
            return new BigDecimal("25000");
        });

        System.out.println("OK: " + service.quote(new BigDecimal("2"), "VND"));

        try {
            service.quote(new BigDecimal("-1"), "VND");
        } catch (IllegalArgumentException ex) {
            System.out.println("PARAM: " + ex.getClass().getSimpleName());
        }

        try {
            service.quote(new BigDecimal("2"), "EUR");
        } catch (IOException ex) {
            System.out.println("DEPENDENCY: " + ex.getClass().getSimpleName());
        }

        service.close();
        try {
            service.quote(new BigDecimal("2"), "VND");
        } catch (IllegalStateException ex) {
            System.out.println("STATE: " + ex.getClass().getSimpleName());
        }
    }
}
```

Compile and run from the directory containing the file (JDK 17 or newer):

```bash
javac -encoding UTF-8 ExceptionTaxonomyDemo.java
java ExceptionTaxonomyDemo
```

```text
OK: 50000
PARAM: IllegalArgumentException
DEPENDENCY: IOException
STATE: IllegalStateException
```

Explanation of the branches:

1. `quote(2, "VND")`: amount and currency code are valid, the service is open, and the provider returns `25000`, so the result is `2 × 25000 = 50000`.
2. `quote(-1, "VND")`: the amount violates `amount >= 0`, throwing `IllegalArgumentException` **before** calling the dependency.
3. `quote(2, "EUR")`: both input and state are valid, but the simulated provider throws `IOException`. This is a dependency error, not a parameter error.
4. After `service.close()`, `quote(2, "VND")` throws `IllegalStateException`; the parameters are still valid and the provider is not called.

The example is intentionally simple: the fixed rate is for illustration only, the regex `[A-Z]{3}` checks **format** rather than proving the code is recognized by ISO 4217, `QuoteService` does not support concurrent access, and `close()` only flips an internal flag (it does not implement `AutoCloseable`). In a real application, you need business-level validation, resource management, and appropriate synchronization.

## 7. Designing Exception Contracts for Public Methods

A good API tells the caller what it must guarantee before calling, the required state, and the kinds of external failures that may occur. Here is an example of the `quote` documentation corresponding to the program above:

```java
/**
 * Converts amount using the exchange rate provided by the provider.
 *
 * @param amount non-negative amount; must not be null
 * @param currency code consisting of exactly 3 uppercase letters; must not be null
 * @return the converted amount
 * @throws NullPointerException if amount or currency is null
 * @throws IllegalArgumentException if amount is negative or currency is malformed
 * @throws IllegalStateException if the service is closed
 * @throws IOException if the rate provider encounters an I/O error
 */
```

This is a **Javadoc block placed immediately before the `quote` method declaration**, not a standalone compilable file. The `@throws` tag documents unchecked exceptions as well; only checked exceptions like `IOException` need to appear in the method signature's `throws` clause (unless handled inside the method).

When choosing an error type, ask yourself:

1. Can the caller detect the invalid condition solely from the parameter value itself and the contract? If yes, it belongs to parameter errors.
2. Are the parameters still valid, while the resource/object is in a phase that does not permit the operation? State error.
3. Did it call into a dependent system/object that failed to fulfill its commitment? Dependency error.
4. Is it an expected business case (not found, out of stock, denied due to permissions, etc.) or a programming error? Consider **a dedicated result or specialized exception**; do not force it into these three groups if the semantics do not fit.

Prefer error names that reflect responsibility and recoverability. Do not choose `IllegalStateException` just to avoid declaring `throws IOException`. Whether an exception is checked or unchecked is a **separate** API decision from cause classification.

## 8. Translating Errors Across Abstraction Layers: Preserving the Cause Category

The infrastructure layer may throw `IOException` or `SQLException`; the business layer may expose a more stable error type. **Only translate when the current layer understands the exact semantics**; do not use a driver message or an arbitrary exception name as proof:

~~~java
try {
    return provider.quote(currency);
} catch (java.io.IOException cause) {
    throw new RateProviderUnavailableException(
            "Không thể lấy tỷ giá", cause);
}
~~~

This is an illustrative snippet assuming `provider`, `currency`, and the domain exception constructor are already defined. `cause` must be passed into the wrapper so investigators can trace the root cause and any suppressed exceptions. Do not conflate **invalid input** with **not-ready state** or **unavailable dependency** just to have a single generic exception type.

For the topic of this article, the key question remains **which group the error belongs to and what the caller can do**. The next article on exception translation shows where to translate, when not to translate, and how to test it; the article on preserving `cause` dives deeper into the identity of the cause object.

## 9. Mapping at the HTTP or Service Boundary

When a Java API sits behind HTTP, the HTTP status must reflect the **specific contract**; there is no mandatory one-to-one mapping between each exception class and a status code:

| Identified Cause | Common HTTP Response Direction | Notes |
| --- | --- | --- |
| Malformed request, missing field, or public validation violation | `400 Bad Request` or `422 Unprocessable Content` | Describe the field to fix; do not expose stack traces to the client |
| Conflict with the stored resource state | `409 Conflict` (depends on the API) | An `IllegalStateException` from an internal bug does not automatically become `409` |
| Requested resource does not exist | `404 Not Found` | Usually a distinct business-domain case, not automatically a parameter error |
| Upstream returned an error/corrupted response | `502 Bad Gateway` (in an appropriate gateway/proxy role) | Choose according to the service's actual role |
| Dependency temporarily unavailable | `503 Service Unavailable` | May include a retry hint when justified |
| Upstream timeout | `504 Gateway Timeout` (when actually acting as a gateway/proxy) | Distinguish from timeouts in the service itself |
| Unhandled internal implementation error | `500 Internal Server Error` | Log internally; limit response details |

For example, if an API has a rule "only cancel orders in PENDING state", cancelling an already-delivered order is a **business state conflict**, typically represented by a dedicated domain error such as `OrderCannotBeCancelledException`. Conversely, using a Java client object after `close()` is an object lifecycle violation, typically suited to `IllegalStateException`. Both cases involve "state", yet the API level and HTTP mapping can differ.

## 10. Common Design Mistakes

- **Turning every error into `IllegalArgumentException`:** conflates a disconnected service with bad caller data; callers will try to fix a value that was actually valid.
- **Turning every error into `IllegalStateException`:** hides `IOException`, SQL timeouts, bugs, and distinct business conditions; makes it hard to tell whether to retry or fix the call sequence.
- **`catch (Exception ex)` and returning `null`/`0`:** turns a failure into a fake valid result, causing errors much further downstream. Only use a fallback if the contract allows it and the fallback value has clear meaning.
- **`throw new RuntimeException(ex.getMessage())`:** loses the original `cause` and stack trace. If wrapping is needed, use a constructor that accepts `cause`.
- **Immediately retrying the API with the same parameters for every exception:** cannot fix parameter or state errors, and can duplicate transactions when a dependency error happens after the other party already received the request.
- **Using text messages as a classification key:** text can change and be localized. Prefer the exception type, a stable error code, or structured attributes.
- **Ignoring the difference between dependency errors and business-domain outcomes:** e.g., HTTP 404 "customer does not exist" is different from a gateway being unable to reach the server.
- **Leaking sensitive details:** returning stack traces, SQL, connection strings, or tokens in client-facing messages.

## 11. Testing the Right Category and Failure Timing

Tests should verify **the exception type** and **that the dependency is not called on invalid-condition branches**. With a fake or mock that counts calls, the minimum test cases are:

| Scenario | Expectation | Is the provider called? |
| --- | --- | --- |
| `amount = null`, service open | `NullPointerException` | No |
| `amount = -1`, service open | `IllegalArgumentException` | No |
| `currency = "vn"`, service open | `IllegalArgumentException` | No |
| `amount = 2`, `currency = "VND"`, service open | Returns correct result | Yes, once |
| `amount = 2`, `currency = "EUR"`, provider throws `IOException` | Preserves `IOException` or wraps in the right type while preserving `cause` | Yes, once |
| After closing the service, valid parameters | `IllegalStateException` | No |

Beyond the happy path, test that messages are helpful, `cause` is not lost when translating errors, timeouts are bounded, retries do not cause repeated side effects, and logging does not leak information. If you have decided to **prioritize parameter validation before state checking** as in the example, add a test where parameters are invalid *and* the service is closed simultaneously to protect that ordering. There is no mandatory Java rule for precedence; the API must choose an order and keep its contract consistent.

For resources that may be mutated by another thread, checking `closed` and then proceeding can cause a race condition if not protected by synchronization. The learning example above is single-threaded; real applications must handle thread safety according to their own contracts.

## 12. Checklist When Designing or Reviewing an API

1. Document parameter preconditions clearly: `null`, value ranges, formats, and public business rules.
2. Document state conditions clearly: before/after `open`, `start`, `commit`, `close`; specify which calls are valid.
3. List dependencies that can fail and how they report errors; determine which errors are recoverable.
4. Choose an exception or result type that accurately expresses the cause and the caller's responsibility; use domain exceptions when needed.
5. Document `@throws`, preserve `cause` when crossing layers, and specify retry/timeout policies where appropriate.
6. Test all three error branches, avoid unnecessary side effects when validation/state checks fail, and ensure response data is safe.

**Rule of thumb:** *Invalid parameter* → fix the passed value; *invalid state* → fix the sequence or lifecycle; *dependency failure* → handle at the integration boundary and recover when safe. A well-designed API helps callers see that difference through its contract and error types, rather than having to guess from exception messages.
