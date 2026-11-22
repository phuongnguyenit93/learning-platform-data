# Preserving the Cause When Translating Technical Errors into Meaningful Exceptions for the Caller in Java

## 1. Objectives

After completing this lesson, you will be able to:

- Distinguish between **exceptions exposed to the caller** and **technical exceptions that caused the failure**.
- Use constructors with a <code>Throwable cause</code> parameter to translate errors without losing the original failure trace.
- Explain how <code>getCause()</code>, stack traces, <code>printStackTrace()</code>, and the <code>Caused by</code> chain support error investigation.
- Distinguish the cause from suppressed exceptions, messages, and information that should be displayed to the user.
- Verify that error translation preserves the **exact cause object**, while avoiding redundant wrapping, hiding errors, or leaking infrastructure details.

## 2. The Problem: One Failure with Two Perspectives

Suppose an API provides the operation <code>getDocument("guide")</code>. The caller only cares about whether the document can be read. Whether the document resides on a filesystem, a database, or a remote service is an implementation detail.

During reading, the technical layer may throw <code>java.nio.file.NoSuchFileException</code> or <code>java.io.IOException</code>. If the API wants to provide a stable error language, it may throw <code>DocumentNotFoundException</code> or <code>DocumentReadException</code> to the caller.

The issue is this: if you only create a new exception with the message "Unable to read document", we know **which operation failed** but may lose **which technical cause led to the failure**. Therefore, a good translation needs to preserve both pieces of information simultaneously:

| Component | Question Answered | Example |
| --- | --- | --- |
| Outer exception (translated exception) | How did the operation at the API layer fail? | <code>DocumentReadException</code> |
| Outer exception message | What context is useful for the caller? | "Unable to read document: guide" |
| Cause | What directly caused the operation to fail at the lower layer? | The original <code>IOException</code> object |
| Stack trace | Through which execution locations was the exception created/thrown? | The data reading location and the exception translation location |

**Preserving the cause** means keeping a reference to the exception object that caused the error and linking it to the new exception, typically with <code>super(message, cause)</code>. The cause is not replaced by a character string or by a new exception of the same type.

Model:

~~~text
Caller: DocumentGateway.get("guide")
                |
                v
       Technical error: IOException
                |
                | catch (IOException original)
                v
   DocumentReadException("Unable to read...", original)
                |
                +---- outer exception: message per the API contract
                |
                +---- getCause(): the original IOException object itself
~~~

Translating the error type and preserving the cause are two related but distinct responsibilities. There are situations where the original exception should be kept without creating a new wrapper; when translation is genuinely needed, preserving the cause helps avoid losing information.

## 3. Cause in Java's Exception Mechanism

The root class <code>java.lang.Throwable</code> provides important mechanisms:

| API | Meaning |
| --- | --- |
| <code>getMessage()</code> | The detail message of the exception currently being inspected; may be <code>null</code> |
| <code>getCause()</code> | The exception linked as the cause of the current exception; may be <code>null</code> |
| <code>printStackTrace()</code> | Prints the stack trace along with the cause/suppressed chain when present, for diagnostics |
| <code>getStackTrace()</code> | Retrieves the stack trace of this <code>Throwable</code> itself as an array of elements |
| <code>getSuppressed()</code> | Retrieves exceptions retained as *suppressed*, not the primary cause |

A <code>Throwable</code> object has at most **one direct cause**, but that cause can also have its own cause, forming a chain. For example:

~~~text
DocumentExportException
    caused by -> DocumentReadException
        caused by -> IOException
~~~

Here:

- <code>exportFailure.getCause()</code> returns <code>DocumentReadException</code>.
- <code>exportFailure.getCause().getCause()</code> returns <code>IOException</code>.
- <code>exportFailure.getCause()</code> does **not** directly return the deepest exception.
- A cause chain is only valuable when each translation adds necessary meaning; you should not add extra layers just to have more layers.

**A cause is different from a message.** A message is text that can change depending on context or implementation version. A cause is a reference to an object containing the error type, message, stack trace, and related information. Copying <code>original.getMessage()</code> into the new message is not equivalent to preserving the cause.

## 4. Constructors with a Cause: The Recommended Approach

When defining an unchecked exception type at the API layer, the simplest constructor for error translation is:

~~~java
public final class DocumentReadException extends RuntimeException {
    public DocumentReadException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

This is **a standalone class** if placed in the file <code>DocumentReadException.java</code>. The <code>RuntimeException</code> constructor accepts both message and cause, so:

- <code>getMessage()</code> on the new exception returns the API-facing message.
- <code>getCause()</code> on the new exception returns the object passed in.
- The stack trace of the new exception reflects where the wrapper was created/thrown, while the cause retains its own stack trace.

If the API uses checked exceptions, the way to preserve the cause is similar—just extend <code>Exception</code> and declare/catch the checked exception according to Java rules:

~~~java
public final class DocumentReadCheckedException extends Exception {
    public DocumentReadCheckedException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

This is also a standalone class if saved in <code>DocumentReadCheckedException.java</code>. Choosing checked vs. unchecked is an API contract choice and does not change the principle of preserving the cause.

### Three Ways to Write It and Their Consequences

The following snippets are **illustrative code placed inside a <code>catch (IOException original)</code> block** with the appropriate exception class.

**Right — API-layer message, original error as cause:**

~~~java
throw new DocumentReadException(
        "Không thể đọc tài liệu đã yêu cầu", original);
~~~

**Wrong — keeps only the message, drops the cause:**

~~~java
throw new DocumentReadException(
        "Không thể đọc tài liệu: " + original.getMessage(), null);
~~~

**Wrong by design — creates a new technical error instead of the original technical error:**

~~~java
throw new DocumentReadException(
        "Không thể đọc tài liệu",
        new IOException(original.getMessage()));
~~~

The third approach creates a new <code>IOException</code> that does not have the same stack trace or identity as the original error. Without linking <code>original</code> as the cause of the intermediate exception, the trace back to the actual incident that occurred is lost. The right approach is usually to pass <code>original</code> directly as the cause.

Do not use the text of the original error to simulate the exception type or put sensitive information into the public message. The new exception's message should describe the failed action according to the contract; the cause serves technical diagnostics.

## 5. Standalone Java 17+ Example: Reading a Document and Preserving the Exact Cause

Create the file **CausePreservationDemo.java** with the full content below. The example uses a simulated data source so that the result is deterministic and does not depend on actual files on disk.

~~~java
import java.io.IOException;
import java.nio.file.NoSuchFileException;
import java.util.Objects;

public class CausePreservationDemo {

    @FunctionalInterface
    interface RawDocumentSource {
        String read(String id) throws IOException;
    }

    static final class DocumentNotFoundException extends RuntimeException {
        DocumentNotFoundException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static final class DocumentReadException extends RuntimeException {
        DocumentReadException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static final class DocumentGateway {
        private final RawDocumentSource source;

        DocumentGateway(RawDocumentSource source) {
            this.source = Objects.requireNonNull(source);
        }

        String getDocument(String id) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("ID tài liệu không hợp lệ");
            }

            try {
                return source.read(id);
            } catch (NoSuchFileException original) {
                throw new DocumentNotFoundException(
                        "Không tìm thấy tài liệu: " + id, original);
            } catch (IOException original) {
                throw new DocumentReadException(
                        "Không thể đọc tài liệu: " + id, original);
            }
        }
    }

    public static void main(String[] args) {
        DocumentGateway success =
                new DocumentGateway(id -> "Nội dung hướng dẫn");
        System.out.println("Thành công: " + success.getDocument("guide"));

        NoSuchFileException missing = new NoSuchFileException("guide");
        DocumentGateway absent = new DocumentGateway(id -> {
            throw missing;
        });

        try {
            absent.getDocument("guide");
        } catch (DocumentNotFoundException translated) {
            System.out.println(
                    "Không tìm thấy: " + translated.getClass().getSimpleName()
                    + " <- " + translated.getCause().getClass().getSimpleName());
            System.out.println(
                    "Giữ đúng instance cause: " + (translated.getCause() == missing));
        }

        IOException diskError = new IOException("Storage failure");
        DocumentGateway failed = new DocumentGateway(id -> {
            throw diskError;
        });

        try {
            failed.getDocument("guide");
        } catch (DocumentReadException translated) {
            System.out.println(
                    "Không đọc được: " + translated.getClass().getSimpleName()
                    + " <- " + translated.getCause().getClass().getSimpleName());
            System.out.println(
                    "Giữ đúng instance cause: " + (translated.getCause() == diskError));
        }
    }
}
~~~

Compile and run with Java 17 or newer:

~~~bash
javac -encoding UTF-8 CausePreservationDemo.java
java CausePreservationDemo
~~~

**Exact stdout:**

~~~text
Thành công: Nội dung hướng dẫn
Không tìm thấy: DocumentNotFoundException <- NoSuchFileException
Giữ đúng instance cause: true
Không đọc được: DocumentReadException <- IOException
Giữ đúng instance cause: true
~~~

### Mechanism Explanation

1. <code>RawDocumentSource</code> represents the raw data provider layer. It is allowed to throw <code>IOException</code>, like many Java I/O APIs.
2. <code>DocumentGateway</code> is the API boundary for the caller. It does not require the caller to understand storage details.
3. <code>NoSuchFileException</code> is caught before <code>IOException</code> because it is a subclass of <code>IOException</code>. The reverse order would make the specialized <code>catch</code> block unreachable.
4. Each <code>catch</code> creates an API-meaningful exception and **passes the same object** <code>original</code> to the constructor.
5. The comparisons <code>translated.getCause() == missing</code> and <code>== diskError</code> evaluate to <code>true</code>. This is stronger evidence than merely checking the same class or same message.
6. The success case does not produce a wrapper. Error translation only happens when the source actually throws a matching exception.
7. Blank ID validation runs before accessing the lower layer; an invalid request error is not disguised as an I/O error.

The example above uses unchecked API exceptions. If the contract prefers checked exceptions, you can extend <code>Exception</code> and declare <code>throws</code> accordingly; **the way the cause is linked remains the same**.

In a real implementation, <code>RawDocumentSource</code> might call <code>Files.readString(...)</code>, JDBC, or another adapter. However, not every technical error should be reduced to "not found": for example, a general <code>IOException</code> is translated to "unable to read" to avoid misstating the cause.

## 6. Reading the Cause Chain During Error Investigation

When an exception wrapper is printed with <code>printStackTrace()</code> or logged with a <code>Throwable</code> object by a logger, the output typically looks something like this:

~~~text
DocumentReadException: Không thể đọc tài liệu: guide
    at ...DocumentGateway.getDocument(...)
Caused by: java.io.IOException: Storage failure
    at ... original error site ...
~~~

This is an **illustration of the stack trace structure**, not the exact stdout of the program above. Package names, file paths, line numbers, stack traces, and formatting may vary depending on how it is run.

Key points to understand:

- The part before <code>Caused by</code> describes the API-layer exception and where it was thrown.
- The <code>Caused by</code> section contains the exception type and stack trace stored on the original technical object.
- If there are multiple cause layers, <code>Caused by</code> entries are displayed sequentially in link order.
- When printing a stack trace, Java may abbreviate common frames with lines like <code>... N more</code>. That is a display optimization, not an indication that the cause was lost.

You should not reconstruct an error chain by concatenating <code>getMessage()</code> from each layer and treating that as complete evidence. A string cannot preserve exception identity, cause structure, or the full stack trace.

### Accessing the Cause in Code

~~~java
Throwable cause = translated.getCause();
if (cause != null) {
    System.out.println("Cause type: " + cause.getClass().getName());
    System.out.println("Cause message: " + cause.getMessage());
}
~~~

This is an **illustrative snippet** assuming the variable <code>translated</code> holds an exception. The <code>null</code> check is necessary because not every exception has a cause. In production code, consider not exposing technical messages to the user interface.

Some libraries provide "root cause" analysis utilities, but <code>Throwable</code> only defines direct cause links. To traverse deeper, you must walk each level as needed; avoid assuming every exception has the same depth or that the cause is always non-<code>null</code>.

## 7. Preserving the Cause Across Multiple Boundaries: When Is Another Wrapper Truly Needed?

Suppose the storage layer has already thrown <code>DocumentReadException</code>. A layer that uses it to **export a report** may want to represent a broader action, such as <code>ReportExportException</code>, because the caller of the report export task needs to understand the failure at the report level.

A reasonable diagram might be:

~~~text
IOException
    |
    | preserve cause when entering DocumentGateway
    v
DocumentReadException
    |
    | only propagate or wrap further if the report export contract
    | needs to express a new semantic meaning
    v
ReportExportException
~~~

If you want to wrap further at a new layer, the constructor still accepts a cause:

~~~java
public final class ReportExportException extends RuntimeException {
    public ReportExportException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Within a business method that has a corresponding <code>gateway</code> object, this can be illustrated as follows:

~~~java
try {
    String document = gateway.getDocument("guide");
    exportReport(document);
} catch (DocumentReadException original) {
    throw new ReportExportException("Không thể xuất báo cáo", original);
}
~~~

**This <code>try/catch</code> snippet is illustrative only**, assuming <code>gateway</code> and <code>exportReport</code> are already declared in the application. If there is no report export semantics to add, let <code>DocumentReadException</code> pass through and avoid redundant wrappers.

A cause chain of three objects is reasonable if it describes three genuinely distinct responsibilities. If every layer wraps with a generic <code>RuntimeException("Error", e)</code>, readers will have to unwrap meaningless layers to find the real error.

### When Should You Not Wrap?

- The exception already expresses the current layer's contract accurately; you can rethrow it with <code>throw e;</code> or let it propagate.
- The current layer only logs and rethrows; creating a new exception solely for logging usually adds no benefit.
- You do not understand the technical cause well enough to classify it reliably; when needed, use an appropriate general API error type with the original cause.
- The exception is a programming bug or a serious error outside the operation's handling contract.

### When Should You Handle Instead of Wrapping?

If the application has a fallback source and can complete the operation according to the contract, that is **error recovery**, and no wrapper may be needed. Conversely, returning <code>null</code>, an empty string, or dummy data just to make the exception disappear will mislead the caller about the result if the contract does not specify that behavior.

## 8. Cause, Suppressed Exceptions, and Resource-Closing Errors

Cause and suppressed exceptions solve two different problems:

- **Cause**: the error that directly caused the current exception, usually translated from a lower layer.
- **Suppressed**: additional exceptions raised during error handling or resource closing, retained so they do not mask the primary error.

With <code>try-with-resources</code>, if both the operation inside <code>try</code> and <code>close()</code> throw exceptions, the error in the <code>try</code> body is typically the primary error; the error from <code>close()</code> is added to <code>getSuppressed()</code> on the primary error.

Standalone Java 17 example, saved as **SuppressedCauseDemo.java**:

~~~java
import java.io.IOException;

public class SuppressedCauseDemo {

    static final class FailingResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("Lỗi khi đóng");
        }
    }

    static final class ReadOperationException extends RuntimeException {
        ReadOperationException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static void read() {
        try (FailingResource resource = new FailingResource()) {
            throw new IOException("Lỗi khi đọc");
        } catch (IOException original) {
            throw new ReadOperationException("Đọc tài nguyên thất bại", original);
        }
    }

    public static void main(String[] args) {
        try {
            read();
        } catch (ReadOperationException translated) {
            Throwable cause = translated.getCause();
            System.out.println("Cause: " + cause.getMessage());
            System.out.println("Suppressed: "
                    + cause.getSuppressed()[0].getMessage());
            System.out.println("Số suppressed: "
                    + cause.getSuppressed().length);
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 SuppressedCauseDemo.java
java SuppressedCauseDemo
~~~

**Exact stdout:**

~~~text
Cause: Lỗi khi đọc
Suppressed: Lỗi khi đóng
Số suppressed: 1
~~~

Here, the wrapper preserves the original <code>IOException("Lỗi khi đọc")</code> object as the cause. That cause object already retains <code>IOException("Lỗi khi đóng")</code> in its suppressed list. If you create a new <code>IOException</code> from the message and discard the original, both the read context and the resource-closing error risk being lost.

Do not assume every <code>IOException</code> has suppressed exceptions; the example program deliberately fails both operations. In production, you must check the length of the <code>getSuppressed()</code> array before accessing elements. When you only need diagnostic logging, passing the whole exception to the logger is usually better than writing manual code to stitch together each suppressed error.

## 9. Do Not Use initCause as the Default Choice

In addition to the <code>Throwable(String message, Throwable cause)</code> constructor, Java provides <code>initCause(Throwable cause)</code>. This API is meant for situations where you need to link a cause **after** creating the exception, such as when a legacy exception class lacks an appropriate constructor.

Illustrative example in an appropriate context:

~~~java
RuntimeException translated =
        new RuntimeException("Không thể xử lý yêu cầu");
translated.initCause(original);
throw translated;
~~~

In the snippet above, <code>original</code> is an existing <code>Throwable</code> object. Do not call <code>initCause</code> multiple times, and do not set the exception itself as its own cause. If the cause was already initialized via a constructor (including a constructor whose cause argument was <code>null</code>), calling <code>initCause</code> again throws <code>IllegalStateException</code>; assigning itself as its own cause is also invalid.

For exception classes you own, a constructor accepting <code>Throwable cause</code> is usually clearer and less error-prone. <code>initCause</code> is better suited for legacy API compatibility and should not be used to patch an incorrectly constructed cause chain.

## 10. Internal Diagnostics vs. Safe Messages for the Caller

Preserving the cause **does not mean exposing all information inside the cause**. Technical exceptions can contain server paths, database table names, query details, hostnames, service addresses, or sensitive data.

You should separate:

1. **Client contract**: business/technical error type at the API level, stable error codes if needed, and messages that do not leak secrets.
2. **Internal diagnostics**: the full exception object, cause chain, suppressed exceptions, and correlation data such as a request ID, stored with access control.
3. **Handling behavior**: the client can decide to notify the user, prompt for re-entry, redirect, or retry when the operation genuinely permits it.

For example, the external API might only respond with "Unable to load document at this time", while internal logs still trace back to <code>DocumentReadException</code> and <code>IOException</code>. Mapping an exception to an HTTP status or gRPC code belongs to the transport boundary, not the I/O layer's responsibility.

### Logging Strategy

When you need to log a stack trace with a logging library that supports <code>Throwable</code> objects, pass the exception to the appropriate logger parameter rather than just concatenating <code>e.getMessage()</code>. However, avoid logging the same exception at every layer and then rethrowing it, as that can produce multiple identical log entries for a single request.

If the error is not handled at the current layer, you can preserve the cause and let the error propagate to an appropriate monitoring boundary. If the current layer has genuinely recovered from the error, log at a level appropriate for a handled incident. The exact policy depends on the application, but preserving the cause keeps observability options open at later layers.

**Avoid** using the low-level exception's message as a mandatory public explanation. Driver or library messages are not a stable contract and may leak information or change between versions.

## 11. Special Cases to Distinguish

### 11.1. Do Not Catch Every Exception and Translate Into a Single Error

~~~java
try {
    executeOperation();
} catch (Exception e) {
    throw new DocumentReadException("Lỗi đọc tài liệu", e);
}
~~~

This is **illustrative code**, not a standalone program. It preserves the cause, but may still **translate the semantics incorrectly**: validation errors, programming bugs, already-translated business errors, or <code>InterruptedException</code> all risk being lumped into "read error". Preserving the cause is an important condition, but **not sufficient** for proper exception translation.

You should catch the exception types within the API's translation scope, classify them according to the contract, and avoid catching <code>Throwable</code> as a routine business error. <code>Error</code> and serious runtime-environment failures should not be turned into recoverable errors by default.

### 11.2. InterruptedException Must Preserve the Interrupt Signal

If a blocking operation throws <code>InterruptedException</code> and the API must convert it to an unchecked exception, the application usually needs to restore the interrupt status before throwing the wrapper:

~~~java
try {
    blockingCall();
} catch (InterruptedException original) {
    Thread.currentThread().interrupt();
    throw new OperationInterruptedException(
            "Thao tác bị ngắt", original);
}
~~~

This is **illustrative code**: <code>blockingCall()</code> and <code>OperationInterruptedException</code> are components assumed to exist in the application context. If the contract allows, declaring and propagating <code>InterruptedException</code> directly is another good option.

Simply storing <code>original</code> as the cause **does not automatically restore the thread's interrupt flag**. These two actions are independent: the cause preserves the evidence, while <code>Thread.currentThread().interrupt()</code> restores the cooperative control signal so upper-level code can observe it.

### 11.3. Do Not Automatically Treat a Timeout as "Not Processed"

A call to an external service that times out may already have been processed by the server before the connection dropped. A wrapper with a cause only indicates the original technical exception; it does not prove the operation failed to execute. Before allowing the client to retry, rely on idempotency, an idempotency key, or the operation's specific contract.

### 11.4. Do Not Modify the Stack Trace Directly to Hide the Cause

You should not call <code>setStackTrace(...)</code> or create a new error object from text merely to strip the original trace. In security-sensitive situations, control **where errors are displayed/logged**, while still preserving internal information under an appropriate retention policy. Only consider stripping information when it is an explicit requirement of a trust boundary.

## 12. Testing: Verifying Cause Identity and the External Contract

A good test suite does not only ask "was an exception thrown?"—it also asks whether the exception is at the **right semantic layer**, and whether the cause is the **exact original object**.

| Scenario | What to Assert |
| --- | --- |
| Data source returns normal content | No exception thrown; content unchanged |
| Source throws <code>NoSuchFileException</code> | Caller receives <code>DocumentNotFoundException</code> |
| Source throws another <code>IOException</code> | Caller receives <code>DocumentReadException</code> |
| Translated exception | <code>translated.getCause() == original</code> |
| Caller receives exposed error | Does not need to depend directly on the adapter's internal exception type to make decisions |
| Source raises an unexpected non-<code>IOException</code> error | Not gratuitously retyped by <code>catch (IOException)</code> branches |
| Resource-closing operation also fails | Suppressed exception remains accessible via the cause if the original cause is preserved |
| Invalid input | Rejected at the input boundary per the contract, not disguised as an infrastructure error |

In the standalone demo in Section 5, two <code>==</code> comparisons verified exact object identity. With JUnit 5, you can write tests using <code>assertThrows</code> and <code>assertSame</code>.

The snippet below is **illustrative within a JUnit 5 project that already has dependencies and the <code>DocumentGateway</code> and <code>DocumentReadException</code> classes in appropriate visibility**:

~~~java
IOException original = new IOException("disk error");
DocumentGateway gateway = new DocumentGateway(id -> {
    throw original;
});

DocumentReadException actual = assertThrows(
        DocumentReadException.class,
        () -> gateway.getDocument("guide"));

assertSame(original, actual.getCause());
~~~

When applying this in a real test file, you need to import <code>java.io.IOException</code> and the static imports from <code>org.junit.jupiter.api.Assertions</code>. The illustrative snippet above is not a standalone Java program.

The key point of <code>assertSame</code>: two exceptions can have the same class and the same message yet be **two different objects**. Checking only <code>getCause() instanceof IOException</code> will miss cases where someone created <code>new IOException(original.getMessage())</code> and lost the original exception.

For API messages, test the stable contract information. Do not couple tests to exact OS error wording or specific stack trace lines, as those vary across environments.

## 13. Common Mistakes When Preserving the Cause

1. **Copying only the message:** <code>new HighLevelException(original.getMessage())</code> does not record the cause object.
2. **Accidentally passing <code>null</code>:** the constructor accepts a cause, but in practice never receives the original error.
3. **Creating a "similar" cause:** replacing <code>original</code> with <code>new IOException(original.getMessage())</code> loses identity, stack trace, and potentially suppressed exceptions.
4. **Preserving the cause while translating to the wrong error type:** for example, turning every exception into <code>NotFoundException</code>. A cause cannot rescue a broken contract.
5. **Wrapping repeatedly across layers without adding meaning:** stack traces become hard to read, and clients must dig through unnecessary wrappers.
6. **Confusing the message with the stack trace:** a message is just a string, whereas the full exception carries far more information.
7. **Forgetting to check <code>getCause() == null</code>:** many exceptions thrown directly have no cause.
8. **Confusing suppressed exceptions with the cause:** resource-closing errors may be stored in the cause's <code>getSuppressed()</code>.
9. **Catching too broadly:** may mask <code>InterruptedException</code>, validation errors, or errors that were already properly translated.
10. **Leaking technical details to users:** preserve the cause internally, but do not automatically send raw stack traces or sensitive messages in API responses.
11. **Logging repeatedly at every catch:** the same incident appears multiple times in logs without adding context.
12. **Tests that only inspect the outer exception type:** fail to detect regressions that drop the original cause.

## 14. How to Review an Error Translation

Read a <code>catch</code> block in order:

1. **Is translation needed?** Does this layer provide a different contract from the layer that raised the error?
2. **Is the mapping accurate?** Does the new exception type express what can be known with certainty from the lower-level error?
3. **Is the original preserved?** Does the constructor receive the **exact caught exception variable** as the cause?
4. **Is the message appropriate?** Does it explain the failed action at the API level without leaking sensitive data?
5. **Is secondary information preserved?** Does the cause retain the stack trace, suppressed exceptions, and library error context?
6. **Do tests prove it?** Is there at least one test asserting <code>assertSame(original, translated.getCause())</code> or equivalent?
7. **What should the next layer do?** Let the exception pass through, translate to another business contract, recover from the error, or map to a transport result?
8. **Are threads and resources handled properly?** Especially regarding interrupts, cleanup, and operations that may have partially succeeded.

**Key takeaway:** The outer exception helps the caller understand **the meaning of the failure**; the cause preserves **the evidence of the failure that occurred**. Combining these two pieces of information properly allows an API to hide implementation details while retaining accurate diagnostic capability when incidents arise.