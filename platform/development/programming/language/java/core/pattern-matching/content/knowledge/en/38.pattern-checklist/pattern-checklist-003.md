# Null-Handling Checklist for Java Pattern Matching (Java 21+)

## 1. Goal: Check the Right Contract, Not Just Avoid NullPointerException

Refactoring from a legacy chain of type checks to `instanceof` patterns, record patterns, or pattern `switch` can change how a program handles `null`. The obvious symptom is a `NullPointerException`, but a more serious bug is sometimes **silently treating missing data as success** or **selecting the wrong business branch**.

This checklist is for writing code, reviewing pull requests, migrating legacy Java code, and designing tests for pattern branches. The goal is to answer clearly:

1. Does the `null` value appear at the **top-level selector** or at a **component inside a record**?
2. Is `null` a value permitted by the contract, a data error that needs a structured return value, or a programming precondition violation?
3. Does the pattern actually match `null` at that position?
4. Does the guard check for `null` **before dereferencing**, and is there a fallback path when the guard is false?
5. Does the `switch expression` handle all subtypes, the `null` case, and the other-type case according to the selector type?
6. Are there dedicated tests verifying **null selector**, **null nested record**, **null component**, **guard false**, and **default**?

**Key point:** there is no single rule like "add `case null` to every switch" that applies across an entire application. `case null` is an **API contract** choice. When an input must be non-null, `Objects.requireNonNull` and an explicit exception may be more appropriate.

This guide uses **Java 21+**, where record patterns and pattern matching in `switch` are stable without enabling preview features. Short illustrative snippets are distinguished from the complete Java program in Section 9.

## 2. 30-Second Decision Checklist

Before reading each `case` line by line, determine the **policy**:

| Review question | If "Yes" | Appropriate action |
| --- | --- | --- |
| Can the selector be absent per contract? | Yes | `case null` returns a clearly documented business/validation result |
| Must the selector always be present? | Yes | Reject explicitly at the boundary, such as with `requireNonNull` |
| Is the selector an object where an inner field can be null? | Yes | Validate the component, use a guard, or enforce a constructor/factory invariant |
| Can a nested record be absent? | Yes | Handle an outer record fallback branch; a top-level `case null` is not a substitute |
| Does the guard call a method on a pattern variable? | Yes | Ensure the variable is non-null **before calling** |
| Is `default` being used to "catch everything"? | Yes | Check null selector, subtype coverage, and unsupported types separately |
| Is the selector a `sealed interface`? | Yes | Use exhaustive branches; consider omitting `default` so the compiler warns when a subtype is added |
| Can multiple fields be invalid at the same time? | Yes | Define error priority order, order guards accordingly, and test |
| Are you migrating from `instanceof` to `switch`? | Yes | Retest null behavior, because the two constructs do not share the same default behavior |

A clear policy can usually be written in a single sentence:

> "At the external event boundary, a null event returns `INVALID:event`; in internal APIs, a null event is an API call error; a null `referral` field is optional; a null `account` or null `account.id` is a data error."

Until you can write such a sentence, **do not pick `case null` or `default` just to make the program compile**.

## 3. Classifying Null Positions: An Essential Checklist Table

It is the same `null`, yet different pattern contexts behave differently:

| Position | Example | Behavior or risk |
| --- | --- | --- |
| Selector of `instanceof` | `Object x = null; x instanceof String s` | `false`; the pattern variable is not in scope on the non-matching path |
| Selector of pattern `switch` | `switch (x)` with `x == null` | Does not automatically run `default`; typically throws `NullPointerException` if no matching null branch exists |
| Explicitly handled selector | `case null -> invalid("event")` | Selects the null branch per contract |
| Outer record present, inner record null | `Signup(null, "web", null)` | `Signup(Account(...))` does not match; needs a broader `Signup(...)` branch |
| Inner record present, field null | `Signup(Account(null), "web", null)` | `var id` receives null; guard needs to check |
| Component modeled as optional | `referral == null` | May be valid and interpreted intentionally |
| Component statically typed `String`, using unconditional component pattern | `TypedText(String text)` with null text | Can match, and variable `text` is still null |
| Component statically typed `Object`, using conditional `String` pattern | `OpenText(String text)` with null text | Inner pattern does not match |
| Required context provided by caller | `routeRequired(null)` | Reject early; do not pretend it is a valid event |

**Do not conflate** "nested record pattern did not match" with "guard returned false". If the nested record is null, the guard on the branch containing the nested record pattern is **never invoked**. If the nested record is present but a field inside it is null, the record pattern can match and the guard is evaluated.

### Short example: before and after adding a null policy

~~~java
// Standalone illustrative method snippet for syntax:
static String describe(Object value) {
    return switch (value) {
        case String s when !s.isBlank() -> "text:" + s;
        case String s -> "blank-text";
        default -> "other";
    };
}
~~~

`describe("abc")` yields `"text:abc"`; `describe(" ")` yields `"blank-text"`; `describe(10)` yields `"other"`. However, **`describe(null)` throws NPE**, not `"other"`.

If the contract requires accepting a missing input and returning a status name:

~~~java
static String describe(Object value) {
    return switch (value) {
        case null -> "missing";
        case String s when !s.isBlank() -> "text:" + s;
        case String s -> "blank-text";
        default -> "other";
    };
}
~~~

If the contract requires the selector to always be present, instead of returning `"missing"`, you can keep the branches and place:

~~~java
java.util.Objects.requireNonNull(value, "value");
~~~

**Checklist:** every null policy change must be accompanied by an updated Javadoc/API contract, null test cases, and verification of caller behavior.

## 4. Checking `instanceof`, Type Patterns, and Flow Scoping

`instanceof` returns false when the left-hand operand is null:

~~~java
Object input = null;

if (input instanceof String text) {
    System.out.println(text.length());
} else {
    System.out.println("not-text");
}
~~~

Output:

~~~text
not-text
~~~

`text` is only in scope on the program path where the pattern is proven to have matched. When using logical operators:

~~~java
if (input instanceof String text && !text.isBlank()) {
    System.out.println("valid");
}
~~~

The right-hand side of `&&` is evaluated only if `instanceof String text` is true. This is a safe coding pattern when the selector itself can be null.

**Do not misapply this reasoning to `||`**:

~~~java
// Invalid: on the right-hand side of ||, text is not guaranteed to be assigned.
// if (input instanceof String text || text.isBlank()) { ... }
~~~

Do not use a pattern variable outside the scope permitted by the compiler. And do not confuse this mechanism with record component patterns, where a `var` can receive null after the outer record matches.

### Questions for the reviewer

- Is the author relying on `instanceof` to exclude a null **selector**, or accidentally assuming it excludes all null **components**?
- Is `&&` used instead of `||` where the pattern variable is only in scope if the left-hand side matches?
- Was an old `if (x instanceof T)` replaced with `switch (x)`, accidentally changing null behavior?
- Is there any manual cast or method call before checking for null/type?

## 5. Checklist for Nested Record Patterns

Example data:

~~~java
record Account(String id) {}
record Signup(Account account, String source, String referral) {}
~~~

Consider four inputs:

~~~java
new Signup(null, "web", null);
new Signup(new Account(null), "web", null);
new Signup(new Account("A1"), null, null);
new Signup(new Account("A1"), "web", null);
~~~

Each case needs a clear meaning:

1. **Account null:** there is no nested object; the pattern `Signup(Account(var id), ...)` does not match.
2. **Account.id null:** the nested object exists; `Account(var id)` matches, and `id` receives null.
3. **Source null:** `var source` receives null and requires validation.
4. **Referral null:** if referral is an optional field, null may be **valid**, not necessarily something to reject.

A `case null` on the `Signup` selector **does not catch** those three component-null cases, because the `Signup` object itself exists.

### Designing safe branches by specificity

~~~java
return switch (event) {
    case null -> invalid("event");

    case Signup(Account(var id), var source, var referral)
            when blank(id) -> invalid("accountId");

    case Signup(Account(var id), var source, var referral)
            when blank(source) -> invalid("source");

    case Signup(Account(var id), var source, var referral) ->
            ok("signup:" + id + ":" + source + ":"
                    + optionalReferral(referral));

    case Signup(var account, var source, var referral) ->
            invalid("account");

    // Other Event variants...
};
~~~

This is an **illustrative skeleton inside `switch`**, with a comment standing in for the remaining branches, so it is not a standalone method. Section 9 contains the full compilable version.

Why is this ordering useful?

- Validation guards come **before** the unguarded success branch.
- The unguarded `Signup(Account(...))` branch after validation covers every `Signup` with a non-null `Account`, even when `referral` is null.
- The broader `Signup(var account, ...)` branch is placed last, catching `Signup` instances with `account == null`.
- Placing `Signup(var account, ...)` earlier could cause the more specific branches after it to be reported as *dominated*.
- Here, when both `accountId` and `source` are invalid, the `accountId` error takes precedence because its guard appears first. This is an **intentional** policy that must be tested.

### Do not dereference in a guard before checking null

~~~java
// Wrong when id can be null:
// case Signup(Account(var id), var source, var referral)
//     when !id.isBlank() -> ...

// Null-safe:
static boolean blank(String text) {
    return text == null || text.isBlank();
}
~~~

`||` short-circuits: when `text == null`, Java does not execute `text.isBlank()`. If you use `&&` to check for a valid value, place `text != null` before the method call.

## 6. An Advanced Trap: A `String`-Typed Component Pattern Can Still Receive Null

Two records:

~~~java
record TypedText(String text) {}
record OpenText(Object text) {}
~~~

If a record's component is declared directly as `String`, the inner pattern `String text` can be an **unconditional pattern**, and Java 21 allows it to match even a null component value:

~~~java
Object typed = new TypedText(null);

boolean matched =
        typed instanceof TypedText(String text) && text == null;

// matched == true
~~~

By contrast, a record whose component is statically typed as `Object` requires a conditional `String` type test:

~~~java
Object open = new OpenText(null);

boolean matched =
        open instanceof OpenText(String text);

// matched == false
~~~

Compare further:

~~~java
Object nothing = null;
boolean matchesTopLevel = nothing instanceof String text;
// matchesTopLevel == false
~~~

**The three results do not contradict each other.** A top-level selector differs from a record component; an unconditional component pattern differs from a conditional pattern on `Object`. Therefore, a review checklist must inspect **the declared type of the component**, rather than seeing the keyword `String` or `var` and assuming null is excluded.

When the case body calls `text.length()`, ask: **does the constructor/factory enforce a non-null invariant?** If not, a guard or validation is needed. A record is a data carrier; it does not automatically create a non-null contract for reference components.

## 7. Checklist for Exhaustive `switch`, `when`, and `default`

With a closed set of commands:

~~~java
sealed interface Event permits Signup, Invoice, Logout {}
~~~

The three record subtypes are final; a `switch expression` handling all three branches can be exhaustive. Still, you must check **guarded patterns** and **nested components**.

### Practical rules

- **A case with `when` is not considered to cover the entire subtype.** If the guard is false, there must be a subsequent branch to handle it.
- **A nested record pattern may fail to match when the inner record is null.** Add a fallback for the outer record if the input has not been validated.
- **Broader branches go after narrower branches.** This is both logical and avoids dominated-case errors.
- **`case null` handles a null selector; `default` does not substitute for it.** You can intentionally combine `case null, default` if they share the same result, but document the conflation of those two meanings clearly.
- **Do not add `default` just to bypass a compiler error** when the subtype set is sealed. A broad fallback hides forgetting to handle a new subtype.
- **Exhaustiveness does not mean a valid payload.** The compiler knows which types are covered; it does not prove that every `Account.id` is non-null or every `Invoice.cents` is positive.

Example of a strict method:

~~~java
static Decision routeRequired(Event event) {
    java.util.Objects.requireNonNull(event, "event");

    return switch (event) {
        case Signup s -> route(s);
        case Invoice i -> route(i);
        case Logout l -> route(l);
    };
}
~~~

This method has a **different policy** from `route(Event event)` with `case null`: it rejects a null selector at entry, while reusing the internal validation logic for every non-null event.

### When is adding `case null` the wrong goal?

If an event is a required parameter in an internal API and null indicates the caller forgot to initialize it, returning `OK:"ignored"` or a "nothing to do" code can mask a bug. Keep an explicit rejection or map to an exception per project convention.

If a boundary receives untrusted data where missing requests are expected, `case null -> invalid("event")` may be right, because **data errors are anticipated** and the caller receives a result type it can handle.

## 8. Test Matrix to Have Before Approving a PR

The practice exercise uses three events:

- `Signup(Account account, String source, String referral)`: `account` and `source` are required; `referral` is optional.
- `Invoice(Account account, long cents)`: valid `account`, positive amount.
- `Logout(String sessionId)`: non-null/non-blank `sessionId`.

Minimum cases to cover:

| Group | Typical input | Expected |
| --- | --- | --- |
| Null selector | `route(null)` | `INVALID:event` |
| Strict null selector | `routeRequired(null)` | `NullPointerException` |
| Valid record | `Signup(Account("A1"),"web",null)` | Success, default referral `none` |
| Optional field | Null or blank referral | Per contract, does not invalidate the whole event |
| Null nested record | `Signup(null,"web",null)` | `INVALID:account` |
| Null component | `Signup(Account(null),"web",null)` | `INVALID:accountId` |
| Blank component | `Signup(Account(" "),"web",null)` | `INVALID:accountId` |
| Null required field | Null source | `INVALID:source` |
| Multiple invalid fields | Null account ID and empty source | `INVALID:accountId` takes precedence |
| Boundary number | `Invoice(Account("A2"),1)` | Success |
| Invalid number | Zero or negative cents | `INVALID:cents` |
| Remaining variant | `Logout(null)` | `INVALID:sessionId` |
| Other selector type | `classifyRaw(42)` | Fallback `other-type` |
| Guard false | Blank string | Fallback `blank-text` |
| `instanceof` null | `null instanceof String` | `false` |
| Unconditional component pattern | `TypedText(String text)`, null component | Can match and `text == null` |
| Conditional component pattern | `OpenText(String text)`, null component | Does not match |
| Missing `case null` | Pattern `switch` with `default` but null selector | Expected NPE |

### Regression checks

Do not test only "no more NPE". A fix can make every path return a default value while still being wrong for the business logic. Test the **exact error code, field name, and fallback path**.

When migrating from `if (x instanceof T)` to pattern `switch`, check the null cases before and after migration to confirm that any change is an **intentional contract change**, not a regression.

## 9. Complete Java 21 Program: 29 Checks

Copy the following code into **`NullChecklistDemo.java`**. The program requires no libraries outside the JDK.

~~~java
public class NullChecklistDemo {
    sealed interface Event permits Signup, Invoice, Logout {}

    record Account(String id) {}
    record Signup(Account account, String source, String referral)
            implements Event {}
    record Invoice(Account account, long cents) implements Event {}
    record Logout(String sessionId) implements Event {}

    enum Code { OK, INVALID }
    record Decision(Code code, String detail) {}
    record TypedText(String text) {}
    record OpenText(Object text) {}

    static Decision ok(String detail) {
        return new Decision(Code.OK, detail);
    }

    static Decision invalid(String field) {
        return new Decision(Code.INVALID, field);
    }

    static boolean blank(String value) {
        return value == null || value.isBlank();
    }

    static String optionalReferral(String value) {
        return blank(value) ? "none" : value;
    }

    static Decision route(Event event) {
        return switch (event) {
            case null -> invalid("event");

            case Signup(Account(var id), var source, var referral)
                    when blank(id) -> invalid("accountId");

            case Signup(Account(var id), var source, var referral)
                    when blank(source) -> invalid("source");

            case Signup(Account(var id), var source, var referral) ->
                    ok("signup:" + id + ":" + source
                            + ":" + optionalReferral(referral));

            case Signup(var account, var source, var referral) ->
                    invalid("account");

            case Invoice(Account(var id), var cents)
                    when blank(id) -> invalid("accountId");

            case Invoice(Account(var id), var cents)
                    when cents <= 0 -> invalid("cents");

            case Invoice(Account(var id), var cents) ->
                    ok("invoice:" + id + ":" + cents);

            case Invoice(var account, var cents) ->
                    invalid("account");

            case Logout(var sid)
                    when blank(sid) -> invalid("sessionId");

            case Logout(var sid) ->
                    ok("logout:" + sid);
        };
    }

    static Decision routeRequired(Event event) {
        java.util.Objects.requireNonNull(event, "event");

        return switch (event) {
            case Signup s -> route(s);
            case Invoice i -> route(i);
            case Logout l -> route(l);
        };
    }

    static String classifyRaw(Object raw) {
        return switch (raw) {
            case null -> "missing";
            case String s when !s.isBlank() -> "text:" + s;
            case String s -> "blank-text";
            default -> "other-type";
        };
    }

    static String missingNullCase(Object raw) {
        return switch (raw) {
            case String s -> "text:" + s;
            default -> "other-type";
        };
    }

    static int passed = 0;

    static void check(String label, boolean result) {
        if (!result) throw new AssertionError(label);
        passed++;
        System.out.println("PASS " + label);
    }

    static void checkEvent(String label, Event event, Decision expected) {
        boolean same = expected.equals(route(event));
        if (event != null) {
            same &= expected.equals(routeRequired(event));
        }
        check(label, same);
    }

    static void checkRaw(String label, Object input, String expected) {
        check(label, expected.equals(classifyRaw(input)));
    }

    static void checkNpe(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected NPE: " + label);
        } catch (NullPointerException expected) {
            check(label, true);
        }
    }

    public static void main(String[] args) {
        checkEvent("missing-event",
                null, invalid("event"));

        checkEvent("signup-no-referral",
                new Signup(new Account("A1"), "web", null),
                ok("signup:A1:web:none"));
        checkEvent("signup-referral",
                new Signup(new Account("A1"), "app", "promo"),
                ok("signup:A1:app:promo"));
        checkEvent("signup-blank-referral",
                new Signup(new Account("A1"), "web", " "),
                ok("signup:A1:web:none"));
        checkEvent("signup-null-account",
                new Signup(null, "web", null),
                invalid("account"));
        checkEvent("signup-null-id",
                new Signup(new Account(null), "web", null),
                invalid("accountId"));
        checkEvent("signup-blank-id",
                new Signup(new Account(" "), "web", null),
                invalid("accountId"));
        checkEvent("signup-null-source",
                new Signup(new Account("A1"), null, null),
                invalid("source"));
        checkEvent("signup-blank-source",
                new Signup(new Account("A1"), " ", null),
                invalid("source"));
        checkEvent("signup-two-bad-fields",
                new Signup(new Account(null), "", null),
                invalid("accountId"));

        checkEvent("invoice-ok",
                new Invoice(new Account("A1"), 250),
                ok("invoice:A1:250"));
        checkEvent("invoice-minimum",
                new Invoice(new Account("A2"), 1),
                ok("invoice:A2:1"));
        checkEvent("invoice-null-account",
                new Invoice(null, 10),
                invalid("account"));
        checkEvent("invoice-null-id",
                new Invoice(new Account(null), 10),
                invalid("accountId"));
        checkEvent("invoice-blank-id",
                new Invoice(new Account(" "), 10),
                invalid("accountId"));
        checkEvent("invoice-zero",
                new Invoice(new Account("A1"), 0),
                invalid("cents"));
        checkEvent("invoice-negative",
                new Invoice(new Account("A1"), -5),
                invalid("cents"));

        checkEvent("logout-ok",
                new Logout("S1"), ok("logout:S1"));
        checkEvent("logout-null-id",
                new Logout(null), invalid("sessionId"));
        checkEvent("logout-blank-id",
                new Logout(" "), invalid("sessionId"));

        checkRaw("raw-null", null, "missing");
        checkRaw("raw-text", "hello", "text:hello");
        checkRaw("raw-blank", " ", "blank-text");
        checkRaw("raw-other", 42, "other-type");

        Object missing = null;
        check("instanceof-null-false",
                !(missing instanceof String s));

        Object typed = new TypedText(null);
        check("typed-component-null",
                typed instanceof TypedText(String text)
                        && text == null);

        Object open = new OpenText(null);
        check("open-component-null",
                !(open instanceof OpenText(String text)));

        checkNpe("required-null",
                () -> routeRequired(null));
        checkNpe("switch-default-null",
                () -> missingNullCase(null));

        System.out.println("ALL PASSED: " + passed);
    }
}
~~~

### Compiling and running

Requires JDK 21 or later:

~~~bash
javac --release 21 NullChecklistDemo.java
java NullChecklistDemo
~~~

**Output when all checks pass:**

~~~text
PASS missing-event
PASS signup-no-referral
PASS signup-referral
PASS signup-blank-referral
PASS signup-null-account
PASS signup-null-id
PASS signup-blank-id
PASS signup-null-source
PASS signup-blank-source
PASS signup-two-bad-fields
PASS invoice-ok
PASS invoice-minimum
PASS invoice-null-account
PASS invoice-null-id
PASS invoice-blank-id
PASS invoice-zero
PASS invoice-negative
PASS logout-ok
PASS logout-null-id
PASS logout-blank-id
PASS raw-null
PASS raw-text
PASS raw-blank
PASS raw-other
PASS instanceof-null-false
PASS typed-component-null
PASS open-component-null
PASS required-null
PASS switch-default-null
ALL PASSED: 29
~~~

### How to interpret the results

- **First 20 event cases:** verify null selector, valid and invalid payloads, optional referral, null nested record, null/blank components, and error precedence. For non-null events, `checkEvent` also compares the results of both `route` and `routeRequired` on the **same input**.
- **4 `classifyRaw` cases:** directly verify `case null`, non-blank `String`, blank `String`, and other types falling into `default`.
- **`instanceof-null-false`:** confirms a null selector does not match a direct type pattern.
- **`typed-component-null` and `open-component-null`:** demonstrate that the two component pattern forms have different null semantics.
- **2 NPE check cases:** confirm that the strict API rejects null and that a pattern switch with `default` but without `case null` still throws NPE.

Each check calls `check`, which throws `AssertionError` if the result is wrong. Thus `ALL PASSED: 29` appears only if every case passes. This test suite demonstrates **Java's behavior in the stated scenarios**; it does not replace parser/JSON integration tests or full business rules in a real system.

## 10. Checklist at the DTO, Parsing, and Domain Boundaries

Not every `null` in Java code comes from the same source. Before writing a pattern `switch` in the domain layer, check what steps the data has already gone through.

~~~text
HTTP / message / file / CLI
         |
         v
Parse input source
         |
         v
Distinguish missing field, explicit null, wrong type, empty string
         |
         v
Validate and map to domain or error result
         |
         v
Pattern matching on domain subtypes
         |
         v
Business handler and result
~~~

In particular:

- **A missing field** in JSON and **a field present with value null** may differ in the API contract. If the parser collapses both into Java `null`, `case null` cannot recover that distinction.
- **A missing body** and **a valid body containing a null field** are different. A `case null` on the DTO only catches the case where the DTO object itself does not exist.
- **Validation in the constructor** can reject invalid data before patterns run. If the constructor disallows a null `Account`, a fallback branch for null `Account` may be defensive at the boundary rather than a regular domain path.
- **`Optional`** can express some absent values, but it does not by itself decide whether null is an error or valid; do not turn every field/parameter into `Optional` without reviewing the API contract.
- **Infrastructure errors** or bugs that leave a variable unexpectedly null do not automatically become input errors; do not catch every `NullPointerException` and return `INVALID`.

Reviewers should ask to make explicit **which point is responsible for validation** and **which invariants patterns can rely on after that point**.

## 11. Checklist for Error Priority and Guard Scope

A pattern with multiple simultaneous invalid conditions requires a priority policy:

~~~java
case Signup(Account(var id), var source, var referral)
        when blank(id) -> invalid("accountId");

case Signup(Account(var id), var source, var referral)
        when blank(source) -> invalid("source");
~~~

If `id == null` and `source == ""`, the first branch wins. That is not a special property of null, but of **branch evaluation order**. If the project needs to return **all validation errors at once**, a switch that decides a single first result like this may not suffice; a validator that collects multiple errors before dispatching is needed.

**Reviewers should ask:**

1. Which validation has higher priority?
2. If multiple errors coexist, does the API return the first error or the full list?
3. Does the guard depend on a null check placed earlier?
4. Does a null nested record cause the pattern not to match, or the guard to evaluate to false?
5. Is there an unguarded branch covering the rest of the subtype?
6. Are logs/metrics needed for failure branches, and do logs expose sensitive information?

Do not use functions with side effects in `when` when only a condition is needed. Debugging, logging, or reordering cases can cause side effects to run differently than expected.

## 12. Common Mistakes to Catch in Code Review

**1. Adding `default -> success` to dodge null.** In a Java 21 pattern switch, `default` does not automatically handle a null selector. Moreover, returning success for missing data can hide upstream errors.

**2. Using `case String s when s == null` to accept a null selector.** A type pattern on the selector does not match null; that guard never runs for a null selector.

**3. Assuming a record pattern guarantees all components are non-null.** `var id` and even unconditional component patterns can match null values depending on the component's static type.

**4. Adding only a top-level `case null` and ignoring nested records.** `Signup(null,...)` does not enter `case null` when the `Signup` selector itself is non-null. The `account` field must be handled separately.

**5. Placing a broad branch before a guarded branch.** The compiler may report a dominated case, or the specific branch may become unreachable. Keep specific branches first, fallback after.

**6. Writing `id.isBlank()` before `id != null`.** This can throw NPE right inside the guard. Use a null-safe `blank` helper or order `&&`/`||` properly.

**7. Treating `sealed` as validation.** `sealed` restricts subtypes; it does not enforce a non-blank account ID or a positive invoice amount.

**8. Adding `default` to a sealed switch just to make it compile.** This can hide missing handling when a new subtype is added. Compiler exhaustiveness is a benefit to leverage.

**9. Changing the null policy without updating tests and docs.** Moving from NPE to `INVALID:event` is an observable change for callers, not just a syntax tweak.

**10. Catching `RuntimeException` broadly and returning a "missing data" error.** Bugs, timeouts, dependency failures, and validation errors are not the same category of error.

**11. Treating optional and required fields the same.** `referral == null` may be valid; `account == null` may be invalid. Evaluate each field according to the business rules.

**12. Forgetting to distinguish missing vs. explicit null from external data.** This must be decided at the parsing layer; patterns only see values already converted into Java objects.

**13. Writing tests only for the happy path.** Without null-selector, null-nested-record, and guard-false cases, a seemingly clean refactor can silently change behavior.

**14. Ignoring the behavior of strict APIs.** `routeRequired(null)` is supposed to throw an exception; changing it to return a success result can hide caller bugs.

## 13. Pull Request Checklist Template

Apply to every new pattern `switch` or `instanceof`:

### A. Data contract

- [ ] Identified whether the selector is nullable.
- [ ] Documented whether null is a valid domain value, invalid data, or an API violation.
- [ ] Distinguished optional fields from required fields.
- [ ] Identified the data source and where validation is performed.
- [ ] Verified that constructor/factory invariants are enforced in code, not just comments.

### B. Pattern correctness

- [ ] Direct `instanceof` has the intended null behavior.
- [ ] Pattern `switch` has `case null` or explicitly rejects null if needed.
- [ ] `default` is not mistaken for the default way to catch null.
- [ ] Nested records have a fallback if an inner object can be null.
- [ ] Nullable components have a guard or invariant protecting them before dereference.
- [ ] Branches with `when` appear before broader branches of the same type.
- [ ] All `sealed` subtypes are covered, avoiding `default` that masks missing cases.
- [ ] Error priority order when multiple fields are invalid has been decided.

### C. Testing

- [ ] Null selector test exists.
- [ ] Normal subtype tests exist for every variant.
- [ ] Null nested record test exists.
- [ ] Null component and blank string tests exist for required fields.
- [ ] Null optional field test exists.
- [ ] Guard-false and fallback-branch tests exist.
- [ ] Unsupported-type test exists if the selector is broad.
- [ ] Strict API exception tests exist, not only nullable result tests.
- [ ] Simultaneous multi-error input test exists to protect priority order.
- [ ] For legacy code refactors, confirmed which behavior changes are intentional.

### D. Maintainability

- [ ] Javadoc/API contract states the null policy and validation source.
- [ ] Logs do not expose sensitive data and do not turn exceptions into arbitrary validation errors.
- [ ] When a new subtype is added, the compiler/tests can flag unhandled places.
- [ ] No broad catch blocks hide bugs or infrastructure errors.

## 14. Practice Exercises for the Checklist

**Exercise 1 — changing the null policy.** Modify `route(Event)` to reject null using `Objects.requireNonNull`. Update the `missing-event` test to expect an exception and explain why this is a contract change, not just a one-line edit.

**Exercise 2 — constructor validation.** Add compact constructors to `Signup`, `Invoice`, and `Logout` to reject invalid data before `route` is called. List the tests that previously returned `INVALID` and must now expect the constructor to throw an exception. Choose the appropriate boundary for a real system.

**Exercise 3 — representing multiple errors.** Replace the "first error wins" strategy with a validator that collects both `accountId` and `source` when both are invalid. Keep the selector's null policy unchanged.

**Exercise 4 — adding a variant.** Add a `Suspend(String reason)` subtype to `Event`. Recompile and observe the `switch expression`s missing a case. Add tests for null/blank `reason`.

**Exercise 5 — deeper nested records.** Change `Account(String id)` to `Account(Profile profile)` with `Profile(String id)`. Test three cases: `Account` null, `Profile` null, and `Profile.id` null; identify which cases have a matching pattern and whether the guard runs.

**Exercise 6 — distinguishing missing/explicit null.** Model a DTO that can indicate whether the `referral` field is absent, explicit null, or a string. Design a clear result type for the parser before mapping to the domain; explain why a plain `String referral` is insufficient if the protocol must distinguish all three cases.

**Exercise 7 — review exercise.** Find the bugs in the following snippet:

~~~java
// Illustrative buggy code: do not use directly in production.
static String bad(Object raw) {
    return switch (raw) {
        case Signup(Account(var id), var source, var referral)
                when !id.isBlank() -> "accepted";
        default -> "ignored";
    };
}
~~~

Hint: the condition `!id.isBlank()` is unsafe when `id == null`; `default` does not automatically handle a null selector; rules for `source`, optional `referral`, and null `account` are missing; `"ignored"` can hide invalid data. Fix it according to a clear contract, write null tests at all three levels, and compare against the decision table at the start of the article.

**Takeaway:** A null-handling checklist does not end at the question "is there a `case null`?". You must determine **where null can occur, whether it is allowed, which pattern handles it, whether the guard is safe, whether the fallback branch is right, and whether tests verify all of it**. In Java 21, the sustainable approach combines a clear API contract, `sealed` types for exhaustiveness checking, null-safe guards, component validation, and an intentional test matrix.