# Keeping Error Information Independent of `message` Wording in Java Custom Exceptions

A Java exception typically carries a message retrieved via `getMessage()`, such as `"quantity must be positive"`. This string is useful for human readers and diagnostics, but **it should not become a control-flow key for the program**: merely changing the wording, translating the message into Vietnamese, or switching libraries can cause `if` branches that compare the message to behave incorrectly.

With **custom exceptions**, a more resilient design separates three responsibilities:

1. **The exception type** represents the failure category appropriate to the API contract, such as `ValidationException` or `OrderException`.
2. **The error code and typed properties** represent the facts the program needs to rely on, such as `ValidationCode.OUT_OF_RANGE`, the field name `quantity`, or a standardized operation code.
3. **`message`** represents an explanatory sentence for human readers/logs that can change without altering handling logic; **`cause`** preserves the original exception object when translating errors across layers.

> Principle: **control with types and structured data; explain with `message`; preserve the root cause with `cause`.** Do not branch business logic based on whether `message` contains a word or matches a sentence verbatim.

## 1. The Problem with Using `getMessage()` as an Error Code

Example of a fragile design:

```java
try {
    placeOrder();
} catch (IllegalArgumentException ex) {
    if ("quantity must be positive".equals(ex.getMessage())) {
        showQuantityError();
    } else {
        showGenericError();
    }
}
```

This is **illustrative code**, assuming the methods are declared appropriately. Simply changing the wording from `"quantity must be positive"` to `"quantity must be greater than zero"` can cause the caller to fall into the generic error branch, even though the nature of the error has not changed at all.

Other problems:

- **Localization:** the Vietnamese version `"Số lượng phải lớn hơn 0"` does not match the English string.
- **Contextual information:** the message might include a field name, request ID, or operation, causing full-string comparison to fail.
- **Library changes:** a number-parsing library might change how `NumberFormatException.getMessage()` is formatted.
- **Missing message:** `Throwable.getMessage()` can return `null`; calling `ex.getMessage().contains(...)` risks throwing a `NullPointerException` right inside the handler.
- **Stability:** a message is a diagnostic interface for human readers, not necessarily a stable machine protocol.
- **Security:** trying to stuff full input values or secrets into the message just to make branching easier can leak sensitive data through logs and stack traces.

Also, do not "fix" the comparison by writing:

```java
if (ex.getMessage().contains("quantity")) {
    // ...
}
```

An unrelated internal error might coincidentally contain the word `quantity`. Text matching with `contains` or regex only perpetuates dependence on wording in a harder-to-control way.

## 2. What Does "Error Information Independent of Message" Actually Mean?

Suppose an input validation rule has three causes:

| Error Fact | Structured Code | Displayable Message |
| --- | --- | --- |
| Missing required quantity | `REQUIRED_FIELD` | `quantity is required` |
| Quantity is not a valid integer | `INVALID_INTEGER` | `quantity must be an integer` |
| Quantity is outside the 1–100 range | `OUT_OF_RANGE` | `quantity must be between 1 and 100` |

**The error code** carries the meaning the program needs to understand and must be kept stable according to the contract. **The message** helps human readers understand the failure condition and can be rewritten for clarity, translated, or phrased differently in logs.

When the caller needs to know which field failed, you can add a `field` property:

```java
String field = ex.getField();
```

The line above is **illustrative code**: `ex` must be a custom exception with a `getField()` method. The caller uses the property instead of searching for the word `quantity` in the message.

For errors with multiple parameters, properties can also include `minAllowed`, `maxAllowed`, `operation`, or `retryable`. However, **you should not add all raw data** to the exception: only keep what is necessary, has a clear contract, and is safe to appear in an object that may be logged.

### Four Types of Data to Keep Separate

| Component | Purpose | Why Can It Change? |
| --- | --- | --- |
| `Throwable` subtype | Categorize failure groups | Java API design |
| Error code (`enum`/constant value) | Stable branching, mapping to responses | Only changed with a compatibility plan |
| Typed context | Identify the related field/operation/rule | Per data contract |
| `message` | Explanation/logs/diagnostics | Wording, localization, UX improvements |
| `cause` | Preserve the original exception | Depends on the failure path and invoked operation |

An exception may have no cause if the error originates directly from a business condition; do not fabricate a fake cause just so every constructor has one.

## 3. Choose the Appropriate Exception Type Before Adding Properties

In the problem of **staying independent of how the message is written**, the first question is whether the caller needs to distinguish failures by **subtype**, **error code**, or both:

- Choose a subtype (`InvalidQuantityException`, `PaymentDeclinedException`) when the caller wants to `catch` for a distinct action.
- Choose a single exception with a typed `ValidationCode` when multiple reasons share the same handling path but the UI/API needs a specific code.
- Choose checked vs. unchecked based on the caller contract, not on whether the error is "fixable."
- If validation failure is an expected outcome of a form, a structured `ValidationResult` may be more appropriate than throwing exceptions in bulk.

Whichever option you choose, **do not compare `getMessage()` to control flow**.

## 4. Designing an Error Code `enum`

A typed code helps callers branch without depending on the language of the message:

~~~java
enum ValidationCode {
    REQUIRED_FIELD, INVALID_INTEGER, OUT_OF_RANGE
}
~~~

An `enum` is useful within the same module; codes exposed publicly over JSON should have stable/versioned strings along with a policy for **unknown codes**. Do not use `ordinal()` as a protocol code: reordering the enum changes the numbers. If enum constant names might change during refactoring, keep a fixed `publicCode` property instead of using `name()` as an uncontrolled public contract.

**The code must describe the meaning of the error**, not merely be an uppercase version of the message. Updating the translation from `"must be an integer"` to `"enter a whole number"` does not change `INVALID_INTEGER`.

## 5. How Should Custom Exception Properties Be Designed?

To **keep error information independent of the message**, a custom exception can declare `private final ValidationCode code` and `private final String field`, expose clear getters/record accessors, and validate against `null` in the constructor. Always use `super(message, cause)` when wrapping a genuine technical error; do not invent a fake `cause` for self-originated validation errors.

Callers read `ex.getCode()` and `ex.getField()`; the UI maps the code to a safe, locale-appropriate message. There is **no need** to parse the field name or value range from `ex.getMessage()`. When an exception crosses a JSON/API boundary, serialize only a DTO with an allowed schema—do not expose the entire stack trace or `Throwable`.

Detailed rules on deep immutability, avoiding duplicate ID copies, collection snapshots, and context minimization are covered in the lesson on designing typed context; here, the focus is proving that **changing the wording does not change the classification result**.

## 6. Complete Java 17+ Example: Validation with Code, Field, and Cause

This example simulates order quantity validation without requiring external files or services. Save the file **`StructuredValidationDemo.java`**:

```java
import java.util.Objects;

public class StructuredValidationDemo {

    enum ValidationCode {
        REQUIRED_FIELD,
        INVALID_INTEGER,
        OUT_OF_RANGE
    }

    static final class ValidationException
            extends IllegalArgumentException {

        private static final long serialVersionUID = 1L;

        private final ValidationCode code;
        private final String field;

        ValidationException(
                ValidationCode code,
                String field,
                String message) {
            this(code, field, message, null);
        }

        ValidationException(
                ValidationCode code,
                String field,
                String message,
                Throwable cause) {
            super(message, cause);
            this.code = Objects.requireNonNull(code, "code");
            this.field = Objects.requireNonNull(field, "field");
        }

        ValidationCode getCode() {
            return code;
        }

        String getField() {
            return field;
        }
    }

    static int parseQuantity(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new ValidationException(
                    ValidationCode.REQUIRED_FIELD,
                    "quantity",
                    "Quantity is required");
        }

        final int number;
        try {
            number = Integer.parseInt(raw);
        } catch (NumberFormatException cause) {
            throw new ValidationException(
                    ValidationCode.INVALID_INTEGER,
                    "quantity",
                    "Quantity must be a whole number",
                    cause);
        }

        if (number < 1 || number > 100) {
            throw new ValidationException(
                    ValidationCode.OUT_OF_RANGE,
                    "quantity",
                    "Quantity must be between 1 and 100");
        }

        return number;
    }

    static void runCase(String raw) {
        try {
            System.out.println("OK quantity=" + parseQuantity(raw));
        } catch (ValidationException ex) {
            System.out.println("ERROR code=" + ex.getCode());
            System.out.println("field=" + ex.getField());
            System.out.println("message=" + ex.getMessage());
            System.out.println(
                    "cause="
                    + (ex.getCause() == null
                            ? "none"
                            : ex.getCause().getClass().getSimpleName()));
        }
    }

    public static void main(String[] args) {
        runCase("5");
        runCase(null);
        runCase("abc");
        runCase("0");
        runCase("200");
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 StructuredValidationDemo.java
java StructuredValidationDemo
```

**Exact stdout:**

```text
OK quantity=5
ERROR code=REQUIRED_FIELD
field=quantity
message=Quantity is required
cause=none
ERROR code=INVALID_INTEGER
field=quantity
message=Quantity must be a whole number
cause=NumberFormatException
ERROR code=OUT_OF_RANGE
field=quantity
message=Quantity must be between 1 and 100
cause=none
ERROR code=OUT_OF_RANGE
field=quantity
message=Quantity must be between 1 and 100
cause=none
```

### Program Analysis

**`runCase("5")`:** the string contains the integer `5`, within the range 1–100; `parseQuantity` returns `5` with no exception.

**`runCase(null)`:** the condition `raw == null || raw.isBlank()` uses *short-circuit* evaluation, so `isBlank()` is not called when `raw` is null. The custom exception is created with `REQUIRED_FIELD` and the `quantity` field, with no cause because the error is detected directly.

**`runCase("abc")`:** `Integer.parseInt` throws `NumberFormatException`. The code catches the error where context can be added; it creates a `ValidationException` with code `INVALID_INTEGER`, preserving `NumberFormatException` as the cause. The handler sees a stable code without relying on JDK-dependent text like `For input string ...`.

**`runCase("0")` and `runCase("200")`:** parsing into a number succeeds, but the value violates the business boundary, so both produce the code `OUT_OF_RANGE`. A single error code can represent the same rule even when the input values differ.

The program intentionally **does not print the raw invalid value**. Input data can sometimes be sensitive or very long, so you should not concatenate arbitrary input directly into `message`.

### Does Changing the Message Change the Logic?

Suppose you change:

```java
"Quantity must be a whole number"
```

to:

```java
"Please enter a valid integer for quantity"
```

This is an example of changing **only a single string in the code**. The `message=...` output will change, but the `INVALID_INTEGER` code and `quantity` field remain the same. If the caller uses `getCode()`, the branching logic **does not change**. This is a key criterion of the design requirement to "keep error information independent of message wording."

## 7. How Callers Handle Errors Using Error Codes Instead of Messages

With the `ValidationException` from the example, a handler can use:

```java
catch (ValidationException ex) {
    switch (ex.getCode()) {
        case REQUIRED_FIELD ->
                markFieldRequired(ex.getField());
        case INVALID_INTEGER ->
                markFieldInvalid(ex.getField());
        case OUT_OF_RANGE ->
                markFieldOutOfRange(ex.getField());
    }
}
```

This is an **illustrative snippet**, assuming the `markField...` methods exist and the block follows an appropriate `try`. The caller relies on the `enum` value. There is no need to call `getMessage()` to decide how to handle it.

Benefits of `switch` on an enum:

1. Handling policy is decoupled from message phrasing.
2. It is easy to test the `REQUIRED_FIELD` branch without locking the test to an English sentence.
3. Messages can be localized.
4. The IDE can detect where updates are needed if a new error code is added.
5. The scope of handling is clearer than an `if/else` chain checking arbitrary keywords.

**However, the handler still needs to understand the meaning of each code.** If a code name is renamed or its meaning is reused for a different error, "having an enum" will not automatically save compatibility. Error codes must have definitions and a lifecycle management process.

## 8. Localization and API Mapping Independent of Technical Messages

An API may want to return a Vietnamese or English message depending on the locale, while internal exceptions retain technical messages to aid investigation. A sound approach is to **translate from the error code to the public message at the communication boundary**.

Example:

```text
ValidationException {
  code = OUT_OF_RANGE,
  field = "quantity",
  message = "Quantity must be between 1 and 100"
}
                  │
                  ▼
         API error mapping
                  │
           ┌──────┴──────┐
           ▼             ▼
     Locale vi-VN   Locale en-US
           │             │
           ▼             ▼
 "Số lượng phải"   "Quantity must"
 "từ 1 đến 100"    "be from 1 to 100"
```

The public message can change by locale without **modifying the `OUT_OF_RANGE` code** and without parsing strings from `getMessage()`.

### Complete Java 17+ Example: Same Error Code, Two Public Messages

Save the file **`ErrorCodeMappingDemo.java`**:

```java
public class ErrorCodeMappingDemo {

    enum ErrorCode {
        ORDER_NOT_FOUND("ORD_404"),
        ORDER_ALREADY_CLOSED("ORD_409");

        private final String publicCode;

        ErrorCode(String publicCode) {
            this.publicCode = publicCode;
        }

        String publicCode() {
            return publicCode;
        }
    }

    static final class OrderException extends RuntimeException {
        private static final long serialVersionUID = 1L;

        private final ErrorCode code;
        private final String internalOrderId;

        OrderException(
                ErrorCode code,
                String internalOrderId,
                String diagnosticMessage) {
            super(diagnosticMessage);
            this.code = java.util.Objects.requireNonNull(
                    code, "code");
            this.internalOrderId =
                    java.util.Objects.requireNonNull(
                            internalOrderId, "internalOrderId");
        }

        ErrorCode getCode() {
            return code;
        }

        String getInternalOrderId() {
            return internalOrderId;
        }
    }

    record ApiError(String code, String message) {}

    static void process(String mode) {
        switch (mode) {
            case "missing" -> throw new OrderException(
                    ErrorCode.ORDER_NOT_FOUND,
                    "internal-17",
                    "Order lookup returned no record");
            case "closed" -> throw new OrderException(
                    ErrorCode.ORDER_ALREADY_CLOSED,
                    "internal-18",
                    "Cannot update a closed order");
            default -> System.out.println("result=OK");
        }
    }

    static ApiError toPublicError(
            OrderException ex, boolean vietnamese) {

        String message = switch (ex.getCode()) {
            case ORDER_NOT_FOUND -> vietnamese
                    ? "Không tìm thấy đơn hàng"
                    : "Order not found";
            case ORDER_ALREADY_CLOSED -> vietnamese
                    ? "Đơn hàng đã đóng"
                    : "Order is already closed";
        };

        return new ApiError(
                ex.getCode().publicCode(),
                message);
    }

    static void runCase(String mode) {
        try {
            process(mode);
        } catch (OrderException ex) {
            ApiError en = toPublicError(ex, false);
            ApiError vi = toPublicError(ex, true);

            System.out.println("code=" + en.code());
            System.out.println("en=" + en.message());
            System.out.println("vi=" + vi.message());
            System.out.println(
                    "diagnostic=" + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        runCase("ok");
        runCase("missing");
        runCase("closed");
    }
}
```

Run:

```bash
javac -encoding UTF-8 ErrorCodeMappingDemo.java
java ErrorCodeMappingDemo
```

**Exact stdout:**

```text
result=OK
code=ORD_404
en=Order not found
vi=Không tìm thấy đơn hàng
diagnostic=Order lookup returned no record
code=ORD_409
en=Order is already closed
vi=Đơn hàng đã đóng
diagnostic=Cannot update a closed order
```

### Why Not Return `ex.getMessage()` Directly to the Client?

In the example, `OrderException` holds `internalOrderId` so the internal layer can identify the operation, but the `ApiError` DTO **does not contain the internal ID**. This is an intentional separation: the client only needs the public code and an appropriate message.

For production:

- Do not automatically return internal messages in HTTP responses; they may contain file paths, SQL, configuration, or sensitive data.
- Map error codes to **HTTP status codes** using clear rules if the application is a web API (for example, resource-not-found errors often map to 404, while state conflicts may map to 409 depending on semantics). Decide according to the actual contract.
- If multilingual messages use a resource bundle or localization system, the lookup key should come from **a stable error code**, not the English sentence itself.
- When wording changes, tests still verify the code and structured data; testing translation content can be a separate test suite.
- Log records should include a non-sensitive correlation ID and the `Throwable` object, without indiscriminately logging personal IDs.

**The `diagnostic=...` output in stdout is for demonstration purposes.** In a real application, this message belongs in controlled internal logs, not in the API response.

## 9. Why Preserve `cause` When Wrapping Library Exceptions into Custom Exceptions?

A structured error does not replace the **technical trail** of the root cause.

Example:

```java
static int parseAge(String raw) {
    try {
        return Integer.parseInt(raw);
    } catch (NumberFormatException cause) {
        throw new ValidationException(
                ValidationCode.INVALID_INTEGER,
                "age",
                "Age must be an integer",
                cause);
    }
}
```

This is an **illustrative method** that must be placed in scope where `ValidationException` and `ValidationCode` from the earlier example are visible. Callers rely on `INVALID_INTEGER` and `age` to decide the response, while `getCause()` still points to the original `NumberFormatException` for investigation.

### How the Trail Gets Lost

```java
catch (NumberFormatException ex) {
    throw new ValidationException(
            ValidationCode.INVALID_INTEGER,
            "age",
            "Age is invalid");
}
```

If you only create a wrapper without `cause`, outer handlers have a harder time knowing whether the real failure was a formatting issue, a number exceeding `int` limits, or another parsing detail. There are situations where omitting the cause is intentional for security policy or abstraction boundaries, but that must be a deliberate decision rather than forgetting the constructor argument.

**`cause` is not `message`.** Building a string `"invalid: " + ex.getMessage()` is not equivalent to preserving the `ex` object. You lose the exception type, stack trace, and suppressed exceptions of the original cause.

### Rethrowing the Same Object

If an intermediate layer does not need to change the error contract, `throw ex;` rethrows the same exception. This preserves the error code, field, cause, and stack trace already recorded on the object. There is no need to create a new wrapper at every layer.

### Avoid Turning `cause` into a Public Error Code

Callers should not inspect the class name `NumberFormatException` in `getCause()` and assume it is an error on the `quantity` field; the parsing layer is the one that knows the field name, so that layer should provide **a structured validation code and field name**. The cause is for diagnostics, not a substitute for the business contract.

## 10. Custom Exceptions with Multiple Context Parameters

If an error has properties that help the caller act accurately, you can add typed fields:

```java
final class RangeViolationException
        extends IllegalArgumentException {

    private static final long serialVersionUID = 1L;

    private final String field;
    private final int minimum;
    private final int maximum;

    RangeViolationException(
            String field, int minimum, int maximum) {
        super("Field is outside the allowed range");
        this.field = java.util.Objects.requireNonNull(
                field, "field");
        this.minimum = minimum;
        this.maximum = maximum;
    }

    String getField() {
        return field;
    }

    int getMinimum() {
        return minimum;
    }

    int getMaximum() {
        return maximum;
    }
}
```

This is **an illustrative class** that can be placed in an appropriate package. The handler can build localized UI messages using `field`, `minimum`, and `maximum` without needing to parse numbers back out of the message.

### What Data Should Not Be Placed in Exception Fields?

You should not automatically store:

- Passwords, tokens, cookies, API keys.
- Entire request bodies or sensitive customer data.
- Very large payloads or mutable objects with complex lifecycles.
- References to connections/streams just to "re-read context" after they have been closed.
- Internal objects with multithreading constraints that the caller cannot manage.

Fields inside an exception object can be logged, serialized, inspected by a debugger, or sent to telemetry. Only keep context that is **necessary, compact, and compliant with security policy**.

### Do Not Forget True Immutability

`private final List<String> details` only makes the **list reference** unchangeable; if the list is mutable, its contents can still be modified. If a custom exception needs to hold a stable collection, consider taking a snapshot:

```java
this.details = java.util.List.copyOf(details);
```

This is an illustrative snippet, applicable when `details` is a non-null list with valid elements. Depending on requirements, defensive copying may also be needed for deeper mutable objects.

## 11. DTO Structure for Error Responses and Public Contracts

An **exception object** and an **API response** serve two different goals:

| Internal Exception | Public Response DTO |
| --- | --- |
| Carries Java type/stack trace/cause | Carries a stable schema for clients |
| Has an internal diagnostic message | Has a message allowed to be public and localized |
| May hold technical context | Contains only fields specified in the contract |
| Java callers can catch by subtype | Clients receive defined string codes/statuses/fields |
| Can change during internal refactoring | Requires version compatibility management |

Illustrative schema example:

```json
{
  "code": "VAL_003",
  "field": "quantity",
  "message": "Số lượng phải nằm trong khoảng cho phép"
}
```

The error code is the field committed to the API version; the message is a display string that can change. In a real system, you should clearly specify which fields are stable, HTTP statuses, how request/correlation IDs are used, and conditions for exposing information.

### Rules for Stable Codes

If a system has already published the code `ORD_404` for "order not found," avoid reusing that code for "order closed" in a later version. Reusing meanings causes clients relying on the old code to misinterpret the error.

A stable code set typically has:

- A **unique** public name or value.
- A precise definition of the error condition.
- An applicable scope within the module/domain.
- Guidance on how clients can handle it.
- A policy for adding new codes, replacing codes, and deprecating old codes.
- Tests ensuring the meaning does not change when the message is edited.

Not every small application needs a complex registry, but from the start you should treat error codes as **contracted data**, distinct from free-form wording.

## 12. Using `switch` on Enums: Benefits and Limitations

Java 17 supports `switch` expressions, which are convenient for mapping error codes to values:

```java
String publicMessage = switch (code) {
    case REQUIRED_FIELD -> "Required field";
    case INVALID_INTEGER -> "Invalid integer";
    case OUT_OF_RANGE -> "Outside allowed range";
};
```

This is an illustrative snippet where `code` has type `ValidationCode` from the earlier example. There is no `default` branch, so if a new enum constant is added without handling it, the compiler can detect that the `switch` expression does not cover all values.

This is a major advantage of **typed codes** over `if (message.contains(...))`. However:

- Callers must manage enum expansion according to a compatibility plan.
- If a code is a string received from an external system, check for unknown inputs instead of calling `Enum.valueOf` unconditionally.
- An enum is a good choice when the set of codes is known at compile time; plugin/extensible systems may need a registry or value object instead of a single enum.
- Do not create enum names that mirror English messages and treat that as separation; an enum should represent **stable semantics**, not just attach identifiers to phrasing.

### What If You Need to Determine Whether an Error Is Retryable?

Some systems add a `retryable` property, but caution is needed. Whether something is "retryable" often depends on **the handling context, retry count, idempotency, transaction state**, and the calling layer's policy—not just the exception name. Do not assume every `IOException` should be retried or that every `ValidationException` can never be processed further; the rule depends on the contract.

Structured data helps make more accurate decisions, but **it does not replace understanding the operation's semantics**.

## 13. Testing the Right Contract Instead of Testing the Entire Message

A brittle test:

```java
// Illustrative: test depends on wording.
assertEquals(
        "Quantity must be a whole number",
        exception.getMessage());
```

Every reasonable wording adjustment can cause the test to fail even though behavior has not changed.

For exceptions with a code and field, tests should prefer:

```java
// Illustrative: requires an assertion framework and an appropriate exception variable.
assertEquals(
        ValidationCode.INVALID_INTEGER,
        exception.getCode());
assertEquals("quantity", exception.getField());
assertInstanceOf(
        NumberFormatException.class,
        exception.getCause());
```

These are **JUnit-style illustrative statements**, not a standalone program; `assertInstanceOf` is an API in appropriate JUnit versions. The test verifies:

- **Stable classification:** code `INVALID_INTEGER`.
- **Context:** field `quantity`.
- **Cause:** `NumberFormatException` is preserved.

You can test messages separately when the message is genuinely part of the public contract or when testing localization resources. In that case, establish upfront that changing wording is an intentional contract change rather than treating it as an error-handling protocol.

### Framework-Independent Testing

Even without JUnit, you can write plain Java checks:

```java
if (ex.getCode() != ValidationCode.INVALID_INTEGER) {
    throw new AssertionError("Unexpected validation code");
}
if (!"quantity".equals(ex.getField())) {
    throw new AssertionError("Unexpected field");
}
if (!(ex.getCause() instanceof NumberFormatException)) {
    throw new AssertionError("Original cause not preserved");
}
```

This is an illustrative snippet placed inside a handler with a properly typed `ex`. The checks rely on **data**, not on the wording of `getMessage()`.

## 14. Version Compatibility When Error Codes Become a Contract

In a single-module application, an enum can be updated in lockstep with callers. However, in a public Java library, external API, or microservices system, error codes may be consumed by many clients.

Changes to consider:

| Change | Typical Impact |
| --- | --- |
| Editing punctuation or phrasing of internal messages | Should not affect code-based logic |
| Translating public messages | Should not change error codes or structured fields |
| Adding an enum constant | Callers with exhaustive `switch` statements may need updates |
| Renaming an enum constant used by Java clients | May break source/binary compatibility |
| Changing a published `publicCode` value | May break clients or stored data |
| Reusing an old code for a new error | Easily causes silent misinterpretation; avoid |
| Changing exception subtype between checked/unchecked | Changes the caller's handling contract |
| Removing a field/context currently used by clients | May break APIs and tests |
| Stopping propagation of a previously provided `cause` | Reduces diagnostic capability |

A structured code is only useful long-term if it is **consistently defined and governed**. Do not assume that using an `enum` automatically makes all changes compatible.

## 15. Common Mistakes

| Mistake | Why It Is Dangerous | How to Fix |
| --- | --- | --- |
| `getMessage().equals("...")` for branching | Wording changes or `null` break logic | Use error codes/typed properties |
| `getMessage().contains("...")` | Word collisions, library/language dependence | Classify according to the contract |
| Lumping all errors into `RuntimeException("failed")` | Cannot distinguish error groups or causes | Choose appropriate subtypes/codes |
| Creating a separate class for every message variant | Type explosion when handling logic is identical | Use one exception type with an enum when appropriate |
| Storing the code only in the message without a getter | Callers still have to parse strings | Store `private final` fields and getters |
| Translating the message to Vietnamese and breaking logic | Violates presentation/handling separation | Perform locale mapping based on the code |
| Wrapping an exception without passing `cause` | Loses stack trace, root exception type, suppressed exceptions | Use a constructor accepting `Throwable cause` |
| Putting secrets or raw payloads into fields/messages | Risks leaking sensitive data in logs/telemetry | Store only safe context |
| Using `enum.name()` as a public code then renaming constants | Breaks the public code contract | Use a separate stable code value if needed |
| Stuffing all business data into a single `detail` string | Falls back to wording dependence | Create typed fields for needed data |
| Assuming `private final List` is immutable | Elements/list may still be mutable | Apply appropriate defensive copying |
| Returning the raw `Throwable` from an API | Exposes implementation details and internal data | Convert to a public DTO |
| Embedding user-facing messages in low-level exceptions | Mixes i18n into libraries/logic | Translate at the communication boundary |
| Testing the entire message when it is not a contract | Brittle tests that block wording improvements | Test code, field, cause, and mapping separately |

## 16. Practice Exercises

**Exercise A — Spotting a fragile contract**

A controller has:

```java
if (ex.getMessage().startsWith("quantity")) {
    return "INVALID_QUANTITY";
}
```

What happens if the library changes the message to `"Invalid value for field quantity"`?

**Answer:** the handling branch can misfire even though the nature of the error has not changed. You should use `ex.getCode()`/`ex.getField()` or a dedicated exception type, rather than relying on a text prefix.

**Exercise B — Is `cause` a business code?**

The parsing layer catches `NumberFormatException` and creates `ValidationException(ValidationCode.INVALID_INTEGER, "quantity", ..., cause)`. Should the caller inspect `cause.getMessage()` to determine which field failed?

**No.** The caller uses the structured field and code. The cause is for diagnosing the source of failure and does not need to contain business field names.

**Exercise C — Does editing the message break the contract?**

Replace `"Quantity must be between 1 and 100"` with `"Enter a quantity from 1 to 100"`. If the code remains `OUT_OF_RANGE`, the field is `quantity`, and the validation conditions are unchanged, will clients relying on the code change branches?

**No.** This is the goal of separating error data from wording.

**Exercise D — Enum or string?**

An application has five validation errors known at compile time. Should you start with an `enum` or free-form strings scattered across the codebase?

**`enum`** generally provides better type checking and easier refactoring. If codes must be published over a network, add stable public values and a versioning policy.

**Exercise E — Sensitive data**

Should you store a raw API token in a `private final String token` field of `AuthenticationException` for convenient logging?

**Not by default.** Fields in an exception can be exposed via logs/debuggers/telemetry. Only store error codes and permitted context; do not construct messages containing secrets.

**Exercise F — Message-based tests**

A test currently compares the full message of `ValidationException`. If QA wants to improve the Vietnamese wording, do all business tests have to be updated?

**They should not.** Separate classification tests (code/field/cause) from translation/wording tests. Only test the full message where the message is explicitly defined as part of the contract.

**Exercise G — One error, two languages**

`OrderException` carries `ORDER_NOT_FOUND`. The API needs Vietnamese or English output. Should you modify `ex.getMessage()` on each exception to match the locale?

**No need.** The API layer can map `ORDER_NOT_FOUND` to the appropriate localized message while keeping the error code unchanged.

**Exercise H — Is a `final` field enough?**

A custom exception has `private final Map<String, Object> metadata` and a getter that returns the map directly. Can you guarantee the context cannot be modified?

**No.** `final` only locks the reference; the map can still be mutated through the getter or another reference. Use defensive copying and appropriate structured types, and be careful with mutable objects inside.

**Exercise I — Changing the meaning of an error code**

Today `ORD_404` means "order not found"; tomorrow the system reuses `ORD_404` to mean "cannot process payment." Is this good practice?

**No.** Clients handling the old code can silently misinterpret it. You need a new code for the new meaning and a compatibility policy.

## 17. Checklist for Designing Stable Custom Exceptions

When creating or reviewing a custom exception class, check the following:

1. **Does the error type need its own subtype?** If callers do not handle it differently, you can use a standard subtype or a single custom exception per domain group.
2. **Checked or unchecked?** Choose based on the caller's actual recovery contract, not arbitrarily.
3. **Is there a stable error code?** Use an `enum`, constant string code, or value object instead of parsing it from the message.
4. **Which properties does the caller actually need?** For example `field`, `operation`, `resourceType`, or boundary values; avoid bloat and avoid secrets.
5. **Are important fields `private final` with getters?** Is defensive copying needed for mutable data?
6. **Do constructors preserve `cause`?** When a wrapper is created from a library error, preserve the original object when appropriate.
7. **Is `message` purely explanatory?** Try changing the wording to verify that no code branches are affected.
8. **Does the public API use its own codes?** If so, codes must remain stable across versions and be separate from localized messages.
9. **Is there clear mapping at communication boundaries?** Do not return raw `Throwable` objects or stack traces to clients.
10. **Is there a policy for changing/adding codes?** Define meanings clearly and avoid reusing old codes.
11. **Do tests focus on code, field, and cause?** Do not lock business tests to message punctuation.
12. **Do logs have sufficient trace without leaking data?** Structured error info and causes must be paired with access controls.
13. **Is handling behavior based on semantics rather than messages?** For example, retry logic, HTTP mapping, and i18n must follow the contract.
14. **Have both direct errors and wrapped errors been tested?** Direct errors may have no cause; wrapped errors may carry a cause and suppressed exceptions.

## Conclusion

**`message` is for human readers; error codes and typed data are for the program.** When designing Java custom exceptions, choose subtypes that reflect failure categories, store stable error codes along with necessary properties, preserve `cause` when translating errors, and craft natural, readable messages **without turning wording into a control condition**.

This separation lets a system update messages, localize text, transition from console to API, refactor internals, and upgrade libraries **without accidentally changing how callers identify and handle errors**. Error codes still require a compatibility contract, and data stored in exceptions must remain compact, meaningful, and safe to log.
