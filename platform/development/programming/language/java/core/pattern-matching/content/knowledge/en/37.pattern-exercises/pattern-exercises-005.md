# Adding `case null` Intentionally: Comprehensive Java Pattern Matching Practice (Java 21+)

## 1. The Problem: Adding a null case is not just fixing an NPE

When migrating code from `if/else` chains and casts to **pattern matching in `switch`**, a seemingly small change can break the `null`-handling contract:

~~~java
static String label(Object value) {
    return switch (value) {
        case String text -> "text:" + text;
        default -> "other";
    };
}
~~~

With `label("abc")`, the method returns `"text:abc"`. With `label(42)`, it returns `"other"`. **With `label(null)`, a Java 21 pattern switch throws `NullPointerException`**, rather than automatically falling into `default`.

You can fix it with:

~~~java
static String label(Object value) {
    return switch (value) {
        case null -> "missing";
        case String text -> "text:" + text;
        default -> "other";
    };
}
~~~

But the more important question is: **is `"missing"` actually the right business result?** If `null` represents a missing value permitted by the API, `case null` is a reasonable choice. If `null` is a programming error because the contract requires a mandatory command, **you should not silently turn it into a valid result**.

This comprehensive practice exercise helps you decide:

- When to use `case null` to represent a business branch.
- When to proactively reject input with `Objects.requireNonNull`.
- When validation needs to return a structured data error instead of throwing an accidental exception.
- Why `default`, `when`, and record patterns do not automatically handle `null` in every position.
- How to handle `null` at the **outer selector**, **nested records**, and **components inside records**.
- How to preserve **exhaustiveness** when a `switch` handles a `sealed interface`.
- How to prove the change is intentional with **positive and negative test cases**, not just with a single line of code.

The main example uses **JDK 21+** because record patterns and pattern `switch` are stable features starting in Java 21. No `--enable-preview` is required.

## 2. Three different business meanings of null

A `null` value is a Java-level state, but **its meaning must be determined by the application contract**. The same `null` in two different APIs may require different behavior.

| Context | Meaning of `null` | Appropriate policy | Example |
| --- | --- | --- | --- |
| Input classifier from an external system | No request yet or absent payload | Return `INVALID` result or a "missing" label | `case null -> invalid("missing-command")` |
| Internal API requiring a mandatory command | Caller violated the contract | Reject early, stating the parameter name clearly | `Objects.requireNonNull(command, "command")` |
| Business data that may be absent | "Unspecified", "not entered", "not available" is a valid state | `case null` with a meaningful domain result | `case null -> "not-selected"` |
| Nullable field inside a record | Payload is missing a component, not necessarily missing the selector | Constructor/factory validation or a guard in the case | `name != null && !name.isBlank()` |
| Nested record is null | Missing child object | Fallback branch for the enclosing object or a data error | `case Envelope(var customer, var memo)` |

**Decision rule:** before adding a null branch, ask **who is responsible for fixing the null value** and **whether null is permitted by the contract**.

- If the caller is allowed to omit a value, mapping null to a domain result may be right.
- If the caller is required to provide an object, rejecting early helps catch bugs faster.
- If the data comes from JSON, a message queue, or an unvalidated DTO, you need to distinguish between a **missing field**, a **field that is null**, and a **field with invalid content** according to the API contract. `case null` on the parsed object cannot distinguish those cases by itself.

Do not add `case null -> defaultValue` just to stop tests from throwing an exception, if that default hides an important data error.

## 3. Java 21 semantics to master

### 3.1. `instanceof` with a null selector

~~~java
Object value = null;

if (value instanceof String text) {
    System.out.println(text.length());
} else {
    System.out.println("not a string");
}
~~~

Output:

~~~text
not a string
~~~

`instanceof` directly returns `false` when the selector is null. The `if` body does not run, so the pattern variable `text` is not dereferenced.

This **does not mean** every `String` declared by a pattern is non-null in every position: record component patterns have their own rules (section 7).

### 3.2. Pattern `switch` does not automatically route null to `default`

~~~java
static String defaultIsNotNull(Object value) {
    return switch (value) {
        case String text -> "string:" + text;
        default -> "other";
    };
}
~~~

With `defaultIsNotNull(null)`, the program throws `NullPointerException` on Java 21. `default` handles **non-null values** that do not match the declared patterns; it does not replace a decision on how to handle null.

If null is a valid case, write `case null`. If null is an API call error, reject it explicitly before the switch; if null is an invalid payload, you can turn it into a validation result.

### 3.3. `when` does not replace `case null`

~~~java
return switch (value) {
    case String text when text.length() > 3 -> "long text";
    case String text -> "short text";
    case null -> "missing";
    default -> "other";
};
~~~

This is **an illustrative expression snippet** that must be placed inside a method returning `String` with an appropriate `value` variable. A top-level type pattern `case String text` only matches when the selector has a non-null `String` value. The `when` guard is evaluated **after the pattern matches**.

Writing `case String text when text == null` is not a way to "catch a null selector": the outer `String` pattern does not match null, so that guard is never invoked for a null selector. A separate `case null` branch is what expresses the intended behavior.

### 3.4. Exhaustiveness over subtypes does not mean the null policy is decided

A `sealed interface` helps the compiler verify that all permitted subtypes are covered in a `switch expression`. However, **null is not a subtype**. Depending on the contract, you still need:

- `case null` when you want to return a result for a null selector; or
- explicit null rejection, for example `Objects.requireNonNull`.

Do not add `default` just to "cover all cases" if the subtype set is already closed and you want the compiler to warn you when a new subtype is added.

## 4. Practice scenario: order command processing

We define three commands in a closed set:

~~~java
sealed interface Command permits Create, Ship, Cancel {}

record Create(String id, int units) implements Command {}
record Ship(String id, String tracking) implements Command {}
record Cancel(String id, String reason) implements Command {}
~~~

For each command, the system must produce a result of type:

~~~java
enum Code { OK, INVALID }
record Result(Code code, String detail) {}
~~~

Data rules for the example:

- `Create` requires `id` to be non-null/non-blank and `units > 0`.
- `Ship` requires `id` and `tracking` to be non-null/non-blank.
- `Cancel` requires `id` and `reason` to be non-null/non-blank.
- A null `Command` selector in the **ingestion path where absence is allowed** is treated as a missing payload, returning `INVALID:missing-command`.
- A null `Command` selector in the **required internal API** is treated as an API call error, intentionally throwing `NullPointerException`.

**Note:** the three records here **intentionally have no constructor validation** to simulate unvalidated command data. Therefore, `new Create(null, -1)` can still be constructed in Java, but the handler will return a validation error. A real system might validate directly in the constructor/factory or at the boundary; what matters is clearly defining the check point.

To avoid duplicating business logic, both null policies will use **the same three handlers**:

~~~java
static boolean blank(String value) {
    return value == null || value.isBlank();
}

static Result onCreate(Create c) {
    if (blank(c.id())) return invalid("create-id");
    if (c.units() <= 0) return invalid("units");
    return ok("created:" + c.id() + ":" + c.units());
}

static Result onShip(Ship s) {
    if (blank(s.id())) return invalid("ship-id");
    if (blank(s.tracking())) return invalid("tracking");
    return ok("shipped:" + s.id() + ":" + s.tracking());
}

static Result onCancel(Cancel c) {
    if (blank(c.id())) return invalid("cancel-id");
    if (blank(c.reason())) return invalid("reason");
    return ok("cancelled:" + c.id());
}
~~~

These are **illustrative methods**. `ok` and `invalid` return a `Result` record in the complete program in section 9. `blank` uses the short-circuiting `||` operator so it does not call `isBlank()` when `value == null`.

These handlers do not handle a null command selector themselves: they are called **after the dispatcher has identified the command type**. The null policy belongs to the **dispatch boundary**, and should not be scattered unnecessarily across individual handlers.

## 5. Policy A: null is a data result to be handled

For a function receiving commands from a source that allows absent payloads:

~~~java
static Result handleNullable(Command command) {
    return switch (command) {
        case null -> invalid("missing-command");
        case Create c -> onCreate(c);
        case Ship s -> onShip(s);
        case Cancel c -> onCancel(c);
    };
}
~~~

How to read it:

1. `case null` clearly expresses the business decision: a command not provided will be **classified as missing data**.
2. The three subsequent type patterns dispatch to each record's handler.
3. `default` is not needed because `Command` is sealed with three final record subtypes; the compiler can verify that the branches for non-null subtypes are exhaustive.
4. The same `Create`, `Ship`, or `Cancel` will yield the same validation result as when going through the strict API in the next section, because both call the same three handlers.

Advantage: the function has a **typed** `Result`, rather than using an unintended NPE as a way to return a data error. Callers can translate `INVALID` into an HTTP response, CLI message, or a business state without having to catch an exception to classify it.

Limitation: null is interpreted as an **expected business input**, so a caller may fail to notice a bug if it was actually supposed to pass a command. Therefore, the method name `handleNullable` and API documentation must state the contract clearly, rather than assuming every place should use this policy.

A good comment near the null branch:

~~~java
// Boundary accepting missing requests: return a structured validation error.
// Do not apply this policy to internal APIs that require a mandatory command.
case null -> invalid("missing-command");
~~~

The comment focuses on the **reason** for choosing the branch rather than merely repeating the syntax "handle null".

## 6. Policy B: null is a violation of the API contract

For an internal function that only permits a non-null `Command`:

~~~java
static Result handleRequired(Command command) {
    java.util.Objects.requireNonNull(command, "command");

    return switch (command) {
        case Create c -> onCreate(c);
        case Ship s -> onShip(s);
        case Cancel c -> onCancel(c);
    };
}
~~~

`Objects.requireNonNull(command, "command")` throws `NullPointerException` early with an easy-to-diagnose parameter name if a caller misuses it. This is not "forgetting to handle null"; it is an **explicit null-rejection decision**.

Comparing the two calls:

~~~java
handleNullable(null); // Result(INVALID, "missing-command")
handleRequired(null); // NullPointerException: command
~~~

These are illustrative calls. If `null` is genuinely a valid missing request per the protocol, use `handleNullable`. If `null` violates an internal function's precondition, use `handleRequired`.

**Do not use a single shared `null -> ok("empty")` mechanism for both.** It turns a caller bug into a fake success state and can make downstream code think a command was processed.

### Should `IllegalArgumentException` be thrown instead of NPE?

Yes, if the API already has a convention of rejecting invalid arguments with `IllegalArgumentException`. Java does not force every method to choose `Objects.requireNonNull`; the key is to **document a consistent contract** and have tests for the null case.

`Objects.requireNonNull` fits mandatory references, whereas payload validation such as `units <= 0` is usually a different domain error. Separating the two layers makes logging and error handling more accurate.

## 7. Null inside a record is different from a null outer selector

A common mistake is adding `case null` at the top of a `switch` and believing that all nested nulls inside the object are now handled.

Example input data:

~~~java
record Customer(String name) {}
record Envelope(Customer customer, String memo) {}
~~~

Cases:

~~~java
Object a = null;
Object b = new Envelope(null, "note");
Object c = new Envelope(new Customer(null), "note");
Object d = new Envelope(new Customer("Lan"), null);
~~~

These four cases are **not the same**:

- `a`: the outer selector is null.
- `b`: the selector exists and is an `Envelope`, but the `customer` component is null.
- `c`: `customer` exists, but `Customer.name` is null.
- `d`: `customer.name` is valid, but `Envelope`'s `memo` component is null.

A `case null` on the selector applies only to `a`. It does not replace validation inside the record.

### Using record patterns with per-layer fallback branches

~~~java
static String inspect(Object raw) {
    return switch (raw) {
        case null -> "missing-selector";

        case Envelope(Customer(var name), var memo)
                when name != null && !name.isBlank()
                  && memo != null && !memo.isBlank() ->
                "ready:" + name + ":" + memo;

        case Envelope(Customer(var name), var memo) ->
                "invalid-fields";

        case Envelope(var customer, var memo) ->
                "missing-customer";

        case String text when !text.isBlank() ->
                "text:" + text;

        case String text -> "blank-text";
        default -> "other-type";
    };
}
~~~

This is a complete Java 21 method **within a scope where `Customer` and `Envelope` are declared**. The runnable version containing all types is in section 9.

Execution paths:

| Input | Selected branch | Reason |
| --- | --- | --- |
| `null` | `case null` | Outer selector is absent |
| `Envelope(Customer("Lan"), "note")` | Guarded record case | Both name and memo have content |
| `Envelope(null, "note")` | `Envelope(var customer, var memo)` | Nested pattern `Customer(...)` does not match null |
| `Envelope(Customer(null), "note")` | `invalid-fields` | Customer exists; null name makes the guard false |
| `Envelope(Customer("Lan"), null)` | `invalid-fields` | Null memo makes the guard false |
| `"hello"` | `case String text when ...` | Direct type pattern matches String |
| `"  "` | Unguarded `case String text` | Non-blank guard returns false |
| `42` | `default` | Type not handled specifically, but non-null |

**Remember case ordering:** a guarded case usually comes before a broader case of the same type. If `Envelope(var customer, var memo)` is placed before the more specific `Envelope(...)` cases, the compiler may report them as *dominated* or they will no longer be selected as intended.

### Why does `when` need a null guard?

In `Envelope(Customer(var name), var memo)`, `var name` and `var memo` only infer the static type of the components; they **can hold null values**. Therefore:

~~~java
name != null && !name.isBlank()
    && memo != null && !memo.isBlank()
~~~

is evaluated from left to right. When `name` or `memo` is null, the corresponding `isBlank()` call is not executed, avoiding an NPE.

If `name.isBlank()` were placed before `name != null`, the guard could throw an NPE during case selection.

## 8. Subtle case: a type pattern on a component can match null

Do not oversimplify and assume that "seeing `String x` in a pattern guarantees it is non-null." Distinguish these two records:

~~~java
record TypedMessage(String body) {}
record BroadMessage(Object body) {}
~~~

In Java 21:

~~~java
Object typed = new TypedMessage(null);

boolean matchesTyped =
        typed instanceof TypedMessage(String body)
        && body == null;

System.out.println(matchesTyped); // true
~~~

Here, the component of `TypedMessage` is declared with static type `String`, so the subpattern `String body` is an **unconditional pattern** for that component type. It can match even a null component.

Meanwhile:

~~~java
Object broad = new BroadMessage(null);

boolean matchesBroad =
        broad instanceof BroadMessage(String body);

System.out.println(matchesBroad); // false
~~~

The component of `BroadMessage` is declared with type `Object`. The subpattern `String body` is a **conditional type pattern**, which only matches when the component holds an actual non-null string.

**Exact comparison:**

| Match | Null input | Result |
| --- | --- | --- |
| `Object x = null; x instanceof String s` | Null outer selector | `false` |
| `TypedMessage(String body)` | Component has static type `String` but null value | Can match, `body == null` |
| `TypedMessage(var body)` | Null `String` component | Can match, `body == null` |
| `BroadMessage(String body)` | Component has static type `Object` and null value | `false` |
| `Envelope(Customer(var name), ...)` | `customer` component is null | Nested record pattern `Customer(...)` does not match |

**Practical consequence:** if you call `body.length()` inside a record pattern branch, check whether a **domain invariant** is enforced by the constructor/factory. Do not conclude a component is non-null just because the pattern writes `String body` or `var body`.

## 9. Complete Java 21 program — 31 test cases

Create the file **`IntentionalNullCasesDemo.java`** with the full content below. The program demonstrates the two null policies for commands, null at three record layers, null in type patterns, and the counterexample where `default` does not catch null.

~~~java
public class IntentionalNullCasesDemo {
    sealed interface Command permits Create, Ship, Cancel {}
    record Create(String id, int units) implements Command {}
    record Ship(String id, String tracking) implements Command {}
    record Cancel(String id, String reason) implements Command {}

    enum Code { OK, INVALID }
    record Result(Code code, String detail) {}
    record Customer(String name) {}
    record Envelope(Customer customer, String memo) {}
    record TypedMessage(String body) {}
    record BroadMessage(Object body) {}

    static Result ok(String text) {
        return new Result(Code.OK, text);
    }

    static Result invalid(String field) {
        return new Result(Code.INVALID, field);
    }

    static boolean blank(String value) {
        return value == null || value.isBlank();
    }

    static Result onCreate(Create c) {
        if (blank(c.id())) return invalid("create-id");
        if (c.units() <= 0) return invalid("units");
        return ok("created:" + c.id() + ":" + c.units());
    }

    static Result onShip(Ship s) {
        if (blank(s.id())) return invalid("ship-id");
        if (blank(s.tracking())) return invalid("tracking");
        return ok("shipped:" + s.id() + ":" + s.tracking());
    }

    static Result onCancel(Cancel c) {
        if (blank(c.id())) return invalid("cancel-id");
        if (blank(c.reason())) return invalid("reason");
        return ok("cancelled:" + c.id());
    }

    static Result handleNullable(Command command) {
        return switch (command) {
            case null -> invalid("missing-command");
            case Create c -> onCreate(c);
            case Ship s -> onShip(s);
            case Cancel c -> onCancel(c);
        };
    }

    static Result handleRequired(Command command) {
        java.util.Objects.requireNonNull(command, "command");
        return switch (command) {
            case Create c -> onCreate(c);
            case Ship s -> onShip(s);
            case Cancel c -> onCancel(c);
        };
    }

    static String inspect(Object raw) {
        return switch (raw) {
            case null -> "missing-selector";

            case Envelope(Customer(var name), var memo)
                    when name != null && !name.isBlank()
                      && memo != null && !memo.isBlank() ->
                    "ready:" + name + ":" + memo;

            case Envelope(Customer(var name), var memo) ->
                    "invalid-fields";

            case Envelope(var customer, var memo) ->
                    "missing-customer";

            case String text when !text.isBlank() ->
                    "text:" + text;

            case String text -> "blank-text";
            default -> "other-type";
        };
    }

    static String defaultIsNotNull(Object value) {
        return switch (value) {
            case String text -> "string:" + text;
            default -> "other";
        };
    }

    private static int passed = 0;

    static void check(String label, boolean condition) {
        if (!condition) throw new AssertionError(label);
        ++passed;
        System.out.println("PASS " + label);
    }

    static void verify(String label, Command command, Result expected) {
        Result nullable = handleNullable(command);
        boolean ok = nullable.equals(expected);
        if (command != null) {
            ok &= handleRequired(command).equals(expected);
        }
        check(label, ok);
    }

    static void checkInspect(
            String label, Object input, String expected) {
        check(label, inspect(input).equals(expected));
    }

    static void expectNpe(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected NPE: " + label);
        } catch (NullPointerException expected) {
            check(label, true);
        }
    }

    public static void main(String[] args) {
        verify("create-ok",
                new Create("O1", 3), ok("created:O1:3"));
        verify("create-null-id",
                new Create(null, 3), invalid("create-id"));
        verify("create-blank-id",
                new Create("  ", 3), invalid("create-id"));
        verify("create-zero",
                new Create("O1", 0), invalid("units"));
        verify("create-negative",
                new Create("O1", -1), invalid("units"));

        verify("ship-ok",
                new Ship("O1", "TR-7"),
                ok("shipped:O1:TR-7"));
        verify("ship-null-id",
                new Ship(null, "TR-7"), invalid("ship-id"));
        verify("ship-blank-id",
                new Ship(" ", "TR-7"), invalid("ship-id"));
        verify("ship-null-tracking",
                new Ship("O1", null), invalid("tracking"));
        verify("ship-blank-tracking",
                new Ship("O1", " "), invalid("tracking"));

        verify("cancel-ok",
                new Cancel("O1", "changed"),
                ok("cancelled:O1"));
        verify("cancel-null-id",
                new Cancel(null, "changed"), invalid("cancel-id"));
        verify("cancel-blank-reason",
                new Cancel("O1", " "), invalid("reason"));
        verify("cancel-null-reason",
                new Cancel("O1", null), invalid("reason"));
        verify("null-command",
                null, invalid("missing-command"));

        checkInspect("envelope-ready",
                new Envelope(new Customer("Lan"), "note"),
                "ready:Lan:note");
        checkInspect("envelope-null-customer",
                new Envelope(null, "note"),
                "missing-customer");
        checkInspect("envelope-null-name",
                new Envelope(new Customer(null), "note"),
                "invalid-fields");
        checkInspect("envelope-blank-name",
                new Envelope(new Customer("  "), "note"),
                "invalid-fields");
        checkInspect("envelope-null-memo",
                new Envelope(new Customer("Lan"), null),
                "invalid-fields");
        checkInspect("envelope-blank-memo",
                new Envelope(new Customer("Lan"), ""),
                "invalid-fields");
        checkInspect("envelope-valid-other",
                new Envelope(new Customer("Minh"), "ok"),
                "ready:Minh:ok");
        checkInspect("top-level-null",
                null, "missing-selector");
        checkInspect("string-normal",
                "hello", "text:hello");
        checkInspect("string-blank",
                "  ", "blank-text");
        checkInspect("other-type",
                42, "other-type");

        Object missing = null;
        check("instanceof-null-false",
                !(missing instanceof String s));

        Object typed = new TypedMessage(null);
        check("record-component-unconditional-null",
                typed instanceof TypedMessage(String body)
                        && body == null);

        Object broad = new BroadMessage(null);
        check("record-component-conditional-null",
                !(broad instanceof BroadMessage(String body)));

        expectNpe("required-rejects-null",
                () -> handleRequired(null));
        expectNpe("default-not-null",
                () -> defaultIsNotNull(null));

        System.out.println("ALL PASSED: " + passed);
    }
}
~~~

### Compile and run

Use **JDK 21 or later**:

~~~bash
javac --release 21 IntentionalNullCasesDemo.java
java IntentionalNullCasesDemo
~~~

**Exact output when all assertions pass:**

~~~text
PASS create-ok
PASS create-null-id
PASS create-blank-id
PASS create-zero
PASS create-negative
PASS ship-ok
PASS ship-null-id
PASS ship-blank-id
PASS ship-null-tracking
PASS ship-blank-tracking
PASS cancel-ok
PASS cancel-null-id
PASS cancel-blank-reason
PASS cancel-null-reason
PASS null-command
PASS envelope-ready
PASS envelope-null-customer
PASS envelope-null-name
PASS envelope-blank-name
PASS envelope-null-memo
PASS envelope-blank-memo
PASS envelope-valid-other
PASS top-level-null
PASS string-normal
PASS string-blank
PASS other-type
PASS instanceof-null-false
PASS record-component-unconditional-null
PASS record-component-conditional-null
PASS required-rejects-null
PASS default-not-null
ALL PASSED: 31
~~~

### Understanding the test results

**Command group:**

- `create-ok`, `ship-ok`, `cancel-ok`: valid commands produce the same `OK` result across both APIs.
- `*-null-id`, `*-blank-*`, `create-zero`, and `create-negative`: payload content validation returns `INVALID` for the specific field. For non-null commands, the test compares **`handleNullable` and `handleRequired`** to ensure business logic is not accidentally altered when changing the null policy.
- `null-command`: calls only `handleNullable(null)` because this API is designed to accept absent requests and return `INVALID:missing-command`.

**Nested record group:**

- `envelope-null-customer`: the `Envelope` record exists, but the `customer` component is null; the nested record branch does not match, so the `missing-customer` fallback is selected.
- `envelope-null-name` and `envelope-null-memo`: the nested record matches, but the guard fails; the `invalid-fields` branch handles it.
- `top-level-null`: only when the outer selector is null does execution enter `case null` of `inspect`.
- `string-normal`, `string-blank`, and `other-type`: verify that guards and type-based fallbacks do not shadow each other.

**Java semantics verification group:**

- `instanceof-null-false`: top-level `instanceof` returns false for null.
- `record-component-unconditional-null`: `TypedMessage(String body)` can match a null component.
- `record-component-conditional-null`: `BroadMessage(String body)` does not match a null component when the static component type is `Object`.
- `required-rejects-null`: `Objects.requireNonNull` proactively rejects null in the strict API.
- `default-not-null`: a pattern `switch` with `default` but without `case null` still throws `NullPointerException`.

The `check` method throws `AssertionError` if the condition is false. Therefore, `ALL PASSED: 31` appears only after every execution path produces the expected result.

**Scope note:** this is a result-handling demo, **not executing real payments or modifying real orders**. When integrating into a real system, separate validation, state checks, and I/O effects appropriately.

## 10. Before–after exercise: fixing a switch missing null without changing the contract

Suppose the old code is:

~~~java
static String classify(Object input) {
    return switch (input) {
        case String text -> "text:" + text;
        case Integer count -> "number:" + count;
        default -> "unsupported";
    };
}
~~~

This is **a syntactically standalone method**, though the example only illustrates a small piece of logic; it is not used in the main program in section 9.

New API requirement: when the request has no data, return `"missing"`. A reasonable fix:

~~~java
static String classify(Object input) {
    return switch (input) {
        case null -> "missing";
        case String text -> "text:" + text;
        case Integer count -> "number:" + count;
        default -> "unsupported";
    };
}
~~~

Changes that must be verified:

1. `classify(null)` now returns `"missing"` as required by the new contract.
2. `classify("hi")` still returns `"text:hi"`.
3. `classify(3)` still returns `"number:3"`.
4. `classify(3.5)` still returns `"unsupported"`.
5. `default` still only handles unsupported types; **it is not misused to represent an absent request**.

If the contract instead states that "`input` must be provided", you should not change it to return `"missing"`. You can keep the switch as is, place `Objects.requireNonNull(input, "input")` at the start of the method, and test that null is rejected.

This is the difference between **fixing behavior per requirements** and **hiding exceptions with a default value**.

## 11. How a null case can affect branch ordering and business errors

When adding `case null`, you must ensure existing branches still work as before. Especially with `when`:

~~~java
// Illustrative switch expression fragment:
case null -> "missing";
case String text when !text.isBlank() -> "text:" + text;
case String text -> "blank-text";
default -> "other";
~~~

- `case null` receives the null selector.
- The type pattern `String text` only receives non-null strings.
- The guard applies only after the pattern matches.
- The unguarded `String text` branch afterward receives blank strings.
- `default` receives unsupported types.

If the general `case String text -> ...` is placed **before** the `String text when ...` branch, the compiler may report the guarded branch behind it as *dominated*. That is an issue of pattern coverage scope, unrelated to whether `case null` comes first or not.

Similarly, when designing data errors:

~~~java
case null -> invalid("missing-command");
case Create c -> onCreate(c);
~~~

do not automatically change `invalid("missing-command")` to `ok("ignored")` just because null "does not need processing." Turning missing input into success can prevent the system from detecting lost commands.

## 12. Handling null at system boundaries: DTOs, domain, and exceptions

An application pipeline typically has three layers:

~~~text
External input (JSON / queue / API / CLI)
              |
              v
Parse and validate according to source contract
              |
              v
Valid domain object or data error
              |
              v
Dispatch via pattern switch / handler
              |
              v
Business result / state error / system error
~~~

**Do not confuse the layers:**

- JSON missing the `command` key is not necessarily equivalent to JSON with `"command": null`. If the protocol distinguishes them, the parser/DTO must preserve that information; once both are normalized into a single Java null value, `case null` **cannot recover the difference**.
- The field `units == 0` is not a null selector. It is numeric validation belonging to `Create`.
- `Ship(null, "TR-7")` is a command object that exists, but its payload is missing a field. `case null` on `Command` does not catch this case; `onShip` must check it.
- A domain state that disallows an operation (for example, a shipped order cannot be cancelled) should be a **different result type from a data error** if the architecture requires distinguishing them.
- A `NullPointerException` caused by a bug should not be broadly caught and turned into "missing input" unless you have proven the null actually came from the data boundary.

A clear contract comment can state:

~~~java
/**
 * Receives a parsed command from a source where the request may be absent.
 * Null is treated as INVALID:missing-command without throwing an exception.
 * Null fields inside the command are validated in the corresponding handler.
 */
static Result handleNullable(Command command) { /* ... */ }
~~~

This is a **Javadoc illustration**, not a standalone runnable method because the body is elided. The important thing is to document:

1. Does the method allow a null selector?
2. What value is null mapped to?
3. Where are null components handled?
4. Who is responsible for fixing the data and reacting to the result?

## 13. Common mistakes when "fixing null"

**Mistake 1 — believing `default` catches null.** A Java 21 pattern `switch` does not automatically enter `default` when the selector is null. Add `case null` if null is an accepted input, or reject early per the contract.

**Mistake 2 — adding `case null -> success` just to avoid NPE.** If null is an invalid payload, returning success hides the problem. Choose a meaningful result such as `INVALID` or reject explicitly.

**Mistake 3 — assuming an outer `case null` handles all nested nulls.** Selector null and component null belong to different layers. Nested records need fallbacks/guards or constructor validation.

**Mistake 4 — writing `case String s when s == null` to catch a null selector.** The `String` type pattern on the selector does not match null; the guard never runs. Use `case null`.

**Mistake 5 — thinking `var` guarantees non-null.** `var` infers the static type; a component pattern `var name` can receive null. You must have a guard or a reliable invariant.

**Mistake 6 — thinking a component pattern `String body` always excludes null.** For a record component declared with type `String`, an unconditional subpattern can match null in Java 21. Do not dereference without a data guarantee.

**Mistake 7 — reversing the null-guard order.** `name.isBlank() && name != null` can throw NPE; `name != null && !name.isBlank()` is safe thanks to short-circuiting.

**Mistake 8 — using `default` to mask subtype additions in a sealed interface.** If the command set is closed, omit `default` and handle all subtypes so the compiler helps detect schema expansion.

**Mistake 9 — confusing "no command" with "command with invalid payload."** A `null` selector belongs to the dispatch point; `new Create(null, -1)` is an existing object that needs validation in the handler/factory.

**Mistake 10 — catching all `RuntimeException`s and returning a data error.** This can hide bugs and infrastructure failures. Catch only the errors the current layer actually knows how to handle.

**Mistake 11 — changing the policy without updating tests.** When switching from rejecting null to returning `Result(INVALID, ...)`, update documentation and test cases; do not leave old callers expecting NPE only to unexpectedly receive a business result.

**Mistake 12 — using `Optional` in place of every null.** `Optional` is useful for representing certain potentially absent results, but it does not automatically solve nested record validation or input contracts; nor does it mean every parameter/field should be converted to `Optional`.

**Mistake 13 — treating logging as null handling.** Logging "request missing" while continuing to dereference the command will still cause an NPE. The null branch must have a proper terminating behavior or fallback.

## 14. Review checklist before finalizing a null case

| Question | How to verify |
| --- | --- |
| Can the selector be null according to the contract? | Read API documentation and data sources |
| If null, is it a valid state or an error? | Clearly choose return vs. exception |
| Is `case null` or `requireNonNull` used per policy? | Test the null path |
| Is `default` mistaken for null handling? | Test `switch(null)` |
| Are type patterns and record patterns in the right order? | Check for dominated cases |
| Can nested records be null? | Test missing child record |
| Can record components be null? | Test null name/field |
| Does the guard check null before dereferencing? | Test null + blank string |
| Does the `sealed switch` cover all subtypes? | Compile without `default` |
| Is an invalid payload distinct from a missing selector? | Test both scenarios separately |
| Was handler logic duplicated after refactoring? | Compare results on identical inputs |
| Are unexpected exceptions being masked? | Review broad catch blocks |
| Is the null contract documented in Javadoc? | Review call sites and API |
| Is at least one type outside the pattern set tested? | Test fallback |
| Was behavior tested after adding a subtype? | Build/compile and regression |

### Practice exercises

1. **Change the policy:** modify `handleNullable` to reject null using `Objects.requireNonNull`. Adjust `null-command` into an exception-checking test case and explain why this is a contract change.
2. **Reject data at the constructor:** add compact constructors to `Create`, `Ship`, and `Cancel`. Existing null-component test cases will need to change from checking `Result(INVALID)` to checking for an exception upon object creation. Compare the two validation strategies.
3. **Add a command:** add subtype `Refund(String id, long cents)` to `Command.permits`. Recompile and identify which branches need to be added to both `switch` statements to keep them exhaustive. Define the null policy separately.
4. **Add a nested record:** extend `Envelope` with `Customer.email`. Write a null-safe guard for email and test missing customer, customer missing name, null email, and blank email.
5. **Distinguish input nulls:** create a `MissingRequest` class or a separate result type to distinguish "no request" from "request with null payload", instead of turning both into a null selector.
6. **Build your own test matrix:** for any `switch`, build a matrix of null selector, valid subtype, subtype with null component, unsupported type, and false guard. Only consider the refactor complete when every row exhibits the expected behavior.

**Remember:** **Adding `case null` intentionally** is a decision about **API contract and domain semantics**, not just adding a branch to avoid `NullPointerException`. A null selector in a pattern switch differs from null in a record component; `default` differs from `case null`; a nullable API differs from an API with mandatory input. Choose a clear policy, preserve exhaustiveness on sealed types, protect components with guards/invariants, and use tests to prove the behavior changed as required.
