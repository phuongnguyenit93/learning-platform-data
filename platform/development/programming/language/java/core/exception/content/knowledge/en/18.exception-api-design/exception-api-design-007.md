# Documenting with @throws and Throwing Conditions

A Java method can fail in many ways: invalid input, an object state that does not permit the operation, a violated business rule, or an unavailable external resource. API consumers need to know **which exceptions are meaningful to them, the exact conditions that cause an exception, and what they can do next**. The Javadoc `@throws` tag helps describe this contract right next to the method or constructor signature.

Good documentation does more than list exception class names. It connects **throwing condition → error type → caller's interpretation**, while remaining consistent with the implementation and tests. This is part of stable API design, and is especially important for libraries and public services reused across many places.

## 1. Distinguishing Three Easily Confused Concepts

In Java, `throw`, `throws`, and `@throws` appear near each other but serve three different roles.

| Syntax | Location | Role |
| --- | --- | --- |
| `throw new SomeException(...)` | Method or constructor body | **Throws** an exception at runtime. |
| `throws SomeException` | Method or constructor signature | **Declares** the exception types allowed to propagate. For checked exceptions, this is part of compile-time checking. |
| `@throws SomeException ...` | Javadoc block `/** ... */` | **Documents** the exception-throwing case for readers of the API documentation; does not affect compilation or create throwing behavior on its own. |

Syntax illustration example, not a standalone program:

```java
/**
 * Finds the number of elements on a page.
 *
 * @param pageSize requested number of elements
 * @return accepted number of elements
 * @throws IllegalArgumentException if pageSize is not positive
 */
public int validatePageSize(int pageSize) {
    if (pageSize <= 0) {
        throw new IllegalArgumentException("pageSize phải dương");
    }
    return pageSize;
}
```

`IllegalArgumentException` extends `RuntimeException`, so it is **unchecked**. The method does not need to declare `throws IllegalArgumentException` to compile, but there is still a clear reason to write `@throws` because callers need to know the input constraint.

Conversely, for a checked exception such as `IOException` (not a subtype of `RuntimeException`), a method that throws or lets that exception propagate must normally declare `throws IOException` or handle it with `catch` according to compile-time rules. **The `@throws` tag cannot replace a `throws` declaration**.

## 2. Syntax and Meaning of @throws

A standard Javadoc tag has the form:

```java
/**
 * ...
 * @throws ExceptionType exact condition that causes the exception to be thrown
 */
```

`ExceptionType` is an exception class name that Javadoc can resolve from the import/package context; use the type that the API actually exposes publicly. The description that follows should indicate the **observable situation**, rather than merely repeating "when an exception occurs".

The same method can have multiple `@throws` tags for different error types:

```java
/**
 * @throws IllegalArgumentException if the order code is invalid
 * @throws IllegalStateException if the session is already closed
 * @throws OrderNotFoundException if the order cannot be found
 */
```

This is an illustrative Javadoc snippet, with `OrderNotFoundException` assumed to be an application exception type; it is not a complete Java example.

`@exception` is an alias accepted by the Javadoc tool for `@throws`. In new code, consistently using `@throws` makes it easier for readers to recognize.

For `<` or `>` operators in Javadoc text, wrap the expression in `{@code ...}` so the documentation generator renders special characters properly. For example:

```java
/**
 * @param amount requested amount
 * @throws IllegalArgumentException if {@code amount <= 0}
 */
```

If you need to reference a Java type in prose, you can use `{@link IllegalArgumentException}`. Javadoc parses these inline tags and generates appropriate code/link formatting in HTML. The Markdown block you are reading is instructional content; `{@code}` and `{@link}` tags have special meaning **inside Javadoc comments in Java code**.

## 3. How Specific Should "Throwing Conditions" Be?

A good description answers the questions: **what input or state causes the error, is the error the caller's or infrastructure's responsibility, and is that exception guaranteed by the contract?**

Compare:

| Weak description | Useful description |
| --- | --- |
| “Throws `IllegalArgumentException` when the argument is wrong.” | “Throws `IllegalArgumentException` if `quantity <= 0`.” |
| “Throws `IllegalStateException` when the state is invalid.” | “Throws `IllegalStateException` if `send()` is called after `close()`.” |
| “Throws `NoSuchElementException` if there is no element.” | “Throws `NoSuchElementException` if the iterator has no more elements and `next()` is still called.” |
| “Throws `IOException` if an error occurs.” | “Throws `IOException` if the file contents cannot be read due to an I/O error.” |
| “Throws `QuotaExceededException` on failure.” | “Throws `QuotaExceededException` if the requested number of records exceeds the account's quota at the time of the call.” |

It is not always possible to pinpoint the exact underlying cause. For `IOException`, the documentation can say "if an I/O error occurs while reading" because that is a broad enough abstraction; you should not commit to specific OS errors or specific subtypes that the implementation happens to throw.

When an error depends on state that changes over time, state when the rule is evaluated. For example, "if the remaining quota **at processing time** is insufficient" is more accurate than "if the account has a low quota", because the caller does not control concurrent transactions.

If there are multiple conditions, you can state them in one tag when the corrective action is the same:

```java
/**
 * @throws IllegalArgumentException if the name is empty or the name length
 *         exceeds the 100-character limit
 */
```

If the conditions lead to **different recovery actions**, consider separate exceptions or error codes instead of an overly broad description.

## 4. Complete Java 17 Example: Both Checked and Unchecked Exceptions

Consider designing `ReservationService.reserve(int)` with two clear conditions:

- A non-positive quantity is an argument error and throws `IllegalArgumentException` (unchecked).
- A quantity greater than the example's limit is a business rule error and throws `ReservationLimitException` (checked).

The API uses `@param`, `@return`, and `@throws` to express inputs, results, and failure conditions. The file below is standalone and can be compiled and run with Java 17+.

Create `ThrowsDocumentationDemo.java`:

```java
/**
 * Demonstrates exception contracts via the Javadoc @throws tag.
 */
public class ThrowsDocumentationDemo {

    /**
     * Checked error when a request exceeds the reservation limit.
     */
    public static final class ReservationLimitException extends Exception {
        /**
         * @param message business error description
         */
        public ReservationLimitException(String message) {
            super(message);
        }
    }

    /**
     * Simple reservation service without database access.
     */
    public static final class ReservationService {

        private static final int MAX_PER_REQUEST = 5;

        /**
         * Accepts a reservation request with a valid quantity.
         *
         * @param quantity number of seats to reserve, must be greater than 0
         * @return confirmation message with the number of seats
         * @throws IllegalArgumentException if {@code quantity <= 0}
         * @throws ReservationLimitException if
         *         {@code quantity > MAX_PER_REQUEST}
         */
        public String reserve(int quantity) throws ReservationLimitException {
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                    "quantity phải lớn hơn 0"
                );
            }
            if (quantity > MAX_PER_REQUEST) {
                throw new ReservationLimitException(
                    "Tối đa 5 chỗ mỗi yêu cầu"
                );
            }
            return "Đã đặt " + quantity + " chỗ";
        }
    }

    /**
     * Runs three scenarios to observe the documented contract.
     *
     * @param args command-line arguments, unused
     * @throws ReservationLimitException if a valid request in the example
     *         unexpectedly exceeds the limit; propagated out of main
     */
    public static void main(String[] args)
            throws ReservationLimitException {
        ReservationService service = new ReservationService();

        System.out.println(service.reserve(2));

        try {
            service.reserve(0);
        } catch (IllegalArgumentException ex) {
            System.out.println("INPUT: " + ex.getMessage());
        }

        try {
            service.reserve(7);
        } catch (ReservationLimitException ex) {
            System.out.println("LIMIT: " + ex.getMessage());
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 ThrowsDocumentationDemo.java
java ThrowsDocumentationDemo
```

Expected output:

```text
Đã đặt 2 chỗ
INPUT: quantity phải lớn hơn 0
LIMIT: Tối đa 5 chỗ mỗi yêu cầu
```

Points to compare against the contract:

1. `reserve(2)` is valid because `0 < 2 <= 5`, so it returns the confirmation message.
2. `reserve(0)` hits the `quantity <= 0` condition first and throws `IllegalArgumentException`; the caller catches the unchecked exception to report the input error.
3. `reserve(7)` exceeds `MAX_PER_REQUEST` and throws `ReservationLimitException`; the caller catches the checked exception according to business handling decisions.
4. `reserve` declares `throws ReservationLimitException` to satisfy Java's rule for checked exceptions; even though it does not declare `throws IllegalArgumentException`, Javadoc still documents that unchecked exception.
5. `main` declares `throws ReservationLimitException` because the `reserve(2)` call is outside `try/catch`. In the example, the quantity `2` cannot trigger the limit error under the current implementation; the declaration is still valid and shows that the compiler checks exceptions by **type and code flow**, not by proving whether a runtime condition actually occurs.
6. The limit `5` is a rule **intentionally chosen specifically for the example**. If a real public API uses a configurable or per-account limit, Javadoc must accurately describe the actual rule.

You can generate HTML Javadoc for the file:

```bash
javadoc -encoding UTF-8 -charset UTF-8 -d api-docs ThrowsDocumentationDemo.java
```

Open `api-docs/index.html` to view the documentation page. In the documentation for `ReservationService.reserve`, the **Throws** section will include both exceptions and their corresponding condition descriptions. The `javadoc` command may emit warnings where the tool expects additional descriptions; the presence of warnings (if any) does not alter runtime behavior.

## 5. @throws Is Not a Runtime Contract-Checking Mechanism

The compiler and JVM **do not read the description in `@throws` to check conditions**. Writing:

```java
/**
 * @throws IllegalArgumentException if quantity is less than 0
 */
```

does not make Java automatically throw an exception when a caller passes a negative number. The implementer must still check the condition or rely on behavior guaranteed by called APIs.

Therefore, documentation can become **wrong or outdated** compared to the code. Common cases:

- The comment promises "throws when `quantity < 0`" while the code checks `quantity <= 0`.
- The comment says "file does not exist" for all `IOException`s, even though permission errors and read errors also occur.
- The comment says "already closed" while the implementation still permits certain operations after `close()`.
- The code changes validation order so an input violating multiple rules receives a different exception first.

Documentation should be cross-checked against logic and tests whenever conditions change. For public contracts with external clients, changing the exception type or throwing condition can affect compatibility even when the Java signature stays the same.

## 6. Which Exceptions Should Be Documented?

For **checked exceptions**, `@throws` documentation usually needs to explain the declared type and the conditions that cause it to propagate. The signature `throws IOException` only indicates that an I/O error is possible; callers still need to know which I/O operation failed.

For **unchecked exceptions**, you do not need to document every `RuntimeException` that could arise from bugs. Prioritize types **intentionally defined as part of the API's behavior**:

- `IllegalArgumentException` when the caller violates a specified precondition.
- `NullPointerException` when a required non-null parameter is passed `null`, if this is a design choice consistent with the contract.
- `IllegalStateException` when the object is in a state that forbids the operation.
- `UnsupportedOperationException` when an optional operation is not supported by the implementation.
- Business domain exceptions so callers can distinguish recoverable errors.

Not every unexpected `NullPointerException` is worth documenting in `@throws`. An NPE caused by an internal programming bug is not a useful condition or behavioral promise for callers. Likewise, do not promise specific exception names thrown by underlying dependencies if they are implementation details that the API intends to hide.

### Wrapped and Propagated Exceptions

If an API catches `SQLException` and intentionally translates it into `RepositoryUnavailableException`, the public documentation should describe the **translated exception** and the situation meaningful to callers. The original exception can be retained as the `cause` for diagnostics, without listing driver subtypes as part of the public contract.

Conversely, if an API exposes `IOException` as part of a file-reading abstraction, you can write `@throws IOException` without creating a custom exception. The goal is the right API boundary, not replacing every JDK exception with a new type.

## 7. Writing Conditions Clear Enough for Callers to Act On

A practical approach is to build a table before writing Javadoc:

| Observable condition | Public exception type | What can the caller do? |
| --- | --- | --- |
| `quantity <= 0` | `IllegalArgumentException` | Fix the parameter before retrying the call. |
| `quantity > limit` | `ReservationLimitException` | Reduce the quantity or adjust the reservation flow. |
| Calling `send()` after `close()` | `IllegalStateException` | Create a new object/session per the contract. |
| Object not found for a valid ID | `ResourceNotFoundException` | Verify the ID or report not found. |
| Stream read encounters I/O error | `IOException` | Handle the read error and consider an appropriate retry. |

The table is a thinking tool and does not need to be repeated verbatim in Javadoc. When writing `@throws` tags, choose a short sentence stating the **primary condition**; explain retries, transactions, post-error state, or recovery in the main description if those details matter.

A Javadoc example **illustrating an API signature**, not a complete program:

```java
/**
 * Sends a packet over an open session.
 *
 * <p>This operation does not automatically retry when transmission fails.
 *
 * @param payload data to send, must not be null
 * @throws NullPointerException if {@code payload == null}
 * @throws IllegalStateException if the session is closed
 * @throws IOException if an I/O error occurs while sending
 */
public void send(byte[] payload) throws IOException;
```

The example has a signature ending with `;` like an interface declaration; when placed in standalone source code, it must be inside an interface or an appropriate abstract method declaration. The descriptions here are a **hypothetical contract for that interface**, not a general claim for all data-sending APIs.

Note: `IOException` does not by itself mean the send failed completely or that no bytes reached the destination. If callers need to know whether retrying is safe, the API must explicitly state partial-send or idempotency semantics.

## 8. When a Single Call Violates Multiple Conditions

Suppose `update(record, token)` receives `record == null` while also being called when the service is closed. If the current code checks `record` first, callers may see `NullPointerException`; if it checks state first, callers may see `IllegalStateException`.

Avoid promising an error precedence order unless callers truly need it. If an order is guaranteed, state it explicitly:

> Argument validation is performed before session state checks; if both are invalid, the method reports the argument error.

If not guaranteed, the documentation should state the condition for each type independently and avoid asserting an uncontrolled order. Whenever validation order changes, review both tests and Javadoc.

For multi-step operations, also consider **when** an error can occur. If validation succeeds but I/O fails, callers need to know whether the method may have partially updated state. `@throws` describes the throwing condition; the main description should state guarantees about post-failure state.

## 9. @throws on Interfaces, Implementations, and Overridden Methods

For APIs with interfaces or base classes, the error contract should live at the **point callers actually depend on**. If callers interact with objects through an interface, the interface's Javadoc is the right place to document the error types and conditions that all implementations must honor.

Structural illustration example; concrete classes are not fully declared here:

```java
public interface Storage {
    /**
     * Reads a resource by key.
     *
     * @param key non-null key
     * @return resource contents
     * @throws NullPointerException if {@code key == null}
     * @throws IOException if reading fails due to an I/O error
     */
    byte[] read(String key) throws IOException;
}
```

An implementation may use a different storage mechanism while still fulfilling this contract. When overriding:

- Java **does not allow** an overriding method to broaden the checked exception list to a checked exception incompatible with the parent method's `throws` clause. For example, an implementation cannot add `throws SQLException` to `read` when the interface only declares `throws IOException` and `SQLException` is not a subtype of `IOException`.
- Java **allows** an overriding method to throw unchecked exceptions not listed in `throws`; however, the new behavior must still conform to the contract promised to callers. "Compiler allows it" does not mean "design-compatible".
- Javadoc supports inheriting documentation from the overridden method; `{@inheritDoc}` can be used when appropriate to pull in existing content. Inspect the generated HTML and add descriptions for genuinely different or implementation-specific constraints, avoiding copy-pasted docs that drift out of sync.
- If an implementation truly cannot meet a behavioral promise in the interface, fix the design or clarify the abstraction; do not merely add `@throws` to legitimize breaking the contract.

Constructors can also use `@throws` to document initialization failure conditions (for example, a missing path or missing configuration parameter). Ensure the documentation reflects errors that actually propagate to callers, not just internal ones.

## 10. Distinguishing Javadoc from System-Wide Error Handling Documentation

The `@throws` tag is suited for **per-method contracts**. Broader concerns may need documentation at the type, module, or API-guide level:

- Consistent error classification across the library; stable error codes or subclasses.
- Retry policies, backoff, idempotency, and post-error state.
- Rollback behavior or side effects before an exception propagates.
- Interrupt/cancellation handling rules in concurrent APIs.
- Security boundaries: messages sent to clients must not contain tokens, SQL, or stack traces.

A Javadoc such as `@throws IOException if an I/O error occurs` may be completely reasonable for stream reading, yet insufficient as documentation for a multi-part upload transaction with complex consistency and retry semantics.

Conversely, do not turn every `@throws` tag into a long paragraph re-explaining the entire architecture. Keep the condition concise, and add links or prose explanations where callers need them.

## 11. Verifying Javadoc and Behavior Together

### 11.1. Tool-Based Verification

You can compile source, run tests, and generate Javadoc as two distinct kinds of verification:

```bash
javac -encoding UTF-8 ThrowsDocumentationDemo.java
java ThrowsDocumentationDemo
javadoc -encoding UTF-8 -charset UTF-8 -d api-docs ThrowsDocumentationDemo.java
```

`javac` confirms the code is valid Java and checks checked exceptions. `javadoc` parses the documentation, attempts to resolve `@throws` types, and generates HTML. Certain doclint options help detect syntax, parameter, or reference issues in documentation; however, **no tool automatically proves that "if quantity <= 0" holds across all execution paths**.

### 11.2. Scenario-Based Testing

For every important `@throws` line, there should be at least a test for the error-triggering condition and a valid boundary case. For example, for `reserve`:

| Input | Expectation |
| --- | --- |
| `quantity = 0` | `IllegalArgumentException` |
| `quantity = -1` | `IllegalArgumentException` |
| `quantity = 1` | Returns success result |
| `quantity = 5` | Returns success result |
| `quantity = 6` | `ReservationLimitException` |

This test set verifies the exact **`0` and `5` boundaries** that the Javadoc commits to; there is no need to assert stack traces or messages from external dependencies. Only if a public message is declared part of the contract should you assert specific strings or intentional error codes.

For stateful APIs, also test `open → close → send`; for I/O errors, use fakes or mocks to trigger the documented case. If a method has multiple error branches, tests should reflect observable branches rather than just line coverage.

### 11.3. Pre-Release Review Checklist

- Is the exception type listed in `@throws` actually thrown or propagated by the method according to the intended contract?
- Are checked exceptions in `throws` explained clearly enough for callers to understand why they occur?
- Are unchecked exceptions intentionally defined for preconditions and API state documented?
- Are boundary conditions (`null`, empty, negative, equal to limit, above limit, closed) accurate?
- Have any class names, error codes, messages, or implementation details accidentally become a public contract?
- When overriding, is the interface/base class Javadoc consistent with the implementation?
- When validation logic or dependencies change, have documentation and tests been updated accordingly?

## 12. Common Mistakes and How to Fix Them

**Writing only "if an error occurs".** This gives no guidance to callers. Describe the failure type and the triggering state/input; for broad I/O, a phrase like "if an I/O error occurs while reading data" is appropriate.

**Writing `@throws` without declaring a checked exception in `throws`.** Comments do not affect compiler checks. You must catch or declare checked exceptions per Java rules.

**Failing to document unchecked exceptions that are part of preconditions.** Conditions like `size <= 0` or "called after close" can be more important than rare checked errors. Write `@throws` for intentionally designed behavior.

**Listing every exception from deep internal calls.** This easily turns implementation details into a contract. Document meaningful public errors; boundary translation should be clear if the implementation changes.

**Documenting conditions that differ from actual code.** For example, the comment says "less than 0" while the code checks "less than or equal to 0". Re-read operators, boundary conditions, and check order; write tests for each boundary.

**Confusing `@return` with `@throws`.** `@return` describes the result on normal completion, whereas `@throws` describes failure paths. For APIs returning sentinels (`null`, empty, `Optional`) instead of throwing, documentation must match that choice.

**Promising schedule- or implementation-dependent conditions.** For example, claiming timeouts are always safe to retry or exceptions only happen before writing data. Only make promises backed by guarantees; describe side effects and post-error state if callers rely on them.

**Using unresolvable exception type names in Javadoc.** Check imports/packages and run `javadoc` to catch reference errors. If example code assumes an undeclared application type, state clearly that it is an illustrative snippet.

## 13. Practice Exercise

Consider a hypothetical API `SessionCache.get(String key)` with the requirements: `key` must be non-null, the cache must be open, if no entry exists it returns `Optional.empty()`, and if the backend is unreachable it throws `CacheUnavailableException`.

Draft the Javadoc using `@param`, `@return`, and `@throws` for the three observable errors: null key, closed cache, and unavailable backend. Also answer: should a **cache miss** have a `@throws` tag?

Reference answer (**illustrative signature only; `CacheUnavailableException` and implementation are not defined**):

```java
/**
 * Looks up an entry by key.
 *
 * @param key lookup key, must not be null
 * @return an Optional containing the value if found; Optional.empty()
 *         if the key is valid but no data exists
 * @throws NullPointerException if {@code key == null}
 * @throws IllegalStateException if the cache is closed
 * @throws CacheUnavailableException if the backend cannot serve the lookup
 */
public Optional<String> get(String key)
        throws CacheUnavailableException;
```

If a cache miss is designed to return `Optional.empty()`, then it is **not an exception** and belongs in `@return`, not `@throws`. This illustrates deciding the success/failure contract before writing documentation.

Key takeaway: **`@throws` documents a verifiable promise about the conditions under which exceptions propagate to callers**. For Javadoc to be trustworthy, it must stay synchronized with the `throws` signature, `throw` conditions in the implementation, interface/base-class contracts, and boundary tests.