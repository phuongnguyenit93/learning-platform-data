# Specifying Inputs, Outputs, Nullability, and Exceptions Across Extension Boundaries in Java

## 1. What Is an Extension Contract?

In an application with runtime extensibility, the **host** invokes code from an **extension/plugin/provider** through a shared API or SPI. For example, the host discovers implementations with ServiceLoader, selects a processor from a registry, or invokes an adapter loaded by a separate class loader. Host and plugin may be developed and upgraded independently by separate teams; the compiler checks only part of the agreement.

Consider the signature:

~~~java
Result process(Request request) throws ExtensionFailure;
~~~

The signature alone does not answer: Can Request be null? Which fields are required? May the plugin mutate the input list? Can Result ever be null? When no data is found, what does the plugin return? Which exceptions signal business/task failures versus contract violations? If each side interprets these differently, a bug in one plugin can trigger a NullPointerException in another layer or be masked as a "successful" result.

An **extension contract** specifies preconditions, postconditions, nullability, failure categories, data ownership, lifecycle, and compatibility requirements. It is part of the stable API, not an accidental detail of an implementation.

## 2. Roles and Responsibilities at the Boundary

| Role | Commitment |
| --- | --- |
| Caller/host | Prepare input satisfying preconditions; catch API usage errors before invoking the plugin |
| Extension | Never break promised invariants; return output satisfying postconditions or throw declared failures |
| Boundary adapter | Validate plugin output, classify errors, preserve causes, and apply the host's error policy |
| Consumer | Rely on public APIs and stable error codes, not internal classes or plugin message strings |

A practical contract should state: input types and value domains; required/optional fields; the "no data found" representation; result invariants; allowed exceptions; timeouts, cancellation, resources, and concurrency where applicable; and policy when a plugin does not comply.

**Preconditions** are what the caller must guarantee before the call; **postconditions** are what the provider must guarantee upon normal return. **Expected failures** must be separated from **contract violations or bugs**.

## 3. Inputs: Early Validation and Ownership Boundaries

### 3.1. Checking More Than Java Types

Reference types in Java can hold null. A properly typed String can still be empty or whitespace-only; a properly typed List can still contain null, invalid elements, or mutable objects. Choose rules upfront for each field: for instance, operation must be non-null and non-blank; items must be non-null and contain no nulls; size must stay within contract limits.

Apply validation in the **host before crossing the boundary** so caller mistakes are not misattributed as plugin bugs. Invariants depending on provider-specific logic can still be checked inside the provider, but cannot replace boundary validation. When normalizing data (trimming, case conversion, path normalization), publish the rules so request meaning is not silently altered.

Objects.requireNonNull(value, "name") provides fail-fast checking; emptiness, numeric ranges, or cross-field consistency require explicit checks. An invalid request should never be dispatched down to a plugin only to throw an obscure exception from a deep layer.

### 3.2. Do Not Accidentally Grant Data Mutation Rights to Plugins

If the host passes an ArrayList directly, a plugin can mutate the list while the host still holds it. With List<String>, List.copyOf creates an unmodifiable copy through the List API and rejects null elements. Records and immutable DTOs help preserve preconditions after validation.

However, List.copyOf protects only the **container**, not deep-copying mutable elements. With List<MutableItem>, elements themselves can still be mutated. Choose immutable DTOs, deep defensive copies, or restricted views according to the contract.

You must also specify whether a plugin may retain a Request or callback after the method returns; who owns transactions, connections, buffers, and request-scoped data. Do not expose internal host state or resources in the extension API without a concrete design reason.

## 4. Outputs: Success, Absence, and Failure States

Three cases must be distinguished:

| Situation | Appropriate representation | Meaning |
| --- | --- | --- |
| Success with data | Non-null Result satisfying invariants | Caller can use it safely |
| Success with no data | Optional.empty(), empty collection, or a published NOT_FOUND code | Valid outcome, not a plugin crash |
| Task could not complete | Declared exception or an explicit failure result type | Caller applies error/retry policy |

Each API should have **only one representation** for one meaning. Do not represent "not found" sometimes as null, sometimes as an exception, and sometimes as an empty list. Never return an empty list to hide a data-source read failure.

A Result must state the invariants of every field: description is non-null and non-blank, count is non-negative, status code matches payload, etc. Returning normally constitutes a commitment that all invariants hold. The host should validate critical postconditions right after receiving output from the plugin, before passing that data to the rest of the system.

If output is a Stream, InputStream, AutoCloseable, or callback, specify **who closes it, when to close it, and how long the data remains valid**. If Result holds a plugin's mutable object, keeping a reference can fail when the plugin is unloaded or its state changes; prefer independent DTOs in the shared API.

## 5. Nullability Rules for Each Position

Java 17 does not automatically treat String, Request, or List as non-null. Write and enforce nullability at every boundary.

| Position | Recommended contract | If violated |
| --- | --- | --- |
| Extension instance | Non-null | Host rejects before call |
| Root request | Non-null | Host rejects before call |
| Required fields | Non-null and within valid domain | Constructor/validator reports invalid input |
| Optional fields | Explicitly allow null or use an alternative representation | Neither caller nor provider guesses |
| Return value of process | Non-null on normal completion | Adapter flags contract violation |
| Lookup value that may be absent | Non-null Optional<Result> or explicit status | Optional.empty() means absent |
| List/Map elements | Non-null unless API states otherwise | Validate on creation and receipt |

Null is distinct from an empty string, zero, false, an empty collection, and NOT_FOUND status. Those values must never silently substitute for one another.

Optional suits **return values that may be absent**, rather than defaulting every parameter or DTO field to Optional. A method returning Optional must still **never return null instead of Optional.empty()**.

Annotations like @Nullable/@NonNull can help IDEs and static analysis tools when a project standardizes on annotations and a checker. Standard Java compilers do not fully enforce nullability contracts merely from annotations; runtime validation at the boundary remains valuable.

## 6. Exceptions: Classifying Errors Before Deciding How to Handle Them

| Case | Example representation | Responsibility/handling |
| --- | --- | --- |
| Caller passes invalid arguments | IllegalArgumentException or NullPointerException before call | Caller fixes input |
| Plugin fails per published business rules | ExtensionFailure (checked, or typed error result) | Host may retry/fallback if safe |
| Plugin returns null against contract | ContractViolation | Host reports plugin postcondition violation |
| Plugin throws undeclared RuntimeException | ContractViolation with original cause | Host classifies plugin fault and diagnoses |
| Provider cannot be found or instantiated | Dedicated discovery error; ServiceConfigurationError with ServiceLoader | Handled by loader/registration |
| JVM encounters a serious error | Error (e.g. OutOfMemoryError) | Do not mask as a business error |

**Checked exceptions** fit when the caller has a specific recovery action for an expected failure. **Unchecked exceptions** typically express programming errors or invalid preconditions. You may choose a Success/Failure result type instead of exceptions, as long as it is consistent; never arbitrarily interpret every RuntimeException as "no data".

When wrapping an exception, always preserve the **cause**:

~~~java
throw new ContractViolation("extension failed unexpectedly", original);
~~~

Never match exception message strings to decide retries; if stable machine handling is needed, publish error codes. Log plugin name, operation, correlation ID, and error code, while avoiding leaking secrets, sensitive requests, or stack traces to callers.

Do not catch Throwable indiscriminately just to keep running: an Error can indicate a critical VM failure. For InterruptedException, propagate it if the method signature allows; if caught without rethrowing, restore the interrupt flag via `Thread.currentThread().interrupt()` and handle cancellation. Never swallow interrupts to pretend work succeeded.

When closing a resource fails while another error is already propagating, try-with-resources preserves the closing failure as a **suppressed exception**. Inspect the primary exception, its cause, and its suppressed exceptions for accurate diagnosis.

Specifically for ServiceLoader, provider loading/lookup is lazy; ServiceConfigurationError can surface while iterating or instantiating providers. Whether to skip a broken provider or fail startup altogether belongs in the **discovery contract**; catching errors at that point differs from catching all Errors during plugin execution.

## 7. Complete Java 17 Example: Two-Way Contract Enforcement

The program below illustrates a simple extension point. Request and Result cannot be null; items cannot contain nulls; count cannot be negative. Expected processing failures go through ExtensionFailure, while null returns or unexpected runtime exceptions are converted by the adapter into ContractViolation.

Create the file **ExtensionContractDemo.java**:

~~~java
import java.util.List;
import java.util.Objects;

public final class ExtensionContractDemo {
    public record Request(String operation, List<String> items) {
        public Request {
            operation = Objects.requireNonNull(operation, "operation");
            if (operation.isBlank()) {
                throw new IllegalArgumentException("operation is blank");
            }
            items = List.copyOf(Objects.requireNonNull(items, "items"));
        }
    }

    public record Result(String description, int count) {
        public Result {
            description = Objects.requireNonNull(description, "description");
            if (description.isBlank()) {
                throw new IllegalArgumentException("description is blank");
            }
            if (count < 0) {
                throw new IllegalArgumentException("count is negative");
            }
        }
    }

    public interface Extension {
        Result run(Request request) throws ExtensionFailure;
    }

    public static final class ExtensionFailure extends Exception {
        public ExtensionFailure(String message) {
            super(message);
        }
    }

    public static final class ContractViolation extends RuntimeException {
        public ContractViolation(String message) {
            super(message);
        }

        public ContractViolation(String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static Result call(Extension extension, Request request)
            throws ExtensionFailure {
        Objects.requireNonNull(extension, "extension");
        Objects.requireNonNull(request, "request");

        try {
            Result result = extension.run(request);
            if (result == null) {
                throw new ContractViolation("extension returned null");
            }
            return result;
        } catch (ExtensionFailure expected) {
            throw expected;
        } catch (ContractViolation violation) {
            throw violation;
        } catch (RuntimeException unexpected) {
            throw new ContractViolation(
                    "extension threw an unexpected exception", unexpected);
        }
    }

    public static void main(String[] args) throws ExtensionFailure {
        Request input = new Request("count", List.of("a", "b"));

        Extension good = request -> new Result(
                request.operation() + ":" + request.items().size(),
                request.items().size());
        System.out.println(call(good, input));

        Extension nullResult = request -> null;
        try {
            call(nullResult, input);
        } catch (ContractViolation ex) {
            System.out.println(ex.getMessage());
        }

        Extension unavailable = request -> {
            throw new ExtensionFailure("data source unavailable");
        };
        try {
            call(unavailable, input);
        } catch (ExtensionFailure ex) {
            System.out.println("failed: " + ex.getMessage());
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac --release 17 ExtensionContractDemo.java
java ExtensionContractDemo
~~~

Exact standard output:

~~~text
Result[description=count:2, count=2]
extension returned null
failed: data source unavailable
~~~

Explanation:

1. The Request record checks operation and then copies items; List.copyOf rejects lists containing null elements. Invalid input is blocked before the plugin processes it.
2. The Result record checks description and count upon construction. A healthy provider returns an output satisfying all postconditions.
3. A provider returning null causes the adapter to throw ContractViolation right at the boundary, rather than letting NullPointerException occur further downstream.
4. A provider throwing ExtensionFailure expresses an expected task failure. The host receives that exact type.
5. An unexpected RuntimeException is wrapped with its cause; Errors are not caught. For cancellation or interruption, if the API supports them, add explicit conventions instead of treating them as ordinary runtime faults by default.

This is a self-contained runnable program; ServiceLoader, lifecycle, and sandboxing must be designed according to your system. Catching an exception must not be mistaken for rolling back side effects that already occurred inside the plugin.

## 8. Control Flow at the Boundary Adapter

~~~text
Caller creates Request
    |
    v
Host checks preconditions
    |-- invalid -> caller error, do not call plugin
    v
Extension.run(request)
    |-- declared ExtensionFailure -> expected task failure
    |-- unexpected RuntimeException -> plugin failure, preserve cause
    v
Normal return
    |
    v
Host checks non-null and postconditions
    |-- invalid -> ContractViolation
    v
Return validated Result to caller
~~~

Validating input alone is not enough because a plugin can still violate the contract. Validating output cannot automatically undo side effects that the plugin already performed before failing. If an operation has side effects, add atomicity, idempotency, transaction, or compensation protocols per operation type.

For asynchronous APIs, separately specify whether the CompletionStage/Future itself may be null, whether the completed value may be null, how cancellation is represented, and how causes are unwrapped from CompletionException/ExecutionException. A Future timeout only bounds how long the caller waits; it does not guarantee that a plugin ignoring interrupts has actually stopped.

## 9. Shared API, Class Loaders, and Contract Evolution

In the JVM, class identity depends on **class name and defining class loader**. Two versions of the same interface with identical names defined by two different loaders are not necessarily castable to each other. Host and plugin need a unified way to share the API contract; never let each plugin bundle an incompatible copy of the interface and expect casts to succeed.

When changing an API version:

- Never arbitrarily change the meaning of null, Optional.empty(), empty lists, or exceptions. That can be a behavioral breaking change even when Java signatures do not change.
- Place public interfaces, DTOs, and exceptions in the shared API. Avoid returning objects from plugin-private libraries or exposing classes loaded only inside a plugin.
- Publish required/optional field rules and version fallbacks; test both binary compatibility and behavioral compatibility.
- Do not turn exception message strings into a protocol. If the host integrates multiple plugins, use stable error codes or contract types.
- Fallback/retry policy belongs to the host; retry only idempotent operations or those with proper deduplication.

## 10. Commitments Accompanying Data and Errors

**Concurrency:** The API must state whether an extension instance can be called concurrently, whether it is reentrant, and who owns mutable state. An interface does not make implementations thread-safe on its own.

**Lifecycle/resources:** The API must state who closes Closeables, when callbacks may be invoked, which thread may invoke them, and how long Request/Result references may be retained. Use try-with-resources on the side responsible for closing.

**Fault isolation:** Exception translation helps the host report errors uniformly, but does not create a sandbox. Plugins running in the same JVM can still impact shared resources. For untrusted code, consider process/JVM isolation and an IPC protocol instead of relying solely on catch blocks.

**Observability:** Structured logs should include provider ID, operation, correlation ID, error classification, and cause; avoid logging sensitive data. Separate caller-safe messages from technical diagnostics meant for operations.

## 11. Contract Test Matrix

| Test case | Expectation |
| --- | --- |
| Extension or Request is null | Host rejects before call |
| Required field is null, blank, or out of range | Fails fast with intentional input error |
| List contains a null element | Rejected when contract specifies non-null |
| Plugin mutates received collection | Does not mutate host's snapshot when API promises immutability |
| Plugin returns valid result | Host receives Result and invariants hold |
| No data found | Uses exact defined absence representation |
| Plugin returns null against contract | Adapter reports ContractViolation |
| Plugin throws ExtensionFailure | Host receives expected failure type |
| Plugin throws unexpected RuntimeException | Adapter preserves cause and classifies plugin failure |
| Provider fails to load or instantiate | Discovery emits dedicated error/event |
| Interruption, timeout, cancellation | Does not swallow interrupt and does not assume task has stopped |
| Concurrent calls or differing API versions | Adheres to thread-safety and compatibility policies |

Use shared **contract tests** for every provider; include fake providers that intentionally return null, produce invalid output, or throw checked/unchecked exceptions. With runtime loading, run integration tests across real class loaders and API versions because unit tests on a single classpath can miss type-identity errors.

## 12. Extension Point Design Checklist

- Nullability, value domains, and mutation/retention rules are explicitly documented for every input.
- Success with data, success with absence, and failure are clearly distinguished; postconditions are validated.
- Caller errors, declared task failures, plugin contract violations, and discovery errors are categorized.
- Exception wrapping preserves causes; logging, interruption, cancellation, and retry policies are defined.
- Public DTOs, interfaces, and exceptions have a consistent class-loader origin and versioning rules.
- Resource ownership, lifecycle, concurrency, and a contract test suite are defined for every provider.

**Principle:** every value and error crossing an extension boundary must have an agreed-upon meaning. The host guarantees valid input, the plugin guarantees valid output or a declared failure, and the boundary adapter verifies both sides.