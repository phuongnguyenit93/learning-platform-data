# Ignoring Changes When a New Subtype Appears

**Topic:** Common pitfalls in Java Core Pattern Matching. The main examples use **Java 21 or later** with sealed interfaces, record patterns, and pattern matching for switch. This article focuses on a dangerous maintenance pitfall: **adding a new subtype while existing handling branches still compile and silently ignore the new data**.

## 1. The problem: the system extends data types, old logic stays unchanged

Suppose an event-processing application has two types: **Added** and **Removed**. Initially, the code handles both and has a general branch for unrecognized cases:

~~~java
// Illustration: Event, Added, Removed are declared elsewhere.
static String legacy(Event event) {
    if (event instanceof Added a) {
        return "ADDED:" + a.id();
    } else if (event instanceof Removed r) {
        return "REMOVED:" + r.id();
    }
    return "IGNORED";
}
~~~

After some time, the domain adds **Updated**. A developer adds the new type without updating the `legacy` method. When encountering `Updated`, both `instanceof` conditions are false and the method returns **IGNORED**.

This is a common pitfall because:

1. **No compile error**: an `if-else` chain has no mechanism to enforce covering all subtypes.
2. **No exception**: the final branch returns a seemingly valid string.
3. **New data can be skipped**: downstream does not realize that an update occurred.
4. **Old tests still pass**: if the test suite only sends `Added`/`Removed`, adding `Updated` goes undetected.
5. **A switch `default` can hide the same issue**: writing a `switch` with `default` does not guarantee business-logic correctness.

**Key takeaway:** "Having a fallback path" does not mean "having designed behavior for new subtypes." Unrecognized cases must be distinguished from cases intentionally ignored by business rules.

## 2. Recognizing patterns that easily lose change signals

### 2.1. `if-else` chain + broad `else` branch

~~~java
if (event instanceof Added a) {
    processAdded(a);
} else if (event instanceof Removed r) {
    processRemoved(r);
} else {
    // Do nothing.
}
~~~

This is a structure that **can silently ignore a new subtype**. If `Updated` appears, the `else` branch emits no warning and performs no corresponding handling. In data ingestion, state synchronization, or payment systems, such silent skipping can cause hard-to-detect consequences.

Not every `else` is wrong. If the business rules define that other types **truly require no action**, a fallback is an intentional choice. The issue is **undocumented and untested silence**.

### 2.2. Switch expression with `default` covering all remaining types

~~~java
// Standalone illustrative example; do not copy differently named methods into the same class.
static String withDefault(Event event) {
    return switch (event) {
        case Added(var id) -> "ADDED:" + id;
        case Removed(var id) -> "REMOVED:" + id;
        case null -> "IGNORED";
        default -> "IGNORED";
    };
}
~~~

**default** makes the switch expression syntactically exhaustive: any value not handled by prior cases goes to `default`. When `Updated` is added, the method still compiles, but `Updated` is mapped to `IGNORED`. The advantage of **the compiler forcing you to add a branch when the sealed hierarchy changes** is gone.

A **`default` that throws an exception** is better for runtime detection, yet still produces no compile error when a subtype is added:

~~~java
// Illustrates a fail-fast fallback only; does not replace exhaustiveness.
default -> throw new IllegalStateException("Unexpected event: " + event);
~~~

It is appropriate when the parent type is open or must handle inputs outside the known scope, but it does not replace a domain review when adding a subtype.

### 2.3. Overly broad type pattern

~~~java
return switch (event) {
    case Added a -> "added";
    case Event e -> "other event";
};
~~~

With a selector of type `Event`, `case Event e` can cover all remaining subtypes. A new subtype will automatically receive the **other event** handling, even when it needs dedicated logic. This pattern is a valid general branch when business logic wants it, but if the goal is to examine each subtype individually, it can mask missing cases just like `default`.

## 3. How to reduce risk: sealed hierarchy + exhaustive switch without `default`

Java has supported **sealed classes/interfaces** since Java 17. A sealed type declares the list of types permitted to directly extend or implement it:

~~~java
sealed interface Event permits Added, Removed, Updated {}

record Added(String id) implements Event {}
record Removed(String id) implements Event {}
record Updated(String id, int version) implements Event {}
~~~

The three records are the directly permitted subtypes. Records are implicitly `final`, so there are no further subclasses beneath these branches.

For a selector of type **Event**, a switch expression with branches covering `Added`, `Removed`, and `Updated` can be written **without `default`**:

~~~java
static String complete(Event event) {
    return switch (event) {
        case Added(var id) -> "ADDED:" + id;
        case Removed(var id) -> "REMOVED:" + id;
        case Updated(var id, var version) ->
                "UPDATED:" + id + "@v" + version;
        case null -> "IGNORED";
    };
}
~~~

This has two benefits:

- Each subtype has an **explicit business decision**: `Updated` data cannot accidentally fall into a catch-all branch.
- If a **Restored** subtype is later added to the `permits` list and the code is recompiled, any switch expression missing `Restored` will be reported as **not exhaustive**. The compiler points directly to the places that need review.

**Important condition:** the compiler can only evaluate based on the type information it sees at compile time. If the selector is `Object` or an extensible subtype (such as via **non-sealed**), you must analyze the corresponding type domain; you cannot assume every switch can omit `default`.

### Why does `case null` still appear?

In this example, the final branch of `legacy` returns `IGNORED` when the input is `null` (because `instanceof` is always false for `null`). When migrating to a pattern switch, having cases for all subtypes **does not guarantee `null` is handled the same way as before**. Without `case null`, switching on `null` can throw `NullPointerException`.

Because we want to **preserve the old behavior on `null`**, the `complete` example uses **`case null -> "IGNORED"`**. In a real system, this can be replaced by explicitly rejecting `null`, but that is an API contract decision, not a side effect to let happen silently during refactoring.

## 4. Complete runnable example on Java 21

The following program intentionally places **three approaches side by side**:

- **legacy:** an `if-else` chain that only knows `Added` and `Removed`.
- **catchAll:** a `switch` with `default`, also only knowing the two old subtypes.
- **exhaustive:** a `switch` without `default` that explicitly handles `Updated` as well.

Save the code in **NewSubtypeDemo.java**:

~~~java
public class NewSubtypeDemo {
    sealed interface Event permits Added, Removed, Updated {}

    record Added(String id) implements Event {}
    record Removed(String id) implements Event {}
    record Updated(String id, int version) implements Event {}

    static String legacy(Event event) {
        if (event instanceof Added a) {
            return "ADDED:" + a.id();
        } else if (event instanceof Removed r) {
            return "REMOVED:" + r.id();
        }
        return "IGNORED";
    }

    static String catchAll(Event event) {
        return switch (event) {
            case Added(var id) -> "ADDED:" + id;
            case Removed(var id) -> "REMOVED:" + id;
            case null -> "IGNORED";
            default -> "IGNORED";
        };
    }

    static String exhaustive(Event event) {
        return switch (event) {
            case Added(var id) -> "ADDED:" + id;
            case Removed(var id) -> "REMOVED:" + id;
            case Updated(var id, var version) ->
                    "UPDATED:" + id + "@v" + version;
            case null -> "IGNORED";
        };
    }

    public static void main(String[] args) {
        Event[] events = {
            new Added("A-1"),
            new Removed("A-2"),
            new Updated("A-3", 2),
            null
        };

        for (Event event : events) {
            System.out.println(legacy(event) + " | "
                + catchAll(event) + " | " + exhaustive(event));
        }
    }
}
~~~

Compile and run:

~~~bash
javac NewSubtypeDemo.java
java NewSubtypeDemo
~~~

Exact output:

~~~text
ADDED:A-1 | ADDED:A-1 | ADDED:A-1
REMOVED:A-2 | REMOVED:A-2 | REMOVED:A-2
IGNORED | IGNORED | UPDATED:A-3@v2
IGNORED | IGNORED | IGNORED
~~~

**Reading the output:**

1. For `Added` and `Removed`, all three approaches return the right result.
2. For **Updated**, both old approaches return `IGNORED`, whereas the exhaustive approach returns **UPDATED:A-3@v2**.
3. For `null`, all three return `IGNORED` because they were explicitly designed to preserve the old contract.
4. The absence of exceptions in the two old approaches **does not prove correctness**. It is precisely why new bugs easily slip past testing if tests for `Updated` are missing.

For important domain data, an `IGNORED` result should be a named and tested business decision. Do not use it as a "harmless default value" when you do not yet know what a new subtype means.

## 5. Verifying whether the compiler detects a missing subtype

Consider a sealed design with three subtypes:

~~~java
sealed interface Signal permits Opened, Closed, Retried {}
record Opened() implements Signal {}
record Closed() implements Signal {}
record Retried(int count) implements Signal {}
~~~

If you write a switch expression that only handles the first two subtypes, the following **does not compile**:

~~~java
// Negative example; not part of the runnable program in section 4.
static String missing(Signal signal) {
    return switch (signal) {
        case Opened o -> "opened";
        case Closed c -> "closed";
    };
}
~~~

The compiler may report:

~~~text
the switch expression does not cover all possible input values
~~~

The reason is that **Retried** can appear without any matching case. The fix should not be to quickly add `default`; decide the proper business behavior when `Retried` appears, for example:

~~~java
case Retried(var count) -> "retried " + count;
~~~

When using a sealed hierarchy and a switch expression without `default`, **adding a new subtype and recompiling** is a particularly useful test. It confirms that consumption points needing updates are clearly reported at compile time.

### Caution: having a case for a subtype does not guarantee covering all of that subtype

Still with `Signal`, this snippet can also be missing a branch:

~~~java
// Negative example: count = 0 does not match the Retried branch.
static String guarded(Signal signal) {
    return switch (signal) {
        case Opened o -> "opened";
        case Closed c -> "closed";
        case Retried(int count) when count > 0 -> "retried";
    };
}
~~~

**when** narrows the case condition. If `Retried(0)` or `Retried(-1)` occurs, no branch handles it. To be exhaustive, add an unguarded case for the remainder:

~~~java
case Retried(var count) -> "invalid retry count";
~~~

Exhaustiveness analysis does not infer arbitrary business predicates as true/false to fill gaps. A guarded case is normally not considered to cover the entire subtype, because the guard can be false.

## 6. Enums face the same kind of bug when new values are added

Suppose a state is modeled as an enum:

~~~java
enum Status { NEW, SENT }
~~~

A switch expression without `default` that includes all enum constants can be exhaustive:

~~~java
static String label(Status status) {
    return switch (status) {
        case NEW -> "new";
        case SENT -> "sent";
    };
}
~~~

If **ARCHIVED** is added later, recompiling this method against the updated enum will detect the missing case. Conversely, if it was originally written as:

~~~java
return switch (status) {
    case NEW -> "new";
    default -> "other";
};
~~~

then `ARCHIVED` automatically goes into **other**. This might be right if "all states except `NEW`" truly share the same handling; but if `ARCHIVED` needs dedicated business logic, `default` has erased the signal to update.

**Review rule:** For enums with a controlled set of values where each constant carries distinct meaning, prefer explicit cases. Only put `default` if a common policy for all other values is a documented decision, not out of worry about "what if a new state is added."

## 7. When does exhaustive switch really help and when does it not?

| Data model | Compiler support | What to consider |
| --- | --- | --- |
| **Sealed interface** with `record`/`final` subtypes | Can prove all subtypes are covered | Avoid `default` hiding new subtypes when each kind needs review |
| **Enum** | Can prove all constants are covered | Do not let new constants fall into an unintended general branch |
| **Sealed with a `non-sealed` branch** | A type pattern for the open branch can cover all descendants | The compiler cannot require listing every descendant added later |
| **Open parent type (`Object`/plain interface)** | No closed list of subtypes from the parent type alone | Need a general branch or a reject/delegate strategy |
| **`if-else` with `instanceof`** | No exhaustiveness obligation equivalent to switch expression | Test all subtypes and warn on unknown types |
| **`switch` with `default`/general case** | Syntactically exhaustive, but multiple subtypes share the fallback | Clarify whether fallback is intended behavior or hides missing branches |

A sealed interface declared **non-sealed** on a child branch allows external extension. When a `switch` uses a type pattern for that `non-sealed` branch, the compiler can consider the branch fully covered; however, new descendants will **not** be required to have separate cases. If the system requires a handling decision for every new kind, consider closing the branch or adjusting the API boundary.

With an open parent type like `Object`, you cannot just list a few cases and expect the compiler to know every subtype that might appear. There, an **observable fail-fast** fallback is usually better than silently ignoring.

## 8. Limitations of exhaustive switch: what can still slip through?

### 8.1. Exhaustiveness does not mean business correctness

The compiler checks that **a handling path exists** for every type/pattern form. It does not know whether returning `"IGNORED"` for `Updated` matches application requirements. Writing an explicit case like:

~~~java
case Updated(var id, var version) -> "IGNORED";
~~~

is still exhaustive, yet may be wrong from a business perspective. Therefore, review requirements and test behavior, rather than relying only on compilation results.

### 8.2. `default` removes the signal when subtypes expand

The compiler does not report a missing branch when a `default` already covers the new subtype. Even if `default` throws an exception and surfaces the bug at runtime, the code still compiles and needs tests or logs/alerts to detect the issue in operations.

### 8.3. `null` is a separate dimension

A sealed hierarchy describes valid subtypes; **it does not turn `null` into a subtype**. With a pattern switch, if a `null` input is not handled by an appropriate `case null`, it can throw `NullPointerException`. A regular `default` is not a substitute for `case null`.

When refactoring from an `instanceof` chain, check the old `null` behavior. You can choose to reject `null` (e.g., `Objects.requireNonNull`) or use `case null` to preserve behavior, but make sure any change is intentional.

### 8.4. Nested record patterns can miss part of a subtype

A case of the form **`Outer(Inner(var value))`** does not match when the `Inner` component is `null`. Even though `Outer` appears in the switch, there may still be an `Outer` with a `null` component left unhandled. In a switch expression, you need a pattern covering the remainder, such as **`case Outer(var inner)`** if appropriate for the record and business contract.

### 8.5. Unsynchronized binary changes

Exhaustiveness is analyzed at **compile time** based on the classes present. If a library changes its hierarchy after a consumer has been compiled and components are deployed out of sync, a `switch` once considered exhaustive may encounter a subtype that older bytecode does not handle. With a pattern switch, such a no-matching-branch situation can lead to **`MatchException`**.

Do not assume "no `default`" automatically protects against all binary changes at runtime. Recompile, run regression tests, and deploy dependent components consistently.

## 9. How to detect missed changes in a real project

A practical plan when adding a new subtype:

1. **Identify all usages of the parent type:** find `switch`, `instanceof`, dispatch methods, serializers, mappers, validators, and tests that handle this hierarchy.
2. **Distinguish each consumer:** parsers, audit logs, notifications, and state machines may need different reactions to the new subtype. Do not infer from one consumer that all of them ignore it.
3. **Leverage `sealed` and `switch` without `default` where appropriate:** the compiler will point out places missing coverage on recompilation.
4. **Search for catch-all branches:** inspect `default`, overly broad parent-type cases, `else`, catch-all visitors, and error-swallowing loggers. They can mask new subtypes.
5. **Finalize business behavior:** for each consumer, decide how to handle the new subtype: transform, reject, record, intentionally ignore, or raise an alert.
6. **Write tests for the new subtype:** do not only test that the object can be constructed, also verify output and side effects in key consumers.
7. **Test error paths:** `null`, missing components, false guards, invalid data, and incompatible versions.
8. **Monitor in operations:** if a fallback is necessary, have clear logs/metrics/alerts and error behavior, avoiding silent no-ops in critical paths.
9. **Recompile and deploy consistently:** check modules that depend on the subtype list, especially when the system uses multiple artifacts/binaries at different versions.

### Testing with a small example

A regression test for the program in section 4 can assert that `Updated` is handled properly:

~~~java
// Illustrative test snippet, within the context of the NewSubtypeDemo class.
String actual = exhaustive(new Updated("A-3", 2));
if (!actual.equals("UPDATED:A-3@v2")) {
    throw new AssertionError("Updated must be processed");
}
~~~

This test will fail if someone accidentally changes the `Updated` branch to `IGNORED`. In a project with a framework like JUnit, you can use `assertEquals`; no framework is needed to understand the principle.

You can also add **completeness** tests at the consumer layer or verify the subtype list depending on the design, but tests do not replace the compiler: use both **compile-time exhaustiveness checks** and **runtime behavior assertions**.

## 10. How to handle cases where ignoring unsupported subtypes is genuinely allowed

Some systems need to receive extensible messages from external sources and **cannot know every type in advance**. In that case, conditional ignoring is not necessarily a bug, but must be clearly specified:

- State the **version support contract**: which types are processed, and which are ignored or rejected.
- Provide **observability**: unknown type notifications, ignore counts, correlation IDs, and appropriate metrics (avoid logging sensitive data).
- Separate **unsupported** branches from malformed data errors. An unknown subtype is different from a supported subtype with invalid content.
- Choose fail-fast or ignore based on criticality. Events affecting money or state should not disappear silently.
- Add tests proving the fallback applies only to **permitted** cases, without masking subtypes within the mandatory contract.

For example, with an open parent type, a final branch that throws an exception with a clear message is usually safer than returning `null` or an empty string. However, **error handling design** also depends on whether there are retries, dead-letter queues, rollbacks, or compensating mechanisms; no single fallback fits every system.

## 11. Common pitfalls and quick prevention

| Pitfall | Consequence | Prevention |
| --- | --- | --- |
| Adding a subtype without updating `instanceof` chains | New subtype hits `else` or is ignored | Find all consumers, add tests for the new subtype |
| Always writing `default` in a sealed `switch` | Compiler does not warn when a subtype is added | Omit `default` when explicit branches and a closed type domain are needed |
| `default` returning `null`/empty/`IGNORED` | Data loss with no error signal | Only ignore when the contract allows; log/metric if needed |
| Assuming a case containing the subtype is enough | Guards or `null` nested records leave gaps | Check the actual matched domain, add covering cases |
| Using an overly broad parent-type case | Automatically lumps new subtypes into one shared behavior | Use specific cases or organize the hierarchy more clearly |
| Forgetting `null` handling when migrating from `if-else` | Behavior changes to `NullPointerException` | State the `null` contract clearly, add `case null` when needed |
| Relying solely on the compiler to prove business logic | `switch` is exhaustive but results are still wrong | Have assertions/tests on outputs and side effects |
| Not recompiling consumers | Old binaries do not recognize the new subtype | Build/test/deploy dependencies consistently |
| Keeping a `non-sealed` branch while expecting compiler warnings for all descendants | Static analysis does not know all future types | Design a more closed domain or define fallback/tests |

## 12. Review checklist when adding a subtype

Before merging a change that adds a new subtype, you can ask in turn:

- [ ] Is this hierarchy sealed, enum, or open? Where did the list of subtypes/values change?
- [ ] Have `switch` statements/expressions without `default` been recompiled and all exhaustiveness errors fixed?
- [ ] Does any `else`/`default`/parent-type case automatically accept the new subtype without business review?
- [ ] If there are guards or nested record patterns, are any values left unhandled?
- [ ] Are there clear rules for `null` selectors and `null` components?
- [ ] Does every key consumer have tests for the new subtype, its output, and its side effects?
- [ ] Is there a plan for binary compatibility and module deployment order?
- [ ] If the new subtype is intentionally ignored, is that clearly documented, observable, and tested?

**Conclusion:** When the set of subtypes expands, **the biggest risk is not a compile error, but having no error at all while new behavior is ignored**. A sealed hierarchy combined with an exhaustive `switch` without `default` lets the compiler turn missing branches into early errors; tests and business reviews ensure the branches have the right content. Only use `else`, `default`, or a general case when handling the remainder is an intentional decision, not a gap left by forgetting to update.