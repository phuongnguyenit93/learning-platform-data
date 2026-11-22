# Wrapping Exceptions and Preserving the Cause in Java Functional Programming

When a Java program calls multiple method layers, especially in **lambdas**, **method references**, and the **Stream API**, an error often occurs at a low level but needs to be handled at a layer with sufficient business context. **Exception wrapping** means creating a new exception appropriate for the API boundary and attaching the original exception as the **cause**, instead of discarding diagnostic information.

Typical pattern:

~~~java
try {
    return parse(rawValue);
} catch (NumberFormatException cause) {
    throw new IllegalArgumentException("Invalid amount: " + rawValue, cause);
}
~~~

Meaning: "At this layer, the request is invalid" **because** "at a lower layer, the string could not be parsed into a number." A constructor taking a cause argument lets investigators trace back both the **error context** and the **original exception along with its stack trace**.

This lesson focuses on the exception-wrapping mechanism, preserving the cause, choosing between checked and unchecked exceptions when working with functional interfaces, and avoiding mistakes that make debugging difficult.

## 1. Why Wrap Exceptions?

Suppose a system receives an amount as a string and converts it to an int. Integer.parseInt("oops") throws **NumberFormatException**. This information is technically accurate, but it does not tell you "which order's amount" that string belongs to.

If business rules require reporting the error with clearer context:

~~~java
static int parseAmount(String rawAmount) {
    try {
        return Integer.parseInt(rawAmount);
    } catch (NumberFormatException cause) {
        throw new IllegalArgumentException(
            "Invalid amount: " + rawAmount,
            cause
        );
    }
}
~~~

The calling layer receives **IllegalArgumentException**: the input violates the contract; someone debugging can still access **NumberFormatException** via error.getCause(). When printing the full stack trace, Java displays the cause chain using **Caused by:** blocks.

Exception wrapping is useful when:

- **Adding context:** the error occurred while reading a document, processing an order, decoding data, loading configuration, or retrieving a record.
- **Changing abstraction level:** the business layer does not want every caller to know the details of file, parser, or database APIs.
- **Adapting exception types:** callback APIs such as Function.apply do not declare checked exceptions.
- **Preserving evidence:** the message and stack trace of the original error remain linked to trace the source.

Exception wrapping **does not mean** every catch block must create a new exception. If the exception already has the right meaning at the boundary in question, letting it propagate may be simpler and more accurate.

## 2. Distinguishing Message, Stack Trace, and Cause

A Throwable in Java has the following related components:

| Component | Method | Purpose |
| --- | --- | --- |
| Exception type | getClass() | The kind of error the current layer wants to report |
| Message | getMessage() | Error description, usually with context |
| Cause | getCause() | The lower-level Throwable that led to this error |
| Stack trace | getStackTrace(), printStackTrace() | Location/call stack when the exception was created or thrown |
| Suppressed exceptions | getSuppressed() | Secondary exceptions retained, for example when closing a resource fails |

When calling:

~~~java
throw new IllegalArgumentException("Bad price", cause);
~~~

Java creates a new exception with a stack trace at the wrapping site while **keeping a reference to cause**. Therefore, low-level call information does not disappear. The cause chain lets you read the error from the business boundary back to the origin.

The two exception objects are **not the same instance**: the wrapper exception has its own type, message, and stack trace, while the original exception retains its initial data.

Example:

~~~java
try {
    Integer.parseInt("not-a-number");
} catch (NumberFormatException original) {
    IllegalArgumentException outer =
        new IllegalArgumentException("Invalid quantity", original);
    System.out.println(outer.getCause() == original); // true
}
~~~

getCause() can return null if the exception was created without a cause. Do not assume every exception has a cause; always check for null when presenting errors.

### 2.1. A Message Is Not a Cause

A pattern that loses data:

~~~java
catch (IOException error) {
    throw new IllegalStateException(error.getMessage());
}
~~~

The new IllegalStateException only carries the **message string**. getCause() will be null and the original exception is no longer linked in the stack trace chain via the cause mechanism.

The right approach when you need to translate the meaning:

~~~java
catch (IOException error) {
    throw new IllegalStateException("Unable to load configuration", error);
}
~~~

If there is no need to change the meaning or contract, you can let IOException propagate:

~~~java
static String readConfig(java.nio.file.Path path) throws IOException {
    return java.nio.file.Files.readString(path);
}
~~~

Do not wrap an error multiple times at every layer just to add "Error occurred". Add meaningful context **at the boundary where that layer understands the operation's meaning**.

### 2.2. Wrapper Message vs. Cause Message

The wrapper exception's message should answer "**which operation failed?**", while the cause describes "**which technical step broke?**". For example:

~~~java
throw new IllegalStateException(
    "Failed to initialize product catalog",
    original
);
~~~

There is no need to copy the entire stack trace into the message. Stack traces should be presented through proper logging or error printing. Avoid putting sensitive information such as passwords, access tokens, personal data, or verbatim secret payloads into the message: the cause may be logged or displayed unintentionally if not handled carefully.

## 3. Constructors and Attaching a Cause

Many standard exceptions have a constructor that takes a string and a Throwable:

~~~java
new IllegalArgumentException("Invalid field", cause);
new IllegalStateException("Invalid state", cause);
new RuntimeException("Operation failed", cause);
new java.io.UncheckedIOException("Read failed", ioCause);
~~~

Depending on the exception class, there may be a constructor taking only Throwable or other overloads. **Not every exception class has the same set of constructors**, so check the signatures of the specific type before using it.

For custom exceptions:

~~~java
final class OrderProcessingException extends RuntimeException {
    OrderProcessingException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

When calling new OrderProcessingException("Cannot process order", cause), the caller can read getCause() to inspect the original error. Name exceptions according to the abstraction level rather than creating a new custom class for every small catch block.

### 3.1. initCause for Legacy APIs

Some exception types or legacy APIs lack a constructor that accepts a cause. Throwable.initCause(cause) is the mechanism for setting the cause in appropriate cases:

~~~java
Exception wrapped = new Exception("Legacy operation failed");
wrapped.initCause(original);
throw wrapped;
~~~

This is an **illustrative snippet that must be placed in a catch/method context declaring throws**. initCause may only be used in valid states; you cannot arbitrarily reassign the cause after it has already been initialized, and it may throw IllegalStateException or IllegalArgumentException if the contract is violated.

**Prefer a constructor that accepts a cause** when available. It is explicit, hard to forget, and creates an object with the full cause relationship already established upon instantiation.

## 4. Checked and Unchecked Exceptions in Functional Interfaces

This is a particularly important aspect of Java functional programming.

Some standard functional interfaces:

~~~java
java.util.function.Function<T, R>       // R apply(T value)
java.util.function.Consumer<T>          // void accept(T value)
java.util.function.Predicate<T>         // boolean test(T value)
java.util.function.Supplier<T>          // T get()
~~~

These SAMs **do not declare checked exceptions**. Therefore, a lambda that directly calls a method with throws IOException cannot be used as a Function without catching or converting the exception.

Invalid example:

~~~java
// DOES NOT COMPILE if readString throws an unhandled IOException.
java.util.function.Function<java.nio.file.Path, String> reader =
    path -> java.nio.file.Files.readString(path);
~~~

Files.readString(Path) declares IOException, whereas Function.apply does not have throws IOException.

### 4.1. Wrapping Checked Exceptions at the Lambda Boundary

You can do this directly inside the lambda:

~~~java
java.util.function.Function<java.nio.file.Path, String> reader =
    path -> {
        try {
            return java.nio.file.Files.readString(path);
        } catch (IOException cause) {
            throw new java.io.UncheckedIOException(
                "Cannot read file: " + path,
                cause
            );
        }
    };
~~~

The lambda now conforms to Function<Path,String> because UncheckedIOException is a **RuntimeException**, not a checked exception. The key point is **passing the cause**: outer handlers still know which IOException occurred.

UncheckedIOException is the standard type for converting **IOException** to an unchecked exception; do not use it to wrap SQLException or arbitrary unrelated exceptions. For other checked exceptions, use an appropriate runtime exception with clear meaning, or define an API that returns error results explicitly.

**Architectural consideration:** converting checked to unchecked does not mean the error disappears or is handled. It only changes the compile-time declaration requirement; callers must still decide where to handle, log, and recover.

### 4.2. Why Not Catch Exception Arbitrarily?

Example to avoid:

~~~java
java.util.function.Function<String, String> action =
    value -> {
        try {
            return execute(value);
        } catch (Exception error) {
            return "";
        }
    };
~~~

This is illustrative code; execute is a hypothetical method. Catching Exception too broadly and returning an empty string turns data-reading errors, programming bugs, or business errors into a seemingly valid result. No evidence remains to diagnose the failure.

You should also not wrap every Exception in a generic RuntimeException if some types require special handling. **Catch the exception types you can actually handle or translate**. Let programming bugs (such as an unexpected NullPointerException) surface instead of hiding them, unless the boundary requires an intentional policy.

## 5. Adapters to Reuse Lambdas with Checked Exceptions

When multiple callbacks need to call methods with throws IOException, repeating try/catch in every lambda makes the code verbose. You can define a custom functional interface with throws:

~~~java
@FunctionalInterface
interface IOFunction<T, R> {
    R apply(T value) throws IOException;
}
~~~

Then create an adapter that converts IOFunction to Function:

~~~java
static <T, R> java.util.function.Function<T, R> unchecked(
        IOFunction<T, R> function) {
    java.util.Objects.requireNonNull(function);
    return value -> {
        try {
            return function.apply(value);
        } catch (IOException cause) {
            throw new java.io.UncheckedIOException("I/O in pipeline", cause);
        }
    };
}
~~~

Benefits:

1. **Error source is preserved:** UncheckedIOException.getCause() is the original IOException.
2. **Stream processing code stays readable:** map(unchecked(MyClass::readData)).
3. **Catches the exact checked exception type:** the adapter handles IOException without swallowing other exceptions.
4. **Isolated testing:** both the success and failure paths of the adapter can be tested.

However, the adapter still allows the callback to perform **I/O and side effects**, so it is not automatically pure or thread-safe. When appropriate, separate reading data beforehand and use Stream to process data already in memory. If checked exceptions need to remain part of an API layer's contract, it may be better not to convert to a standard Function in the first place.

### 5.1. A Generic Adapter Is Not a License to Catch Throwable

Java allows declaring an interface such as:

~~~java
@FunctionalInterface
interface ThrowingFunction<T, R, E extends Exception> {
    R apply(T value) throws E;
}
~~~

However, if you write a generic adapter, you must decide the policy for converting each E into a runtime exception, adding context, and preserving the cause. Catching Throwable too broadly can also interfere with serious Errors and other control mechanisms. Do not build a "sneaky throw" just to bypass checked exceptions, because callers may lose the ability to understand the error contract at compile time.

### 5.2. Wrapping Errors Does Not Change Stream Laziness

~~~java
List<String> results = paths.stream()
    .map(unchecked(path -> Files.readString(path)))
    .toList();
~~~

This example is an illustrative snippet requiring imports for Files, List, and an appropriate paths type. Building the pipeline with map **does not necessarily perform file reading yet**. IOException is wrapped when the function is actually invoked during the execution of a terminal operation such as toList().

If the pipeline short-circuits, such as with findFirst, the callback may not run on every element; therefore, do not treat a lambda inside a Stream as guaranteed to execute every logging or I/O call. In a parallel Stream, exceptions can originate from worker threads, and which failing element is observed first is not always the same as in a sequential stream.

## 6. Wrapping Exceptions to Add Business Context

A parser exception usually knows "the text is invalid", but does not know which record it belongs to. When wrapping, add useful information at the current layer:

~~~java
static int parseQuantity(String orderId, String rawQuantity) {
    try {
        return Integer.parseInt(rawQuantity);
    } catch (NumberFormatException cause) {
        throw new IllegalArgumentException(
            "Invalid quantity in order " + orderId,
            cause
        );
    }
}
~~~

The business layer can read the specific order, while getCause() preserves the original NumberFormatException.

In a multi-layer chain:

~~~text
OrderService: cannot create order
    caused by CatalogException: cannot resolve product
        caused by IOException: catalog source unavailable
~~~

This is a structural illustration, not fixed JVM output. Each layer **should wrap only when adding meaning or intentionally changing the error contract**. Wrapping across many layers only to repeat "failed" adds noise to the stack trace without helping debugging.

A practical rule:

- If the current layer **can recover**, handle the specific case and continue when safe.
- If the current layer **cannot recover** but can add useful context, wrap in the appropriate exception type and preserve the cause.
- If the current layer **cannot add anything**, let the appropriate exception propagate.
- At the final boundary (HTTP, CLI, job runner), translate the error into an appropriate response or status; log it with the cause chain, but do not return the full internal stack trace to end users.

## 7. Wrapping with the Right Type and Handling Special Exceptions

### 7.1. IOException and UncheckedIOException

Use UncheckedIOException when actually wrapping an IOException:

~~~java
catch (IOException cause) {
    throw new UncheckedIOException("Cannot load document", cause);
}
~~~

Code catching UncheckedIOException can retrieve the IOException-typed cause via getCause(), making it convenient to handle I/O errors as a distinct group.

### 7.2. NumberFormatException and IllegalArgumentException

NumberFormatException **is already** a subclass of IllegalArgumentException. If the calling layer needs to know the specific parse error without extra context, you can let the original exception propagate. If you need to explain which business data was invalid, wrapping in IllegalArgumentException with a cause can add value.

~~~java
catch (NumberFormatException cause) {
    throw new IllegalArgumentException("Invalid tax percentage", cause);
}
~~~

Do not wrap merely out of a mechanical rule; evaluate the added information and the exception type the API intends to expose.

### 7.3. InterruptedException Requires Preserving the Interrupt Signal

InterruptedException has special meaning in concurrency. Some waiting operations clear the interrupted status when throwing InterruptedException. If you must convert it to an unchecked exception and cannot keep throwing the checked exception, you normally need to **restore the interrupt flag** before throwing:

~~~java
catch (InterruptedException cause) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Operation interrupted", cause);
}
~~~

This is an illustrative snippet placed inside an appropriate try/catch block. Depending on the system contract, you may choose to cancel the task or use a cancellation-specific exception; do not treat a simple interrupt as a regular I/O error. **Preserving the cause does not replace restoring the interrupt status** when needed.

### 7.4. Do Not Arbitrarily Catch Error

Do not use catch (Throwable) to wrap everything in a RuntimeException. Throwable includes Errors such as OutOfMemoryError and LinkageError, which applications should generally not catch and convert universally. Restrict the set of handleable exceptions and keep the policy explicit.

### 7.5. CompletionException and ExecutionException

In asynchronous code, **CompletableFuture.join()** can throw CompletionException, while Future.get() typically surfaces ExecutionException for task failures. These wrappers can hold the root cause via getCause(). When debugging, inspect the cause chain rather than stopping at the "CompletionException" or "ExecutionException" message.

Do not arbitrarily unwrap and rethrow a checked Throwable where the contract does not allow it. Preserve the proper error type and API policy at the boundary.

## 8. How Is Cause Different from Suppressed Exceptions?

These two mechanisms are easily confused:

- **Cause:** answers "which exception caused or underlies the current exception?".
- **Suppressed exception:** stores an additional exception that the program does not want to replace the primary exception, commonly occurring when **try-with-resources** already has an error in the body and close() also fails.

Structural illustration:

~~~java
try (SomeResource resource = openResource()) {
    performWork(resource); // May throw the primary exception.
}
// If close() also fails, the close error can become
// a suppressed exception on the primary exception.
~~~

This is Java pseudocode with hypothetical types/methods, not a standalone program.

Read suppressed exceptions via error.getSuppressed(). Do not use initCause to try to "turn" a secondary exception into the cause, because the two relationships carry different meanings.

**Important:** wrapping an exception using a constructor that takes a cause retains the original exception object, including any suppressed exceptions attached to it. When logging, use a logger overload that accepts a Throwable argument to print the full cause and suppressed details rather than only printing getMessage().

## 9. Complete Java 17+ Program

This example brings together three key ideas:

1. The parseAmount method catches NumberFormatException, wraps it in IllegalArgumentException, and **preserves the cause**.
2. The functional interface IOFunction<T,R> allows declaring **throws IOException**; the unchecked adapter converts it to Function<T,R> for Stream.
3. The program catches exceptions at the main boundary, printing the **wrapper message**, **cause type**, and **cause message** to prove the link remains intact.

Create the file **CausePreservingDemo.java**:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.function.Function;
import java.util.stream.Stream;

public class CausePreservingDemo {
    @FunctionalInterface
    interface IOFunction<T, R> {
        R apply(T value) throws IOException;
    }

    static <T, R> Function<T, R> unchecked(IOFunction<T, R> function) {
        Objects.requireNonNull(function);
        return value -> {
            try {
                return function.apply(value);
            } catch (IOException cause) {
                throw new UncheckedIOException("I/O in pipeline", cause);
            }
        };
    }

    static String load(String key) throws IOException {
        if ("missing".equals(key)) {
            throw new IOException("resource not found");
        }
        return key.toUpperCase(Locale.ROOT);
    }

    static int parseAmount(String raw) {
        try {
            return Integer.parseInt(raw);
        } catch (NumberFormatException cause) {
            throw new IllegalArgumentException("Invalid amount: " + raw, cause);
        }
    }

    public static void main(String[] args) {
        List<Integer> valid = Stream.of("10", "20")
            .map(CausePreservingDemo::parseAmount).toList();
        System.out.println("valid=" + valid);

        try {
            Stream.of("10", "oops", "30")
                .map(CausePreservingDemo::parseAmount).toList();
        } catch (IllegalArgumentException error) {
            System.out.println("parse message=" + error.getMessage());
            System.out.println("parse cause=" +
                error.getCause().getClass().getSimpleName());
        }

        List<String> loaded = Stream.of("alpha", "beta")
            .map(unchecked(CausePreservingDemo::load)).toList();
        System.out.println("loaded=" + loaded);

        try {
            Stream.of("alpha", "missing")
                .map(unchecked(CausePreservingDemo::load)).toList();
        } catch (UncheckedIOException error) {
            System.out.println("io message=" + error.getMessage());
            System.out.println("io cause=" +
                error.getCause().getClass().getSimpleName());
            System.out.println("io detail=" + error.getCause().getMessage());
        }
    }
}
~~~

Compile and run in the directory containing the file using **JDK 17 or later**:

~~~bash
javac CausePreservingDemo.java
java CausePreservingDemo
~~~

**Exact stdout:**

~~~text
valid=[10, 20]
parse message=Invalid amount: oops
parse cause=NumberFormatException
loaded=[ALPHA, BETA]
io message=I/O in pipeline
io cause=IOException
io detail=resource not found
~~~

### Explaining the Output

- The two numbers 10 and 20 are valid and pass through Stream.map normally.
- "oops" triggers NumberFormatException, which parseAmount wraps in IllegalArgumentException with a message describing the invalid input. getCause().getClass().getSimpleName() returns NumberFormatException.
- The two keys alpha and beta pass through load and are converted to uppercase. This is the adapter's success branch.
- Upon encountering "missing", load throws IOException("resource not found"). The adapter catches IOException specifically and throws UncheckedIOException("I/O in pipeline", cause).
- At the main boundary, the exception is caught; message belongs to the **wrapper**, while the IOException type and "resource not found" message come from the **cause**.
- Because the program prints selected fields rather than calling printStackTrace(), stdout is short and stable. In a real system, a logger can record the wrapper's full stack trace to show the Caused by blocks.

The load method in the program simulates a data source so the example can run standalone, **without reading a real file**. In a real application, you can replace load with Files.readString(Path) or an API declaring throws IOException while keeping the same adapter pattern and cause preservation.

## 10. Testing Cause Preservation

When testing exception wrapping, do not just assert that some exception was thrown. Verify the **wrapper type, meaningful message, and original cause**.

JUnit 5-style test example, assuming accessible classes:

~~~java
// JUnit 5 assertion illustration, not a standalone program.
IllegalArgumentException error = assertThrows(
    IllegalArgumentException.class,
    () -> CausePreservingDemo.parseAmount("bad")
);

assertTrue(error.getMessage().contains("Invalid amount"));
assertInstanceOf(NumberFormatException.class, error.getCause());
~~~

This snippet requires importing the corresponding JUnit 5 assertions. If a method has context requirements such as orderId or file path, tests should also verify that the wrapper message contains the required context, **without asserting the entire system message that may vary across JDK versions** when unnecessary.

For an I/O adapter, you can use a fake IOFunction that throws a fixed IOException and verify:

~~~java
// Unit test idea, placed in a context where unchecked and IOFunction are available.
IOException original = new IOException("broken stream");
IOFunction<String, String> failing = value -> {
    throw original;
};

UncheckedIOException wrapped = assertThrows(
    UncheckedIOException.class,
    () -> unchecked(failing).apply("input")
);

assertSame(original, wrapped.getCause());
~~~

The key point here is **assertSame**: the exact same original IOException instance is preserved as the cause, rather than creating a new IOException that only copies the message. In real integration tests, also verify logging policies, error mapping, and that no sensitive data leaks.

### 10.1. Testing Success and Failure Paths

A good adapter must handle both branches:

- **Success:** returns the exact value provided by IOFunction without adding or losing data.
- **Failure:** throws the exact promised unchecked exception type, with the cause being the original checked exception.
- **Does not mask other exceptions:** unrelated RuntimeExceptions can propagate if the adapter only catches IOException.
- **Null boundary:** if the API forbids a null callback, validate explicitly and early with Objects.requireNonNull; do not create a lambda and only discover null when processing an element.

This testing matters more than merely running an example with valid input: if an adapter accidentally writes new RuntimeException(e.getMessage()), the success path still works, but the original diagnostic information is lost.

## 11. Logging and Error Observability in Real Applications

There is no need to log the full error at the parser layer, wrap and log again at the repository layer, log at the service layer, and finally log at the HTTP handler: a single error can turn into multiple duplicate log entries.

A generally useful rule:

1. **Wrap** when adding meaning/context or when changing the exception contract.
2. **Let propagate** when there is no recovery policy yet.
3. **Log once at the appropriate boundary**, passing the Throwable directly to the logger to preserve stack trace/cause/suppressed details.
4. **Return safe information** to the client. Public error codes should be understandable without exposing accounts, tokens, or internal system details.

Illustration using a common logging API style:

~~~java
// Logging API illustration; "logger" is provided by the application.
logger.error("Failed to process order {}", orderId, exception);
~~~

Use the proper overload of the logging library in use. Do not log only exception.getMessage() and drop the Throwable if you want to preserve the stack trace.

Operationally, consider **valid, controlled context** (task code, non-sensitive ID, operation type, error code). Exception wrapping must not be used to put private data into logs or responses without authorization.

## 12. Common Mistakes When Wrapping Exceptions

**Mistake 1 — losing the cause:** throw new RuntimeException(error.getMessage()). The fix is to pass the Throwable itself into a constructor that supports a cause.

**Mistake 2 — creating a new error without adding context:** wrapping IOException in RuntimeException("error", cause) across multiple layers. Wrap only at meaningful boundaries and choose a message describing the operation.

**Mistake 3 — swallowing errors:** catch (Exception e) { return null; } can cause a pipeline to return bad data without the caller realizing it. If null is a valid result, distinguish errors from valid results through an explicit contract.

**Mistake 4 — duplicate logging:** catching, logging in full, and rethrowing at every layer. Designate where logging is responsible and where layers only translate meaning.

**Mistake 5 — wrapping with the wrong type:** using UncheckedIOException for an exception unrelated to I/O, or turning a validation error into a misleading system error. The wrapper type affects the caller's catching and handling strategy.

**Mistake 6 — forgetting checked exceptions on SAMs:** Function.apply and Consumer.accept do not declare throws IOException. You need to catch/translate, use an adapter, or define a custom interface with appropriate throws.

**Mistake 7 — thinking wrapping equals recovery:** throwing a new RuntimeException still causes the pipeline to fail when evaluated; it does not turn an error into a valid result or automatically retry the task.

**Mistake 8 — catching InterruptedException and ignoring it:** this can break cancellation handling. When you cannot rethrow it and decide to convert the type, remember to consider Thread.currentThread().interrupt() per the contract.

**Mistake 9 — confusing cause and suppressed:** an error during close() alongside the primary error is suppressed; do not replace the primary cause just to keep the secondary error.

**Mistake 10 — catching Throwable broadly:** this can catch serious Errors that the application cannot recover from. Catch only the group appropriate for the boundary.

**Mistake 11 — relying on lambda execution count:** Stream is lazy and can short-circuit; exceptions in map/filter only appear when the callback is invoked. Do not expect every element to run to completion before an error is reported.

**Mistake 12 — leaking data in messages:** putting raw passwords, tokens, secret file contents, or personal data into exception messages. Choose the minimal required context, and filter/log safely according to application rules.

## 13. Checklist for Reviewing Code with Exception Wrapping

| Question | What to check |
| --- | --- |
| Why wrap? | Does it add necessary context or change the error contract? |
| Is the cause preserved? | new Wrapper(message, original) or equivalent mechanism |
| Is the wrapper type meaningful? | IllegalArgumentException, UncheckedIOException, domain error... |
| Are errors swallowed? | No returning fake seemingly valid values on unexpected errors |
| Is the catch too broad? | Avoid catch Throwable and unconditional catch Exception |
| Does it conform to SAM? | Especially checked exceptions in Function/Stream |
| Is interrupt preserved? | Consider InterruptedException and cancellation policy |
| Is it handled at the boundary? | No duplicate logging; appropriate error mapping |
| Are stack/cause/suppressed preserved? | Logger receives Throwable rather than just message |
| Are error paths tested? | Assert wrapper, cause, and message context |
| Is data protected? | No sensitive information leaked in exceptions/logs |

## 14. Self-Check Questions

1. What is the difference between throw new RuntimeException(error.getMessage()) and throw new RuntimeException("Read failed", error)?
2. Why cannot a lambda passed to Function<Path,String> directly call Files.readString(path) when IOException is unhandled?
3. When should you use UncheckedIOException instead of RuntimeException?
4. If a service already throws a business exception with a complete cause, does the controller layer necessarily have to wrap it again?
5. What is the difference between Throwable.getCause() and getSuppressed()?
6. Why should you check getCause() in unit tests instead of only comparing messages?
7. What happens if you catch IOException in map, return "", and continue collecting?
8. When should InterruptedException be handled differently from a data-parsing error?
9. Can a Stream throw an error during pipeline construction, or only when a terminal operation executes the callback?
10. How can you add context about a failing record without exposing sensitive data?
11. Why can catch(Throwable) to wrap all errors be dangerous?
12. Does wrapping an exception make a callback pure or thread-safe?

**Remember:** Good exception wrapping is **adding meaning at the right boundary without losing evidence**. In Java functional programming, converting checked exceptions to unchecked exceptions for lambda/Stream compatibility must always be an intentional decision and **pass the original cause**. Inspect the error type, message, cause, stack trace, suppressed exceptions, and final handling policy rather than merely trying to make the code compile.