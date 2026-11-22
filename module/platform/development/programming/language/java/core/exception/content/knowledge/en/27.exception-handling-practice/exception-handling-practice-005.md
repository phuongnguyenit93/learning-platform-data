# Creating Business Exceptions with `cause` and Context Data in Java

When the storage layer throws an `IOException`, the business layer may need to inform the caller that the **“unable to load profile”** operation has failed. If it only throws `new RuntimeException("error")`, the reader loses the technical cause and struggles to identify the related request or object. If it simply propagates the raw `IOException`, the business API forces the caller to understand storage implementation details.

The solution is to design a **business/domain exception** with a clear contract: a **stable error code**, a descriptive message, a **`cause` that preserves the original error** when wrapping, and selective **context data** to aid diagnosis. This practice belongs to **Java Core – Exception / Practice**, using Java 17+ syntax. Standalone programs include `javac`/`java` commands and deterministic outputs; integration examples with JUnit/logger are explicitly noted.

## 1. The Problem: Technical Errors and Business Errors Are Not at the Same Abstraction Level

A processing flow typically looks like this:

```text
HTTP/CLI/Job boundary
       |
       v
ProfileService.loadProfile("P-17")
       |
       v
ProfileRepository.read("P-17")
       |
       +-- IOException("storage offline")
               |
               v
Service adds business context:
    BusinessException(
      code=PROFILE_UNAVAILABLE,
      message="Failed to load profile",
      cause=<original IOException>,
      context={operation=profile.load, profileId=P-17}
    )
               |
               v
Boundary classifies, logs with Throwable,
returns public error code or marks job as failed
```

At the repository layer, `IOException` indicates **how a technical dependency failed**. At the service layer, `PROFILE_UNAVAILABLE` indicates **which business operation did not complete**. The boundary can decide whether to return a response, display a notification, retry, or stop the job without depending on all repository implementation details.

**Do not blindly create a business wrapper for every exception.** If the error is a bug (`NullPointerException` due to faulty code), wrapping it as “profile not found” can hide the root cause and misreport the incident type. Only convert the exception type when the current layer has enough information to establish an accurate business meaning.

## 2. Four Key Parts of a Business Exception

| Component | Role | Example |
|---|---|---|
| **Exception type** | Marks the error family belonging to the business domain | `BusinessException extends RuntimeException` |
| **Error code** | Stable code for handling logic, metrics, API contract | `PROFILE_UNAVAILABLE` |
| **Message** | Explains the failure for log reading; may vary by language | `"Không tải được hồ sơ"` |
| **Cause** | Preserves the original `Throwable` to retain stack, type, and source error details | `IOException("storage offline")` |
| **Context** | Selected fields that can be processed by machines | `operation`, `profileId`, `requestId` |

An error code should have a meaning **more stable than wording**. For example, a controller can map `PROFILE_UNAVAILABLE` to an appropriate API result, while internal messages can be edited without breaking the client contract. Context allows finding the exact event in logs and correlating requests, provided it only contains data permitted to be logged.

Some design principles:

1. **Preserve the cause**, do not merely copy `cause.getMessage()` into a new string.
2. **Context data is immutable from the user's perspective**, preventing modification after the exception is created.
3. **Do not include sensitive information** such as passwords, tokens, cookies, keys, personal content, or raw payloads in the message/context.
4. **Do not turn an exception into a container for all state**: keep only the fields needed to decide on the error or investigate it.
5. **Do not return raw stack traces to end users**. Public error codes and safe messages are a separate contract from internal technical details.
6. An exception is thrown only when there is a contract failure. Do not create a `Throwable` on the happy path just in case.

## 3. Choosing `RuntimeException` or Checked `Exception`?

Both approaches are valid, depending on the API design:

- `extends RuntimeException`: the caller is not forced by the compiler to `catch`/`throws`; suitable if this is a business failure handled at the application boundary or if most callers cannot recover immediately.
- `extends Exception`: the caller must catch or declare it; suitable if the API **intentionally requires** the caller to consider the failure possibility and choose a recovery path.

There is no rule that *every business exception must be unchecked* or *every business exception must be checked*. What matters is that the API expresses **recoverability, predictability, and handling responsibility**.

Minimal unchecked class example:

```java
public final class ProfileUnavailableException
        extends RuntimeException {
    public ProfileUnavailableException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
```

This is **a standalone class definition that can be saved in** `ProfileUnavailableException.java`. However, it only holds message/cause; to classify multiple scenarios and attach context, we will build a more complete version in the next example.

If an error **is already a domain exception with the right code/context**, upper layers can propagate it instead of wrapping it again in a similar type. Layered wrapping without adding semantics creates long stack traces and unnecessary `Caused by` chains.

## 4. Main Practice: Exception with Error Code, `cause`, and Immutable Context

Create the file `BusinessExceptionDemo.java`:

```java
import java.io.IOException;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;

public class BusinessExceptionDemo {
    enum ErrorCode {
        PROFILE_UNAVAILABLE
    }

    static final class BusinessException extends RuntimeException {
        private final ErrorCode code;
        private final Map<String, String> context;

        BusinessException(
                ErrorCode code,
                String message,
                Throwable cause,
                Map<String, String> context) {
            super(message, cause);
            this.code = Objects.requireNonNull(code, "code");
            this.context = Map.copyOf(
                    Objects.requireNonNull(context, "context"));
        }

        ErrorCode code() {
            return code;
        }

        Map<String, String> context() {
            return context;
        }
    }

    @FunctionalInterface
    interface ProfileSource {
        String read(String profileId) throws IOException;
    }

    static String loadProfile(
            String profileId, ProfileSource source) {
        Objects.requireNonNull(profileId, "profileId");
        Objects.requireNonNull(source, "source");

        try {
            return source.read(profileId);
        } catch (IOException cause) {
            throw new BusinessException(
                    ErrorCode.PROFILE_UNAVAILABLE,
                    "Không tải được hồ sơ",
                    cause,
                    Map.of(
                            "operation", "profile.load",
                            "profileId", profileId));
        }
    }

    public static void main(String[] args) {
        String value = loadProfile("P-17", id -> "Lan");
        System.out.println("success = " + value);

        try {
            loadProfile("P-17", id -> {
                throw new IOException("storage offline");
            });
        } catch (BusinessException error) {
            System.out.println("code = " + error.code());
            System.out.println("message = " + error.getMessage());
            System.out.println("cause = "
                    + error.getCause().getClass().getSimpleName()
                    + ": " + error.getCause().getMessage());
            System.out.println("context = "
                    + new TreeMap<>(error.context()));
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac BusinessExceptionDemo.java
java BusinessExceptionDemo
```

Exact output:

```text
success = Lan
code = PROFILE_UNAVAILABLE
message = Không tải được hồ sơ
cause = IOException: storage offline
context = {operation=profile.load, profileId=P-17}
```

### Explanation of Each Component

- `ErrorCode` is an enum. `PROFILE_UNAVAILABLE` is used to classify the error, independent of the Vietnamese message content.
- `BusinessException extends RuntimeException` retains all `Throwable` behavior, including stack trace, `getCause()`, and `getSuppressed()`.
- `super(message, cause)` is the most important line for **exception chaining**. It links the business error to the original `IOException`.
- `context` is `Map<String,String>`. `Map.copyOf(...)` creates a map that cannot be modified via standard APIs; the example uses `String` values only, which are immutable.
- `Objects.requireNonNull(...)` rejects a null `code` or context map at construction time; `Map.copyOf` does not accept null keys or values.
- `ProfileSource` acts as a dependency that can be replaced by a fake lambda. No database or network is needed to reproduce the success/failure paths.
- Only the service layer knows the business operation `"profile.load"` and `"P-17"`, so it adds the exact context here.
- `new TreeMap<>(error.context())` is used **only for printing the example** to ensure deterministic key ordering. `Map.copyOf` does not guarantee an iteration order suitable for hard-coded output.

On the success path, no business exception is created. On the error path, the caller receives business information, while `getCause()` still holds the technical error. When the logger prints the full `Throwable`, the stack trace can display the `Caused by:` branch for `IOException`.

### Why Not Pass the Map Directly to the Constructor and Keep the Reference?

If you only do:

```java
this.context = context;
```

a caller holding the original `HashMap` could modify the fields after the exception is created. By the time logging occurs, the context would no longer reflect the initial failure situation. With `Map.copyOf`, key/value pairs are copied into a collection that cannot be modified through the returned map.

Note: **an immutable map does not mean deep immutability if values are mutable objects**. Using `Map<String,String>` or bounded immutable values makes control much simpler than `Map<String,Object>` containing entities, sessions, request bodies, or objects with mutable state.

## 5. Verifying Immutability and Cause Identity

A well-designed business exception can be passed across multiple layers after instantiation. Those layers must see the same error code, the same captured context, and the same root cause that was passed in.

File `BusinessExceptionInvariantDemo.java`:

```java
import java.io.IOException;
import java.util.HashMap;
import java.util.Map;

public class BusinessExceptionInvariantDemo {
    static class BusinessException extends RuntimeException {
        private final String code;
        private final Map<String, String> context;

        BusinessException(
                String code, String message,
                Throwable cause, Map<String, String> context) {
            super(message, cause);
            this.code = code;
            this.context = Map.copyOf(context);
        }

        String code() {
            return code;
        }

        Map<String, String> context() {
            return context;
        }
    }

    public static void main(String[] args) {
        IOException original = new IOException("disk error");

        Map<String, String> input = new HashMap<>();
        input.put("operation", "report.export");

        BusinessException error = new BusinessException(
                "REPORT_UNAVAILABLE",
                "Không xuất được báo cáo",
                original,
                input);

        input.put("operation", "changed later");

        System.out.println("code = " + error.code());
        System.out.println("cause identity = "
                + (error.getCause() == original));
        System.out.println("snapshot = "
                + error.context().get("operation"));

        try {
            error.context().put("operation", "tampered");
        } catch (UnsupportedOperationException expected) {
            System.out.println("context modifiable = false");
        }
    }
}
```

Commands:

```bash
javac BusinessExceptionInvariantDemo.java
java BusinessExceptionInvariantDemo
```

Output:

```text
code = REPORT_UNAVAILABLE
cause identity = true
snapshot = report.export
context modifiable = false
```

Meaning:

1. After creating the exception, mutating `input` does not alter the stored context.
2. `error.getCause() == original` proves **the exact cause object** was preserved, rather than creating a new exception with the same message.
3. Callers cannot modify the returned map via `put`.
4. Message and error code provide two distinct contract layers: human explanation and machine classification.

The demo program uses a minimal constructor without enforcing `code != null`. In production designs, add checks for required parameters and corresponding tests. This does not change the practice's takeaway regarding context/cause snapshots.

## 6. Which Context Data Fields Are Useful?

**Context is not a copy of the entire request.** It should answer a few essential diagnostic questions:

- **What was being done?** `operation=invoice.export`, `resource=profile`.
- **Which object was involved?** `profileId=P-17`, `orderId=O-42`, with validated IDs.
- **Can logs be correlated?** `requestId=R-103`, system-generated/managed `traceId`.
- **At which phase did it fail?** `phase=repository.read`, `attempt=3`, `dependency=profile-store`.
- **Is there an error code for grouping?** `PROFILE_UNAVAILABLE` should be a dedicated field, without needing to embed it into every message.

Information that **should not** appear in exception context or message: passwords, JWTs, cookies, authorization headers, API keys, credit cards, raw request bodies, sensitive medical/personal information, or entire entities with uncontrolled `toString()`.

Use only an **allowlist** of permitted fields. Even IDs should be length-bounded and follow data logging policies. Unvalidated client data should not be placed directly into logs as a trusted ID.

### Representation Options

| Representation | Advantages | Points to Note |
|---|---|---|
| `Map<String,String>` | Easy to extend, works well with structured logging | Must manage keys, values, size, and avoid typos in keys |
| Explicit fields like `orderId`, `operation` | Compiler helps enforce types and requiredness | Increases number of constructors/types when there are many error groups |
| `record ErrorContext(...)` | Structurally immutable in Java 17, expresses schema | Need to decide which fields are common to all errors |
| A single `details` string | Simple initially | Hard to search/classify and easy to mix in sensitive data |
| Arbitrary `Map<String,Object>` | Flexible | Hard to guarantee deep immutability and safe serialization |

If a domain has a few main error types with fixed fields, a **strongly typed** context class/record may be better than a map. If a unified error system across many operations is needed, a map with an allowlist/validation is also valuable.

### How to Bound Context Before Creating an Exception

Example **illustrative snippet**:

```java
static String safeId(String raw) {
    if (raw == null || !raw.matches("[A-Za-z0-9_-]{1,32}")) {
        return "unavailable";
    }
    return raw;
}
```

The method above illustrates how to restrict the length and characters of a **technical ID**. Do not use this regex for human names or internationalized data if the purpose differs. On the error path, avoid computing context via a new DB/HTTP call just to make the message look nicer; that secondary operation could also fail and mask the original cause.

## 7. `cause` Differs from Context Data

`cause` is a **`Throwable` object**, having its own type, message, and stack. Context is **metadata for understanding the operation**, not the cause.

Example:

```text
BusinessException
  code    = PROFILE_UNAVAILABLE
  message = Failed to load profile
  context = {profileId=P-17, operation=profile.load}
  cause   = IOException("storage offline")
```

Two mistakes to avoid:

1. Only storing `context.put("rootCause", e.toString())` without passing `e` to the constructor. This loses the original type/stack and the standard `Caused by` chain.
2. Only passing the cause without adding context at the boundary that knows the operation. Later callers might see `"connection refused"` without knowing which business operation it belonged to.

**No need to wrap multiple times if context is already sufficient.** A business exception may pass through a controller, job runner, or mapper; those layers typically read code/context rather than creating new wrappers.

If a `Throwable` originates from an asynchronous callback, you may encounter `CompletionException` or `ExecutionException` at the observing layer. Classify the **observed error layer** properly and keep the real cause; do not create a wrapper just because you see the name `CompletionException`.

## 8. Checked Business Exception: Another Option for Public Contracts

A report export task may publicly declare that the caller **must account for business failures**. In that case, using `extends Exception` is a well-founded choice.

File `CheckedBusinessExceptionDemo.java`:

```java
import java.io.IOException;

public class CheckedBusinessExceptionDemo {
    static final class ExportException extends Exception {
        private final String code;
        private final String reportId;

        ExportException(
                String code, String reportId,
                String message, Throwable cause) {
            super(message, cause);
            this.code = code;
            this.reportId = reportId;
        }

        String code() {
            return code;
        }

        String reportId() {
            return reportId;
        }
    }

    @FunctionalInterface
    interface ReportSource {
        String read() throws IOException;
    }

    static String export(
            String reportId, ReportSource source)
            throws ExportException {
        try {
            return source.read();
        } catch (IOException cause) {
            throw new ExportException(
                    "REPORT_SOURCE_FAILED",
                    reportId,
                    "Không xuất được báo cáo",
                    cause);
        }
    }

    public static void main(String[] args) {
        try {
            System.out.println("success = "
                    + export("R-7", () -> "ready"));

            export("R-7", () -> {
                throw new IOException("source disconnected");
            });
        } catch (ExportException error) {
            System.out.println("code = " + error.code());
            System.out.println("reportId = " + error.reportId());
            System.out.println("cause = "
                    + error.getCause().getClass().getSimpleName());
        }
    }
}
```

Run:

```bash
javac CheckedBusinessExceptionDemo.java
java CheckedBusinessExceptionDemo
```

Output:

```text
success = ready
code = REPORT_SOURCE_FAILED
reportId = R-7
cause = IOException
```

`export(...)` declares `throws ExportException`. The caller must catch or propagate this checked exception. `reportId` is represented as a dedicated field: if this is a required domain field, an explicit field gives the API a stronger contract than an arbitrary map key.

The example intentionally has no external dependencies beyond the JDK. In real systems, consider constructor null checks for `code`/`reportId`, ID length-bounding policies, and protecting diagnostic information.

## 9. Do You Need a Constructor Without `cause`?

Not every business exception is caused by another exception. A validation such as “quantity must be positive” can be detected **directly**:

```java
if (quantity <= 0) {
    throw new BusinessException(
            ErrorCode.INVALID_QUANTITY,
            "Số lượng phải lớn hơn 0",
            null,
            Map.of("field", "quantity"));
}
```

This is an **illustrative snippet** using a class/enum structure similar to the main example; `INVALID_QUANTITY` must be added to the corresponding enum. In this case **there is no source `Throwable`**, so `cause == null` is appropriate. Do not create a fake `IllegalArgumentException` just so the constructor always has a cause.

If the class serves both direct errors and wrapped errors, you can provide two constructors:

```java
BusinessException(
        ErrorCode code, String message,
        Map<String, String> context) {
    this(code, message, null, context);
}

BusinessException(
        ErrorCode code, String message,
        Throwable cause, Map<String, String> context) {
    super(message, cause);
    this.code = Objects.requireNonNull(code);
    this.context = Map.copyOf(context);
}
```

These are **illustrative constructors located inside the `BusinessException` class** with `code` and `context` fields; `Map` and `Objects` imports are required. They do not form a standalone class if you only copy these two snippets.

Constructors should have a consistent, documented parameter order; APIs with too many `String`-typed parameters are very easy to pass in the wrong order. If the context has many fields, consider using a dedicated `ErrorContext` object or clearly named factory methods.

## 10. Do Not Couple Business Exceptions to a Logging Framework

A business exception should be **data about an error and an error-propagation mechanism**, not the place that directly decides to log, return HTTP responses, or retry.

Avoid:

```java
BusinessException(...) {
    logger.error("...", cause);
    // and then the outer caller logs the same error again
}
```

This is a **discouraged** idea. A self-logging constructor can emit an `ERROR` entry even when the caller recovers; it also couples tests and domain classes to logging infrastructure.

Instead:

```text
Repository: throws appropriate technical error
Service: adds business context/cause if needed
Controller/Job boundary: decides handling and logs according to a single policy
Error mapper: creates a safe public response
```

If an error is recovered in the service (e.g., via fallback), the service can report a metric or appropriate event. If the error is not recovered and reaches the final boundary, one log entry with the full `Throwable`/cause/context is usually far more valuable than duplicate logs at every `catch`.

A domain exception should also not open network connections, query a data store, or perform I/O upon construction. Doing so can slow down the error path or throw a new exception that masks the original error.

## 11. When Cleanup Fails: Preserve `Suppressed` Alongside `cause`

A real-world failure can contain **multiple incidents**:

1. The processing body throws `IOException("write failed")`.
2. `close()` also throws `IOException("close failed")`.
3. The service wraps the primary error into a business exception.

If `try-with-resources` is used, the close error is stored **in `getSuppressed()` of the primary error**, rather than automatically becoming `getCause()` of the business exception. When wrapping, it is important to **preserve the source `Throwable`**, because it carries the suppressed information as well.

File `BusinessExceptionSuppressedDemo.java`:

```java
import java.io.IOException;

public class BusinessExceptionSuppressedDemo {
    static final class FailingResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    static final class ExportException extends RuntimeException {
        ExportException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static void writeReport() throws IOException {
        try (FailingResource resource = new FailingResource()) {
            throw new IOException("write failed");
        }
    }

    static void exportReport() {
        try {
            writeReport();
        } catch (IOException cause) {
            throw new ExportException(
                    "Không thể ghi báo cáo", cause);
        }
    }

    public static void main(String[] args) {
        try {
            exportReport();
        } catch (ExportException error) {
            Throwable root = error.getCause();
            System.out.println("outer = "
                    + error.getClass().getSimpleName());
            System.out.println("cause = " + root.getMessage());
            System.out.println("suppressed count = "
                    + root.getSuppressed().length);
            System.out.println("suppressed = "
                    + root.getSuppressed()[0].getMessage());
        }
    }
}
```

Compile and run:

```bash
javac BusinessExceptionSuppressedDemo.java
java BusinessExceptionSuppressedDemo
```

Output:

```text
outer = ExportException
cause = write failed
suppressed count = 1
suppressed = close failed
```

`BusinessException` here is simplified to `ExportException` holding only message/cause to highlight the `Suppressed` mechanism. In a full domain exception pattern, add error code and context as in the main example.

**Do not overwrite `cause` with the cleanup exception.** `Caused by` answers the causal relationship between the wrapper and the source error, while `Suppressed` holds the secondary cleanup error. A business exception can have its own suppressed array if code calls `addSuppressed`; in this example, the suppressed exception resides on the **root `IOException`**. Therefore `error.getSuppressed()` may be empty while `error.getCause().getSuppressed()` has elements.

## 12. At the API Boundary: Separate Internal Details from the Response

A business exception may carry rich investigative data, but the public response must follow a **separate contract**.

Conceptual example:

```text
Internal BusinessException:
    code    = PROFILE_UNAVAILABLE
    message = Failed to load profile
    cause   = IOException("storage offline")
    context = {profileId=P-17, operation=profile.load}

Public response:
    errorCode = PROFILE_UNAVAILABLE
    message   = Service temporarily unavailable
    requestId = R-103
```

This is a **data description**, not a mandatory standard JSON/API schema. Do not expose raw stack traces, file paths, DB structures, SQL, credentials, or source exception contents in the HTTP body.

Plain Java example illustrating classification:

```java
static int httpStatusFor(String code) {
    return switch (code) {
        case "INVALID_QUANTITY" -> 400;
        case "PROFILE_UNAVAILABLE" -> 503;
        default -> 500;
    };
}
```

This is an **illustrative method** inside a class, not a complete HTTP server. 400/503 are merely suggested policies for the corresponding cases. For resource-not-found, state-conflict, or access-denied errors, decide the status based on the service contract, not solely on the class name.

**Be careful with 4xx/5xx:** an `IllegalArgumentException` may originate from a server bug rather than client input. Only map to 400 when there is evidence the error is the request's responsibility. Do not classify all unchecked exceptions as “user errors”.

### Logger Integration Snippet

With an SLF4J-compatible logger API:

```java
logger.error(
        "operation={} errorCode={} requestId={} context={}",
        operation,
        businessError.code(),
        requestId,
        businessError.context(),
        businessError);
```

This is an **integration snippet**, requiring a logging library/logger and the declared variables. `businessError` is the **`Throwable` object as the last argument**; with APIs supporting this signature, the logger can print the stack trace, cause, and suppressed exceptions. Check the overloads/structured-logging API of your library version.

In production, sometimes you do not need to print the entire context as `toString()`: the logger can record structured fields and apply better masking/retention. Avoid logging in the repository, service, and global handler if they are all reporting **the same final failure**.

## 13. Standard Pattern: Translate Errors at the Boundary with Sufficient Context

Responsibilities can be divided as follows:

```text
Repository
  readProfile(id) throws IOException
      |
      +-- does not create business codes that belong only to the service
      |
Service
  loadProfile(id)
      |
      +-- catches IOException that can be mapped to a domain error
      +-- creates BusinessException(P... , cause, validated context)
      |
Boundary
  onFailure(BusinessException)
      |
      +-- classifies code, metrics, logs, response/job outcome
```

Review questions when seeing a `catch`:

- **Does this layer truly understand the cause in business terms?** If not, propagate it or use a meaningful technical exception.
- **Is there already an equivalent business exception?** If so, wrapping it again is usually unnecessary.
- **Which context does the current layer know for certain?** Do not fabricate a fake `requestId` or guess a transaction ID.
- **Is the exact original `Throwable` preserved?** Do not keep only the message.
- **What should the end user see?** This is the responsibility of the boundary/API mapper.
- **Does it need to be logged right now?** If it will be rethrown and the final handler already logs it, avoid duplicate logs.

When an operation has retries, context can add `attempt=3` or `retryExhausted=true` as safe fields. However, do not log `ERROR` with full stack traces for every unfinished attempt; a final error with good context usually reflects the outcome accurately.

## 14. Designing a Strongly Typed Context When Needs Are Fixed

With a few required fields, a `record` in Java 17 offers a clean option:

```java
record ErrorContext(
        String operation,
        String resourceId,
        String correlationId) {
}
```

This is **a record that can be placed in a separate file or an appropriate package**. The record itself has final components and accessors; however, if a component is a mutable object, the record does not automatically deep-copy it. With `String`, the data is immutable.

A business exception class can hold:

```java
private final ErrorContext context;

BusinessException(
        ErrorCode code,
        String message,
        Throwable cause,
        ErrorContext context) {
    super(message, cause);
    this.code = Objects.requireNonNull(code);
    this.context = Objects.requireNonNull(context);
}
```

This is an **illustrative constructor snippet** belonging to a class with declared `code` and `context` fields. Advantage: the compiler helps catch misspelled field names, the IDE supports navigation, and key fields appear directly in the API. Disadvantage: the schema is less flexible than a map across many operation types.

Distinguish using a `record` for **context** from using a record as an **exception**: a Java record implicitly extends `java.lang.Record`, so a record **cannot simultaneously extend `RuntimeException`**. To create a custom `Throwable`, use `class extends Exception/RuntimeException`.

## 15. Context Does Not Replace Stack Trace and Message

An anti-pattern:

```java
throw new IllegalStateException(
        "PROFILE_UNAVAILABLE; "
        + "profileId=" + id
        + "; cause=" + cause.getMessage());
```

This is an **illustrative snippet** inside a `catch`. It mixes error code, context, and cause description into a single string. Without passing `cause` to the constructor, the caller loses the **original `Throwable` type and stack trace**. The message string is also hard to parse and prone to breaking due to language changes or escaping.

Better pattern:

```java
throw new BusinessException(
        ErrorCode.PROFILE_UNAVAILABLE,
        "Không thể tải hồ sơ",
        cause,
        Map.of("profileId", id, "operation", "profile.load"));
```

This is an **illustrative snippet** using the exception definition from Section 4. The error code is for decision-making, context is for log filtering, message is for human readers, and cause is for the technical reason. These roles complement one another.

Do not rely on `Throwable.toString()` as a storage format for machines to parse; `toString()` mainly combines the class name and `getLocalizedMessage()`. For machine readability, use dedicated fields/codes.

## 16. Thoroughly Testing the Error Code, Cause, Context, and Success Path Contract

JUnit Jupiter helps test exception types and fields. Below is a **JUnit 5 integration example**, assuming the `BusinessExceptionDemo` class from Section 4 is accessible from tests in the same package.

File `BusinessExceptionContractTest.java`:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.io.IOException;
import org.junit.jupiter.api.Test;

class BusinessExceptionContractTest {
    @Test
    void returnsProfileOnSuccess() {
        String value = BusinessExceptionDemo.loadProfile(
                "P-17", id -> "Lan");

        assertEquals("Lan", value);
    }

    @Test
    void keepsBusinessCodeCauseAndContextOnFailure() {
        IOException root = new IOException("storage offline");

        BusinessExceptionDemo.BusinessException error =
                assertThrows(
                    BusinessExceptionDemo.BusinessException.class,
                    () -> BusinessExceptionDemo.loadProfile(
                        "P-17", id -> { throw root; }));

        assertEquals(
                BusinessExceptionDemo.ErrorCode.PROFILE_UNAVAILABLE,
                error.code());
        assertSame(root, error.getCause());
        assertEquals("P-17", error.context().get("profileId"));
        assertEquals("profile.load",
                error.context().get("operation"));
        assertThrows(
                UnsupportedOperationException.class,
                () -> error.context().put("other", "value"));
    }
}
```

The test requires the `org.junit.jupiter` dependency and a Maven/Gradle/IDE test runner. Do not run it directly with `java BusinessExceptionContractTest` without setting up the test environment. The nested classes of the main example have default package-private visibility, so place the test in the same package if keeping the code as-is.

**Why are these assertions useful?**

- The success test proves the valid path does not throw a business exception and returns the expected value.
- `assertThrows` verifies **the exact exception type per the contract**; it accepts subclasses. If the contract requires the exact class, consider `assertThrowsExactly` when JUnit supports it.
- `assertSame(root, error.getCause())` verifies that **the exact cause object** is preserved, rather than creating a new similar `Throwable`.
- The two context assertions verify that context remains accurate when the error is propagated.
- Attempting `put` confirms that the context map view cannot be modified.

### Testing a Validation Error Without a Cause

If an API creates a business exception **directly** due to invalid input, expectations might be:

- `error.code() == INVALID_QUANTITY`.
- `error.getCause() == null` when there is no source error.
- Context contains only safe field/constraint names.
- No side effects on the data store.

Do not force every exception to have a non-null cause. **A cause is required when wrapping an actual error; a cause does not necessarily exist when directly detecting a business rule violation.**

## 17. Plain JDK Testing Without a Framework

If you want to quickly verify a contract without JUnit, you can write your own assertions. File `BusinessExceptionSmokeTest.java`:

```java
import java.io.IOException;
import java.util.Map;

public class BusinessExceptionSmokeTest {
    static final class DomainFailure extends RuntimeException {
        private final String code;
        private final Map<String, String> context;

        DomainFailure(
                String code, Throwable cause,
                Map<String, String> context) {
            super("read failed", cause);
            this.code = code;
            this.context = Map.copyOf(context);
        }

        String code() {
            return code;
        }

        Map<String, String> context() {
            return context;
        }
    }

    static void check(boolean condition) {
        if (!condition) {
            throw new AssertionError("Contract violated");
        }
    }

    static String read(boolean fail) {
        if (!fail) {
            return "OK";
        }

        IOException root = new IOException("offline");
        throw new DomainFailure(
                "READ_UNAVAILABLE",
                root,
                Map.of("operation", "data.read"));
    }

    public static void main(String[] args) {
        check("OK".equals(read(false)));
        System.out.println("success tested");

        try {
            read(true);
            throw new AssertionError("Expected DomainFailure");
        } catch (DomainFailure e) {
            check("READ_UNAVAILABLE".equals(e.code()));
            check(e.getCause() instanceof IOException);
            check("data.read".equals(
                    e.context().get("operation")));

            System.out.println("failure tested");
            System.out.println("cause = "
                    + e.getCause().getClass().getSimpleName());
        }
    }
}
```

Compile and run:

```bash
javac BusinessExceptionSmokeTest.java
java BusinessExceptionSmokeTest
```

Output:

```text
success tested
failure tested
cause = IOException
```

This is a standalone test example for a small exception class, independent of the first demo. If the code were changed to **swallow the error** and return `"OK"`, the failure-path test throws `AssertionError`. If the cause or error code is omitted, the checks also catch it. These custom assertions illustrate contract thinking; in larger projects, use a testing library for better reporting, fixtures, and suite management.

## 18. Controlling Logs and Observability

A business exception with context does not automatically mean it should be logged at every layer. The decision to log should belong to the component that knows **the final outcome** of the request/job.

A practical policy:

| Case | Action | Appropriate Log |
|---|---|---|
| Repository throws `IOException`, service will wrap it | Propagate error, preserve cause | Usually no duplicate `ERROR` needed |
| Service catches error and recovers via fallback | Return fallback data, report metric | `INFO`/`WARN` or metric based on impact |
| `BusinessException` reaches global handler and request fails | Map error code/status, log full `Throwable` once | `ERROR` if it is an unexpected failure/needs investigation |
| Invalid client input per contract | Create validation error with clear code | Can be `INFO`/metric, not `ERROR` stack by default |
| Expected cancellation/interrupt | Cooperate to stop and clean up | Usually not a business error |
| Cleanup error has independent consequences | Preserve suppressed, assess incident | Can log a separate event if independently meaningful |

To correlate logs across layers, use a request ID or trace ID generated at the entry boundary and passed through context/telemetry. If using `ThreadLocal`/MDC in asynchronous tasks, ensure proper propagation and cleanup mechanisms; do not assume a new thread automatically inherits the caller's context.

Do not put an entire stack trace into `context` as a string. `Throwable` already holds stack, `Caused by`, and `Suppressed` information; the logger should be configured to record those structures when needed.

## 19. Common Implementation Mistakes

### 19.1. Creating a New Exception Without Passing `cause`

Wrong:

```java
catch (IOException e) {
    throw new BusinessException(
            ErrorCode.PROFILE_UNAVAILABLE,
            "Không tải được hồ sơ",
            null,
            Map.of("operation", "profile.load"));
}
```

The snippet above uses the main example class. `null` breaks the causal chain even though `e` exists. Fix it by passing `e` as the cause parameter.

### 19.2. Keeping Only the Raw `getMessage()` of a Technical Error

```java
throw new RuntimeException("Source failed: " + e.getMessage());
```

This illustrative snippet can lose the original exception type and stack; messages can vary by library/JDK. If wrapping is needed, use a constructor that accepts `Throwable`, and let the logger print the cause.

### 19.3. Turning an Exception into an Automatic Logger

A `BusinessException` constructor calling `logger.error` creates a log entry on every instantiation, even when the caller recovers. Separate event logging from error data to avoid repeating stack traces across multiple layers.

### 19.4. Letting Context Reference a Mutable Map

Keeping a reference to the input `HashMap` allows the context to be modified after the error occurs. Use `Map.copyOf`, `Collections.unmodifiableMap` on a copy, or a record with immutable values.

### 19.5. Using `Map<String,Object>` to Store Entire Entities

Objects can mutate, `toString()` can be expensive, or it may expose data. Store only safe, normalized, bounded fields.

### 19.6. Using Error Messages as Error Codes

Comparing `"Không tìm thấy hồ sơ"` in control logic easily breaks when changing languages or editing wording. Use a stable enum/string code.

### 19.7. Mapping Every `RuntimeException` to an Input Error

A `NullPointerException` from a server bug is not automatically an HTTP 400. You must determine whether the error was caused by the client violating the contract.

### 19.8. Re-wrapping Business Exceptions at Every Layer

Three layers all doing `throw new BusinessException(..., caught)` creates unnecessary wrapper layers; investigation becomes harder and context information tends to duplicate. Only add a wrapper if changing **semantics** or the layer's contract.

### 19.9. Using Exceptions to Carry Sensitive Data

Do not put tokens, secrets, SQL containing data, private addresses, or user payloads into context. Logs are stored and accessed in places separate from the business processing flow; privacy must be part of exception design.

### 19.10. Letting Message Construction Cause a New Error

A message supplier that performs I/O or serializes overly large objects can trigger a second error, masking the primary error. Messages and context should be prepared from **readily available, cheap, and reliable information** on the error path.

### 19.11. Confusing `cause` with `suppressed`

A `close()` error occurring after a primary processing error is usually **suppressed**. Do not manually replace the cause with the cleanup error; use `try-with-resources` or a mechanism that preserves both exceptions.

### 19.12. Tests Only Checking for `RuntimeException`

Overly broad tests can pass due to an unexpected `NullPointerException`. Check the exact business exception, code, cause, and context; add success tests to avoid regressions in normal behavior.

## 20. Workflow for Building Business Exceptions in Real Projects

You can apply the following order:

1. **List business scenarios that genuinely need classification**: invalid validation, resource unavailable, conflict, dependency failure, operation rejected.
2. **Define the contract with callers**: checked/unchecked, exception type, public error code, retryability, display message.
3. **Choose the context schema**: validated ID/operation/correlation ID, allowlisted and size-bounded; do not store secrets.
4. **Define immutable exception fields**: `final`, read-only getters, `Map.copyOf`, or a context record with immutable data.
5. **Preserve the cause** when wrapping technical errors at a boundary with sufficient semantic meaning.
6. **Preserve suppressed exceptions** if cleanup also fails; prefer `try-with-resources`.
7. **Wrap only at the appropriate layer**, avoiding duplicate log-and-throw at every `catch`.
8. **Map at the boundary**: translate `ErrorCode` into a safe response/job result, and log the `Throwable` with context at the responsible place.
9. **Test both paths**: success, failure, cause identity, context snapshot, required fields, cleanup side effects.
10. **Monitor in production**: metrics by error code/operation, trace ID, error rate, retry outcome, and log-protection policies.

### Quick Pre-Merge Checklist

- Does the exception type accurately reflect the contract and do callers know how to handle it?
- Is `ErrorCode` stable and independent of message wording?
- Does the wrapping constructor call `super(message, cause)`?
- If it is a directly detected validation error, is `cause` being `null` appropriate?
- Is the context immutable, containing only safe, stable, and sufficient fields?
- Are whole entities, request bodies, tokens, and mutable objects avoided?
- Are both `cause` and `suppressed` preserved if both processing and cleanup fail?
- Is a single layer responsible for mapping results/logs rather than logging repeatedly across layers?
- Do tests verify success, exception type, error code, `getCause()`, context, and side effects?
- Is the public response separated from sensitive technical details in the `Throwable`?

**Conclusion:** a good business exception is a **structured error contract**, not a long message string. Use an appropriate exception type, a **stable error code**, a helpful message, `super(message, cause)` to preserve the root cause, and **immutable, safe context** for diagnosis. Only convert error types where business semantics are understood, preserve suppressed exceptions when cleanup fails, and test both the success path and the error path.
