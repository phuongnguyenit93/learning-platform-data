# Letting Exception Messages Become a Data Format That Other Code Must Parse — A Common Java Pitfall

> **Scope:** Java Core → Exception → Common Pitfalls. This lesson explains why `Throwable.getMessage()` is normally content intended for human readers rather than a stable protocol for software, and how to move from `contains`/`startsWith`/regex on messages to **exception types, error codes, typed fields, root causes, and result types**. Includes runnable Java 17 examples, API contracts, testing, and migration strategies.

## 1. A Single Phrase Can Change Entire Business Logic

Suppose a payment service encounters a declined transaction error and the caller handles it as follows:

~~~java
// Counter-example; charge() and respond... are application-defined functions.
try {
    charge();
} catch (RuntimeException ex) {
    if (ex.getMessage().contains("DECLINED")) {
        return respondPaymentDeclined();
    }
    return respondInternalError();
}
~~~

With the message `"Payment DECLINED for pay-17"`, the caller treats it as "declined". However, the exact same kind of error with the message `"Thanh toán bị từ chối: pay-17"`, `"Payment was declined"`, or `"Card issuer rejected request"` could be misclassified as a system error. A change in **diagnostic wording** has become a change in **program behavior**.

This is the **exception message as data contract** anti-pattern: there is no published `errorCode` field, no schema or compatibility policy; one layer inadvertently uses `getMessage()` as another layer's data format. Such bugs can affect HTTP status codes, retries, UI, alerts, idempotency, or decisions on whether to reverse a transaction.

**Principle:** messages serve explanation and diagnostics; programmatic data must be defined and consumed through a **structured, typed** contract.

## 2. Why `getMessage` Is Not an Error Code

`Throwable` is an object containing information about an error. Its parts serve different purposes:

| Property | Meaning | Proper Usage |
|---|---|---|
| Java type of the exception | Classification by API contract | `catch (SpecificException ex)`, `instanceof` |
| `getMessage()` | Error description string, typically aimed at human readers | Display/diagnostics after data sanitization |
| `getLocalizedMessage()` | Description that may be customized per locale | Do not use for machine logic decisions |
| `getCause()` | Link to the underlying cause when wrapped | Root-cause tracing, classifying cause types when the contract allows |
| `getStackTrace()` | Execution trace | Debugging, logging; do not use line numbers/file names as business codes |
| `getSuppressed()` | Secondary suppressed errors, e.g., resource-closing errors | Diagnostics and cleanup; do not parse text into codes |
| `code`/`id` fields defined by custom exceptions | Domain data with a contract | Classification, API mapping, correlation |

The JDK has no general rule guaranteeing that the messages of every `IllegalArgumentException`, `SQLException`, or `NumberFormatException` remain unchanged across versions. If a provider only documents the **exception type and throwing conditions**, callers should not unilaterally promote a message string into an API contract.

This **does not mean messages are useless**. A good message still describes the operation, failure condition, and safe context for humans to investigate. It is simply not the source of truth for machine-readable branching, unless the provider officially defines a stable grammar.

## 3. Fragile Ways of Parsing Text

### Using `contains` or `startsWith`

~~~java
// Illustrates the anti-pattern only.
if (ex.getMessage().startsWith("ORDER_NOT_FOUND")) {
    // ...
}
~~~

Changes in prefix, letter case, whitespace, locale, or wrapper layers can all skew the result. If the message is `null`, calling `contains` can even throw a `NullPointerException` and mask the original error.

### Using `split` to Extract a Business ID

~~~java
// Should not be used as a primary data source.
String paymentId = ex.getMessage().split(":")[1];
~~~

A message may add colons, newlines, an ID containing the delimiter, or omit elements; the parser may produce the wrong ID, an `ArrayIndexOutOfBoundsException`, or unsafe data.

### Using Regex to Extract a Number

~~~java
// Illustrative code: regex depends on wording.
java.util.regex.Matcher m =
        java.util.regex.Pattern.compile("row (\d+)").matcher(ex.getMessage());
~~~

Even with a valid regex, `"row 12 invalid"` can become `"invalid record at line 12"`. If the row position matters, the API should expose `rowNumber()` or a `ValidationError` with a `position` field instead of forcing callers to parse the message.

### Relying on Dependency Wording

A newer version of a library may change `"Connection refused"` to `"Failed to connect"` or wrap the exception with a different message. Do not rely on the word `"refused"` in text to decide whether to retry. If the SDK provides an HTTP status, vendor error code, or official subtype, use those properties instead.

## 4. Complete Java 17 Example: Bad vs. Good When Messages Change

The following example simulates the same declined-payment error with two different message strings. The wrong approach reads text, whereas the right approach reads `FailureCode` and preserves the technical error's `cause`.

Save as **`ExceptionMessageContractDemo.java`**:

~~~java
import java.util.Objects;

public class ExceptionMessageContractDemo {
    enum FailureCode {
        PAYMENT_DECLINED,
        PROVIDER_UNAVAILABLE
    }

    static final class PaymentFailure extends RuntimeException {
        private final FailureCode code;
        private final String paymentId;

        PaymentFailure(FailureCode code, String paymentId,
                       String description, Throwable cause) {
            super(description, cause);
            this.code = Objects.requireNonNull(code, "code");
            this.paymentId = Objects.requireNonNull(paymentId, "paymentId");
        }

        FailureCode code() {
            return code;
        }

        String paymentId() {
            return paymentId;
        }
    }

    static int fragileHttpStatus(RuntimeException error) {
        // Wrong: relies on the message instead of structured classification.
        return error.getMessage().contains("DECLINED") ? 402 : 500;
    }

    static int stableHttpStatus(PaymentFailure error) {
        return switch (error.code()) {
            case PAYMENT_DECLINED -> 402;
            case PROVIDER_UNAVAILABLE -> 503;
        };
    }

    static String publicCode(PaymentFailure error) {
        return switch (error.code()) {
            case PAYMENT_DECLINED -> "payment_declined";
            case PROVIDER_UNAVAILABLE -> "provider_unavailable";
        };
    }

    public static void main(String[] args) {
        RuntimeException english =
                new IllegalStateException("Payment DECLINED for pay-17");
        RuntimeException vietnamese =
                new IllegalStateException("Thanh toán bị từ chối: pay-17");

        System.out.println("bad English: " + fragileHttpStatus(english));
        System.out.println("bad Vietnamese: " + fragileHttpStatus(vietnamese));

        PaymentFailure typed = new PaymentFailure(
                FailureCode.PAYMENT_DECLINED,
                "pay-17",
                "Thanh toán bị từ chối: pay-17",
                new IllegalStateException("gateway response 05"));

        System.out.println("good status: " + stableHttpStatus(typed));
        System.out.println("good code: " + publicCode(typed));
        System.out.println("good paymentId: " + typed.paymentId());

        Throwable cause = typed.getCause();
        System.out.println("good cause: "
                + cause.getClass().getSimpleName()
                + ": " + cause.getMessage());
    }
}
~~~

Compile/run with JDK 17+:

~~~bash
javac ExceptionMessageContractDemo.java
java ExceptionMessageContractDemo
~~~

**Exact stdout:**

~~~text
bad English: 402
bad Vietnamese: 500
good status: 402
good code: payment_declined
good paymentId: pay-17
good cause: IllegalStateException: gateway response 05
~~~

Explanation:

1. `fragileHttpStatus` only recognizes the uppercase English word `DECLINED`. The Vietnamese version results in `500`, even though the business event has not changed.
2. `PaymentFailure` stores the error code in the `FailureCode` enum and the `paymentId` identifier in two typed fields.
3. `stableHttpStatus` reads `error.code()`. When the message is improved or localized, the decision does not change.
4. `publicCode` maps the internal enum to a public error code with a clear contract.
5. `getCause()` retains the original technical exception that the logging layer can use for investigation; the HTTP layer does not need to parse `"gateway response 05"`.
6. Status code `402` only illustrates **the example API's policy**; it does not claim that every payment system must use HTTP 402. Real applications choose status codes based on their published HTTP/domain contract.
7. There are no frameworks or background threads in the program; the output is deterministic, keeping the focus on error design.

## 5. Typed Exceptions: Error Types, Codes, and Separate Context

When an API still needs to throw exceptions, machine-readable information can be modeled with a class that has dedicated fields:

~~~java
// Java 17 declaration snippet; can be placed in a class or top-level file.
enum OrderErrorCode {
    NOT_FOUND, ALREADY_PAID, STORAGE_UNAVAILABLE
}

final class OrderOperationException extends RuntimeException {
    private final OrderErrorCode code;
    private final String orderId;

    OrderOperationException(
            OrderErrorCode code, String orderId, Throwable cause) {
        super("order operation failed", cause);
        this.code = java.util.Objects.requireNonNull(code);
        this.orderId = orderId;
    }

    OrderErrorCode code() { return code; }
    String orderId() { return orderId; }
}
~~~

Here `getMessage()` can change from `"order operation failed"` to `"unable to process order"` without breaking callers reading `code()` or `orderId()`. Using a constructor that accepts `cause` ensures the original error's trace is not severed.

However, adding too many subclasses for every single error code also makes the hierarchy hard to manage. You can use a few exception types with meaningful abstractions, paired with an enum `code` for fine-grained classification. For public APIs across multiple services, string-based error codes with a schema/version and support for unknown codes are often more flexible than a rigidly synchronized enum.

### Preserving Semantics at the Right Layer

- The repository knows technical errors: `SQLException`, I/O exceptions, driver codes.
- The service knows domain semantics: order does not exist, payment declined, downstream dependency unavailable.
- The boundary knows how to map to HTTP/queue/job outcomes and safe public messages.

Do not force a controller to parse `SQLException.getMessage()` to decide an HTTP status. The repository/service should translate errors into structured abstractions while preserving `cause` and information needed for investigation.

## 6. Should You Always Catch by Subtype?

`catch (SpecificException ex)` is a strongly typed approach that works well when a library publishes subtypes to distinguish errors. For example:

~~~java
// Illustrative snippet; classes/methods are hypothetical application code.
try {
    repository.load(orderId);
} catch (OrderNotFoundException ex) {
    return respondNotFound();
} catch (StorageUnavailableException ex) {
    return respondUnavailable();
}
~~~

If multiple error codes belong to the same domain exception type, using `switch (ex.code())` can be better than creating many empty classes:

~~~java
// Snippet; OrderOperationException was declared above.
switch (ex.code()) {
    case NOT_FOUND -> respondNotFound();
    case ALREADY_PAID -> respondConflict();
    case STORAGE_UNAVAILABLE -> respondUnavailable();
}
~~~

You must distinguish between the **actual cause** and the **handling decision**. A `TimeoutException` does not automatically guarantee that the remote operation has not committed; retry policy also depends on idempotency, attempt budget, and the external system's state. A message containing the word "timeout" is even less sufficient for making that decision.

## 7. Result Types for Frequently Rejected Outcomes

For expected outcomes in UI, validation, or import flows, exceptions are sometimes not the best channel. Use a Java 17 sealed result type:

~~~java
// Illustrative type declarations in a Java 17 program.
sealed interface ParseResult permits Accepted, Rejected { }

record Accepted(int value) implements ParseResult { }

enum RejectReason {
    EMPTY, NOT_A_NUMBER, OUT_OF_RANGE
}

record Rejected(RejectReason reason) implements ParseResult { }
~~~

Callers can handle `Rejected.reason()` instead of throwing `NumberFormatException` and parsing the message to learn that "the 7th character is invalid". If the position is needed, add a record field `int position`. For results that only need presence/absence, `OptionalInt` or `Optional<T>` may be simpler.

Do not replace exceptions with `null` or a generic `"error"` string and consider the problem solved: that usually creates an even vaguer contract. The goal is to **accurately represent the information the caller needs to handle**.

## 8. Messages Can Change Due to Localization

An error code should remain stable regardless of locale:

~~~text
code=payment_declined
vi-VN: "Phương thức thanh toán bị từ chối."
en-US: "The payment method was declined."
~~~

Changing a translation must never cause `retryable`, HTTP status, or outcome type to change. Do not write:

~~~java
// Counter-example.
if (ex.getLocalizedMessage().contains("từ chối")) {
    // Making policy decisions based on display language.
}
~~~

Instead, define an `errorCode + locale → displayMessage` catalog or use `ResourceBundle`/an i18n service at the boundary. User-facing messages and internal messages can differ. Never return raw SQL error messages, tokens, or internal paths in an API response.

## 9. Do Not Parse JDK and Library Messages

For example, `Integer.parseInt(input)` throws `NumberFormatException` if the string is invalid. If you need to know the exact input to display an error, you **already have the input**; there is no need to use regex to extract it back from `ex.getMessage()`.

With JDBC, `SQLException` provides `getSQLState()` and `getErrorCode()` in addition to `getMessage()`. These codes must be interpreted according to the SQLState/vendor contract and deployment configuration, but they are far more intentional than running regex on driver descriptions.

With HTTP clients/SDKs, use the response status, provider error code, or typed error body when supported. Some libraries do not publish machine-readable codes; in that case, look for a suitable API or place an adapter to contain the risk rather than letting the entire application depend on wording.

**Do not infer a stable code just because a string or number is present.** Error codes also need documentation, mapping, versioning, and a policy for new codes.

## 10. Building API Responses with Stable Codes and Mutable Messages

A structured JSON response should separate:

~~~json
{
  "code": "payment_declined",
  "message": "Unable to pay with the selected method.",
  "requestId": "req-42",
  "details": {
    "paymentId": "pay-17"
  }
}
~~~

This is an **illustrative** schema with dummy IDs. `code` is for client classification; `message` is for display; `requestId` aids support investigation; `details` contains schema-defined fields permitted for public exposure.

**Do not concatenate JSON using strings from `ex.getMessage()`**: wording may contain quotes, newlines, control characters, or sensitive information. Use a serializer/JSON library that supports escaping and schema versioning. Do not expose `Throwable`, stack traces, causes, or raw SQL to clients.

Distinguish internal errors from public responses: public codes can be stable enough for the client ecosystem, while exception classes and stack traces serve server-side diagnostics.

## 11. When Is Parsing an Error String Acceptable?

A string **can** be a protocol if the provider **publishes a clear machine-readable grammar**. Examples include a tool with a versioned output protocol, an error CSV with formal escaping, or a `message` whose contract explicitly states it contains a structured encoding.

Minimum conditions:

- Documented schema, version, and encoding/escaping rules.
- Tests for malformed input and unknown fields.
- Compatibility policy when adding or modifying fields.
- Grammar does not vary by locale beyond what is documented.
- Size limits and validation for untrusted data.
- No better typed API is being ignored.

If a library only describes a message as "a string describing the exception", you must not infer that it is a parseable contract. If you are forced to integrate a legacy library that only returns text, isolate the parser in **a single adapter** with version-specific regression tests instead of letting every service parse it independently. Avoid using such fragile parsers for critical payment or rollback decisions whenever possible.

## 12. Logging: Read Structured Fields, Not Regex on Messages

A log event can carry:

~~~json
{
  "event": "payment_failed",
  "operation": "authorize_payment",
  "requestId": "req-42",
  "paymentId": "pay-17",
  "errorCode": "payment_declined",
  "exceptionType": "PaymentFailure",
  "causeType": "IllegalStateException"
}
~~~

The log above is a **sample**, not program stdout. A structured logger should emit `errorCode`, operation, and IDs as independent fields while also recording the `Throwable` to preserve the stack and cause. There is no need to dump the entire exception into a text field and later use regex to recover the error code.

Do not create metric labels from `getMessage()`: messages contain dynamic IDs, URLs, and variable data, causing high cardinality and potential information leaks. Metrics should be grouped by `operation`, `errorCode`, `dependency`, or other stable categories; request IDs belong in logs/tracing.

If an error passes through multiple layers, avoid logging the same stack trace at the repository, service, and controller if each layer just logs and rethrows. Lower layers should translate the error type while preserving `cause`; the layer owning the final outcome logs the event with full context. Separate retry/compensation events can still have their own logs when needed.

## 13. Security: Exception Messages Are Not Safe Public Data

`Throwable.getMessage()` sometimes contains:

- API keys or access tokens embedded in URLs.
- Connection strings or SQL with sensitive parameters.
- Internal file paths, hostnames, configuration names.
- Emails, phone numbers, customer identifiers, or request payloads.
- Raw error bodies controlled by external providers.

Do not pass messages directly into HTML/API responses or metrics. Only emit `code` and safe public messages controlled by the application itself. If a business ID is stored in a typed exception, it still requires access-control review, redaction, and sensitive-data checks. **Typed does not mean safe-to-log.**

Client-supplied input used as an ID can contain newlines or control characters; validate and cap lengths before placing them into logging fields to reduce log injection risk.

## 14. Retry, Timeout, and Cancellation Cannot Rely on Keywords

Code like `getMessage().toLowerCase().contains("timeout")` cannot answer:

1. Did the timeout occur at the caller, DB, queue, or HTTP transport?
2. Was the request already committed on the server?
3. Is the operation idempotent?
4. Was the task cancelled or did it simply time out?
5. Is there remaining retry budget and backoff?
6. Was the exception wrapped by another error?

Classify based on **official exception types/error codes**, dependency policies, and **business state**. `CancellationException` and `InterruptedException` carry cooperative cancellation semantics and must be handled according to their contracts; do not replace them by searching for the string `"cancelled"`.

If a network request times out, do not assume it caused no side effects; you may need an idempotency key or status inquiry before retrying. Typed error codes improve classification, but they do not automatically provide rollback.

## 15. Compatibility When Adding Error Codes to Legacy APIs

Suppose legacy code only throws `RuntimeException("ORDER_MISSING: id")` and clients already parse the prefix. Changing the message immediately could break old clients. Migration should include:

1. Auditing all places using `getMessage()` for logic, including services, tests, alerts, SDKs, and web clients.
2. Adding typed fields or error codes to API/server responses while preserving `cause`.
3. Publishing the set of codes and their meanings, and defining a policy for unknown codes.
4. Migrating callers to the new fields in phases, writing tests for two languages/messages.
5. Keeping the legacy mechanism during a compatibility window if an existing contract has active consumers, while discouraging new consumers.
6. Measuring usage, announcing deprecation, and removing the legacy parser following the versioning process.
7. Not changing success/failure or retry semantics just because the format changed.

A distributed client may receive a new code not present in an older version's enum. When the public protocol uses string codes, a safe fallback such as `"unknown_error"` and logging the request ID for investigation are needed; **do not guess the code from the message**. A Java `switch` on an internal enum can be exhaustive, but multi-version protocols must still account for extensibility.

## 16. Essential Test Suite

| Scenario | Result to Verify |
|---|---|
| Same error code, English/Vietnamese messages | Same branch, status, and retry policy |
| Message with added prefix, suffix, or request ID | Logic remains correct |
| Null/empty message | No NPE from message parsing |
| Two different errors sharing a keyword | Not misclassified |
| Multi-layer wrappers | `cause` and error code remain accurate |
| New unknown error code | Safe fallback, independent of wording |
| JSON response with quotes/newlines/Unicode | Serializer escapes properly |
| Error containing sensitive information | Public response/log redaction follows policy |
| Timeout/cancel/normal failure | Distinguished by contract, not regex |
| Monitoring | Stable `code` field, full message not used as label |
| Refactoring/changing translations | Machine-readable tests do not change |
| Legacy adapter | Parser is isolated, with specification and version tests |

JUnit 5 example testing independence from wording (requires the JUnit dependency and placing the test in the same package as the demo class):

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class PaymentCodeTest {
    @Test
    void localizationDoesNotChangeStatus() {
        var en = new ExceptionMessageContractDemo.PaymentFailure(
                ExceptionMessageContractDemo.FailureCode.PAYMENT_DECLINED,
                "pay-17", "Payment declined", null);
        var vi = new ExceptionMessageContractDemo.PaymentFailure(
                ExceptionMessageContractDemo.FailureCode.PAYMENT_DECLINED,
                "pay-17", "Thanh toán bị từ chối", null);

        assertEquals(402, ExceptionMessageContractDemo.stableHttpStatus(en));
        assertEquals(402, ExceptionMessageContractDemo.stableHttpStatus(vi));
        assertEquals(en.code(), vi.code());
    }
}
~~~

This test **cannot be run using plain JDK `javac` alone** because it uses JUnit 5. Tests should assert `code`/status/typed fields, not the entire message string, unless explicitly testing translations or human-facing wording.

## 17. Especially Easy-to-Miss Pitfalls

1. Using `contains("not found")` instead of a `NoSuchFileException` subtype or error code.
2. Parsing `SQLException.getMessage()` even though the API provides `getSQLState()`/`getErrorCode()`.
3. Extracting `orderId` from the message instead of passing the ID/context along with the request.
4. Using `getLocalizedMessage()` to drive workflow; changing locale changes logic.
5. Wrapping an exception and dropping `cause`, forcing adapters to scan strings from lower layers.
6. Creating error codes from the entire message, causing high cardinality in dashboards/metrics.
7. Returning raw exception messages as JSON/HTTP responses, leaking internal data.
8. Treating every `"timeout"` in text as a safely retryable error.
9. Changing a public contract from throwing to a future/result or changing error codes without a compatibility plan.
10. Treating any new string code as a known enum code without a fallback.
11. Running complex unbounded regexes on externally controlled messages.
12. Forgetting the `getMessage() == null` case or messages containing delimiters/control characters.
13. Treating the deepest cause as the entire error meaning; wrapper layers can carry important business IDs and error codes.
14. Logging sensitive messages across multiple layers when a single failure event with a code and safe context is sufficient.

## 18. Code Review Checklist

When encountering code that classifies exceptions:

1. Does any branch depend on `getMessage().contains`, `startsWith`, `split`, regex, or substring?
2. Is the message published by the API as a protocol with an official schema? If not, what should replace it?
3. Are the exception type/subtype and `code` field expressive enough for what the caller needs?
4. Is `cause` preserved when translating errors across layers?
5. Are business IDs, request IDs, and input positions passed through dedicated fields/context?
6. Do public codes have a versioning/unknown-code policy and separate message localization?
7. Do retries account for actual idempotency and side effects?
8. Are logs and metrics grouped by code/operation rather than dynamic messages?
9. Could the message contain secrets/PII? Does the public response have redaction/escaping?
10. Do tests prove that changing wording **does not change branching**?

## 19. Summary

**Do not use exception messages as a data format that other code must parse.** `Throwable.getMessage()` describes errors for humans and can change due to wording, localization, context, or dependency versions. Using it as an error code makes logic fragile and hard to test.

Clearly separate **messages** (for reading), **error codes/exception types** (for machine classification), **typed fields** (for extracting data), **causes** (for investigation), and **public error responses** (for clients to consume by schema). A simple yet very effective test is to replace an English message with a Vietnamese one while keeping the error code unchanged and requiring the handling outcome to remain **identical**.

### References

- [Java SE 17 — Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html)
- [Java SE 17 — RuntimeException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/RuntimeException.html)
- [Java SE 17 — SQLException](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLException.html)
- [Java SE 17 — ResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html)
- [Java Language Specification `11 — Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html)
