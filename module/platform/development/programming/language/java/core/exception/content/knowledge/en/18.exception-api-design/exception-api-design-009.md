# Do Not Let Dependency Library Details Become an Unintentional Public Contract

When a Java API calls a data-parsing library, HTTP client, JDBC driver, or external SDK, that library may throw very specific exceptions. If those exception types, error codes, messages, or internal handling details leak across the API boundary, API consumers will unintentionally depend on a library they did not directly choose. Replacing the library or upgrading its version later can become a breaking contract change.

The goal is to **expose stable error semantics at the functional level**, keep dependency details inside the implementation, and still preserve the information needed for diagnosis. This is a Java exception design decision; it is not necessary to create a wrapper class for every exception.

## 1. When does an exception become part of an API contract?

A method's contract does not consist only of its name, parameters, and return type. Callers also need to know:

- Under what situations the operation can fail: invalid data, non-existent resource, access denied, service temporarily unavailable...
- Which errors the caller can **handle intentionally** (fix input, retry, display a message, roll back a transaction)?
- Stable signals for classifying errors: public exception types, error codes/enums, or a documented result contract.
- Post-failure guarantees: did the operation mutate state, is it safe to retry, could data have been partially written?

Example of an **illustrative signature, not a complete Java program**:

```java
// The API accidentally forces clients to know the parser library.
public Report importReport(String input) throws VendorParseException;
```

If `VendorParseException` is a checked exception declared in `throws`, calling code must catch or redeclare it; clients may have to bring in the dependency containing that type just to compile. Even when the exception is unchecked (not required to appear in `throws`), it still creates an implicit dependency if consumers catch it specifically, check it with `instanceof`, or rely on the class name/message to make decisions.

A public `IOException` type **is not automatically a bad design**: it is a common JDK abstraction and may be the right contract for an I/O-operating API. The problem is when an API exposes an **unintended implementation detail**.

## 2. Ways dependencies leak

| Leak point | Example | Consequence |
| --- | --- | --- |
| Checked exception signature | `throws VendorParseException` | Clients are coupled to the dependency's type at compile time. |
| Untranslated unchecked exception | Vendor SDK throws `VendorTimeoutException` straight through the API | Clients may rely on the vendor class to classify errors. |
| Public type containing a dependency class | `VendorError getLastError()` | The return type also becomes part of the contract, even when `throws` is clean. |
| Internal error codes or messages | Matching `"VND-1042"` or `getMessage()` | Upgrading versions, changing languages, or swapping libraries can break logic. |
| Documentation, examples, client tests | Guiding `catch (VendorXException e)` | An initially "accidental" behavior can be treated by the community as a compatibility guarantee. |
| Error serialization | Exposing raw class names, stack traces, or `cause` in JSON returned to clients | Exposes internal structure, dependencies, and sometimes sensitive information. |

`getCause()` is useful for diagnosis, but **you should not promise that the vendor cause class will remain stable**. If a framework automatically serializes the entire throwable, you need to explicitly control the returned data; merely "wrapping" an exception while still returning the full stack trace externally does not create an information boundary.

## 3. Designing an intentional error boundary

Place an error-translation layer where the system communicates with the dependency: an adapter, repository, gateway, or service implementation. Translate the **semantics** of the error, not just the class name.

1. **List the behaviors callers need to distinguish.** For example, `INVALID_FORMAT` (fix the data), `RESOURCE_NOT_FOUND` (choose another resource), `TEMPORARY_UNAVAILABLE` (consider retrying). Only separate errors if callers need to take different actions.
2. **Choose an error contract owned by the API.** In Java, this is usually a domain-specific exception accompanied by a stable enum/error code. Keep error types specific enough to handle, avoiding a vague `RuntimeException` for every case.
3. **Catch specific error types close to the library call site.** Translate `VendorParseException` to the API's format error, `VendorTimeoutException` to a temporary error, and so on. Avoid `catch (Exception)` and labeling everything as an input error.
4. **Preserve the root cause for investigation.** Pass the caught exception to `super(message, cause)`, or use `initCause` if there is a valid reason. Do not concatenate the entire stack trace into the message.
5. **Separate public messages from diagnostic information.** User-facing messages should be stable and safe; internal logs are where operational context and the cause belong. Do not log the same stack trace multiple times at every layer.
6. **Document stable behavior.** State the public exceptions, error codes, trigger conditions, retryability, and post-failure state. Do not promise vendor behavior you cannot control.

Typical flow:

```text
Client
  → Public API / Service
      → Dependency Adapter
          → External library throws VendorParseException
      ← Adapter catches the error and translates it to ReportImportException(INVALID_FORMAT)
  ← Client handles it based on the API's error code
```

You do not need to translate every exception: programming errors such as `NullPointerException` caused by internal bugs should be fixed and logged with their true cause, rather than disguised as "invalid user data."

## 4. Standalone Java 17 example: wrapping errors and preserving the cause

Suppose a parser library can throw `VendorParseException`. A report-import API exposes `ReportImportException` and the `ReportError` code owned by the API itself. To make the example standalone without downloading dependencies, `VendorParser` below is an **internal mock library**.

Create the file `DependencyBoundaryDemo.java`:

```java
public class DependencyBoundaryDemo {

    // The public part is the error contract that clients are allowed to rely on.
    public enum ReportError {
        INVALID_FORMAT,
        TEMPORARY_UNAVAILABLE
    }

    public static final class ReportImportException extends RuntimeException {
        private final ReportError code;

        public ReportImportException(
                ReportError code, String message, Throwable cause) {
            super(message, cause);
            this.code = code;
        }

        public ReportError code() {
            return code;
        }
    }

    public static final class ReportService {
        private final VendorParser parser = new VendorParser();

        /**
         * @throws ReportImportException when the data cannot be imported.
         */
        public int importReport(String text) {
            try {
                return parser.parseTotal(text);
            } catch (VendorParseException cause) {
                throw new ReportImportException(
                    ReportError.INVALID_FORMAT,
                    "Dữ liệu báo cáo không hợp lệ",
                    cause
                );
            }
        }
    }

    // Mock dependency: vendor classes do NOT appear
    // in the public signature or public error codes of ReportService.
    private static final class VendorParser {
        int parseTotal(String text) {
            int separator = text.indexOf('=');
            if (separator < 0) {
                throw new VendorParseException("Missing '='");
            }
            try {
                return Integer.parseInt(text.substring(separator + 1));
            } catch (NumberFormatException cause) {
                throw new VendorParseException("Invalid integer", cause);
            }
        }
    }

    private static final class VendorParseException extends RuntimeException {
        VendorParseException(String message) {
            super(message);
        }

        VendorParseException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static void main(String[] args) {
        ReportService service = new ReportService();
        try {
            service.importReport("total=?");
        } catch (ReportImportException ex) {
            System.out.println(ex.code());
            System.out.println(ex.getMessage());
            System.out.println(ex.getCause() != null);
        }
    }
}
```

Compile and run:

```bash
javac DependencyBoundaryDemo.java
java DependencyBoundaryDemo
```

Expected output:

```text
INVALID_FORMAT
Dữ liệu báo cáo không hợp lệ
true
```

Explanation:

- `Integer.parseInt("?")` throws `NumberFormatException`, which the mock parser translates into `VendorParseException`.
- `ReportService.importReport` catches the exact dependency error and throws `ReportImportException` with `ReportError.INVALID_FORMAT`.
- Callers only need to handle `ReportImportException` and `code()`. Replacing `VendorParser` with another parser does not necessarily change the API contract.
- `super(message, cause)` preserves the cause chain for diagnosis; `getCause() != null` shows that this information is still present. Clients **should not inspect the vendor cause type** as a business condition.
- In a real library, you can split public types into separate files (`ReportService.java`, `ReportImportException.java`, `ReportError.java`) and place the vendor adapter in an internal package. This example uses nested classes so it only needs a single self-contained file.

`TEMPORARY_UNAVAILABLE` is declared here as an extensible code; the example **does not simulate network errors** and does not claim to handle timeouts/retries.

## 5. Checked exception or unchecked exception?

Both can create a good contract or create unintended coupling.

| Option | Suitable when | Notes |
| --- | --- | --- |
| Stable API checked exception | Callers are expected to decide how to recover and the compiler should remind them to handle it; e.g., a file-reading API exposing `IOException` or a domain API with a checked `ImportFailedException` | `throws` is part of the Java signature; adding or changing checked exceptions affects client source code. |
| Stable API unchecked exception | Not every caller has a useful way to recover, or callers handle errors at a higher boundary | Still document the error types/codes and behavior; "unchecked" does not mean "no contract." |
| Result object with error branches | Errors are an expected, frequent outcome and the business flow needs to force callers to consider all cases | Do not replace throwing exceptions for bugs or unexpected infrastructure failures. |

It is not necessary to turn every `IOException` into a custom-named exception. For a stream-reading library, `IOException` may be the stable abstraction itself; when using a specialized SDK to load a document by ID, an error code like `DOCUMENT_NOT_FOUND` or `TEMPORARY_UNAVAILABLE` may be more helpful to clients.

Do not declare `throws Exception` just to avoid choosing the right error. It makes the API unclear while still failing to prevent dependencies; `throws` also does not control all unchecked exceptions.

## 6. Translation table based on caller actions

An **illustrative** design table for a document-import API; vendor exception names are sample placeholders:

| Cause in adapter | Public exception/code to use | What should the caller do? |
| --- | --- | --- |
| `VendorParseException` due to malformed content | `INVALID_FORMAT` | Fix the file/input; retrying as-is is usually futile. |
| `VendorNotFoundException` | `RESOURCE_NOT_FOUND` | Check the ID or choose another resource. |
| `VendorTimeoutException` due to transient timeout | `TEMPORARY_UNAVAILABLE` | Retry with limits and backoff if the operation is safe to repeat. |
| `VendorAuthenticationException` due to server credentials configuration | `INTERNAL_INTEGRATION_ERROR` or an appropriate contract | Alert operations; do not mislabel it as a user input error. |
| `IllegalArgumentException` when the API detects an invalid caller argument | Can keep the JDK's `IllegalArgumentException` or expose a dedicated input error | Fix how the API is called. |
| Bugs, broken invariants, unexpected `NullPointerException` | Usually let the internal error-handling mechanism record it | Fix the code; do not try to "translate" it into a normal business error. |

Classify based on **actual meaning**, not solely on the exception name. For instance, the same `IOException` can have different causes; you cannot assume every `IOException` is safe to retry.

### Which layer should hold the exception?

An SDK-facing adapter can catch vendor types and translate them into a stable application-level technical exception. A business service can further translate that into a domain error when the context is clear enough. However, avoid pointless multi-layer wrapping:

```text
VendorTimeoutException
  → PaymentGatewayUnavailableException
  → CheckoutTemporarilyUnavailableException
```

Two translations only make sense if each layer adds distinct meaning for **that layer's own consumers**. If a service only catches and renames without adding semantics, removing one wrapper layer makes the code clearer and easier to trace.

## 7. Special situations where semantics must be preserved

**Thread interruption and task cancellation.** If an adapter catches `InterruptedException`, it usually needs to restore the interrupt flag with `Thread.currentThread().interrupt()` before translating/exiting, unless the API intentionally propagates `InterruptedException`. Do not turn a cancellation signal into an error to be retried indefinitely. `CancellationException` should also be handled according to the system's cancellation policy. The following is an **illustrative snippet**, assuming an API-defined `TaskAbortedException` type:

```java
try {
    blockingCall();
} catch (InterruptedException cause) {
    Thread.currentThread().interrupt();
    throw new TaskAbortedException("Tác vụ đã bị ngắt", cause);
}
```

**Fatal errors and bugs.** Do not use `catch (Throwable)` to wrap everything, because it also catches `Error` such as `OutOfMemoryError`. Do not indiscriminately use `catch (RuntimeException)` and convert every error into `INVALID_FORMAT`; that hides bugs and destroys error semantics.

**Closing resources.** With `try-with-resources`, errors occurring while closing a resource may reside in `getSuppressed()` of the primary exception. When translating an exception, preserving `cause` retains the trace path to the original suppressed exceptions; dropping `cause` can lose this information. Do not just take `cause.getMessage()` and throw a new exception without a cause.

**Transactions and partial writes.** A "service unavailable" exception does not by itself guarantee that the operation did not succeed on the server side. For write APIs, document idempotency, request IDs, partial-write possibilities, and retry conditions. Wrapping a transport error into a stable code is not enough to make retries safe.

**Sensitive information.** Vendor messages may contain internal URLs, SQL, table names, tokens, or user data. Do not directly use `cause.getMessage()` as the message returned to clients. Keep the cause for access-controlled logs; public messages should contain minimal sensitive information while still giving callers enough to act on.

## 8. Compatibility when replacing a dependency

Suppose the first version uses parser A, and a later version switches to parser B:

- **Before:** clients catch `ParserAException` and read an error code defined by A.
- **After, without a boundary:** clients must change imports, update `catch` blocks, and possibly understand B's error code system.
- **After, with an intentional contract:** the service still throws `ReportImportException` with `INVALID_FORMAT`; only the adapter code and error mapping change.

However, **keeping the exception name is not enough**. You must also preserve the semantics: which inputs are rejected, which error takes precedence when multiple causes exist, which error code is returned, and whether retrying is safe. Changing parsers may alter input validation criteria; if that is part of the contract, you must still evaluate compatibility and update tests/documentation.

If an older API **already exposed** a vendor exception and consumers rely on it, removing it immediately can break source code or runtime behavior. You should evaluate usage, versioning policy, deprecation/migration plans, and compatibility testing. You cannot assume that merely changing a checked exception to an unchecked one is a fully compatible upgrade.

## 9. Testing at the right boundary

Design tests around what the API promises, rather than trying to freeze library details:

1. When input has a format error, assert the **public error type**, `code() == INVALID_FORMAT`, and a safe public message. Do not assert the vendor name/message from `getCause()`.
2. For transient dependency errors, mock a timeout in the adapter, and verify the public code and the retry/idempotency policy declared by the API.
3. For unknown infrastructure errors or bugs, verify they are not misclassified as user data errors.
4. For errors with a cause, verify the cause is preserved for internal diagnosis; do not treat the **specific cause type** as an API promise.
5. When swapping libraries, rerun the vendor-independent contract test suite before publishing a new version.
6. Test JSON/log output boundaries to ensure stack traces, tokens, SQL statements, or dependency class names are not accidentally exposed to external clients.

The API's Javadoc should describe **conditions and actions**. Example for the method in this article:

```java
/**
 * Imports the total amount from the report content.
 *
 * @param text content in the form "total=123"
 * @return the total amount value
 * @throws ReportImportException if the content cannot be parsed;
 *         code() is INVALID_FORMAT when the format is invalid
 */
public int importReport(String text) {
    // Implemented in ReportService in the full example above.
    throw new UnsupportedOperationException("Minh họa chữ ký/Javadoc");
}
```

The Javadoc snippet above **only illustrates contract documentation**, not a replacement implementation for the runnable program; `UnsupportedOperationException` is a syntax placeholder in this snippet.

## 10. Common mistakes

- **Wrapping every exception in `RuntimeException("Failed")`:** loses semantics and handling guidance; if the cause is omitted, diagnostics are lost as well.
- **Using `cause.getMessage()` as the public message:** turns internal formatting into a contract and can leak sensitive data.
- **Catching `Exception` at every layer:** hides bugs, hides interruption errors, and produces many wrapper layers and hard-to-read stack traces.
- **Assuming unchecked exceptions do not affect the API:** clients can still catch or inspect them; documented promises also create constraints.
- **Inventing too many error classes:** increases complexity when callers have no different actions to take. A stable enum/error code is sometimes enough.
- **Forgetting retry semantics:** a timeout does not tell you whether the server has already processed the request.
- **Vendor-dependent tests:** asserting exact text, vendor subtypes, or stack traces causes tests to break when swapping libraries even when public behavior is correct.

## 11. Self-check for API design

Before publishing a new method or upgrading a dependency, ask yourself:

1. If we swap the library tomorrow, will callers have to import/catch different classes, change string comparisons, or change business logic?
2. Which **meaningful errors** do API consumers rely on to handle failures, and where are they documented?
3. Are the cause chain and suppressed exceptions still available for diagnosis, and is what is exposed to clients safe?
4. Does the contract clearly state post-failure state, retry conditions, and whether an error is the caller's or infrastructure's fault?
5. Are there tests confirming that public behavior **does not depend on a specific parser/SDK**?

Principle to remember: **design exceptions around what clients need to know and can handle; keep dependency error types, error codes, and messages inside the implementation, unless you intentionally choose them as the contract.**
