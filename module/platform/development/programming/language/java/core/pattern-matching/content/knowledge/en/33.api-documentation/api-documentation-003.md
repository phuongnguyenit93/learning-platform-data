# Documenting Null Behavior in Java Pattern Matching APIs

**Topic:** Java Core Pattern Matching — API and Documentation. This article uses **Java 21 or later** for record patterns (JEP 440) and pattern matching for switch (JEP 441); type patterns with instanceof have been standard since Java 16. The goal is to design, publish, and verify the **null-handling contract** of an API, not merely to make a switch branch compile.

## 1. Why Is Null Behavior Part of the API Contract?

A Java method with reference-type parameters can be called with **null** unless checks prevent it. API users need to know:

1. Is it allowed to pass **null** into the method?
2. If null is passed, does the method **return a result**, **return a value indicating absence**, or **throw an exception**?
3. If the parameter is a **record**, can its component be null?
4. If a record nests another record, does a null inner component behave differently from the selector itself being null?
5. Can the method **return null**? If so, what does null mean?
6. What are the exception types, throwing conditions, stable messages (if any) to rely on, and caller responsibilities?

Without a clear contract, two methods that both return String can mislead callers: one uses null as "no data," while the other treats it as a programming error. When refactoring from an instanceof chain to a pattern switch, the null policy can **change unintentionally**.

**Null behavior** is not just the **case null** syntax. It encompasses **inputs, internal data, outputs, exceptions, and documented behavior**. It is a factor in API compatibility: changing from "accept null and return a default value" to "throw NullPointerException" can break callers even though the method signature has not changed.

## 2. Three Kinds of Null to Distinguish

In pattern matching code, there are at least three situations that must be separated:

| Case | Example | What to Watch For |
| --- | --- | --- |
| **Null selector** | **formatNullable(null)** | The value passed into the switch is null; requires case null or a rejection policy |
| **Null record component** | **new Text(null)** | The record exists, but its value component is null |
| **Null nested record** | **new Box(null)** | Box exists, yet the inner component expected to be a Text is null |

It is also necessary to distinguish **Box(new Text(null))**: the Box record is non-null, and the inner Text record is also non-null, but the String value inside Text is null.

These cases can lead to different behaviors. If the API groups them into a single result such as "EMPTY", the documentation must clearly state the scope of that grouping. If it is necessary to distinguish between "no payload", "payload with empty text", and "payload containing an absent nested record", they should be represented by distinct results or a clear result type.

### 2.1. instanceof Returns false When the Operand Is null

~~~java
Object value = null;

boolean text = value instanceof String;     // false
boolean number = value instanceof Integer;  // false
~~~

A type pattern also does not bind a variable when the operand is null:

~~~java
Object value = null;
if (value instanceof String text) {
    System.out.println(text.length());
} else {
    System.out.println("not a String");
}
~~~

The output of the second snippet is **not a String**. The null case falls into else and does not throw NullPointerException solely because of the instanceof operator.

### 2.2. Pattern Switch Has Its Own Null Rules

For a pattern switch on a reference selector, if the selector is null and there is no matching null-handling label, a normal switch throws **NullPointerException**. A plain **default** is not a substitute for **case null**.

~~~java
static String describe(Object value) {
    return switch (value) {
        case String text -> "text";
        case null -> "missing";
        default -> "other";
    };
}
~~~

This snippet handles a null selector **explicitly** and returns **missing**. If you omit case null, do not assume default will return other for null.

### 2.3. Record Patterns Can Match Records with Null Components

A **Text(null)** is a valid Text object if its constructor does not forbid null. A matching pattern can bind a null component, such as **case Text(var value)**. Therefore, code inside the case must account for whether value can be null according to the record's contract.

With **Box(null)**, a nested record pattern requires a Text object to deconstruct, such as **case Box(Text(var value))**, and cannot match a null inner component by deconstructing a non-existent Text. A broader branch such as **case Box(var inner)** can handle the remaining Box cases.

Explain null selectors and null components separately in Javadoc. Merely writing "null supported" is too vague when an API uses multiple levels of records.

## 3. Choose a Null Policy Before Writing Code

Typically there are three viable contracts:

**A. Null is a valid input with a specific meaning.** For example, a service accepts an optional payload: when there is no payload, it returns **NO PAYLOAD**. The documentation must state that value clearly; the code uses case null or checks before the switch.

**B. Null is an invalid input.** For example, the **requireText** method requires a real Payload. The API can call **Objects.requireNonNull(payload, "payload")** to throw NullPointerException right at the boundary, before handling subtypes.

**C. Null is turned into a strongly typed business state.** For larger APIs, instead of using null as a "not found" signal, you can return **Optional<T>**, a sealed result hierarchy, or a result object that accurately describes **Found / Missing / Invalid**. This approach fits when callers need to distinguish among reasons for missing data.

Not every API should accept null. Choose based on domain meaning and design principles. Good phrasing in documentation is **"this parameter may be null; in that case returns ..."** or **"does not accept null; throws ..."** — avoid unverifiable statements such as "null is handled safely."

### Decision Table

| Contract | Typical Clear Implementation | What Documentation Must State |
| --- | --- | --- |
| Null selector is valid | **case null -> "NO PAYLOAD"** | Return value when selector is null |
| Null selector is invalid | **Objects.requireNonNull** | Exception type and throwing condition |
| Null component treated as empty | **case Text(var value)** + guard or check | Distinction between null, blank, and nonblank |
| Null component violates invariant | Validation in the record constructor | Record cannot be created with a null component via a valid constructor |
| Missing result is a normal state | **Optional<T>** or result type | Meaning of absence, and whether null can be returned |
| Null must be forwarded downstream | Explicit policy at boundary and related tests | Whether downstream accepts null or converts it |

**Note:** Catching a generic NullPointerException and turning it into "no data" is dangerous: it can mask unintended null bugs inside the logic. Handle null **at the point where the cause is known**, rather than relying on a broad catch to guess its meaning.

## 4. Put the Contract into Javadoc: @param, @return, and @throws

Javadoc is the official place to publish the behavior of a public API. Three tags are especially useful:

- **@param:** whether the parameter accepts null; if null is valid, what it means.
- **@return:** whether the result is ever null; which sentinel value or empty result corresponds to which state.
- **@throws:** the exception type thrown and the condition that causes it.

Example of a method that **allows a null selector**:

~~~java
/**
 * Builds a human-readable description for a payload.
 *
 * <p>Allows {@code payload == null}; in that case returns {@code "NO PAYLOAD"}.
 * For a {@code Text} whose value is null, empty, or whitespace-only,
 * returns {@code "EMPTY TEXT"}. For a {@code Box} without non-empty
 * inner text, returns {@code "EMPTY BOX"}.
 *
 * @param payload payload to display; may be null
 * @return description string; never null
 */
static String formatNullable(Payload payload) {
    // Body appears in the complete program in section 7.
    throw new UnsupportedOperationException("illustrative declaration");
}
~~~

**This is an illustrative signature and Javadoc**, not an implementation to paste into the program in section 7. The actual method in section 7 has a full body and is runnable.

Example of a method that **rejects null**:

~~~java
/**
 * Retrieves the verbatim string of a Text.
 *
 * @param payload must be a non-null Text with a non-null value
 * @return the Text value string, never null;
 *         an empty string is still a valid result
 * @throws NullPointerException if payload is null or Text.value is null
 * @throws IllegalArgumentException if payload is not a Text
 */
static String requireText(Payload payload) {
    // Body appears in the complete program in section 7.
    throw new UnsupportedOperationException("illustrative declaration");
}
~~~

The two examples are **contract documentation** only. Statements about null, empty strings, and exceptions must match the implementation exactly. Do not write **@return never null** if any branch actually returns null; do not imply that every IllegalArgumentException is caused by null, because the two error types carry different meanings.

### Should Callers Rely on Exception Messages?

Messages aid debugging, but many APIs should not treat **getMessage()** text as a stable format for callers to parse. A contract usually only needs the **exception type** and **throwing condition**. If downstream callers need stable error codes, design an enum or dedicated error type rather than comparing message strings.

## 5. Type Patterns, Record Patterns, and Null at Each Level

Consider the following model:

~~~java
sealed interface Payload permits Text, Count, Box {}

record Text(String value) implements Payload {}
record Count(int value) implements Payload {}
record Box(Text inner) implements Payload {}
~~~

**Text**, **Count**, and **Box** are all final records, while Payload is a sealed interface. Because the three records do not have compact constructors checking for null, **Text(null)** and **Box(null)** can be constructed. That is an illustrative choice for learning about null contracts; in a real system you might **forbid null right in the constructor**.

### Record Pattern with a Guard

~~~java
case Text(String value) when value != null && !value.isBlank() ->
        "TEXT: " + value.trim();
case Text(var value) -> "EMPTY TEXT";
~~~

The first case only accepts a non-null, non-blank value. The second case has no guard and covers the remaining Text instances, including a null value. Thus a null component does not cause an error when calling **trim()** in the first branch: the condition **value != null && ...** is short-circuit evaluated.

**Common mistake:** changing the **&&** operator to **||** could call **isBlank()** when value is null, causing the guard to throw NullPointerException. A guard throwing an exception is different from a guard returning false: the error propagates rather than falling through to try the next case as a false result would.

### Nested Record Pattern and Fallback Branch

~~~java
case Box(Text(String value))
        when value != null && !value.isBlank() ->
        "BOX: " + value.trim();
case Box(var inner) -> "EMPTY BOX";
~~~

If Box.inner is null, the pattern **Box(Text(...))** cannot deconstruct an inner Text. If inner is **new Text(null)**, the first branch's logic also produces no displayable text. The **Box(var inner)** branch handles the remaining cases according to the example contract.

**Pattern-level takeaway:** An outer record being non-null does not guarantee that all of its components are non-null. Use record patterns to extract data; use invariants or explicit checks to verify whether the data is allowed to be null.

## 6. APIs That Reject Null: Fail Fast and Report Clearly

Suppose a method only accepts a **Text** with a non-null value component:

~~~java
static String requireText(Payload payload) {
    Objects.requireNonNull(payload, "payload");
    return switch (payload) {
        case Text(var value) -> Objects.requireNonNull(value, "text.value");
        case Count c -> throw new IllegalArgumentException("expected Text");
        case Box b -> throw new IllegalArgumentException("expected Text");
    };
}
~~~

**Objects.requireNonNull(payload, "payload")** throws NullPointerException if the selector is null. Because null has already been rejected before the switch, the switch does not need a case null to fulfill this contract. This is **boundary rejection**: readers immediately see that null is disallowed and see the specific reason.

If the selector is Text but value is null, the check **Objects.requireNonNull(value, "text.value")** throws NullPointerException. If the selector belongs to another subtype, the method throws IllegalArgumentException meaning "wrong payload kind."

Three input categories are distinguished:

1. **null payload:** missing required object.
2. **null Text.value:** object exists, but its internal data is invalid per requireText's contract.
3. **Count/Box:** valid Payload type, but not Text.

Not every API needs to separate these. The key point is to **choose a policy, implement it consistently, document @throws accurately, and test it**.

### Why Not Just Use default?

A switch **default** can provide fallback behavior for subtypes, but it does not fully describe the null contract. With a sealed Payload, listing all three subtypes lets the compiler check exhaustiveness. If a new subtype is added later, a switch without default forces developers to review the branches. Conversely, a broad default can silently lump a new subtype into inappropriate handling.

## 7. Complete Java 21 Program

The example below provides three APIs with different null contracts:

- **formatNullable(Payload)**: accepts a null selector, returns a non-null String.
- **requireText(Payload)**: rejects a null selector, rejects a null Text.value, and rejects non-Text Payload types.
- **hasNonblankText(Payload)**: uses an instanceof record pattern; returns boolean, where a null selector returns false.

All belong in the same file **NullBehaviorApiDemo.java**:

~~~java
import java.util.Objects;

public class NullBehaviorApiDemo {
    sealed interface Payload permits Text, Count, Box {}

    record Text(String value) implements Payload {}
    record Count(int value) implements Payload {}
    record Box(Text inner) implements Payload {}

    /**
     * Formats a payload into a descriptive string.
     *
     * @param payload may be null; null is treated as no payload
     * @return descriptive string, never null; a null selector yields
     *         "NO PAYLOAD"; a Text with a null/blank value yields
     *         "EMPTY TEXT"; a Box without valid text yields
     *         "EMPTY BOX"
     */
    static String formatNullable(Payload payload) {
        return switch (payload) {
            case Text(String value) when value != null && !value.isBlank() ->
                    "TEXT: " + value.trim();
            case Text(var value) -> "EMPTY TEXT";
            case Count(int n) -> "COUNT: " + n;
            case Box(Text(String value))
                    when value != null && !value.isBlank() ->
                    "BOX: " + value.trim();
            case Box(var inner) -> "EMPTY BOX";
            case null -> "NO PAYLOAD";
        };
    }

    /**
     * Extracts the verbatim value of a Text payload.
     *
     * @param payload must be a non-null Text with a non-null value
     * @return Text.value, never null; may be an empty string
     * @throws NullPointerException if payload is null or Text.value is null
     * @throws IllegalArgumentException if payload is Count or Box
     */
    static String requireText(Payload payload) {
        Objects.requireNonNull(payload, "payload");
        return switch (payload) {
            case Text(var value) -> Objects.requireNonNull(value, "text.value");
            case Count c -> throw new IllegalArgumentException("expected Text");
            case Box b -> throw new IllegalArgumentException("expected Text");
        };
    }

    /**
     * Checks whether payload is a Text with non-blank content.
     *
     * @param payload may be null; null returns false
     * @return true only when it is a Text with a non-null, non-blank value
     */
    static boolean hasNonblankText(Payload payload) {
        return payload instanceof Text(var value)
                && value != null && !value.isBlank();
    }

    static void printException(Payload payload) {
        try {
            System.out.println("TEXT VALUE: " + requireText(payload));
        } catch (NullPointerException | IllegalArgumentException ex) {
            System.out.println("REJECTED: " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        System.out.println(formatNullable(null));
        System.out.println(formatNullable(new Text(" hello ")));
        System.out.println(formatNullable(new Text(" ")));
        System.out.println(formatNullable(new Text(null)));
        System.out.println(formatNullable(new Count(7)));
        System.out.println(formatNullable(new Box(new Text(" nested "))));
        System.out.println(formatNullable(new Box(null)));
        System.out.println(formatNullable(new Box(new Text(null))));
        System.out.println(hasNonblankText(new Text("ok")));
        System.out.println(hasNonblankText(null));
        printException(new Text("hello"));
        printException(null);
        printException(new Text(null));
        printException(new Count(7));
    }
}
~~~

Compile and run with **JDK 21+**:

~~~bash
javac NullBehaviorApiDemo.java
java NullBehaviorApiDemo
~~~

Exact output:

~~~text
NO PAYLOAD
TEXT: hello
EMPTY TEXT
EMPTY TEXT
COUNT: 7
BOX: nested
EMPTY BOX
EMPTY BOX
true
false
TEXT VALUE: hello
REJECTED: payload
REJECTED: text.value
REJECTED: expected Text
~~~

### Reading the Output Against the Contract

**Line 1:** formatNullable(null) does not throw an error and returns NO PAYLOAD. This is an explicit API decision, not the default behavior of every switch.

**Line 2:** Text with a non-blank value is trimmed for display. Note that **requireText** is a different API and intentionally returns the verbatim string without trimming.

**Lines 3–4:** Text(" ") and Text(null) are both grouped into EMPTY TEXT per formatNullable's documentation.

**Line 5:** Count(7) yields COUNT: 7; there is no null concept for the primitive int component.

**Lines 6–8:** Box containing a Text with valid content returns BOX: nested; Box(null) and Box(new Text(null)) both receive EMPTY BOX, even though their data structures differ. If the application needs to distinguish them, the contract and logic must change.

**Lines 9–10:** hasNonblankText returns true for Text("ok") and false for a null selector. The variable is only bound when the instanceof pattern matches.

**Line 11:** requireText accepts Text("hello"), returns hello, and the caller prints TEXT VALUE: hello.

**Line 12:** A null selector is rejected by Objects.requireNonNull; the caller catches NullPointerException and prints REJECTED: payload.

**Line 13:** Text(null) is rejected at the value component, with the message text.value.

**Line 14:** Count is not a Text; an IllegalArgumentException is thrown per the contract.

This is a small example focused on null behavior, requiring no frameworks or preview flags. The purpose of printing exceptions is to **observe how it works**, not to recommend that all production code catch those exceptions and merely print strings; in real applications, error boundaries should fit the API layer, transactions, and logging.

## 8. Null Behavior Test Matrix

To verify whether an API implements its Javadoc faithfully, design a test matrix across multiple levels rather than just one null case.

| Test Input | formatNullable | requireText | hasNonblankText |
| --- | --- | --- | --- |
| **null** | NO PAYLOAD | NPE (payload) | false |
| **new Text("ok")** | TEXT: ok | returns "ok" | true |
| **new Text("")** | EMPTY TEXT | returns "" | false |
| **new Text("   ")** | EMPTY TEXT | returns verbatim blank string | false |
| **new Text(null)** | EMPTY TEXT | NPE (text.value) | false |
| **new Count(7)** | COUNT: 7 | IAE (expected Text) | false |
| **new Box(null)** | EMPTY BOX | IAE (expected Text) | false |
| **new Box(new Text(null))** | EMPTY BOX | IAE (expected Text) | false |
| **new Box(new Text("x"))** | BOX: x | IAE (expected Text) | false |

**NPE** is NullPointerException; **IAE** is IllegalArgumentException. This table describes the contracts of the three illustrative methods, not mandatory rules for every Java API.

A test should verify the **return value** and **exception type** as specified by the contract. If exception message text is not guaranteed to be stable, tests should not lock onto the exact message. For APIs spanning multiple Java versions or external integrations, also test compatibility when changing how absent values are represented.

### Direct Checks Without a Framework

Within the same scope of the example class, you can write:

~~~java
// Additional verification snippet, placed inside the same NullBehaviorApiDemo class.
if (!formatNullable(null).equals("NO PAYLOAD")) {
    throw new AssertionError("null selector behavior");
}
if (hasNonblankText(null)) {
    throw new AssertionError("instanceof null behavior");
}
try {
    requireText(null);
    throw new AssertionError("expected NullPointerException");
} catch (NullPointerException expected) {
    // Matches contract: null selector is not accepted.
}
~~~

This snippet is only for additional verification and **must not be copied verbatim outside the class** and expected to run on its own. With JUnit, you can use assertEquals, assertFalse, and assertThrows to express the corresponding conditions. Also test **new Text(null)** and **new Box(null)** to distinguish null at different levels.

## 9. A Model's Null Contract Differs from a Service's Contract

An often overlooked point: a **service method's** Javadoc cannot replace a **record's** constructor contract.

The illustrative model allows:

~~~java
new Text(null);
new Box(null);
~~~

If the domain decides Text.value must always have content, it can enforce that right in the constructor:

~~~java
// SEPARATE design variant, not combined with the Text declaration in section 7.
record StrictText(String value) {
    StrictText {
        Objects.requireNonNull(value, "value");
        if (value.isBlank()) {
            throw new IllegalArgumentException("blank value");
        }
    }
}
~~~

Once the invariant is enforced in the constructor, a service processing StrictText can rely on that non-null condition for validly constructed objects. This does not eliminate the need to document a null selector on a method accepting StrictText or a super-interface.

**Records do not automatically forbid null for reference components.** A compact constructor is the way to express invariants. Also consider collections, mutable objects, and deserialized data: do not assume every value source obeys domain rules if the system has special object-instantiation mechanisms.

When deciding whether to place validation in the model or in a method:

- If **a null component makes the record itself meaningless everywhere**, putting the invariant in the constructor can be simpler.
- If **the record is raw external data** and consumers have different policies, you can allow null and let each API define its contract clearly.
- If an object goes through multiple validation steps, consider using distinct types for **raw input** and **validated domain value**.

## 10. Nullability Annotations: Helpful, but No Replacement for Javadoc

Beyond Javadoc, many projects use annotations such as **@Nullable**, **@NonNull**, or **@NullMarked** depending on their ecosystem. For example, a library might publish:

~~~java
// Illustrates an annotation dependency from a project library;
// not standalone JDK-only code.
@Nullable
String findName(String id);
~~~

**Java SE does not have a universal @Nullable annotation in java.lang that every tool interprets identically.** A project must choose a specific annotation/tooling ecosystem (such as JSpecify, NullAway, Checker Framework, or IDE/framework-provided annotations) and configure the corresponding checker.

An annotation can help IDEs and static analysis catch invalid call sites. However:

1. It does not automatically insert **Objects.requireNonNull** at runtime.
2. Not all nullable annotations share the same semantics across every framework.
3. If the annotation and Javadoc contradict each other, callers remain confused and tools may analyze them differently.
4. Nullability on a **type argument** (such as a List's elements being nullable) differs from **the List reference itself** being nullable.

Use annotations **consistently** with the actual method implementation, Javadoc, and tests. Document the supporting library version and configuration in the build when onboarding developers.

## 11. Null Returns, Optional, and Structured Result Types

Return contracts are just as important as input contracts. Common return forms:

| Return Form | Meaning | Documentation Note |
| --- | --- | --- |
| **T** (nullable) | null is a defined signal | State clearly when null is returned; caller must check |
| **Non-null T** | Success always produces a value | Guarantee on all return paths; @throws on failure |
| **Optional<T>** | Presence or absence of a value | Never return null instead of Optional.empty() |
| **Result hierarchy** | Cases such as Success/NotFound/Invalid/Error | Each subtype has its own meaning; use exhaustive switch |
| **Exception** | Normal contract cannot be completed | State type and throwing conditions in @throws |

Example retrieval API:

~~~java
// Sketch snippet; repository is declared in application code.
Optional<String> findName(String id);
~~~

If choosing Optional, the documentation can specify "null id causes NullPointerException; not found returns Optional.empty()." Do not convert every null into Optional.empty() if null is actually **invalid** data. "Not found" is different from "invalid argument," "timeout," or "corrupted record."

For public APIs, changing from **nullable String** to **Optional<String>** is a signature change and usually requires updating callers; it cannot always be done without affecting compatibility.

## 12. Refactoring from instanceof to switch: Do Not Change Null Policy Unintentionally

A legacy snippet:

~~~java
static String oldLabel(Object value) {
    if (value instanceof String s) {
        return "text:" + s;
    }
    return "other";
}
~~~

Here **oldLabel(null)** returns **other**. If converted to:

~~~java
static String newLabel(Object value) {
    return switch (value) {
        case String s -> "text:" + s;
        default -> "other";
    };
}
~~~

then the new code **does not preserve the null behavior** of the old code: a null selector in a pattern switch needs explicit handling and otherwise throws NullPointerException. To keep the old contract, write:

~~~java
static String equivalentLabel(Object value) {
    return switch (value) {
        case String s -> "text:" + s;
        case null, default -> "other";
    };
}
~~~

In Java 21, the **case null, default** label is the syntax for handling null and the remaining values together. It can be replaced by two separate labels with the same result if you want to emphasize that null is an explicit decision.

If the project wants to **switch to rejecting null**, document it as an intentional API change and update Javadoc, tests, and release notes rather than treating it as a pure syntax refactoring.

### Warning About Case Ordering and Guards

In a pattern switch, a general case can make a more specific branch after it unreachable (**dominance**). A null-checking guard can also throw an error when the wrong operator is used. Review all of the following:

- Does a null selector hit the intended case?
- Is a null component checked before calling methods on it?
- Does a branch whose guard evaluates to false have a remaining path to handle it?
- Does a broad/default case hide the meaning of a new subtype or state?

## 13. Checklist for Documenting Null Behavior Before Publishing an API

When reviewing an API that uses Java Pattern Matching, use these questions:

1. **Inputs:** Which parameters are nullable? Is a null selector valid?
2. **Model:** Which record components are nullable? Can a nested record be missing its inner object?
3. **Output:** Can the method return null? Is an empty string different from null?
4. **Fallback:** Do case null, default, and instanceof else have clearly defined, consistent behavior?
5. **Exceptions:** When are NullPointerException, IllegalArgumentException, or domain exceptions thrown?
6. **Javadoc:** Do @param, @return, and @throws accurately document all of the above situations?
7. **Annotations:** Does the nullability annotation system match the actual implementation?
8. **Tests:** Are there tests for null selector, null component, nested null, blank, valid subtypes, and mismatched subtypes?
9. **Compatibility:** If null behavior changed, have callers, documentation, and regression tests been updated?
10. **Observability:** When null errors occur in production, does logging/tracing help distinguish intentional missing data from bugs without exposing sensitive data?

### Recurring Mistakes

- **Writing "null safe" without stating the outcome**: callers still do not know whether null yields a string, Optional, or an exception.
- **Confusing instanceof and switch**: instanceof null returns false, whereas pattern switch has its own null-selector rules.
- **Assuming default automatically catches null**: switch default does not replace a case null contract.
- **Confusing an existing record with non-null components**: Text(null) and Box(null) are two distinct states.
- **Catching all NullPointerExceptions**: can mask programming bugs instead of handling permitted inputs.
- **Using annotations while forgetting the runtime contract**: annotations can assist static analysis but do not guarantee exceptions or fallbacks.
- **Lumping errors and absent data together**: returning null or Optional.empty() for every error prevents callers from distinguishing the cause.
- **Skipping tests during refactoring**: converting if-else to switch can alter null behavior while still compiling cleanly.

**Conclusion:** Documenting null behavior is a public commitment about **which input values are valid, which values are returned, and which exceptions can occur**. With Java Pattern Matching, always distinguish **null selector**, **null component**, and **null nested record**; understand the difference between **instanceof** and **pattern switch**; write accurate **@param**, **@return**, and **@throws** tags; and keep Javadoc, annotations, implementation, and tests aligned. Pattern syntax makes code clearer, but only an intentional and verified contract helps callers use an API safely.