# Argument Validation, Exception Types, and Error Messages Can Change

During **Java Advance Compatibility Migration**, many changes do not break compilation yet still alter how a program handles invalid input. A method that previously accepted **null**, checked bounds only when using data, or returned a specific exception may switch to earlier validation, throw a different exception, or produce a different error message after upgrading the JDK, a framework, or a dependency.

This is part of the **Default Behavior** chapter. For safe migration, treat **argument validation**, **exception type**, and **error message** as three related but distinct behavioral dimensions. If the system has consumers or partners relying on any of these dimensions, a change even in a single error branch can affect compatibility.

For example:

- An old API accepted an empty string and returned a default result; the new API throws **IllegalArgumentException**.
- Old code threw **NullPointerException** on a later dereference; new code uses **Objects.requireNonNull** and throws at the start of the method.
- A library changes **NumberFormatException** to a domain exception or vice versa.
- A newer JVM provides more detailed **NullPointerException** messages, causing tests that compare the exact message text to fail.
- Validation order changes from checking state to checking arguments, so the same invalid call can receive a different exception.
- A framework changes how exceptions map to HTTP status, error codes, or response bodies.

This lesson focuses on how to identify, design, and test these changes without confusing binary compatibility with behavioral compatibility.

## 1. The Error Contract Is Part of API Behavior

An API does not only have a contract for valid input. It also has behavior when input is invalid, resources are missing, or the system is in a state that disallows the operation.

Consider the method:

~~~java
public Money transfer(String accountId, long amount);
~~~

For valid input, the consumer cares about the transfer result. For invalid input, the consumer may care about:

- Is **accountId = null** interpreted as a default account or rejected?
- Is **accountId = ""** accepted?
- Is **amount = 0** valid or an error?
- Which exception does **amount < 0** trigger?
- Are arguments validated before accessing the database?
- Does the exception contain a stable error code for the consumer to branch on?
- When multiple input errors occur, which error is returned first?
- Is the exception wrapped by another layer at the boundary?
- Is there sensitive information in the message or log?

A consumer may catch a specific exception:

~~~java
try {
    transferService.transfer(accountId, amount);
} catch (IllegalArgumentException ex) {
    showInputError();
}
~~~

If the new version switches to **IllegalStateException** for the same condition, the consumer source still compiles and bytecode still links, yet the **catch** branch no longer works as expected.

**Source/binary compatibility does not guarantee behavioral compatibility in error branches.**

### 1.1. Classifying Dimensions to Examine

| Dimension | Question | Example Change |
|---|---|---|
| Input domain | Has the accepted argument set changed? | No longer allows null |
| Validation timing | At what point is validation performed? | Throws immediately on call, instead of during processing |
| Validation precedence | If multiple arguments are invalid, which error takes precedence? | Checking index before payload |
| Exception class | Has the exception type changed? | IllegalArgumentException to NullPointerException |
| Exception hierarchy | Does the consumer catch by superclass or subtype? | A specialized RuntimeException is added |
| Exception wrapping | Is there an outer wrapping exception layer? | CompletionException wrapping the original error |
| Message | Do content, structure, or locale change? | Message includes variable name |
| Cause and suppressed | Is the cause chain different? | I/O error preserved as cause |
| Side effects | Did side effects occur before throwing? | Writing logs/events before validation |
| Public error representation | Do HTTP/gRPC/message errors change? | HTTP 400 to 422, JSON code changed |

This classification helps the team avoid fixing a message bug by changing an exception type without understanding the consumer contract.

## 2. Why Can Upgrading Java Change Validation?

Changes can appear at multiple layers:

1. **JDK:** standard APIs revise validation algorithms or improve diagnostics; exact behavior depends on the specification and release.
2. **Libraries:** dependencies update guard logic, parsers, mappers, or wrappers.
3. **Frameworks:** binding, conversion, bean validation, or exception resolvers change.
4. **Application:** refactoring alters check order and thrown exceptions.
5. **Runtime/configuration:** locale, charset, timezone, providers, or JVM flags alter error representation.
6. **Deployment environment:** proxies, classloaders, drivers, and the serialization layer change how exceptions propagate.
7. **Generated code:** code generators, annotation processors, or bytecode enhancement can introduce validation different from the prior release.

When a test reports a different message after migration, do not automatically conclude it is a Java change. Identify the **actual layer throwing the exception** and the corresponding artifact version.

### 2.1. Check the Specification Before Speculating

Each API may document certain exceptions in Javadoc. For example, immutable factory methods such as **List.of(...)** reject null elements; such behaviors must be confirmed from the API contract.

However, the **exact message string** is rarely promised as a stable API, even when the exception type is documented. Do not turn a message observed in a test on the current JDK into a long-term contract without explicit documentation.

When evaluating changes, distinguish:

- **Specified behavior:** defined by Javadoc or a public contract.
- **Documented framework behavior:** described by the vendor for a specific version.
- **Observed behavior:** seen in logs/tests, which may be an implementation detail.
- **Application-owned contract:** published and controllable by the team itself.

## 3. Common Java Exceptions Related to Arguments

Some exceptions commonly appear when handling invalid arguments:

| Exception | Typical Meaning | Example |
|---|---|---|
| **IllegalArgumentException** | Argument value is invalid for the method | Negative amount when disallowed by business rules |
| **NullPointerException** | Non-null reference requirement violated or null dereference | Objects.requireNonNull |
| **IndexOutOfBoundsException** | Index or range is out of bounds | Objects.checkIndex |
| **NumberFormatException** | String cannot be parsed into the expected numeric format | Integer.parseInt |
| **IllegalStateException** | Object state does not allow the current operation | Operating after close |
| **UnsupportedOperationException** | Operation is not supported by the implementation | Calling add on an immutable collection |
| **ClassCastException** | Actual cast is incompatible with the target type | Invalid cast at runtime |
| **DateTimeParseException** | Unable to parse date/time string per formatter | LocalDate.parse |
| **PatternSyntaxException** | Invalid regular expression | Pattern.compile |
| **SecurityException** | Security policy denies the operation | Blocked access in certain APIs |
| **IOException** | I/O failure, possibly wrapped at a higher layer | Reading from a stream |
| **CompletionException** | Wraps exceptions in asynchronous processing | CompletableFuture.join |

**NumberFormatException** extends **IllegalArgumentException**, while **DateTimeParseException** also belongs to a specialized runtime exception branch. Teams need to pay attention to the inheritance hierarchy if consumers catch by superclass.

### 3.1. Exception Types Convey More Than Severity

Sometimes two exceptions are both **RuntimeException** yet carry different semantics:

- **IllegalArgumentException:** caller supplied an invalid value.
- **IllegalStateException:** the object/service is in a disallowed state.
- **NullPointerException:** a required reference is not allowed to be null.
- **IndexOutOfBoundsException:** the index/range value falls outside valid index bounds.

Changing the exception type can alter how clients classify errors, retry, report, or map errors to HTTP statuses. Therefore, do not replace **NullPointerException** with **IllegalStateException** merely because both are unchecked exceptions.

### 3.2. Messages from Standard APIs

Example illustrating invalid input cases:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class InvalidArgumentsDemo {
    public static void main(String[] args) {
        // NullPointerException: List.of prohibits null elements.
        List.of("A", null);

        // IllegalArgumentException: Map.of prohibits duplicate keys.
        // Map.of("k", 1, "k", 2);

        // IndexOutOfBoundsException for an out-of-bounds index.
        // Objects.checkIndex(10, 3);

        // NumberFormatException if the string is not a valid integer.
        // Integer.parseInt("12x");
    }
}
~~~

The commented lines are independent examples for trying each case, avoiding stopping at the first error. Do not write unit tests requiring these examples to always contain the exact same English message.

## 4. Null Checks: Explicit and Implicit Behavior

### 4.1. NullPointerException from Dereferencing

~~~java
public String normalize(String input) {
    return input.trim();
}
~~~

If **input == null**, the error occurs when calling **trim()**. The NPE message depends on the runtime and can change when upgrading the JDK.

### 4.2. NullPointerException from requireNonNull

~~~java
import java.util.Objects;

public String normalize(String input) {
    Objects.requireNonNull(input, "input must not be null");
    return input.trim();
}
~~~

In this case, the API proactively validates and supplies an application-owned message. This has the following advantages:

- The error occurs right at the entry point.
- The violated condition can be stated clearly.
- Less dependent on the JVM's automatic NPE message format.
- Supports more accurate contract testing if the application publishes the message.

However, switching from implicit dereferencing to explicit validation can change the **failure location**, **stack trace**, and ordering relative to other operations. If consumers rely on these factors, compatibility must be verified.

### 4.3. Choosing NPE or IllegalArgumentException for Null?

Java allows applications to design their own contracts. **Objects.requireNonNull** uses **NullPointerException**. Some business APIs choose **IllegalArgumentException** to represent any invalid argument, including null.

There is no benefit in mixing the two approaches and changing them on every refactor. Establish a convention for public APIs, document it in Javadoc, and test it.

Example using explicit exceptions:

~~~java
public final class RegistrationService {
    public String register(String email) {
        if (email == null) {
            throw new IllegalArgumentException("email is required");
        }
        if (email.isBlank()) {
            throw new IllegalArgumentException("email must not be blank");
        }
        return email.strip();
    }
}
~~~

If the v1 contract declared **IllegalArgumentException** when email is null, switching to **NullPointerException** in v2 can break consumers catching that specific exception. The choice must consider API history and compatibility policy, not just coding style.

### 4.4. Null and Collection Factories

APIs such as **List.of(...)**, **Set.of(...)**, and **Map.of(...)** do not allow null. Switching from an **ArrayList** that can contain null to **List.of** changes not only mutability, but also the input domain.

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> mutable = new ArrayList<>();
mutable.add(null);             // Can contain null.

List<String> immutable = List.of("A");
// immutable.add("B");         // UnsupportedOperationException.
// List.of("A", null);         // NullPointerException.
~~~

If a migration changes how collections are constructed to optimize memory or use newer Java APIs, check whether real data contains nulls. Tests that only check collections with valid elements will not catch this change.

## 5. Numeric Domain, Index, and Range Validation

### 5.1. Checking Negative Numbers, Zero, and Overflow

A numeric-processing API needs to define:

- Are negative values accepted?
- Is zero a valid case or a sentinel?
- Is the maximum boundary value permitted?
- Is there a risk of integer overflow during computation?
- Are NaN and infinity distinguished if using floating-point?

Example:

~~~java
public long calculateFee(long amount) {
    if (amount < 0) {
        throw new IllegalArgumentException(
            "amount must be greater than or equal to 0"
        );
    }
    return Math.multiplyExact(amount, 2);
}
~~~

In the example, a very large positive input can cause **Math.multiplyExact** to throw **ArithmeticException** due to overflow. If v1 silently wrapped on overflow whereas v2 uses **multiplyExact**, this is a behavioral change for boundary inputs even though both versions compile.

### 5.2. IndexOutOfBoundsException and Check Order

~~~java
import java.util.Objects;

public char characterAt(String text, int index) {
    Objects.requireNonNull(text, "text");
    Objects.checkIndex(index, text.length());
    return text.charAt(index);
}
~~~

If **text == null** and **index** is also invalid, an NPE occurs before the index check. Reversing the guard order can cause a different error to surface first.

In Java, **Objects.checkIndex** validates an index and throws **IndexOutOfBoundsException** when invalid. For start/end intervals, there are APIs **checkFromToIndex** and **checkFromIndexSize** to express range rules more clearly.

### 5.3. Guard Order Is Observable Behavior

Example v1:

~~~java
public void update(int index, String value) {
    if (index < 0) {
        throw new IndexOutOfBoundsException("index");
    }
    if (value == null) {
        throw new IllegalArgumentException("value");
    }
    // Update...
}
~~~

Example v2:

~~~java
public void update(int index, String value) {
    Objects.requireNonNull(value, "value");
    if (index < 0) {
        throw new IndexOutOfBoundsException("index");
    }
    // Update...
}
~~~

With **index = -1** and **value = null**, v1 throws **IndexOutOfBoundsException**; v2 throws **NullPointerException**.

If the system wants to commit to a specific check order, document it in the contract. Otherwise, tests should focus on one invalid condition at a time to avoid locking down an ordering that is not guaranteed.

## 6. Strings, Parsing, and Data Formatting

Upgrading the JDK version, parsers, validation libraries, or configuration can alter how inputs are parsed.

### 6.1. Empty String Differs from Null String

~~~java
String input = "";
~~~

**input** here is not null, yet empty. An API may accept an empty string as a default value or reject it. Switching from:

~~~java
if (input == null) {
    throw new IllegalArgumentException("missing");
}
~~~

to:

~~~java
if (input == null || input.isBlank()) {
    throw new IllegalArgumentException("missing or blank");
}
~~~

expands the set of rejected inputs. **String.isBlank()** checks whitespace characters per Java rules, unlike **isEmpty()** which only checks for length zero.

### 6.2. Number Parsing

~~~java
int value = Integer.parseInt("12");
~~~

An invalid string throws **NumberFormatException**. However, another parser might support whitespace, separators, or fallbacks. If a migration changes the parser, the set of valid inputs can change.

Example:

~~~java
Integer.parseInt(" 12 "); // NumberFormatException
Integer.parseInt("12");   // Succeeds
~~~

Do not "fix" errors by unintentionally trimming input if the old contract required rejecting whitespace. Conversely, if the API previously accepted input with whitespace, dropping the trim step in the new version is a breaking behavior.

### 6.3. Date and Time Parsing

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeParseException;

try {
    LocalDate.parse("2026-02-30");
} catch (DateTimeParseException ex) {
    System.out.println(ex.getErrorIndex());
}
~~~

**DateTimeParseException** provides specialized details such as the parsed input string and error index. It can be useful for diagnostics, yet when a library/framework wraps this exception, the consumer may receive a different high-level exception.

Do not compare exact message text from the parser if documentation does not guarantee the string's content and language. For public APIs, convert necessary information into a stable **error code** and **field path**.

### 6.4. Locale and Encoding

Error messages from frameworks, validation providers, or the operating system can be localized. The same error may produce a Vietnamese, English, or other-language string depending on locale.

If tests depend on messages, pin the locale and message source. However, it is more stable to assert the error code/field/type rather than display text.

For JSON, XML, or text inputs, encoding and parser configuration must also be considered. A differently decoded string can lead to different validation results even when Java source code is unchanged.

## 7. Helpful NullPointerException and JVM-Generated Messages

Newer JDKs support more detailed NPE messages in many cases, helping identify which expression caused a null dereference. **Helpful NullPointerExceptions** was introduced in JDK 14 (JEP 358) and enabled by default in subsequent releases.

Example:

~~~java
public class Example {
    static class Customer {
        String name;
    }

    public static void main(String[] args) {
        Customer customer = null;
        System.out.println(customer.name.length());
    }
}
~~~

A JVM supporting helpful NPEs can explain that a field cannot be read because a variable or intermediate result is null. The exact wording can depend on the JVM, release, bytecode, and failure site.

### 7.1. Do Not Treat JVM Messages as an API Contract

A test like the following easily breaks when upgrading the JDK:

~~~java
assertEquals(
    "expected exact JVM text",
    exception.getMessage()
);
~~~

If the exception is a JVM-generated NPE, this string is normally diagnostic output, not an application-controlled contract.

Prefer:

~~~java
assertThrows(NullPointerException.class, () -> service.run(null));
~~~

or if you want to enforce input validation at the entry point, check a message actively produced by the API via **requireNonNull** and published as part of the contract.

### 7.2. Why Can Messages Differ?

- Different JDK versions and JVM implementations.
- Bytecode generated by different compilers.
- An NPE raised by a dereference differs from an explicitly thrown NPE.
- Some runtime situations lack sufficient information to construct the same message.
- JVM flags can affect the details of helpful NPEs.
- Frameworks may catch and wrap the original exception.

Therefore, snapshot tests of stack traces or JVM messages from one machine should not be a cross-JDK compatibility gate without a specific contractual reason.

## 8. Exception Wrapping Changes the Error Type Observed by Consumers

A validation error may originate as **IllegalArgumentException** yet reach the consumer as **CompletionException**, **ExecutionException**, **InvocationTargetException**, or another framework exception.

### 8.1. Synchronous and Asynchronous

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public final class AsyncDemo {
    static String convert(String input) {
        if (input == null) {
            throw new IllegalArgumentException("input required");
        }
        return input.toUpperCase();
    }

    public static void main(String[] args) {
        CompletableFuture<String> task =
            CompletableFuture.supplyAsync(() -> convert(null));

        try {
            task.join();
        } catch (CompletionException ex) {
            System.out.println(ex.getCause().getClass().getName());
        }
    }
}
~~~

With asynchronous processing, a consumer calling **join()** can receive a **CompletionException** wrapping the original error. **get()** uses **ExecutionException** for task failures. If migration switches a synchronous API to asynchronous or changes the invocation framework, the exception type seen at the boundary can change even while inner validation logic stays the same.

### 8.2. Reflection and Proxies

Invoking a method via reflection can wrap the thrown exception inside **InvocationTargetException**:

~~~java
try {
    method.invoke(target, arguments);
} catch (java.lang.reflect.InvocationTargetException ex) {
    Throwable root = ex.getCause();
    System.err.println(root);
}
~~~

Framework proxies can further wrap or translate exceptions. When analyzing a bug, examine both the **top-level exception** and the **root cause**; avoid determining the exception type from a single log line.

### 8.3. Do Not Discard the Cause When Translating Exceptions

If you want an API to emit a domain exception, preserve the cause to assist investigation:

~~~java
public final class ImportException extends RuntimeException {
    public ImportException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

~~~java
try {
    parseDocument(input);
} catch (IllegalArgumentException ex) {
    throw new ImportException("Invalid document format", ex);
}
~~~

This provides a stable exception type at the boundary while preserving the actual source of failure. If consumers previously caught **IllegalArgumentException** directly, switching to **ImportException** is still a contract change that requires evaluation.

## 9. How Should an Application API Define Its Error Contract?

A public API can choose different stability levels for different error components.

### 9.1. Separate Machine-Readable Codes from Human-Readable Messages

Example domain error model:

~~~java
public enum ErrorCode {
    CUSTOMER_ID_REQUIRED,
    AMOUNT_OUT_OF_RANGE,
    RESOURCE_NOT_FOUND
}
~~~

~~~java
public final class DomainValidationException
        extends IllegalArgumentException {

    private final ErrorCode code;
    private final String field;

    public DomainValidationException(
            ErrorCode code, String field, String message) {
        super(message);
        this.code = code;
        this.field = field;
    }

    public ErrorCode getCode() {
        return code;
    }

    public String getField() {
        return field;
    }
}
~~~

~~~java
public final class PaymentService {
    public void pay(String customerId, long amount) {
        if (customerId == null || customerId.isBlank()) {
            throw new DomainValidationException(
                ErrorCode.CUSTOMER_ID_REQUIRED,
                "customerId",
                "Customer id is required"
            );
        }
        if (amount <= 0) {
            throw new DomainValidationException(
                ErrorCode.AMOUNT_OUT_OF_RANGE,
                "amount",
                "Amount must be positive"
            );
        }
        // Execute business logic after validation.
    }
}
~~~

At this boundary, consumers can branch on **ErrorCode** instead of parsing **getMessage()**. The message can still serve logs or UI display and vary by locale.

### 9.2. What Should Be Published?

| Error Component | Treat as Contract? | Notes |
|---|---|---|
| Public exception type | Possibly, if consumers are instructed to catch it | Document in Javadoc and migration guide |
| Stable error code | Recommended for external APIs | Suitable for machine reading and error routing |
| Offending field/path | Possibly | Preserve format and privacy |
| HTTP status or gRPC code | Yes | Affects protocol behavior |
| Response body structure | Yes | Ensures schema compatibility |
| Display message | Usually should not be pinned | Wording or language may change |
| Stack trace and line numbers | No | Depends on build/JDK/refactoring |
| Internal class names and cause text | Usually no | Implementation details |
| Error order when multiple arguments fail | Only if explicitly committed | Otherwise, test each invalid case individually |
| Retryability | Possibly | Important for automated consumers |

The key point is that **you do not need to freeze every piece of error information**. Freeze only what consumers genuinely rely on, and clearly mark parts that have diagnostic value only.

### 9.3. Documenting Validation in Javadoc

~~~java
/**
 * Charges a positive amount for a nonblank customer id.
 *
 * @param customerId a nonblank customer id
 * @param amount amount greater than zero
 * @throws DomainValidationException
 *         if customerId is null/blank or amount is not positive
 */
public void pay(String customerId, long amount) {
    // Implementation...
}
~~~

If errors carry machine-readable codes, reference the error code table in API documentation as well. For long-lived public methods, Javadoc helps migration teams evaluate breaking behavior before upgrading dependencies.

## 10. Framework Layer: Validation and HTTP Error Mapping

In Spring MVC, Jakarta Validation, or similar frameworks, errors can occur before controller code executes.

Example:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;

public record PaymentRequest(
    @NotBlank String customerId,
    @Positive long amount
) {
}
~~~

If a controller uses **@Valid** and binding is configured appropriately, the framework can detect constraint violations when receiving a request. However, the internal exception type and HTTP response representation also depend on the controller signature, validator, framework version, and exception handler.

### 10.1. Upgrading Frameworks Can Change the Error Path

For example, the same invalid request:

~~~json
{
  "customerId": "",
  "amount": -10
}
~~~

After migration, the following may change:

- Whether validation runs before or after conversion.
- Syntactically malformed request bodies classified differently from syntactically valid requests violating constraints.
- The exception type thrown by the framework.
- Default HTTP status and response content type.
- Field names and error details in the response.
- How the framework handles **MethodArgumentNotValidException**, **ConstraintViolationException**, or related exceptions.

Do not assume that a single Spring or Jakarta Validator exception name covers every invalid-input scenario. Testing at the HTTP boundary shows what consumers actually receive.

### 10.2. Stabilizing Public Error Responses at the Boundary

An exception handler layer can translate internal errors into a common model:

~~~java
public record ApiError(
    String code,
    String field,
    String message
) {
}
~~~

Example response:

~~~json
{
  "code": "CUSTOMER_ID_REQUIRED",
  "field": "customerId",
  "message": "Customer id is required"
}
~~~

Consumers should use **code** and **field** as machine-readable signals. Even if **message** is localized or reworded, backward compatibility at the code/schema level can still be preserved.

If a service publishes an exact message as part of its contract, changing the message still requires versioning or migration notices. Avoid using the excuse "messages are display-only" to unilaterally break a published contract that consumers legitimately rely on.

### 10.3. Spring Can Wrap Exceptions Across Multiple Layers

A service throws **IllegalArgumentException**, yet the controller path may apply:

- Binding/conversion before calling the service.
- Bean validation before entering the method.
- AOP proxies.
- Controller advice and exception resolvers.
- Upstream HTTP gateways/proxies.

Therefore, when comparing v1/v2, observe the **final output of the system**, not just unit tests calling the service directly.

## 11. Validation Order and Side Effects

An easy-to-miss change is **detecting an error at a different point in time**, even when the exception type stays the same.

### 11.1. Fail Fast vs. Fail Late

Version 1:

~~~java
public void submit(String requestId, String body) {
    audit.logReceived(requestId);
    String normalized = body.trim(); // Null -> NPE after audit.
    repository.save(normalized);
}
~~~

Version 2:

~~~java
public void submit(String requestId, String body) {
    Objects.requireNonNull(body, "body");
    audit.logReceived(requestId);
    repository.save(body.trim());
}
~~~

Both can throw an NPE when body is null. However, v1 wrote an audit record before failing, whereas v2 does not. If the system uses audits to count failed requests, observable behavior has changed.

For a public API, consider:

- Validation before or after logging?
- Can events, transactions, or database writes happen before throwing?
- Is the error safe to retry?
- Does it violate idempotency?
- Does it cause a partial update?
- Are metrics/alerts based on call counts of a code path?

### 11.2. Validation and Transactions

~~~text
Request
   |
   v
Input validation
   |
   v
Begin transaction
   |
   v
Business operation
   |
   v
Commit
~~~

This is a commonly desired flow for invalid input, though systems may have separate audit, authentication, or authorization requirements. Not all validation must occur before every side effect; what matters is that the ordering is explicitly designed and consistent with the contract.

If migration moves validation outside a transaction or places it into a new interceptor, verify rollback semantics and error mapping.

## 12. Testing Error Cases with JUnit 5

To verify validation, test not only the happy path, but also boundary cases, null inputs, and mismatched types.

### 12.1. assertThrows

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

final class PaymentServiceTest {
    @Test
    void rejectsNonPositiveAmount() {
        PaymentService service = new PaymentService();

        DomainValidationException ex = assertThrows(
            DomainValidationException.class,
            () -> service.pay("C-001", 0)
        );

        assertEquals(
            ErrorCode.AMOUNT_OUT_OF_RANGE,
            ex.getCode()
        );
        assertEquals("amount", ex.getField());
    }
}
~~~

**assertThrows** accepts an exception of the requested type or any of its subtypes. This fits when the contract publishes a base exception and allows specialized subtypes.

### 12.2. assertThrowsExactly

When a contract requires an exact specific class, JUnit 5 provides **assertThrowsExactly**:

~~~java
@Test
void exactExceptionTypeIsRequired() {
    assertThrowsExactly(
        IllegalArgumentException.class,
        () -> legacyApi.rejectInvalidValue(-1)
    );
}
~~~

If the API has the right to move from **IllegalArgumentException** to a specific subtype while still honoring its contract, assertThrowsExactly creates an overly brittle test. Choose the assertion based on the contract to preserve, not personal preference.

### 12.3. When to Test Messages?

A test checking the message can be appropriate if the message is an application-owned and committed string, for example:

~~~java
assertEquals(
    "amount must be positive",
    ex.getMessage()
);
~~~

However, if the message comes from the JDK, a parser, or a framework without a stability guarantee, prefer asserting:

- Published exception class or class hierarchy.
- Error code.
- Field/path.
- Appropriate root cause.
- Absence of unwanted side effects.
- Response status/schema at the boundary.

### 12.4. Testing Boundary Parameters with Parameterized Tests

~~~java
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import static org.junit.jupiter.api.Assertions.assertThrows;

class AmountValidationTest {
    @ParameterizedTest
    @ValueSource(longs = {-100L, -1L, 0L})
    void rejectsNonPositiveAmount(long amount) {
        PaymentService service = new PaymentService();

        assertThrows(
            DomainValidationException.class,
            () -> service.pay("C-001", amount)
        );
    }
}
~~~

In addition to invalid values, test valid boundary values: minimum accepted number, maximum number, zero if allowed by contract, Unicode strings, whitespace, empty lists, and duplicate-key cases.

### 12.5. Testing Multiple Input Errors

When multiple fields are invalid simultaneously, do not assert a single message if validation order is not part of the contract.

There are two approaches:

1. **Test each rule independently:** all other fields are valid, with only one field invalid.
2. **Test aggregated results:** if the API supports returning a list of violations, assert the present codes/fields without relying on order, unless the API publishes an ordering guarantee.

Example testing a single rule:

~~~java
@Test
void missingCustomerIdHasStableCode() {
    PaymentService service = new PaymentService();

    DomainValidationException ex = assertThrows(
        DomainValidationException.class,
        () -> service.pay(null, 100)
    );

    assertEquals(
        ErrorCode.CUSTOMER_ID_REQUIRED,
        ex.getCode()
    );
}
~~~

### 12.6. Verifying No Side Effects Occur

If validation errors must be detected before writing data, you can use a mock or fake repository:

~~~java
@Test
void invalidRequestMustNotWriteAnything() {
    PaymentService service = new PaymentService(repository);

    assertThrows(
        DomainValidationException.class,
        () -> service.pay(null, 100)
    );

    verifyNoInteractions(repository);
}
~~~

**verifyNoInteractions** is a typical Mockito method; the snippet assumes repository is created as a mock and PaymentService has a constructor accepting the repository. When using this pattern in a real project, adapt it to the actual API.

## 13. Cross-Version Testing Matrix

Migration requires a baseline to distinguish legacy behavior from new behavior.

| Test Case | Test Value | Baseline to Record | Target Result to Compare |
|---|---|---|---|
| Null | **null** | Accepted, default, or exception? | Input domain and exception |
| Empty string | **""** | Accepted or rejected? | Validation rule |
| Blank | **"   "** | Trimmed, accepted, or rejected? | isBlank/normalization |
| Negative | **-1** | Exception type and timing | Range contract |
| Zero | **0** | Sentinel or valid value? | Boundary semantics |
| Very large | **Long.MAX_VALUE** | Overflow, clamp, or fail? | Arithmetic behavior |
| Duplicate keys | Two equal keys | Overwrite or reject? | Collection API |
| Null element | Collection containing null | Accepted or rejected? | Factory contract |
| Invalid numeric string | **"12x"** | Parser/exception | Parser compatibility |
| Invalid date | Nonexistent date | Parse/validation | DateTimeParseException/cause |
| Two invalid fields | Both id and amount invalid | Order or error set | Priority if published |
| Async failure | Task throws an exception | Wrapper/cause | Boundary exception |
| HTTP invalid request | Malformed JSON or constraint violation | Status/code/schema | Protocol compatibility |
| Locale change | Same error under different locale | Message and code | I18n vs machine contract |

Not all tests need to assert exact messages. The goal is to record the **contract that truly needs protection**, alongside current observations so the team can decide which parts are allowed to change.

### 13.1. Two Different Testing Directions

**Golden regression** captures baseline behavior and compares it against the target. It helps detect every observable change, including changes not specified in requirements.

A **contract test** fails only when a published contract clause is violated. It should not fail merely because a stack trace has an extra frame or a JVM diagnostic message differs.

Combining both approaches is more effective: use golden regression to **detect** changes, and use contracts and migration decisions to **classify** whether a change is acceptable.

## 14. How to Survey Actual Errors When Upgrading the JDK/Framework

### Step 1: Lock Down the Baseline Environment

Record:

- JDK vendor and version.
- JDK compiler, **--release**, and bytecode target.
- Framework and dependency versions.
- Relevant locale/timezone/charset.
- Validation and exception handler configuration.
- Artifact checksum and commit.
- Test logs/HTTP error samples.

If the baseline cannot be reproduced, the team will find it very difficult to confirm whether a change was caused by the migration or already existed.

### Step 2: Gather Consumer-Facing Contracts

Classify APIs:

- **Internal-only:** used solely inside one module and can change alongside its consumer.
- **Shared library:** shared by other modules that may not upgrade simultaneously.
- **Public SDK/SPI:** has independent consumers and typically needs a clear compatibility policy.
- **Network API:** consumers inspect status, code, and body rather than Java exceptions directly.
- **Batch/event API:** consumers may observe dead-letter messages, retry policies, or error payloads.

For each category, identify which exceptions belong to the public contract and which are merely implementation details.

### Step 3: Collect Negative Cases

Focus on:

- Null, empty, blank.
- Boundary values, overflows.
- Collection null, duplicate, empty.
- Parsing invalid/ambiguous input.
- Wrong state or missing resource.
- Concurrent calls and async failures.
- Malformed JSON/XML.
- Multi-field validation and error ordering.

Combine synthetic data with sanitized logs. Do not include tokens, passwords, or raw personal data in test fixtures/logs.

### Step 4: Compare v1 and v2

Run the same data on the baseline and target environments. Record:

~~~text
Case ID:
Input class:
JDK / framework / library version:
Accepted / Rejected:
Exception type:
Exception superclass:
Root cause type:
Error code:
Field/path:
HTTP status (if applicable):
Message (diagnostic only if not part of contract):
Side effects:
Source artifact checksum:
Result: expected / changed / uncertain
~~~

### Step 5: Classify Changes

| Change Type | Handling Approach |
|---|---|
| Specified JDK behavior is preserved | Keep as-is; update overly strict tests if needed |
| Internal message changed but contract unchanged | Do not force preserving the exact message; record diagnostic note |
| Public exception type changed | Evaluate breaking change, wrapper, or compatibility layer |
| Stricter validation rule | Check real data, consumers, and rollout plan |
| Looser validation rule | Assess security/invariants and data risks |
| HTTP error code/schema changed | Run consumer contract tests; consider versioning |
| Validation timing/side effects changed | Evaluate transactions, auditing, retries, and idempotency |
| Exception changed only due to dependency conflict | Fix the dependency graph or classpath |

### Step 6: Make Decisions

Each change should be tagged with one of the following actions:

- **Preserve:** retain the old behavior via a compatibility adapter or explicit guard.
- **Adapt:** update consumers or mappings to accept the new contract.
- **Version:** create a new API version if the change has major impact.
- **Accept:** accept non-contract diagnostic changes.
- **Block:** postpone migration if tests/evidence are missing for a critical consumer.

Do not apply the label "no impact" just because the code still compiles.

## 15. Preserving Backward Compatibility with an Adapter

Suppose a new dependency rejects input with **IllegalStateException**, whereas the public API previously committed to **IllegalArgumentException**.

You can preserve the exception type at the boundary:

~~~java
public final class LegacyCompatibleParser {
    private final NewParser parser;

    public LegacyCompatibleParser(NewParser parser) {
        this.parser = parser;
    }

    public ParsedValue parse(String value) {
        try {
            return parser.parse(value);
        } catch (IllegalStateException ex) {
            throw new IllegalArgumentException(
                "Invalid input", ex
            );
        }
    }
}
~~~

The snippet assumes **NewParser** and **ParsedValue** are application types. The adapter is appropriate only if **IllegalStateException** here genuinely represents invalid input. Do not catch every IllegalStateException and convert it into a caller error, because that type can also indicate a bug or corrupted system state.

### 15.1. When Should You Fix at the Boundary?

- A dependent library changed an exception type outside your control.
- Existing consumers catch the published exception.
- Internal errors can be mapped accurately to public errors.
- All consumers cannot be upgraded simultaneously.
- Tests exist for the relevant conditions and causes.

### 15.2. When Should You Not Keep Old Behavior?

- The old behavior ignores invalid data, posing a security or data-loss risk.
- Input errors cannot be reliably distinguished from system errors.
- Old messages expose sensitive data.
- Consumers were never promised exact messages.
- The compatibility workaround introduces ambiguity that masks system failures.

When old behavior must be broken, provide versioning, migration notes, and clear notice to consumers.

## 16. Security and Observability of Error Messages

An error message may be helpful to developers yet dangerous when returned directly to clients.

Examples that should not be returned verbatim:

~~~text
Failed SQL query in table user_tokens:
SELECT token FROM user_tokens WHERE customer_id='...'
~~~

Or:

~~~text
Invalid password: secret-value
~~~

These messages expose database details, queries, or sensitive data. When upgrading frameworks, the default error handler may change how much information is returned externally.

### 16.1. Separating External Messages and Internal Diagnostics

External response:

~~~json
{
  "code": "INVALID_REQUEST",
  "message": "The request contains invalid data",
  "traceId": "request-123"
}
~~~

Internal logs can retain the exception type, cause, and stack trace per security policy. **traceId** helps correlate errors without exposing internal implementation details in the public API.

### 16.2. Error Messages Should Have Appropriate Stability

A pragmatic rule of thumb:

- **Error code**: stable and documented.
- **Field/path**: stable within the published schema.
- **Message**: human-readable, open to refinement or localization if not promised verbatim.
- **Stack trace**: for diagnostic use only.
- **Cause**: stored internally for investigation; never exposed directly externally.
- **Correlation ID**: used for cross-tracing between client and server.

## 17. Common Mistakes During Migration

### 17.1. Testing Only the Happy Path

An API may work accurately on valid inputs while having completely changed its null/invalid behavior.

Remediation: add negative tests categorized by input domain and exception contract.

### 17.2. Asserting Verbatim JVM or Library Messages

Messages can change across runtimes, locales, implementations, parsers, or dependencies.

Remediation: assert code/type/field and published contracts; treat unstable messages as diagnostic.

### 17.3. Catching RuntimeException or Exception Too Broadly

~~~java
try {
    process();
} catch (RuntimeException ex) {
    return defaultValue();
}
~~~

This snippet can swallow programming errors, state errors, and input errors alike. When migration introduces a new error, the program may silently return a default value.

Remediation: catch the exact exception type at the boundary, preserve the cause, and log appropriately.

### 17.4. Changing Exception Type Just to Use a New Utility

Replacing manual validation with **Objects.requireNonNull** can turn **IllegalArgumentException** into **NullPointerException**. This is not a completely harmless refactor if consumers depend on the old exception type.

Remediation: compare contracts and preserve the old error type if necessary.

### 17.5. Using Message Strings to Control Business Logic

~~~java
if (ex.getMessage().contains("not found")) {
    retry();
}
~~~

This is fragile because messages are not designed as machine-readable codes. After migration, wording may change or be translated.

Remediation: use error codes, stable exception subtypes, or official statuses.

### 17.6. Ignoring Validation Precedence

Two invalid fields may be evaluated in a different order after refactoring.

Remediation: commit to ordering only if required by business rules; otherwise test each validation rule separately or assert the set of violations.

### 17.7. Equating the Root Cause with the Exception Observed at the Public Boundary

A **NumberFormatException** can reach the client as a framework **MethodArgumentTypeMismatchException** or a different HTTP error body.

Remediation: test at the right boundary and inspect the cause chain.

### 17.8. Abusing Adapters to Mask System Errors

Catching all exceptions and converting them to **INVALID_ARGUMENT** can cause database errors, bugs, or timeouts to be treated as input errors.

Remediation: classify causes based on verifiable evidence, not by guessing from messages.

### 17.9. Failing to Check Side Effects on Error

Whether an error happens before or after emitting an event, saving to a database, or opening a transaction can alter idempotency and retry behavior.

Remediation: inspect state after an invalid request, not only the exception type.

## 18. Rollout Plan for Validation Changes

If migration intentionally tightens validation, design a transition for existing data and consumers.

A reference roadmap:

~~~text
Baseline
    |
    v
Collect real inputs, summarize violations
    |
    v
Define new contract and error codes
    |
    v
Notify consumers, support in parallel if needed
    |
    v
Deploy appropriate observability/feature flags
    |
    v
Run negative/contract/integration tests
    |
    v
Canary or controlled rollout
    |
    v
Monitor error rate, support tickets, retries
    |
    v
Complete or roll back according to criteria
~~~

### 18.1. Metrics to Monitor

- Rejected request count by **error code**.
- HTTP 4xx/5xx rate if it is a network API.
- Exception count by class and origin site.
- Retry count and dead-letter messages.
- Parsing/conversion error count by field.
- Count of transactions with side effects before failing.
- Differences between service versions running in parallel.

Do not put sensitive raw inputs into metric labels. Use codes/fields with controlled cardinality.

### 18.2. Rollback Conditions

Rollback should be considered if:

- The error rate spikes unexpectedly.
- A critical consumer cannot handle the new error code/type.
- Data valid under the old contract is rejected without migration.
- Retry behavior causes traffic amplification.
- New validation errors mask system errors.
- Error responses inadvertently leak sensitive data.

If changes caused data to be written in a new format, rolling back code alone may not be enough. Verify bidirectional data read/write compatibility.

## 19. Behavioral Change Documentation Template

When recording a behavioral change in the migration register, you can use this template:

~~~text
Change ID:
API/Method/Endpoint:
Owner:
Baseline JDK/framework/dependency:
Target JDK/framework/dependency:

Input case:
Old behavior:
Old exception type:
Old error code/status:
Old message (diagnostic only if not part of contract):
Old side effects:

New behavior:
New exception type:
New error code/status:
New message (diagnostic or contract):
New side effects:

Source of change:
Specified/documented/observed:
Affected consumers:
Compatibility decision:
Migration action:
Acceptance criteria:
Tests/evidence:
Rollback plan:
Residual risk:
~~~

### 19.1. Decision Example

~~~text
Change ID: BEH-014
API: POST /payments
Input case: amount = 0

Old behavior: Accepted and ignored payment
New behavior: Rejected before persistence

Public code: AMOUNT_OUT_OF_RANGE
HTTP status: 400
Message: Display text; may be localized

Compatibility decision:
- Breaking for clients sending zero as no-op.
- Provide migration notes and consumer update window.
- Keep code/status stable once new API version is published.

Acceptance:
- Valid payments unchanged.
- Zero rejected consistently.
- No payment event or database write on rejection.
- No sensitive payload in response/log.
~~~

The values in the example are hypothetical application policies, not mandatory default rules of the JDK or Spring.

## 20. Checklist Before Concluding Compatible Migration

### Input Contracts

- [ ] Identified null, empty, blank, boundary, and invalid-format inputs.
- [ ] Distinguished specified behavior from merely observed behavior.
- [ ] Located changes to parsers, collection factories, and validation utilities.
- [ ] Reviewed validation order when multiple errors occur.
- [ ] Determined whether input domain changes are intentional or unintended.

### Exceptions and Messages

- [ ] Listed public exception types to preserve.
- [ ] Reviewed exception superclasses/subtypes.
- [ ] Checked wrappers and root causes across sync/async/framework layers.
- [ ] Avoided using JVM-generated messages as contracts without a guarantee.
- [ ] Provided stable error codes/statuses/fields for machine-reading consumers.
- [ ] Prevented leaking sensitive data through error messages.

### Testing

- [ ] Added negative tests for null, range, parsing, and duplicates.
- [ ] Tested exception types at the appropriate contract level: subtype or exact.
- [ ] Tested HTTP error schema if the API is exposed over the network.
- [ ] Added tests ensuring no unintended side effects occur.
- [ ] Executed the same cases on both baseline and target.
- [ ] Saved artifacts, JDK, dependency versions, and test evidence.
- [ ] Separated golden observations from public acceptance criteria.

### Operations

- [ ] Identified consumers affected by new exceptions/statuses/codes.
- [ ] Prepared compatibility/adapter/versioning plans if breaking.
- [ ] Set up telemetry by error code and invalid request rate.
- [ ] Assessed retries, transactions, idempotency, and rollback.
- [ ] Obtained owner approval for residual risk.

## 21. Reference Documentation for Cross-Checking

When handling an actual case, read the exact version's specifications and documentation:

- **Java Language Specification – Exceptions:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html
- **Objects API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Objects.html
- **NullPointerException API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/NullPointerException.html
- **JEP 358 – Helpful NullPointerExceptions:** https://openjdk.org/jeps/358
- **Java Collections factory methods:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html
- **JUnit 5 User Guide:** https://junit.org/junit5/docs/current/user-guide/
- **Jakarta Validation:** https://jakarta.ee/specifications/bean-validation/
- **Spring Framework Reference:** https://docs.spring.io/spring-framework/reference/

JDK and framework documentation describe the contract per release; specific error messages from one build are only observed evidence. When discrepancies arise, verify the artifact, runtime, API used, and error type at the right boundary.

---

**Conclusion:** Argument validation, exception types, and error messages are all behaviors that can change during Java migration. To preserve compatibility, clearly decide which parts form a stable contract and which are merely diagnostics, build negative/contract tests for invalid cases, observe both root causes and public-boundary errors, and protect invariants/side effects. Do not treat a changed message as a breaking change if it was never promised, yet also do not treat validation or exception-type changes as harmless merely because all source code still compiles successfully.