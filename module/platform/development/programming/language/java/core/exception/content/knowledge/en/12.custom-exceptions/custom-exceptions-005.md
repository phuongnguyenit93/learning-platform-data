# Typed Context Properties and Avoiding Redundant Data in Java Custom Exceptions

> **Scope:** Java Core → Exception → Custom Exceptions. A good custom exception carries more than just a `message` and `stack trace`. When the caller needs to **handle failures differently based on an error code, resource identifier, field name, or task state**, the exception can provide **explicitly typed context properties**. However, adding every piece of data to an exception does not automatically make an API better: duplicate fields, values computable from other fields, easily desynchronized fields, or sensitive data will make handling and maintenance harder.

## 1. The Problem to Solve

Imagine an order service rejecting a request because the ordered quantity exceeds the available stock. A simple way to throw:

```java
throw new IllegalArgumentException(
        "Đơn ORD-21 đặt 8 sản phẩm, chỉ còn 3");
```

This string might be enough for **humans reading logs**, but if the UI needs to know specifically whether to show a "reduce quantity" button, the caller has to split the text or guess. That is a brittle contract: changing the language, punctuation, or wording can break the message-parsing code.

A custom exception with typed context separates two purposes:

- **Stable, machine-usable information:** `ErrorCode.INSUFFICIENT_STOCK`, `orderId`, `requestedQuantity`, `availableQuantity`.
- **Human-oriented information:** `getMessage()` describes what happened. The message wording can change according to logging requirements without affecting behavior-deciding code.

At the same time, you should not redundantly store `requestedQuantity` in the exception, in a separate `Map`, in a `details` string, and additionally in a copy of the entire `Order`. A single source of truth helps reduce the risk of conflicting copies.

**Goal:** store **just enough, meaningful, clearly typed, appropriately immutable, safe to pass across handling layers, and free of redundant data**.

## 2. What Does "Typed Context Properties" Mean?

A custom exception can define fields with specific semantics:

```java
final class InvalidQuantityException extends IllegalArgumentException {
    private final String orderId;
    private final int requestedQuantity;
    private final int availableQuantity;

    InvalidQuantityException(String orderId,
                             int requestedQuantity,
                             int availableQuantity) {
        super("Số lượng đặt vượt số lượng tồn");
        this.orderId = orderId;
        this.requestedQuantity = requestedQuantity;
        this.availableQuantity = availableQuantity;
    }

    String orderId() {
        return orderId;
    }

    int requestedQuantity() {
        return requestedQuantity;
    }

    int availableQuantity() {
        return availableQuantity;
    }
}
```

This is a **valid class declaration, though not yet a program with `main`**. A caller catching `InvalidQuantityException` can read directly:

```java
// Example in a compatible handler:
System.out.println(e.orderId());
System.out.println(e.requestedQuantity());
System.out.println(e.availableQuantity());
```

Instead of:

```java
// Anti-example: do not parse the message to make decisions.
String message = e.getMessage();
// Find "ORD-" and then extract the quantity using substring/regex.
```

Properties are called **typed** because they use `int` for quantities, `String` with clear semantics (or a dedicated ID type if needed), `enum` for error codes, `Instant` for timestamps, `URI` for resources, or a `record` to group related information. Not all of them should be present in the same exception.

### 2.1. What Counts as Useful Context?

A field is useful when at least one of the following goals needs it:

1. **Caller selects how to handle:** error code or business classification.
2. **Diagnostics:** task/resource ID to correlate with logs without including sensitive data.
3. **User feedback:** field name and valid limits to display correction guidance.
4. **System observability:** subsystem code or request ID to correlate events.
5. **Safe recovery:** information permitted for choosing a fallback source, conditional retry, or requesting new input.

Do not add a field just because it is "available at throw time." An exception should store the **minimum context required by the error-handling contract**.

## 3. Comparing Three Representation Levels

| Design Approach | Example | Strengths | Limitations |
| --- | --- | --- | --- |
| `message` only | `throw new IllegalArgumentException("...");` | Concise, sufficient for errors rarely needing special handling | Does not provide typed fields for the caller |
| Arbitrary `Map<String,Object>` | `Map.of("orderId", id, "qty", 8)` | Easy to extend, suited for telemetry without a fixed schema | Misspelled keys, runtime type mismatches, hard to discover, easy data leakage |
| Typed fields / `record` / `enum` | `ErrorCode`, `OrderContext` | Compile-time type checking, clear API, IDE support, easy to test | Adds classes/API; requires considering schema changes and compatibility |

**There is no rule** that every exception must have a `record` or `enum`. If the calling layer only needs to recognize an "invalid argument," `IllegalArgumentException` with a good message may suffice. Use a custom exception when there is a **genuine specialized handling contract**.

## 4. Choosing the Inheritance Hierarchy for a Custom Exception

Every Java exception belongs to the `Throwable` hierarchy:

```text
Throwable
├── Exception
│   ├── IOException
│   └── RuntimeException
│       ├── IllegalArgumentException
│       └── IllegalStateException
└── Error
```

If this is a caller contract violation (such as a negative quantity or insufficient stock under a specific API), a subclass of `IllegalArgumentException` or `RuntimeException` can make sense. If the caller **is expected to handle it with compile-time checking** (for example, failure of a contractually recoverable operation), a checked `Exception` subclass can be useful.

Example defining a **checked exception**:

```java
final class ImportFailedException extends Exception {
    ImportFailedException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

Example of an **unchecked exception**:

```java
final class InvalidRequestException extends IllegalArgumentException {
    InvalidRequestException(String message) {
        super(message);
    }
}
```

These are illustrative classes without `main`. Whether an exception is checked or unchecked **does not dictate** whether its context properties should be typed. The two concerns should be evaluated separately: the error-handling contract and the error data to carry.

### 4.1. Do Not Create an `Error` for Business Errors

`Error` is reserved for failure branches that normal applications should not treat as recoverable business incidents. A class like `InvalidOrderError extends Error` just to carry `orderId` usually misrepresents the semantics and bypasses standard `catch(Exception)` handlers. If you need to signal a contract violation or business failure, use an appropriate exception type.

## 5. Java 17 — Designing Error Codes, a Context `record`, and a Specialized Exception

The following complete example has:

- `enum ErrorCode` replacing free-form error code strings.
- `record OrderContext` grouping properties **belonging to the same situation**.
- `InsufficientStockException` extending `IllegalArgumentException`, keeping a typed code and context.
- A handler choosing action via `code()`, without parsing `getMessage()`.

Create file **`TypedOrderExceptionDemo.java`**:

```java
import java.util.Objects;

public class TypedOrderExceptionDemo {
    enum ErrorCode {
        INSUFFICIENT_STOCK,
        INVALID_QUANTITY
    }

    record OrderContext(String orderId,
                        int requestedQuantity,
                        int availableQuantity) {
        OrderContext {
            if (orderId == null || orderId.isBlank()) {
                throw new IllegalArgumentException("Thiếu orderId");
            }
            if (requestedQuantity < 0 || availableQuantity < 0) {
                throw new IllegalArgumentException(
                        "Số lượng không được âm");
            }
        }
    }

    static final class InsufficientStockException
            extends IllegalArgumentException {
        private final ErrorCode code;
        private final OrderContext context;

        InsufficientStockException(OrderContext context) {
            super("Số lượng đặt vượt số lượng tồn");
            this.code = ErrorCode.INSUFFICIENT_STOCK;
            this.context = Objects.requireNonNull(context);
        }

        ErrorCode code() {
            return code;
        }

        OrderContext context() {
            return context;
        }
    }

    static void reserve(OrderContext context) {
        if (context.requestedQuantity() >
                context.availableQuantity()) {
            throw new InsufficientStockException(context);
        }
        System.out.println("OK: " + context.orderId());
    }

    public static void main(String[] args) {
        OrderContext normal = new OrderContext("ORD-1", 2, 5);
        OrderContext shortage = new OrderContext("ORD-2", 7, 3);

        reserve(normal);

        try {
            reserve(shortage);
        } catch (InsufficientStockException e) {
            System.out.println("Code: " + e.code());
            System.out.println("Order: " + e.context().orderId());
            System.out.println("Requested: "
                    + e.context().requestedQuantity());
            System.out.println("Available: "
                    + e.context().availableQuantity());
            System.out.println("Message: " + e.getMessage());
        }
    }
}
```

Run with JDK 17+:

```bash
javac -encoding UTF-8 TypedOrderExceptionDemo.java
java TypedOrderExceptionDemo
```

**Exact stdout:**

```text
OK: ORD-1
Code: INSUFFICIENT_STOCK
Order: ORD-2
Requested: 7
Available: 3
Message: Số lượng đặt vượt số lượng tồn
```

**Key takeaways:**

1. The caller identifies the insufficient-stock error via the **exception type** or `ErrorCode.INSUFFICIENT_STOCK`, without depending on Vietnamese text.
2. `OrderContext` contains only information about the order situation. The quantity fields are `int`, not text needing re-parsing.
3. `code` is fixed in this subclass; if only a single error kind can occur, having both a specialized subclass **and** a fixed code field can be redundant. The next section explains how to pick one source of truth.
4. `record` automatically provides accessors, `equals`, `hashCode`, and `toString` based on its components. **Avoid logging a record's default `toString` if it contains sensitive data.**
5. Invariant checks in the record constructor prevent creating an `OrderContext` with negative quantities. This validates the **context data** and does not replace full business input validation.
6. `InsufficientStockException` holds a single `OrderContext` reference instead of storing three separate copies of `orderId`, `requestedQuantity`, and `availableQuantity`.

### 5.1. If You Already Have a Specialized Subtype, Do You Still Need `ErrorCode`?

Not always. For a handler:

```java
catch (InsufficientStockException e) {
    // The Java type is already sufficient to distinguish an insufficient-stock error.
}
```

storing an extra `code = INSUFFICIENT_STOCK` can **repeat the same fact**. However, an error code is still useful if the API must return a stable code to clients, record unified metrics across multiple exception types, or map to an external system.

Decide accordingly:

- If the whole system is pure Java and the subtype is clear enough: you can keep just the **exception type** and context.
- If the error code is part of a protocol/telemetry: keep one stable code; consider **deriving the code from the subtype** instead of storing a copy that could go out of sync.
- If one exception type covers multiple cases: an `enum` `code` may be genuinely necessary data.
- If an error code is stored alongside a subtype, design the constructor to prevent passing an arbitrary code that contradicts the subtype.

### 5.2. Do Not Pass an Arbitrary Code into a Subclass with Fixed Semantics

A design that easily creates contradictions:

```java
// Design anti-example, not a complete program.
new InsufficientStockException(
        ErrorCode.INVALID_QUANTITY, context);
```

If such a constructor is allowed, the Java type says "insufficient stock" while the code says "invalid quantity." You should **derive the fixed code from the exception type**, or switch the design to a general exception with a controlled code, rather than creating two conflicting contract fields.

## 6. The "Single Source of Truth" Rule for Context

Redundant data takes many forms, not just two fields with similar names.

| Data | Form of Redundancy | Better Design |
| --- | --- | --- |
| `orderId` in context and a separate field on the same object | Two places holding the same ID | A single `OrderContext.orderId()` |
| `amount` and `amountText` | Text derivable from the number | Store the number, format on display |
| `status` and `isFailure` | Boolean derivable from status | Store only the typed status |
| `errorCode` and `errorName` | Name derivable from the enum | Store only `ErrorCode`, call `name()` when needed |
| `cause` and `originalException` | Two references to the same root error | Use `getCause()` if it is a causal relationship |
| `message` and `description` copied identically | Two strings describing the same meaning | Message for human readers; separate context via typed fields |
| `timestamp` and `ageMillis` | `ageMillis` changes over time | Store the required timestamp, compute age at read time |
| Full `userProfile` and `userId` | Holding excessive data, PII risk | Safe ID or request ID only |
| `Map<String,Object>` and typed getters with the same data | Two schemas to keep in sync | Choose the typed API as primary source; build map only for export |
| `Throwable` stored in a separate field and passed to `super(message, cause)` | Two references to the same cause | Use `getCause()`, do not keep a duplicate |

**Messages are not forbidden from mentioning quantities for human readability.** "Avoiding redundancy" primarily refers to **source-of-truth state** and copies that can diverge. The message is typically a **rendering** of the data or a natural description; the key is **never parsing the message back to make decisions**.

### 6.1. Store Base Values Only, Compute Derived Values When Needed

For example, given `requestedQuantity` and `availableQuantity`:

```java
int shortage = Math.max(
        0, context.requestedQuantity()
                - context.availableQuantity());
```

If `shortage` is purely a deterministic calculation from the other two fields, you do not need a third `shortage` field in the exception. Storing all three creates the risk that a constructor or refactor computes it inconsistently.

**Intentional exception:** sometimes you need to store a "snapshot" of a derived value because the calculation rule depends on an exchange rate, timestamp, algorithm version, or external state. In that case, the value cannot truly be re-derived from the two existing inputs and may be worth storing, provided its snapshot semantics are clearly documented.

### 6.2. Do Not Store a Large Domain Object Just to Get an ID

Avoid:

```java
// Design anti-example; Order is a large domain object.
class FailedOrderException extends RuntimeException {
    private final Order entireOrder;
}
```

This is not a complete class. Holding `entireOrder` in a `Throwable` can inadvertently drag along large data, mutable state, references to sessions/connections, or sensitive data. An exception may outlive the failing operation due to log queues, retry frameworks, or storage.

Replace it with a **minimal identifier** and a few fields meaningful for recovery/diagnostics:

```java
private final String orderId;
private final ErrorCode code;
```

These fields must have clear semantics. For IDs of different kinds that are easily confused, a typed value object can be better than a generic `String`.

## 7. Immutability: `final` Is Necessary but Not Sufficient

An exception object itself is **not strictly immutable**, because `Throwable` has APIs such as `addSuppressed` and `setStackTrace`. Nevertheless, **custom context fields** should remain stable after the exception is created so that callers, loggers, and multiple threads never observe different values.

Checklist:

- Use `private final` for context fields.
- Validate `null` and invariants in the constructor.
- Do not provide setters that mutate the error code or IDs after the failure occurred.
- If the context contains `List`/`Set`/`Map`, make an appropriate unmodifiable defensive copy.
- For mutable objects nested inside a collection, copying the collection **is not a deep copy**. Prefer immutable components or snapshots of the needed fields.
- Do not store open resources or domain objects with uncontrolled lifecycles.
- Avoid passing exception objects with mutable context across threads without a clear concurrency contract.

### 7.1. Java 17 — Record with `List.copyOf` to Keep a Snapshot

Create file **`ImmutableContextDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class ImmutableContextDemo {
    record BatchContext(String batchId, List<String> itemIds) {
        BatchContext {
            Objects.requireNonNull(batchId, "batchId");
            itemIds = List.copyOf(
                    Objects.requireNonNull(itemIds, "itemIds"));
        }
    }

    static final class BatchFailedException
            extends RuntimeException {
        private final BatchContext context;

        BatchFailedException(BatchContext context) {
            super("Lô xử lý thất bại");
            this.context = Objects.requireNonNull(context);
        }

        BatchContext context() {
            return context;
        }
    }

    public static void main(String[] args) {
        List<String> original = new ArrayList<>(
                List.of("A", "B"));

        BatchContext snapshot =
                new BatchContext("B-1", original);
        BatchFailedException e =
                new BatchFailedException(snapshot);

        original.add("C");

        System.out.println("Gốc: " + original.size());
        System.out.println("Snapshot: "
                + e.context().itemIds().size());
        System.out.println("Items: "
                + String.join(",", e.context().itemIds()));

        try {
            e.context().itemIds().add("D");
        } catch (UnsupportedOperationException ignored) {
            System.out.println("Không thể sửa snapshot");
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 ImmutableContextDemo.java
java ImmutableContextDemo
```

Stdout:

```text
Gốc: 3
Snapshot: 2
Items: A,B
Không thể sửa snapshot
```

**Why does this matter?**

1. `original` is a mutable list held externally.
2. `List.copyOf` creates an unmodifiable list whose `String` elements are already immutable.
3. Mutating `original` after creating the exception does not alter the internal context.
4. The `context().itemIds()` getter does not let callers add elements.
5. If the list contains mutable objects other than `String`, `List.copyOf` only protects the list structure; it **does not make mutable elements immutable**.

Note: `List.copyOf` rejects `null` elements. If `null` is meaningful in your context model, a different contract is needed, though normally an ID list should not contain `null`.

## 8. Use `enum` or `record` for Error Codes and Context Fields?

An `enum` works well for a closed set of values with a finite list and stable semantics:

```java
enum ValidationCode {
    MISSING_FIELD,
    INVALID_FORMAT,
    OUT_OF_RANGE
}
```

A `record` fits an immutable-at-reference-level group of data with value-based behavior:

```java
record FieldIssue(String field, ValidationCode code,
                  int min, int max) {
}
```

This is a declaration-style example without `main`. Consider whether every field is meaningful for **every code value**. If `MISSING_FIELD` has nothing to do with `min`/`max`, a record holding all four fields can produce confusing states.

Simpler alternatives:

- Split into separate context types per error group if the schemas genuinely differ.
- Use an `ErrorCode` and field ID, adding bounds only when the error type actually needs them.
- Use a sealed hierarchy or specialized subtypes when the contract is complex enough; not mandatory for every system.
- Avoid a "mega context" with dozens of `null` fields and flags that are hard to keep consistent.

### 8.1. Required vs. Optional Fields

A required property should be validated right in the constructor. For example:

```java
this.orderId = Objects.requireNonNull(orderId, "orderId");
```

For optional values, have a clear policy: `null` may be a valid internal contract, or use a dedicated meaningful representation. Do not add `Optional` fields out of habit without considering serialization, API ergonomics, and usage.

### 8.2. Do Not Treat Every `String` as "Losing Type Safety"

`orderId` as a `String` is sometimes the sensible choice when existing APIs communicate with strings. Type safety is about fitting the contract, not the number of wrapper classes. If `userId` and `orderId` (both `String`) are frequently mixed up, a typed ID such as `record OrderId(String value)` can significantly reduce mistakes.

## 9. Do Not Duplicate `cause` and `suppressed` into Separate Fields

`Throwable` already provides:

```java
Throwable getCause()
Throwable[] getSuppressed()
StackTraceElement[] getStackTrace()
String getMessage()
```

Therefore, a normal custom exception **does not need** to add:

```java
// Redundant design, NOT recommended:
private final Throwable originalException;
private final String originalMessage;
private final StackTraceElement[] originalStack;
```

If `originalException` is the cause, pass it to `super(message, cause)` and read it back via `getCause()`. Storing `originalMessage` and the stack array separately increases memory usage, complicates lifecycle, and may retain unnecessary snapshots.

Similarly, if try-with-resources already attaches close failures via `addSuppressed`, there is no need to add a parallel `List<Throwable> cleanupErrors`, unless it represents a distinct business structure with independent semantics.

### 9.1. `message` Does Not Replace Typed Context

Conversely, you cannot argue that because `getMessage()` already contains `orderId`, all typed fields are redundant. The message is meant for human readers and may vary by locale. If the caller needs the order ID for lookup or the API must return an error code, typed context is the **contract data**.

A consistent design can:

- Store `orderId` and `ErrorCode` in typed fields.
- Use a short message, e.g., "Không đủ tồn kho".
- When logging, combine getters for structured output.
- When returning an API response, map code/context to a controlled response.
- Never parse `getMessage()` to recover the order ID.

### 9.2. Boundary Between `cause` and `context`

`cause` answers "Which `Throwable` led to this exception?". `context` answers "Which case/identifier/parameters are involved?". An `IOException` should be the cause if it actually caused the failure. Do not put an `IOException` inside a context `Map<String,Object>` to replace the cause chain.

## 10. Java 17 — Checked Exception with Typed Context and Preserved Cause

Create file **`PaymentProcessingDemo.java`**:

```java
import java.io.IOException;
import java.util.Objects;

public class PaymentProcessingDemo {
    enum FailureCode {
        PROVIDER_UNAVAILABLE,
        INVALID_RESPONSE
    }

    record PaymentContext(String transactionId, String providerCode) {
        PaymentContext {
            Objects.requireNonNull(transactionId, "transactionId");
            Objects.requireNonNull(providerCode, "providerCode");
        }
    }

    static final class PaymentProcessingException extends Exception {
        private final FailureCode failureCode;
        private final PaymentContext context;

        PaymentProcessingException(FailureCode failureCode,
                                   PaymentContext context,
                                   Throwable cause) {
            super("Không thể xử lý thanh toán", cause);
            this.failureCode =
                    Objects.requireNonNull(failureCode);
            this.context = Objects.requireNonNull(context);
        }

        FailureCode failureCode() {
            return failureCode;
        }

        PaymentContext context() {
            return context;
        }
    }

    static void invokeProvider() throws IOException {
        throw new IOException("Kết nối thất bại");
    }

    static void charge(PaymentContext context)
            throws PaymentProcessingException {
        try {
            invokeProvider();
        } catch (IOException e) {
            throw new PaymentProcessingException(
                    FailureCode.PROVIDER_UNAVAILABLE,
                    context, e);
        }
    }

    public static void main(String[] args) {
        PaymentContext context =
                new PaymentContext("TX-17", "PROVIDER-A");
        try {
            charge(context);
        } catch (PaymentProcessingException e) {
            System.out.println("Code: " + e.failureCode());
            System.out.println("Transaction: "
                    + e.context().transactionId());
            System.out.println("Provider: "
                    + e.context().providerCode());
            System.out.println("Cause: "
                    + e.getCause().getClass().getSimpleName());
            System.out.println("Message: " + e.getMessage());
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 PaymentProcessingDemo.java
java PaymentProcessingDemo
```

Stdout:

```text
Code: PROVIDER_UNAVAILABLE
Transaction: TX-17
Provider: PROVIDER-A
Cause: IOException
Message: Không thể xử lý thanh toán
```

**Explanation:**

- `PaymentProcessingException extends Exception` is a **checked exception**, so `charge` declares `throws PaymentProcessingException`.
- `FailureCode` lets the caller choose a policy based on a stable value, without using `getMessage().contains("thanh toán")`.
- `PaymentContext` contains the transaction ID and provider code needed for investigation. It does not hold the full payment object or card numbers.
- The original `IOException` is passed to `super(message, cause)`. It is **not** stored redundantly in a field like `originalIOException`.
- `getCause()` provides the diagnostic trail for the I/O-layer failure.
- The example code does not perform real payments: it only illustrates error-contract design and reproducible output.

### 10.1. Why Not Use `String failureCode`?

Strings can be used if error codes must match an external protocol with a dynamically changing set of values. But within a Java module that has a fixed set of codes, an `enum` helps the compiler and IDE recognize valid options, reduces typos, and makes `switch` logic clear.

When mapping to HTTP/JSON, **do not automatically use `enum.ordinal()` as a stable error code**: enum ordering can change. Use the name or a controlled protocol code field if the public API requires long-term compatibility.

## 11. Choosing Context Based on the Error Handler

The same failure can be observed at different layers:

| Exception Reader | Data Typically Needed | Should Not Be Stuffed into the Exception |
| --- | --- | --- |
| Java caller | Exception type, error code, identifier, failing field | Copy of the entire request |
| UI/Form validation | Field name, validation code, necessary limits | Stack trace, SQL, tokens |
| Orchestration service | Task ID, phase, appropriate retry info | Open `Connection`, `InputStream` |
| Logging system | Request/correlation ID, code, cause, stack | Passwords or secret keys |
| External API client | Public error code and safe message | Internal class names, file paths, raw cause chain |
| Metrics system | Finite/low-cardinality code | `orderId`, `userId`, or transaction ID as high-cardinality metric labels |

**Minimizing context does not mean omitting needed information.** For instance, a safe request ID can help correlate logs, though it does not necessarily have to be stored in every exception if a logging context (MDC or tracing context) is already present and its lifecycle is properly managed.

### 11.1. Do Not Push All Context into the Exception

If a piece of information is only used for logging at one layer and does not need to travel with the exception, it can be passed through an appropriate logging/tracing context. Conversely, if the caller genuinely needs to know which field failed in order to handle it, placing a typed field on the exception can be clearer than relying on a logging side-channel.

The practical question is **who is responsible for using the information, for how long, and where**.

## 12. Sensitive Data, Large Data, and Security

Exceptions may be logged automatically, displayed in crash reports, sent to monitoring systems, or retained in queues; their properties can be inspected via debugging, reflection, or serialization depending on the environment.

Avoid putting into context:

- Passwords, access tokens, refresh tokens, session cookies, or secret keys.
- Full payment card numbers, authentication data, or entire user profiles.
- Unfiltered request bodies, JSON containing personal information, or `Authorization` headers.
- Streams/connections and objects whose lifecycles extend beyond the exception's intent.
- Extremely large collections or object graphs that could increase memory retention.
- Values that the caller is not authorized to access.

Instead, choose **non-sensitive reference IDs**, error codes, publicly permissible field names, and controlled values. Even IDs can be data requiring protection depending on system context; there is no "always safe" list for every application.

### 12.1. Java 17 — Typed Context Without Retaining Secret Values

Create file **`SafeValidationContextDemo.java`**:

```java
import java.util.Objects;

public class SafeValidationContextDemo {
    enum Field {
        API_TOKEN,
        EMAIL,
        AMOUNT
    }

    enum ValidationCode {
        MISSING,
        INVALID
    }

    static final class SafeValidationException
            extends IllegalArgumentException {
        private final Field field;
        private final ValidationCode code;
        private final String requestId;

        SafeValidationException(Field field,
                                ValidationCode code,
                                String requestId) {
            super("Dữ liệu đầu vào không hợp lệ");
            this.field = Objects.requireNonNull(field);
            this.code = Objects.requireNonNull(code);
            this.requestId =
                    Objects.requireNonNull(requestId);
        }

        Field field() {
            return field;
        }

        ValidationCode code() {
            return code;
        }

        String requestId() {
            return requestId;
        }
    }

    static void checkToken(String token, String requestId) {
        if (token == null || token.isBlank()) {
            throw new SafeValidationException(
                    Field.API_TOKEN,
                    ValidationCode.MISSING,
                    requestId);
        }
    }

    public static void main(String[] args) {
        try {
            checkToken("", "REQ-42");
        } catch (SafeValidationException e) {
            System.out.println("Field: " + e.field());
            System.out.println("Code: " + e.code());
            System.out.println("Request: " + e.requestId());
            System.out.println("Message: " + e.getMessage());
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 SafeValidationContextDemo.java
java SafeValidationContextDemo
```

Stdout:

```text
Field: API_TOKEN
Code: MISSING
Request: REQ-42
Message: Dữ liệu đầu vào không hợp lệ
```

**Why is this safer?** The exception only holds the field name and error code, not the input token. This does not replace other security controls, but it reduces the risk of accidentally logging the secret value itself in `toString()`, the message, or the context object.

Also avoid calling `getMessage()` with a string built from the entire token: many frameworks log messages by default.

### 12.2. Do Not Serialize Raw Exceptions to Clients

An API response should be a curated DTO, such as `{code, field, requestId, safeMessage}`. Do not return the raw exception, stack trace, cause, suppressed exceptions, and all custom fields directly. This distinction both improves security and keeps the API contract independent of the Java implementation.

## 13. Human Messages and Machine Codes

`getMessage()` is prose; it is not guaranteed to remain unchanged across versions, languages, configurations, or detail levels. A typed `errorCode` is used when machine logic needs a stable policy.

Reasonable handler example:

```java
switch (e.code()) {
    case INSUFFICIENT_STOCK ->
            System.out.println("Đề xuất giảm số lượng");
    case INVALID_QUANTITY ->
            System.out.println("Yêu cầu số lượng hợp lệ");
}
```

This is an illustrative snippet requiring a variable `e` with a `code()` accessor returning `ErrorCode`. The goal is **not branching on message substrings**.

If the application is multilingual, it is common to store the code/field and map to a localized message at the **presentation layer**, rather than making a localized string the sole source of truth inside the exception.

### 13.1. Priority/Classification Pitfalls

If handlers classify by subtype, sometimes **no error code is needed**. If handlers classify by error code, sometimes **you do not need a subclass per code**. You should not necessarily build two parallel classification systems and try to keep every mapping in sync.

Choose one coherent design and provide an adapter/mapping when communicating with external layers, rather than storing multiple copies simultaneously in every `Throwable`.

## 14. Preserving `cause` and `suppressed` Relationships

When a lower-level error causes a higher-level error:

```java
try {
    callExternalService();
} catch (java.io.IOException e) {
    throw new ServiceOperationException(
            "Không thể gọi dịch vụ", context, e);
}
```

This is an illustrative snippet assuming `ServiceOperationException` has the corresponding constructor. The `context` property describes the operation (e.g., ID and phase), while `cause` is the exception that occurred. The two **do not replace each other**.

In try-with-resources, resource-closing failures can be attached as **suppressed exceptions** to the primary exception. Do not duplicate them into `List<Throwable> closeFailures` on your custom exception if `getSuppressed()` already suffices.

### 14.1. Java 17 — Context and Cause Are Separate Responsibilities

Create file **`ContextWithCauseDemo.java`**:

```java
import java.io.IOException;
import java.util.Objects;

public class ContextWithCauseDemo {
    record TaskContext(String taskId, String phase) {
        TaskContext {
            Objects.requireNonNull(taskId);
            Objects.requireNonNull(phase);
        }
    }

    static final class TaskFailedException
            extends RuntimeException {
        private final TaskContext context;

        TaskFailedException(TaskContext context, Throwable cause) {
            super("Tác vụ thất bại", cause);
            this.context = Objects.requireNonNull(context);
        }

        TaskContext context() {
            return context;
        }
    }

    public static void main(String[] args) {
        IOException original =
                new IOException("Nguồn dữ liệu mất kết nối");
        TaskFailedException error = new TaskFailedException(
                new TaskContext("JOB-9", "READ"),
                original);

        System.out.println("Task: " + error.context().taskId());
        System.out.println("Phase: " + error.context().phase());
        System.out.println("Message: " + error.getMessage());
        System.out.println("Cause: "
                + error.getCause().getClass().getSimpleName());
        System.out.println("Suppressed: "
                + error.getSuppressed().length);
    }
}
```

Run:

```bash
javac -encoding UTF-8 ContextWithCauseDemo.java
java ContextWithCauseDemo
```

Stdout:

```text
Task: JOB-9
Phase: READ
Message: Tác vụ thất bại
Cause: IOException
Suppressed: 0
```

The exception keeps `TaskContext` for task identification, while `IOException` resides in `getCause()`. No second field `private IOException originalIOException` is needed. Because the program has no secondary close/cleanup errors, the suppressed count is `0`.

## 15. Important Constructor Rules

The constructor of a `Throwable` subclass should establish valid state right from the start:

```java
public final class DataImportException extends Exception {
    private final String importId;
    private final FailureCode code;

    public DataImportException(String importId,
                               FailureCode code,
                               Throwable cause) {
        super("Nhập dữ liệu thất bại", cause);
        this.importId =
                java.util.Objects.requireNonNull(importId);
        this.code =
                java.util.Objects.requireNonNull(code);
    }

    public String importId() {
        return importId;
    }

    public FailureCode code() {
        return code;
    }
}
```

This is a **class template**, assuming `FailureCode` is already defined and the file/class follows Java naming rules. It is not a standalone program.

Ensure that:

- The `super(message, cause)` call is placed properly according to Java constructor rules.
- Required fields are validated; use `Objects.requireNonNull` when appropriate.
- No duplicate copy of `cause` is stored; call `getCause()` when needed.
- No file I/O, network calls, or heavy operations occur inside the exception constructor; exceptions should be lightweight and easy to construct on failure paths.
- No overridable methods are called from the constructor if they depend on subclass fields that are not yet initialized.
- Consider constructor overloads if callers have both with-cause and without-cause cases; avoid meaningless overloads nobody uses.
- Messages are short and free of sensitive data.

### 15.1. What Happens If You Call `super` and Then Validate Fields?

Validation may throw `NullPointerException` or `IllegalArgumentException` inside the constructor before the intended exception finishes constructing. That is valid Java, but the caller will see an exception-construction failure instead of the intended exception. Identify **which context is always available** on the failure path and design the constructor so required values can genuinely be supplied.

Do not create a fake "required context" if many failure paths actually lack an ID. You can split the exception type or use a clearly documented nullable contract when appropriate.

## 16. Choosing Snapshots Over References to Changing State

Suppose an `Order` has mutable state and is stored as a field:

```java
// Anti-pattern when the caller can continue modifying the order.
private final Order order;
```

Even if the field is `final`, **the `order` object itself can still change** after the exception is created. When logged later, the current data no longer reflects the state at failure time.

Replace with snapshot data:

```java
record QuantitySnapshot(String orderId,
                        int requested,
                        int availableAtFailure) {
}
```

A `record` containing `String` and `int` like this is a simple, stable value context. The name `availableAtFailure` tells readers the value is a **snapshot at the time of failure**, not the current live stock.

This is an important distinction:

- Current "available quantity" belongs to the domain store and can change.
- "Available at failure" is an observation from a single processing attempt.
- If the caller wants the **latest** stock, it must query the appropriate data source rather than treating the exception as holding live state.

### 16.1. A Snapshot Is Not Automatically a Deep Copy

A record containing `List<OrderLine>` where `OrderLine` is mutable can still change through references. `List.copyOf` only protects the list structure, not every child object. Depending on the risk level, choose immutable components, convert to IDs/primitive values, or write purposeful deep-copy logic.

## 17. Logging and Serialization: Consequences of Adding Fields

Java `Throwable` implements `Serializable`, but that does **not** mean every custom field is automatically suitable for Java serialization. If an exception class has a field pointing to a non-serializable object, serialization can fail. In modern Java, do not choose Java native serialization as a public API protocol just because `Exception` already implements `Serializable`.

If a project genuinely must serialize exceptions across an internal Java boundary:

- Field types must be compatible with serialization requirements, or have a mapping strategy.
- Consider `serialVersionUID`, class-change compatibility, and version-skew risks.
- Do not store objects containing credentials/resources in serialized exceptions.
- Do not rely on mutating incompatible context fields across versions.
- Consider converting errors into **DTOs with a stable schema** for HTTP, events, and message queues instead of serializing `Throwable` directly.

Java supports `record` serialization with its own rules if components are serializable; a `record` **does not automatically make every component serializable**. If serialization is a requirement, evaluate and test the actual structure.

### 17.1. Typed Data Is Not Necessarily "Metric-Safe"

An `ErrorCode` is a good metric label because it has a bounded set of values. An `orderId`, `transactionId`, or email can produce an enormous number of labels (*high cardinality*). Even though these fields are strongly typed, you should not use them directly as metric labels. Put IDs into logs/tracing according to policy, while metrics should generally use fixed codes/subsystems.

## 18. Testing a Custom Exception's Contract

A good test does more than ask "was an exception thrown?". For a custom exception with typed context, verify:

1. **Correct exception type** on the failure path.
2. **Correct code** if the code is part of the contract.
3. **Correct context fields** for the given input.
4. **Invariants** of the constructor/record.
5. **Cause** preserved when wrapping a lower-level exception.
6. **Immutability** of the context when the input contains a mutable collection.
7. **No sensitive data** in logged/returned messages or context.
8. **Success path** does not throw unnecessary exceptions.

With JUnit 5, a conceptual test example:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class TypedOrderExceptionDemoTest {
    @Test
    void shortageProvidesTypedDetails() {
        var context = new TypedOrderExceptionDemo.OrderContext(
                "ORD-5", 9, 2);

        var error = assertThrows(
                TypedOrderExceptionDemo.InsufficientStockException.class,
                () -> TypedOrderExceptionDemo.reserve(context));

        assertEquals(
                TypedOrderExceptionDemo.ErrorCode.INSUFFICIENT_STOCK,
                error.code());
        assertEquals("ORD-5", error.context().orderId());
        assertEquals(9, error.context().requestedQuantity());
        assertEquals(2, error.context().availableQuantity());
    }
}
```

**This is an illustrative test file, not a standalone `javac` file:** it requires JUnit Jupiter on the classpath and placing the test file in the same default package or adjusting visibility/package accordingly. The code focuses on testing **structured data**, not parsing message text.

### 18.1. Do Not Test Context via Default `toString()`

`record.toString()` and `Throwable.toString()` are meant for display, not as a stable schema for software parsing. Test getters/field types instead of asserting a specific string formatting unrelated to the API contract.

### 18.2. Testing Against Redundant Data

Test a mutable context that is modified after throwing the exception: do the exception's getters preserve the right snapshot? If code has two fields representing the same value, you could test their consistency—but it is better to remove the redundant field at design time rather than adding tests to maintain two copies forever.

## 19. Choosing Between Custom Exceptions and Structured Error Results

Not every validation failure should throw an exception. If user form input frequently has multiple invalid fields, a result type:

```java
record ValidationIssue(String field, String code) {}
record ValidationResult(
        boolean valid,
        java.util.List<ValidationIssue> issues) {}
```

may be more appropriate than using `Throwable` for each expected error. This is an **illustrative type definition**, without a `main` program. When multiple errors occur simultaneously, a list of `ValidationIssue` usually expresses the data more directly than a list of suppressed exceptions (which are meant for secondary error relationships).

Decide by semantics:

- **Exception:** unable to complete the operation per its contract; requires unwinding or caller failure-path handling.
- **Result/validation errors:** expected failures as part of normal communication flow, where multiple issues can be aggregated and returned without throwing.

If you use a custom exception, keep its context clearly meaningful; do not turn every business outcome into an exception just because you can create typed fields.

## 20. Common Mistakes and How to Fix Them

| Design Mistake | Why It Is Dangerous | Fix |
| --- | --- | --- |
| Parsing `getMessage()` to extract order ID/code | Text changes without a machine contract | Provide typed getters |
| `Map<String,Object>` for all context | Wrong keys/types only surface at runtime | Use fields/records/enums when schema is known |
| Keeping both `quantity` and `quantityText` | Easy to drift when formatting or updating | Store only quantity; format at presentation |
| Keeping an entire mutable domain entity | Delayed logging sees changed state; data leakage | Store a minimal snapshot |
| `private final List<T>` without copying | Caller can still mutate the list | `List.copyOf`; check for mutable elements |
| Using `record` and assuming deep immutability | Components may point to mutable objects | Choose immutable/snapshot components |
| Storing `originalException` alongside `cause` | Duplicates data `Throwable` already has | `super(message, cause)` + `getCause()` |
| Storing arbitrary `errorCode` in a subtype with fixed semantics | Type and code can contradict each other | Derive code, restrict constructor |
| Putting passwords/tokens into messages | Can be logged automatically | Store only field/code and safe IDs |
| Using user IDs as metric labels | High cardinality and privacy risk | Metrics on bounded codes; IDs in controlled logs |
| Returning raw `Throwable` over HTTP | Leaks stack, cause, internal fields | Map to a filtered DTO |
| Adding dozens of getters "just in case" | Bloated API, harder versioning | Only fields with actual use cases |
| Using `Error` for domain errors | Wrong semantics and misses common handlers | Use appropriate `Exception`/`RuntimeException` |
| Catching a custom exception and returning "OK" | Hides failure, corrupts state | Recover genuinely or report failure |
| Dropping `cause` to shorten logs | Loses root-cause trail | Keep cause; adjust logger policy if needed |
| Using suppressed exceptions as a list of all validation issues | Misuses `Throwable` relationship semantics | Use a result with a list of issues |
| Using native serialization as a public error protocol | Couples to implementation and risks data exposure | Use a DTO / versioned schema |
| Treating context properties as live state | Snapshot is stale after throwing | Name fields "atFailure" and query the store for fresh values |

## 21. Practice Exercises

### Exercise 1 — Find Redundant Data

An exception has `orderId`, `order`, `orderIdText`, and `context.getOrderId()`. Choose one place as the single source of truth. Explain why keeping the entire `order` object can let state change and retain sensitive data.

### Exercise 2 — Error Code or Subtype?

Design `InsufficientStockException` with `ErrorCode.INSUFFICIENT_STOCK`. State one case where the code is genuinely useful (mapping to API/metrics) and one case where the Java subtype alone is sufficient. If keeping both, how must the constructor prevent the type and code from contradicting each other?

### Exercise 3 — Collection Snapshot

Run `ImmutableContextDemo`, then try removing `List.copyOf` from the compact constructor. After `original.add("C")`, how will `context.itemIds().size()` change? Why is `private final BatchContext context` not enough to guarantee a snapshot if the record holds a reference to a mutable list?

### Exercise 4 — Cause or Separate Field?

In `PaymentProcessingDemo`, try adding `private final IOException original;` with the same reference passed to `super(message, e)`. Does it add any handling capability? **No**, if the caller already has `getCause()` and needs no other special typed contract; remove the duplicate.

### Exercise 5 — Security

Modify `SafeValidationContextDemo` so the input is a very long fake token. Verify that stdout and the getters still **do not** output the token. Identify other places where raw input could be logged accidentally and how to control them.

### Exercise 6 — Enum and External Protocol

Suppose an API returns JSON code `"STOCK_LOW"`, while the Java enum is named `INSUFFICIENT_STOCK`. Design an explicit mapper instead of relying on `ordinal()` or implicitly treating `enum.name()` as an immutable contract. Test the mapping for each public code.

### Exercise 7 — Multiple Validation Errors

A form has 3 invalid fields at once. Would you create 3 suppressed exceptions or one `ValidationResult` containing 3 `ValidationIssue`s? Explain why a structured result usually expresses expected validation failures more clearly than suppressed errors.

### Exercise 8 — Derivable Data

A context stores `requested=7`, `availableAtFailure=3`, `shortage=4`. If shortage is always `max(0, requested-available)`, remove the redundant field and compute it when needed. If the business has rounding rules or point-in-time exchange rates, when is a derived snapshot value worth keeping?

### Exercise 9 — Contract Testing

Write a JUnit test confirming that `PaymentProcessingException` is checked, has the right code/context, and `getCause()` is the original `IOException`. Do not assert the `getMessage()` string if the message is not a stable machine contract.

### Exercise 10 — Designing Usage Boundaries

An exception currently stores a list of 100,000 item IDs. This is real information, but should all of it be placed inside a `Throwable`? Propose a batch ID, a count, a few sample failed indices, or a separate report location so the exception does not retain excessive data.

## 22. Context-Aware Exception Design Checklist

- [ ] Is a custom exception genuinely needed beyond standard exceptions or a result type?
- [ ] Did you choose checked vs. unchecked properly based on the caller's contract?
- [ ] Is it clear who uses each context field?
- [ ] Are fields appropriately typed (`enum`, numbers, typed IDs, `record`) instead of parsing messages?
- [ ] Are fields in a consistent state and validated in the constructor?
- [ ] Are recomputable values **derived rather than stored redundantly**?
- [ ] Did you avoid storing `cause`/stack/suppressed a second time when `Throwable` already provides APIs?
- [ ] If both a subtype and a code express an error kind, are they guaranteed to be consistent?
- [ ] Did you avoid storing large/mutable domain objects, unnecessary collections, or open resources?
- [ ] Have context collections needing snapshots been defensively copied?
- [ ] Do you keep in mind that `final` does not make an entire object graph immutable?
- [ ] Is the message meant for humans and never parsed by code for decisions?
- [ ] Are tokens, passwords, and sensitive bodies/headers excluded from messages and context?
- [ ] Do loggers and API responses have separate policies and avoid serializing raw `Throwable` externally?
- [ ] Are IDs used properly in logging/tracing rather than as high-cardinality metric labels?
- [ ] Do fields added to the exception make sense for versioning/serialization if the system uses them?
- [ ] Do tests verify type/code/context/cause, snapshots, and failure paths?
- [ ] When an error occurs, can the caller handle it or report failure per the contract?

**Conclusion:** Design a custom exception as a **compact, structured failure report**. Keep typed fields that are genuinely useful to the caller, use `enum`/`record` where they add clarity, control snapshots and privacy, and **do not duplicate data already present** in `Throwable` or other fields. `message` helps humans understand; `code` and context help software handle; `cause` preserves the causal chain. Balancing these three groups of information makes exceptions easier to read, easier to test, and more stable as the application grows.
