# Writing Javadoc for a Sealed Hierarchy in Java

## 1. Why Does a Sealed Hierarchy Need Dedicated Javadoc?

`sealed` and `permits` restrict which direct types are allowed to extend a class or interface. For example:

```java
sealed interface Outcome permits Success, Failure, Retry {}

record Success(String requestId, String value) implements Outcome {}
record Failure(String requestId, String errorCode, String message)
        implements Outcome {}
record Retry(String requestId, int afterSeconds) implements Outcome {}
```

This snippet illustrates the structure and is not a standalone program. The compiler knows the set of permitted subtypes, but **does not know the business contract**: what kind of success `Success` represents, what unit `Retry.afterSeconds` uses, whether `Failure.errorCode` can be null, or how a null `Outcome` value should be handled.

**Javadoc** needs to turn a type hierarchy into **a usable API contract**, explaining information that cannot be inferred merely from reading class names or `permits`:

1. The role and scope of the parent type.
2. The meaning of each permitted subtype and the conditions under which it is created.
3. The data rules for each record component: required, nullable, units, and constraints.
4. The behavior of methods, constructors, and factories; `@return` and `@throws`.
5. How callers should branch, null-handling policies, and API versioning.
6. What happens when the library adds, deprecates, or changes a subtype.

**Java milestones:** `record` became final in Java 16 (JEP 395), `sealed` became final in Java 17 (JEP 409); record patterns and pattern matching for `switch` became final in Java 21 (JEPs 440, 441). The complete program at the end of this article uses **JDK 21+** because it uses `switch` over record patterns, without needing `--enable-preview`. Javadoc for a sealed hierarchy does not require pattern switches: the same sealed model can be documented on Java 17.

## 2. Dividing Documentation Responsibilities by Layer

| API Element | What to Document in Javadoc |
| --- | --- |
| **Sealed interface/abstract class** | Domain meaning, list of variants and links, relationships between them, extension restrictions, null policy |
| **Permitted subtype** | What specific state it represents, when it occurs, validity conditions for the subtype |
| **Record declaration** | Describe each component with `@param`, units, nullability, immutability if relevant |
| **Public constructor/factory** | Validation, exception-throwing cases, guarantees upon successful instantiation |
| **Public abstract/default method** | Shared contract for callers, return value, side effects, override rules if any |
| **Helper API using pattern switch** | Handled branches, null behavior, output, errors, and impact when adding a subtype |

**Do not only write Javadoc on the parent type.** Sentences like “An outcome” or “A retry” do not tell users whether `Retry(0)` is valid, or whether `Failure.message` may be exposed to external clients.

### 2.1. Parent Type Javadoc Describes the Overall Picture

Example Javadoc for the interface:

```java
/**
 * The result of one request, with three permitted variants.
 *
 * <p>Each subtype represents a different business outcome.
 * A null reference is not one of the variants.</p>
 *
 * @apiNote Prefer an exhaustive pattern switch to arbitrary type tags.
 * @since 1.0
 * @see Success
 * @see Failure
 * @see Retry
 */
public sealed interface Outcome permits Success, Failure, Retry {
    // Public API methods...
}
```

This is an **illustrative** snippet and needs to be placed in a class or package where the subtypes are declared. Using `{@link Success}` or `{@link Retry}` in the prose also creates inline links to the related types.

Javadoc should accurately describe the “closed world” nature: a `sealed` interface directly allows only the subtypes listed in `permits`, enforced by Java's language rules. **There is no standard `@sealed` Javadoc tag** to replace the `sealed` keyword; only language-level code enforces that restriction.

Note: `sealed` does not mean every subtype at every level is final. A permitted subtype declared `non-sealed` can open up a new extension point. In this example, the subtypes are `record` types, which are implicitly `final`, so the set of variants is simple and closed.

### 2.2. Subtype Javadoc Describes Individual Meaning

- `Success`: the request completed successfully and produced a result.
- `Failure`: the request completed with an application error code and error details.
- `Retry`: the request should be retried after a positive number of seconds; this is not a terminal outcome.

Use descriptions that clarify the relationships between states rather than merely repeating the subtype name. If a name like `Failure` also includes errors that should be retried, either change the model or explain it accurately; do not write docs that contradict the `terminal()` method.

## 3. Recommended Javadoc Tags

| Tag | Purpose | Example |
| --- | --- | --- |
| `@param` | Method parameter or **record component** when placed on a record declaration | `@param afterSeconds strictly positive delay in seconds` |
| `@return` | Describes a method's return value | `@return a nonblank correlation ID` |
| `@throws` | Describes an exception and when it is thrown | `@throws IllegalArgumentException if delay is not positive` |
| `@since` | The **library/API** version that introduced the element | `@since 1.0` |
| `@see` | Link to a related item in the documentation | `@see Retry` |
| `{@link Type}` | Inline link to a type, method, or member | `{@link Outcome}` |
| `{@code value}` | Inline code literal, avoiding HTML misinterpretation | `{@code null}` |
| `@apiNote` | Usage guidance for API callers | `@apiNote Handle every variant.` |
| `@implSpec` | Behavioral specification of a default/concrete implementation | `@implSpec Returns false only for Retry.` |
| `@implNote` | Implementation note when helpful to implementers | `@implNote Uses a type test.` |
| `{@inheritDoc}` | Inherits documentation from an overridden method per Javadoc rules | `/** {@inheritDoc} */` |

**`@since 1.0` is the version of the example library**, not “Java has had `sealed` since version 1.0.” If a new subtype is added in release 1.1, put `@since 1.1` on that subtype. The minimum JDK required to compile is separate information and belongs in build/compatibility notes.

You do not need to use all of these tags on every member. For example, `@implSpec` is useful for a `default method` that actually has a body, whereas a record that only holds components does not necessarily need it.

## 4. Writing @param for Record Components

On the **Javadoc of a record declaration**, `@param` describes each component. For example:

```java
/**
 * A request to retry after a delay.
 *
 * @param requestId nonblank correlation identifier
 * @param afterSeconds delay in seconds, strictly greater than zero
 * @since 1.0
 */
public record Retry(String requestId, int afterSeconds) implements Outcome {
    // Validation...
}
```

`afterSeconds` is a primitive `int`, so it cannot be `null`. The rule that needs to be explained is that **the value must be greater than 0**, in **seconds**. Saying “afterSeconds is the delay” is not enough for an API user.

A record has accessors (`requestId()`, `afterSeconds()`) and a canonical constructor. `@param` documentation on the record declaration lets Javadoc present the contract of the components. If you define a **compact canonical constructor** for validation, document the corresponding exceptions on the constructor:

```java
/**
 * Validates a retry request.
 *
 * @throws IllegalArgumentException if requestId is null/blank
 *         or afterSeconds is not positive
 */
public Retry {
    requireText(requestId, "requestId");
    if (afterSeconds <= 0) {
        throw new IllegalArgumentException("afterSeconds must be positive");
    }
}
```

The second snippet is **the constructor declaration body inside the `Retry` record**, assuming a `requireText` helper as in the complete program. A compact constructor runs validation before Java finishes assigning the components. Writing “afterSeconds strictly positive” in Javadoc while still allowing `new Retry("REQ-1", -2)` to construct an object is **incorrect documentation**, not an invariant.

### 4.1. Document Null Policies Clearly

Distinguish these cases:

- A reference variable `Outcome outcome` can still be `null`; `sealed` does not forbid that.
- A `Success` instance can hold a null component if its constructor allows it; a record does not automatically forbid all nulls.
- A record pattern such as `Success(var id, var value)` can still bind a `value == null` component with `var`; a pattern is not a business validator.
- A nested record pattern such as `NestedRecord(...)` does not match if the entire record value at that level is null, unlike `var` which matches null.

For APIs with non-null constraints, enforce real validation and document `@throws` where appropriate. If a method allows null to represent “no data,” state that clearly in `@param` and `@return`.

## 5. Shared Methods: @return, @apiNote, and @implSpec

A sealed interface can define a shared contract:

```java
public sealed interface Outcome permits Success, Failure, Retry {
    /**
     * Returns the correlation identifier.
     *
     * @return a nonblank request identifier
     */
    String requestId();

    /**
     * Reports whether processing has finished without another attempt.
     *
     * @return true for completed outcomes, false for a retry request
     * @implSpec This implementation returns false only for {@link Retry}.
     */
    default boolean terminal() {
        return !(this instanceof Retry);
    }
}
```

`requestId()` is a shared method; each record has a `requestId` component whose generated accessor satisfies the contract. The constructors in the complete example at the end check that the identifier is non-null and non-blank, so `@return` does not overpromise.

In `terminal()`, `@return` describes the result observed by the caller; `@implSpec` specifies how the default implementation works. If `permits` is later expanded with another type, both this implementation and its documentation must be reviewed.

`@apiNote` is suitable for usage advice, such as “Prefer an exhaustive pattern switch.” `@implNote` is used when implementation notes are helpful, such as why a particular algorithm was chosen; do not turn changeable implementation details into public promises if they are not part of the contract.

### 5.1. Inheriting Javadoc with {@inheritDoc}

An `@Override` method can inherit Javadoc content from a superclass or interface method using `{@inheritDoc}` when documentation inheritance applies. Example **placed inside the `Retry` record** when writing an explicit accessor:

```java
/** {@inheritDoc} */
@Override
public String requestId() {
    return requestId;
}
```

This code is **not required**; the record provides the accessor automatically. More importantly, `{@inheritDoc}` on a method **does not generate Javadoc for the record subtype itself**, cannot replace the description of `Retry`, and does not alter the `permits` list.

For an overridden method that changes the contract or adds important constraints, write explicit documentation instead of using `{@inheritDoc}` to hide differences.

## 6. Standalone Program: A Fully Documented Sealed Hierarchy

Create the file **`SealedHierarchyJavadocDemo.java`**:

```java
/**
 * Demonstrates a documented, closed outcome API.
 *
 * @since 1.0
 */
public class SealedHierarchyJavadocDemo {
    private static void requireText(String text, String name) {
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException(name + " required");
        }
    }

    /**
     * Result of one request, with exactly three permitted variants.
     *
     * <p>Each variant has its own data contract. A null reference is
     * not an outcome variant; callers must decide how to handle null.</p>
     *
     * @apiNote Prefer an exhaustive pattern switch to arbitrary type tags.
     * @since 1.0
     * @see Success
     * @see Failure
     * @see Retry
     */
    public sealed interface Outcome permits Success, Failure, Retry {
        /**
         * Returns the correlation identifier.
         *
         * @return a nonblank request identifier
         */
        String requestId();

        /**
         * Reports whether processing has finished without another attempt.
         *
         * @return true for completed outcomes, false for a retry request
         * @implSpec This implementation returns false only for {@link Retry}.
         */
        default boolean terminal() {
            return !(this instanceof Retry);
        }
    }

    /**
     * A successfully processed request.
     *
     * @param requestId nonblank correlation identifier
     * @param value nonblank result text
     * @since 1.0
     * @see Outcome
     */
    public record Success(String requestId, String value) implements Outcome {
        /**
         * Validates the success components.
         *
         * @throws IllegalArgumentException if an argument is null or blank
         */
        public Success {
            requireText(requestId, "requestId");
            requireText(value, "value");
        }
    }

    /**
     * A completed request that failed with a documented error.
     *
     * @param requestId nonblank correlation identifier
     * @param errorCode nonblank application error code
     * @param message nonblank readable explanation
     * @since 1.0
     */
    public record Failure(String requestId, String errorCode, String message)
            implements Outcome {
        /**
         * Validates all failure components.
         *
         * @throws IllegalArgumentException if a component is null or blank
         */
        public Failure {
            requireText(requestId, "requestId");
            requireText(errorCode, "errorCode");
            requireText(message, "message");
        }
    }

    /**
     * A request for a later attempt; it is not terminal.
     *
     * @param requestId nonblank correlation identifier
     * @param afterSeconds strictly positive delay before another attempt
     * @since 1.0
     */
    public record Retry(String requestId, int afterSeconds) implements Outcome {
        /**
         * Validates the retry components.
         *
         * @throws IllegalArgumentException if requestId is null/blank
         *         or afterSeconds is not positive
         */
        public Retry {
            requireText(requestId, "requestId");
            if (afterSeconds <= 0) {
                throw new IllegalArgumentException("afterSeconds must be positive");
            }
        }
    }

    /**
     * Converts an outcome to a short diagnostic string.
     *
     * @param outcome an {@link Outcome}, or null when absent
     * @return a string for the matching variant; "missing" for null
     * @apiNote Do not expose raw error details to untrusted clients.
     */
    public static String summarize(Outcome outcome) {
        return switch (outcome) {
            case Success(var id, var value) -> "success:" + id + ":" + value;
            case Failure(var id, var errorCode, var message) ->
                    "failure:" + id + ":" + errorCode;
            case Retry(var id, var delay) -> "retry:" + id + ":" + delay;
            case null -> "missing";
        };
    }

    public static void main(String[] args) {
        Outcome success = new Success("REQ-1", "stored");
        Outcome failure = new Failure("REQ-2", "OUT_OF_STOCK", "Try later");
        Outcome retry = new Retry("REQ-3", 30);

        System.out.println(summarize(success));
        System.out.println(summarize(failure));
        System.out.println(summarize(retry));
        System.out.println(summarize(null));
        System.out.println("terminal:" + success.terminal() + ":" + retry.terminal());

        try {
            new Retry("REQ-4", 0);
            throw new AssertionError("Invalid retry accepted");
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid-retry:" + expected.getMessage());
        }
    }
}
```

**Compile and run with JDK 21+:**

```bash
javac --release 21 SealedHierarchyJavadocDemo.java
java SealedHierarchyJavadocDemo
```

**Exact output:**

```text
success:REQ-1:stored
failure:REQ-2:OUT_OF_STOCK
retry:REQ-3:30
missing
terminal:true:false
invalid-retry:afterSeconds must be positive
```

Tested with JDK 24/JShell and verified to produce these exact six lines. `sealed`, `record`, record patterns, and `switch` with patterns are all final features as of Java 21. If a project must compile with Java 17, the sealed hierarchy and records can still be used, but `summarize` must be rewritten using `instanceof` type patterns or polymorphic dispatch; do not lower `--release` to 17 while keeping `case Success(var id, ...)`.

### 6.1. Verifying Documentation Against Behavior

- `@return` on `requestId()` promises a nonblank ID; the three compact constructors use `requireText` to enforce this.
- `@param value` on `Success` specifies nonblank; `new Success("REQ-1", null)` is rejected by the constructor.
- `@param afterSeconds` documents a positive delay; `new Retry("REQ-4", 0)` throws `IllegalArgumentException`.
- `terminal()` has an implementation matching `@implSpec`: `Success` and `Failure` are terminal, `Retry` is not.
- `summarize(null)` returns `"missing"` as stated in `@return`; the switch expression has `case null`.
- `Failure.message` is diagnostic text, while `summarize` only outputs `errorCode`; `@apiNote` warns against exposing raw error details externally.

The program intentionally uses small records with `String` and primitive types to demonstrate the contract; it is not a replacement for logging, error localization, retry scheduling, or serialization in a production system.

## 7. Generating HTML Javadoc and Reading the Published Docs

After creating the file, run with JDK 21+:

```bash
javadoc -encoding UTF-8 -charset UTF-8 -d api-docs SealedHierarchyJavadocDemo.java
```

The `api-docs` directory and HTML files are generated when **you run this command** in your own environment. Open `api-docs/index.html`, navigate to the `SealedHierarchyJavadocDemo` class page, and then inspect the nested types `Outcome`, `Success`, `Failure`, and `Retry`.

To check more strictly for issues detectable by Javadoc doclint:

```bash
javadoc -Xdoclint:all -encoding UTF-8 -charset UTF-8 -d api-docs SealedHierarchyJavadocDemo.java
```

**Testing distinction:** the runtime behavior was verified on JDK 24; running `javadoc` is a separate documentation-generation step for the learner or project to execute. A passing program run **does not prove** that HTML links or doclint checks are clean; always generate and inspect the actual Javadoc before releasing.

**Checklist for reviewing the generated docs:**

1. On `Outcome`, are the subtypes, null policy, and usage clearly explained?
2. Do `@see`, `{@link Outcome}`, and `{@link Retry}` point to the right types?
3. Do the record components have `@param` entries covering meaning, units, and invariants?
4. Do the constructors document `IllegalArgumentException` conditions matching the code?
5. Does `terminal()` have clear `@return` and `@implSpec` descriptions?
6. Does `summarize` clearly state that it accepts null and what it returns?
7. Are there any doclint warnings, HTML errors, or unresolved links to fix?
8. Were the docs generated with the exact JDK, encoding, classpath/module path, and library version being released?

For Maven or Gradle projects, integrate the build system's Javadoc task or plugin so the classpath and toolchain stay consistent. Javadoc can also run in CI, configured to warn or fail depending on project policy.

## 8. `permits` Is a Language Rule, Not a Comment

If a class directly implements a sealed interface without being listed in `permits`:

```java
// INTENTIONALLY INVALID: Extra is not permitted by Outcome.
class Extra implements Outcome {
    @Override
    public String requestId() {
        return "REQ-5";
    }
}
```

The compiler rejects that implementation. Testing this scenario on JDK 24 produces an error stating that the class is not allowed in the `permits` list. This intentionally invalid snippet **is not included in the runnable program in section 6**.

A Javadoc comment saying “You may extend this interface freely” would be a false promise if the code is `sealed` and only permits a few subtypes. Adding `@see` does not grant extension rights. You must change the `permits` list/modifiers in code or design a dedicated extension point.

### 8.1. When Adding a New Subtype

Suppose API version 1.1 adds `Canceled`. In addition to source changes, you must update:

- The parent type's Javadoc and `@see` links.
- Documentation for `Canceled`, including its components and `@since 1.1`.
- `@implSpec` on default methods such as `terminal()` if the new state changes their logic.
- Exhaustive `switch` expressions handling `Outcome`; add the corresponding case.
- Unit tests, negative tests, public API/changelog, and compatibility policies.

Adding a subtype to a sealed hierarchy can cause previously exhaustive `switch` expressions in client code to fail to cover all cases. Do not assume adding a new record is always a harmless, backward-compatible change.

### 8.2. If Plugin-Based Extension Is Needed

A closed `sealed interface` with only final records is unsuitable if external plugins must be able to add direct subtypes. Design an open interface, an SPI/registry, or an appropriate `non-sealed` branch instead, and update the docs to state clearly where extension is allowed and where it is not.

## 9. Cases Requiring Extra Care in Javadoc

**Exceptions:** `@throws` should describe errors that can actually occur under the contract, not copy every exception the compiler allows. For example, the `Retry` constructor throws `IllegalArgumentException` if the request ID is null/blank or the delay is non-positive; that case is covered by a test.

**Records:** record components are final, but a component referencing a mutable object can still be mutated through that object. Do not write “deeply immutable” when a model contains a `List` or another mutable object without defensive copying.

**`@since`:** record the library/API version, not the Java language version. Java 21 is used for the test program because of pattern switches, whereas a sealed `Outcome` and records can exist in Java 17.

**Documentation inheritance:** method implementations may use `{@inheritDoc}` when the parent method's contract applies directly, but record declarations still need their own Javadoc to explain the subtype and record components. For overrides that change semantics, write specific docs.

**Deprecation:** the `@Deprecated` annotation marks the API in code and for the compiler; the `@deprecated` Javadoc tag explains why it is deprecated and what to use instead. A deprecated subtype still needs to be accounted for in `permits` and pattern handling according to your migration policy, rather than being deleted abruptly from the hierarchy.

**Security:** `Failure.message` may contain sensitive details; Javadoc should state limits on logging or displaying it. Do not promise “safe for public output” unless filtering rules and tests are in place.

## 10. Common Javadoc Mistakes

| Mistake | Consequence and Fix |
| --- | --- |
| Documenting only the parent type and leaving subtypes blank | The API has states without clear semantics; document every subtype |
| Writing `@param` that merely repeats the component name | Callers do not know units or constraints; document meaning and data limits |
| Writing `@since 21` to mean JDK 21 | Easily confused with library version; state library version and JDK requirement separately |
| Treating `@sealed` as a directive that controls subtypes | No standard tag replaces `sealed`/`permits` in Java |
| Documenting a component as non-null while the constructor allows null | Misleading docs; enforce the invariant and add negative tests |
| Using `{@inheritDoc}` to skip writing record docs | Only inherits method docs in valid cases; does not replace subtype documentation |
| Omitting constructor failure conditions | Callers do not know valid input rules; document `@throws` accurately and test them |
| Automatically adding `default` when handling a sealed hierarchy | Can hide missing cases when a new permitted subtype is added; prefer exhaustive `switch` |
| Forgetting `case null` or a null policy | `null` is not a subtype; explicitly define whether it is accepted or rejected |
| Forgetting to update Javadoc after adding a subtype | API docs list incomplete variants; update links, contracts, tests, and release notes |
| Treating clean stdout as valid Javadoc | Generate HTML and check doclint, links, and encoding separately |
| Copying Java 21 pattern switches into Java 17 source | Source compatibility error; use `instanceof` or upgrade the toolchain |

## 11. Review Checklist by API Element

**On the sealed parent:**

- The parent type describes the domain and the intentional set of variants.
- `@see` or `{@link}` tags point to the right subtypes and related operations.
- The docs clearly state the null policy and extension policy.
- Adding subtypes follows a versioning and compatibility process.

**On record subtypes:**

- State names are clear and descriptive.
- Every significant component has `@param` stating units, nullability, and invariants.
- Constructors/factories enforce the conditions promised in the docs.
- `@throws` documents actual exceptions, especially for external input.

**On public methods:**

- `@param`/`@return`/`@throws` fully explain the contract.
- `@apiNote` provides usage advice and `@implSpec` specifies implementation behavior where useful.
- Overrides only use `{@inheritDoc}` when inherited method docs genuinely fit.
- Switches over sealed types cover all variants, define a null policy, and are tested.

**In CI and documentation builds:**

- Code builds with the right `--release` and runtime target.
- Tests cover valid states, null inputs, and invalid invariants.
- HTML Javadoc is generated and checked for links, tags, and doclint warnings.
- Whenever a subtype or API changes, docs and tests are updated together.

## 12. Exercise: Write Javadoc for Another Sealed API

Problem: a ticket-booking result API has three variants:

- `Confirmed(String bookingId, String confirmationCode)`: confirmed; both fields are nonblank.
- `Rejected(String bookingId, String reason)`: rejected; `reason` is required.
- `Waitlisted(String bookingId, int position)`: waitlisted; `position` is a positive 1-based ordinal number.

Requirements:

1. Define `sealed interface BookingResult permits Confirmed, Rejected, Waitlisted` and the three implementing records.
2. Write Javadoc for the parent explaining the set of variants, the null policy, and how callers should branch.
3. Write `@param` for each record component, especially the unit/indexing of `position` and the meaning of `confirmationCode`.
4. Add compact constructors that validate invariants; document `@throws IllegalArgumentException`.
5. Write `describe(BookingResult value)` using record patterns and `case null`; test each branch, invalid data, and null.
6. Try adding a subtype outside `permits` to observe the compiler rejection; update Javadoc when extending the hierarchy.
7. Generate HTML with `javadoc -Xdoclint:all` and review links, tags, and contract details.

Annotation hint (abbreviated declaration, without validation yet):

```java
/**
 * A booking accepted and assigned a confirmation code.
 *
 * @param bookingId nonblank identifier
 * @param confirmationCode nonblank code for the booking
 * @since 1.0
 */
record Confirmed(String bookingId, String confirmationCode)
        implements BookingResult {}
```

Variant-handling hint (place inside a class/method where the model is declared):

```java
static String describe(BookingResult value) {
    return switch (value) {
        case Confirmed(var id, var code) -> "confirmed:" + id + ":" + code;
        case Rejected(var id, var reason) -> "rejected:" + id + ":" + reason;
        case Waitlisted(var id, var position) ->
                "waitlisted:" + id + ":" + position;
        case null -> "missing";
    };
}
```

A reader of the HTML Javadoc should be able to answer: whether `position = 0` is valid; what `describe(null)` returns; whether an external class can implement `BookingResult`; and when `Rejected` is used instead of `Waitlisted`. If the docs cannot answer these questions, improve the contract before releasing.

## 13. Conclusion and Official References

A **sealed hierarchy is easy to understand and use correctly** when you combine: (1) `sealed`/`permits` so the compiler restricts subtyping; (2) records and constructors to guard data invariants; (3) Javadoc so readers understand meaning and contracts; and (4) tests plus HTML/doclint checks to verify both behavior and documentation.

References:

- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [JEP 395 — Records](https://openjdk.org/jeps/395)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Oracle Java 21 — Javadoc Tool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javadoc.html)
- [Oracle Java 21 — Documentation Comment Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/javadoc/doc-comment-spec.html)
