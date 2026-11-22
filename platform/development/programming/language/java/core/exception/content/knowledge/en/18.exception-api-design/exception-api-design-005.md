# Exception Translation at Abstraction Boundaries in Java

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain why an API should express errors in the language of the abstraction layer it provides.
- Identify the right place for exception translation between the infrastructure layer and the business layer.
- Map specific exceptions to exceptions that are meaningful to the caller while preserving the root cause through cause chaining.
- Design a consistent error contract and make sound decisions between checked exceptions and unchecked exceptions.
- Avoid hiding errors, multi-layer redundant wrapping, overly broad catches, or mishandling thread interruption.

## 2. What Is Exception Translation?

**Exception translation** is the technique of catching an exception thrown by an implementation layer and converting it into an exception that belongs to the contract of the layer providing the API. The caller receives an error type that reflects the operation they requested, rather than having to know whether the underlying layer uses files, JDBC, an HTTP client, or a third-party library.

For example, a document repository method provides the operation **read a document by name**. Underneath, it uses the file system and may encounter <code>NoSuchFileException</code> or <code>IOException</code>. The document repository layer can publish two errors whose semantics are close to the needs of the API consumer:

- <code>DocumentNotFoundException</code>: the requested document does not exist.
- <code>DocumentAccessException</code>: the document cannot be read due to an access or infrastructure error.

This is a change in the **abstraction level of the error**, not an operation that fixes the root cause. The new exception should still store the original exception in <code>cause</code> to support diagnostics.

A typical processing flow:

~~~text
Application / Use case
        |
        | read("intro.txt")
        v
DocumentRepository       <- error contract in terms of "document"
        |
        | Files.readString(...)
        v
Java NIO / File system   <- errors in terms of "path, file, I/O"

NoSuchFileException
        |
        | catch, classify, preserve cause
        v
DocumentNotFoundException
        |
        v
Application handles it in terms of "document not found"
~~~

If clients of <code>DocumentRepository</code> have to directly catch a series of storage-specific <code>IOException</code> types, the abstraction boundary has leaked implementation details into the upper contract.

## 3. When Should Exceptions Be Translated?

**You should translate** when all three of the following conditions apply:

1. **The current layer owns an independent contract**: such as a repository, gateway, adapter, service API, or facade.
2. **The underlying exception is not the right language for the caller**: errors from JDBC, the filesystem, or an HTTP client only reflect the implementation.
3. **There is a reliable mapping** from the underlying error to the meaning of the operation: for example, missing record/document, version conflict, access denied, or a transient dependency failure.

**Do not mechanically translate** every exception at every method call. In a file-handling library designed for callers to handle I/O directly, declaring <code>throws IOException</code> may be the right contract. If the exception type already belongs to the API's language and the caller understands it, wrapping it in another generic exception only loses information.

It is also important to distinguish:

- **Translation**: changing the type or semantics of the exception; the error continues to be thrown.
- **Handling/recovery**: actually resolving the error, such as using a fallback source or letting the user retry.
- **Logging**: recording the error for observability; logging itself does not handle the error.
- **Mapping at communication boundaries**: converting business errors into an HTTP response, gRPC status, or response code. This can happen at a different layer, after exception translation is complete.

## 4. Classifying Errors Before Mapping

One infrastructure exception does not always correspond to one business exception. You need to rely on the operation context and reliable signals from the underlying API.

| Low-level signal | Example of an appropriate high-level error | What to check |
| --- | --- | --- |
| File not found when reading a document | <code>DocumentNotFoundException</code> | The file actually represents the requested document |
| No record found by ID | <code>EntityNotFoundException</code> | Whether an empty result is a normal case under the contract |
| Unique constraint violation when creating a resource | <code>DuplicateResourceException</code> or conflict error | Identify the exact constraint; avoid treating every SQL error as duplicate data |
| Timeout or external service connection failure | <code>ExternalServiceUnavailableException</code> | Only assert transience if justified; a timeout does not prove the operation did not run |
| Unclassified <code>IOException</code> | <code>DocumentAccessException</code> | Preserve the cause to trace detailed root causes |
| Invalid input data before calling infrastructure | <code>IllegalArgumentException</code> or API validation error | Validate upfront; do not pretend it is an I/O error |

**Principle:** translate based on *provable semantics*, and avoid inferring the cause solely from the exception's message string. Do not compare <code>getMessage()</code> against a fixed text snippet to decide the error type; messages can vary by operating system, driver, locale, or library version.

The order of <code>catch</code> blocks also matters. For example, <code>NoSuchFileException</code> is a subclass of <code>IOException</code>, so the more specific type must be caught before the broader type; doing the reverse makes the specific branch unreachable and Java reports a compile-time error.

## 5. Standalone Java 17+ Example

This example uses a replaceable text store port to reproduce three scenarios—**success**, **not found**, and **I/O error**—without depending on files currently on the machine. The translation point is in <code>DocumentRepository.read</code>. In a real environment, that port could be wired to <code>Files.readString</code>, a database system, or an external service.

Create the file **ExceptionTranslationDemo.java**:

~~~java
import java.io.IOException;
import java.nio.file.NoSuchFileException;

public class ExceptionTranslationDemo {

    @FunctionalInterface
    interface TextStore {
        String read(String name) throws IOException;
    }

    static final class DocumentNotFoundException extends RuntimeException {
        DocumentNotFoundException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static final class DocumentAccessException extends RuntimeException {
        DocumentAccessException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static final class DocumentRepository {
        private final TextStore store;

        DocumentRepository(TextStore store) {
            this.store = java.util.Objects.requireNonNull(store);
        }

        String read(String name) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException(
                        "Document name must not be blank");
            }

            try {
                return store.read(name);
            } catch (NoSuchFileException e) {
                throw new DocumentNotFoundException(
                        "Document not found: " + name, e);
            } catch (IOException e) {
                throw new DocumentAccessException(
                        "Unable to read document: " + name, e);
            }
        }
    }

    private static void show(String scenario, DocumentRepository repository) {
        try {
            System.out.println(scenario + ": " + repository.read("intro.txt"));
        } catch (DocumentNotFoundException | DocumentAccessException e) {
            System.out.println(
                    scenario + ": " + e.getClass().getSimpleName()
                    + " (cause=" + e.getCause().getClass().getSimpleName() + ")");
        }
    }

    public static void main(String[] args) {
        show("Success",
                new DocumentRepository(name -> "Hello Java"));

        show("Not found",
                new DocumentRepository(name -> {
                    throw new NoSuchFileException(name);
                }));

        show("I/O error",
                new DocumentRepository(name -> {
                    throw new IOException("Disk unavailable");
                }));
    }
}
~~~

Compile and run with Java 17 or later:

~~~bash
javac -encoding UTF-8 ExceptionTranslationDemo.java
java ExceptionTranslationDemo
~~~

Standard output (stdout):

~~~text
Success: Hello Java
Not found: DocumentNotFoundException (cause=NoSuchFileException)
I/O error: DocumentAccessException (cause=IOException)
~~~

**How each branch works:**

1. If <code>TextStore.read</code> returns text, <code>DocumentRepository.read</code> returns it verbatim without creating an exception.
2. If the port throws <code>NoSuchFileException</code>, the repository throws <code>DocumentNotFoundException</code>. The caller knows **the document was not found**, without needing to know where documents are stored.
3. If the port throws another <code>IOException</code>, the repository throws <code>DocumentAccessException</code>. Thus, unclassified I/O errors are still accurately expressed at a general level.
4. Each new exception is initialized with <code>super(message, cause)</code>, so <code>getCause()</code> returns the exact lower-level exception. The cause chain can also span multiple layers when needed for diagnostics.

To use real Java NIO, you can replace the port initialization as shown in the following **integration snippet** (this is an expression placed within code that has the appropriate imports and context, not a standalone Java program):

~~~java
DocumentRepository repository = new DocumentRepository(
        name -> java.nio.file.Files.readString(
                java.nio.file.Path.of(name),
                java.nio.charset.StandardCharsets.UTF_8));
~~~

Note: <code>Files.readString</code> can also throw exceptions that do not belong to <code>IOException</code>, such as <code>SecurityException</code> in access-check contexts. The two <code>catch</code> branches above only translate <code>NoSuchFileException</code> and <code>IOException</code>; the example does not claim to handle every possible file system error.

## 6. Preserving `cause`: Translating Semantics Without Losing the Origin

When `DocumentRepository` catches `IOException` and throws `DocumentAccessException`, the new object needs a message at the document layer **and** a reference to the exact infrastructure error:

~~~java
catch (IOException original) {
    throw new DocumentAccessException(
            "Unable to read document", original);
}
~~~

This is an illustrative snippet belonging to a method with a corresponding `try` block. `getCause()` on the wrapper points to **the exact `original` instance**; the original error's stack frames and suppressed exceptions remain on that object. Do not merely copy `original.getMessage()` into the wrapper's message, and do not manually copy the stack trace onto a new object. If the error is already an appropriate public type, let it propagate instead of wrapping it in another layer that just says "failed".

The lesson on **preserving `cause` when translating technical errors** examines cause identity, multi-layer chains, and the impact of suppressed exceptions in depth; the current lesson focuses on **translation boundaries and classifying public error types**.

## 7. Designing Exception Contracts for an API

Before declaring a new exception, determine **whether the caller needs to take different actions**. If clients can choose separate actions for "not found" and "cannot access", two distinct error types add value. If causes cannot be reliably distinguished, a single general access error type may be more appropriate.

A good contract should have:

- **Stable and meaningful names**: distinguish missing resources, bad requests, conflicts, and dependency failures.
- **Clear ownership scope**: exceptions belong to that layer's API, avoiding forcing upper layers to depend on a specific driver or library.
- **Documented throw conditions**: even for unchecked exceptions, describe them in the Javadoc/contract.
- **Preserved cause**, adding useful business identifiers if safe (such as a document ID rather than a server file path).
- **No false recovery promises**: "access failed" does not automatically mean "retrying will succeed".

Example contract declaration (API illustration, not a standalone program):

~~~java
public interface DocumentReader {
    /**
     * Reads the text of the identified document.
     *
     * @throws DocumentNotFoundException if the document does not exist
     * @throws DocumentAccessException if the document store cannot read the data
     * @throws IllegalArgumentException if the document name is invalid
     */
    String read(String name);
}
~~~

In a public API, custom exceptions should have appropriate visibility (<code>public</code> if clients in other packages need to catch them), and client code should only rely on published types. In the demo, classes are nested in a single file for easy execution, so multi-file organization for a published library is not shown.

### Checked or unchecked?

Java divides exceptions into:

- **Checked exceptions**: any <code>Exception</code> that does not extend <code>RuntimeException</code>; the compiler forces callers to catch them or declare <code>throws</code>.
- **Unchecked exceptions**: <code>RuntimeException</code> and its subclasses (in addition, <code>Error</code> and its subclasses are also unchecked). Callers are not forced to declare or catch them.

The example uses unchecked domain exceptions so the API does not couple every call site to <code>throws IOException</code>. This is a **design decision of the example**, not a universal rule.

Choose checked exceptions if the API wants to force callers to acknowledge an expected failure condition that usually has a reasonable recovery path. Choose unchecked when errors cannot or should not be forced to be handled at every call site, or when following the architecture's general convention. Whichever you choose, keep semantics, cause, and contract documentation consistent. Do not simply turn <code>IOException</code> into an anonymous <code>RuntimeException</code> just to bypass the compiler.

## 8. Choosing the Right Translation Boundary

In a multi-layered system, for example:

~~~text
Controller / CLI / Consumer
          |
          v
      Use-case Service
          |
          v
   DocumentRepository       => translates file/JDBC errors into repository errors
          |
          v
       File system

HTTP boundary / CLI boundary => if needed, maps API errors to status/messages
~~~

An error should only be translated when **the meaning provided by that layer genuinely changes**. The repository can own <code>DocumentNotFoundException</code>. The service should let the error pass through if it already matches the service's contract; translate it again only when the service adds different semantics, such as "unable to complete dossier publication" spanning multiple business operations.

If the HTTP layer maps <code>DocumentNotFoundException</code> to HTTP status 404, that is a rule of the HTTP adapter and should not make the repository depend on an <code>HttpStatus</code> type. For unknown infrastructure errors, the adapter typically returns a safe generic error instead of sending the internal exception verbatim.

Several choices need to be consistent across the entire API:

| Decision | Verification question |
| --- | --- |
| Return an empty value or throw an error when not found? | Is "document absent" a normal outcome of this lookup operation? |
| Have a separate error type for access denied? | Does the caller have a distinct action and a reliable enough signal to classify it? |
| Which exceptions are published to clients? | Can the contract remain stable when swapping the storage system? |
| Is retry allowed? | Is the operation idempotent, or could it have partially succeeded despite a timeout? |

A lookup API can use <code>Optional</code> when "does not exist" is a normal scenario. For an API that guarantees a document must exist, a not-found exception usually expresses the intent more clearly. Both are contract choices; do not automatically convert every empty value into an exception.

## 9. Exceptions Should Not Be Swallowed or Distorted

### 9.1. Do Not Catch Broadly Without Purpose

Error-prone pattern:

~~~java
try {
    doWork();
} catch (Exception e) {
    throw new RuntimeException("Failed", e);
}
~~~

This is an illustrative example, **not a standalone program**. It can lump validation errors, programming bugs, already-translated business errors, and other checked exceptions into one generic type. The caller can no longer tell which errors need handling. Catch only the types that belong to the translation boundary; if you need a broad catch at the application entry point to log or prevent a crash, that is a different responsibility.

Never use <code>catch (Throwable)</code> as a routine way to translate errors: <code>Error</code> can represent severe JVM conditions and does not belong to the set of recoverable business errors.

### 9.2. Do Not Turn Errors Into Fake Success Results

~~~java
try {
    return store.read(name);
} catch (IOException e) {
    return null;
}
~~~

Unless the contract explicitly defines <code>null</code> as a handled error state, this code erases the distinction between "no content" and "system failure". The caller might proceed as if the read succeeded.

### 9.3. Do Not Wrap Redundantly When Meaning Has Not Changed

~~~java
catch (DocumentAccessException e) {
    throw new RuntimeException("Unable to read document", e);
}
~~~

When no new meaning is added, the wrapper only adds another layer of stack trace and strips the caller of a useful error type. You can let the exception pass through intact.

### 9.4. Handle InterruptedException Intentionally

<code>InterruptedException</code> carries a thread-control signal and should not be automatically treated like an ordinary infrastructure error. For code waiting on a blocking operation:

~~~java
try {
    blockingOperation();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw new TaskCancelledException("Task interrupted", e);
}
~~~

This is **illustrative code**, assuming an appropriate <code>blockingOperation()</code> and <code>TaskCancelledException</code>. When a blocking method throws <code>InterruptedException</code>, the interrupt status has usually been cleared; call <code>interrupt()</code> to restore the signal if you cannot propagate that checked exception directly upward. In APIs that allow it, propagating <code>InterruptedException</code> directly is also a valid option. Never silently swallow the interruption and continue running as normal.

### 9.5. Do Not Lose Errors While Closing Resources

For resources implementing <code>AutoCloseable</code>, prefer <code>try-with-resources</code>. If both the main operation and closing the resource fail, Java keeps the main operation's exception as the primary exception and typically attaches the close error to the <code>getSuppressed()</code> list. When translating exceptions, preserving the original cause allows suppressed exceptions to remain traceable. Avoid writing a manual <code>finally</code> block to close resources and accidentally replacing the primary exception with a close error.

## 10. How to Test Exception Translation

Tests should verify **the contract and the cause**, rather than trying to match the entire stack trace or environment-dependent messages.

| Input scenario | Result to verify |
| --- | --- |
| Port returns a text string | Return value is preserved; no exception is thrown |
| Port throws <code>NoSuchFileException</code> | Throws the exact <code>DocumentNotFoundException</code> |
| Port throws a general <code>IOException</code> | Throws the exact <code>DocumentAccessException</code> |
| Translated error has a cause | <code>getCause()</code> is **the exact same instance** of the original exception |
| Null/blank document name | Appropriate input error is thrown; store is not called |
| Another <code>RuntimeException</code> from the port | Not unintentionally altered by the two <code>catch IOException</code> branches |

You can verify the cause directly using a pre-created <code>IOException</code> instance. **Illustrative code within the same access scope as the demo**:

~~~java
IOException original = new IOException("I/O failure");
DocumentRepository repository = new DocumentRepository(name -> {
    throw original;
});

try {
    repository.read("intro.txt");
    throw new AssertionError("Must throw DocumentAccessException");
} catch (DocumentAccessException translated) {
    if (translated.getCause() != original) {
        throw new AssertionError("Did not preserve the original cause");
    }
}
~~~

The <code>==</code> comparison here is intentional: it checks that **the same instance** is preserved as the cause, not just the same exception type. In a JUnit project, you can apply <code>assertThrows</code> and <code>assertSame</code> to express these two assertions.

## 11. Common Design Mistakes

1. **Exposing infrastructure exception types** in the public API even though clients only work with business concepts: changing the storage system forces clients to change their error-handling code.
2. **Creating a single generic exception for all situations**: loses the ability to distinguish not-found, conflict, insufficient permissions, and dependency failures.
3. **Translating based on message strings** instead of exception types, status codes, or clear contracts: brittle when drivers or locales change.
4. **Omitting the cause**: makes it hard to find the call site and the actual root cause.
5. **Catching broadly and wrapping twice**: accidentally changes an already appropriate error type and complicates the stack trace.
6. **Logging the same error at every layer and rethrowing**: generates duplicate logs, making a single incident hard to inspect. Have a strategy to log at the layer that actually handles it or at an appropriate monitoring boundary.
7. **Using business errors to mask programming bugs** such as <code>NullPointerException</code> or invariant violations unintentionally.
8. **Changing the API without maintaining the exception contract**: clients catching a specific error type can be broken even if the method signature for unchecked exceptions does not change.

## 12. Project Application Checklist

When designing or reviewing a method across an abstraction boundary, check yourself:

- At **what conceptual level** is the caller requesting the operation (document, account, order, task)?
- Which exceptions are infrastructure details, and which already belong to the public contract?
- Can each case that requires separate handling be reliably identified?
- Is the **cause** preserved while protecting sensitive information when constructing public messages?
- Are specific exceptions caught before general ones, avoiding catching unrelated errors?
- Does checked/unchecked match client error-handling expectations and project conventions?
- Are the success path, mapped error paths, and cause identity tested?
- Can the upper layer handle errors according to the contract without knowing the specific storage library?

When you can answer these questions, exception translation helps **keep the API stable across technology changes** while leaving enough information to investigate incidents. The value of the technique lies in accurate semantic mapping, the right boundaries, and preserving the root cause.