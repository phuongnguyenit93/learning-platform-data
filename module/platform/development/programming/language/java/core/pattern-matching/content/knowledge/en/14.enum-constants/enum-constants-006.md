# Comparing `enum switch` with Lookup `Map` in Java

## 1. Two Ways to Convert an Enum into a Result

When a variable has an `enum` type, we often need to convert its state into a display label, response code, access permission, or action. Two very common options are:

- **`switch` on enum:** directly describes the logic for each enum constant inside a control structure.
- **`Map<Enum, Value>`:** separates the mapping information into data consisting of enum keys and corresponding values; for enum keys, `EnumMap` should be considered.

As a simplified example, assume we already have `enum TaskState { NEW, RUNNING, DONE, FAILED }`.

**Using a `switch` expression:**

```java
static String labelBySwitch(TaskState state) {
    return switch (state) {
        case NEW -> "New";
        case RUNNING -> "Running";
        case DONE -> "Done";
        case FAILED -> "Failed";
    };
}
```

**Using `EnumMap`:**

```java
EnumMap<TaskState, String> labels = new EnumMap<>(TaskState.class);
labels.put(TaskState.NEW, "New");
labels.put(TaskState.RUNNING, "Running");
labels.put(TaskState.DONE, "Done");
labels.put(TaskState.FAILED, "Failed");

String label = labels.get(TaskState.DONE); // "Done"
```

The snippets above are **illustrative code in a context where `TaskState` is already defined**; a standalone runnable program is provided in Section 7.

If the input value is `DONE`, both approaches return `"Done"`. However, they differ significantly in **exhaustiveness checking, handling of missing keys, mutability of the lookup table, and clarity of logic**.

### Is `case NEW` a type pattern?

**No.** In `switch (state)` with a selector of type `TaskState`, `case NEW` is an **enum constant label**; it does not declare a pattern variable like `case String text` or `case Point(int x, int y)`. This lesson belongs to the Java Core Pattern Matching track because when designing modern `switch` constructs, you need to distinguish **constant labels** from **type/record patterns** and understand how the compiler checks exhaustiveness.

Since Java 14, `switch` expressions have been a standard feature. The Java 21 code in this lesson uses the common `case ... -> ...` form; no preview flags are needed.

## 2. The Most Important Difference: Compile-Time Exhaustiveness Checking

### `switch` expressions have exhaustiveness checking

Given the enum:

```java
enum TaskState {
    NEW, RUNNING, DONE, FAILED
}
```

If a `switch` expression lists all four constants, the compiler knows that every **non-`null`** enum value has a matching case:

```java
return switch (state) {
    case NEW -> "New";
    case RUNNING -> "Running";
    case DONE -> "Done";
    case FAILED -> "Failed";
};
```

Now suppose you add the constant `CANCELLED` to `TaskState` and **recompile** the program without updating the `switch`. The expression above will cause a compile error because the `CANCELLED` branch is missing.

This is a major advantage when an enum state has business meaning that must be handled explicitly: **the compiler helps catch code paths that have not been written yet**.

If you add:

```java
default -> "Other";
```

then the `switch` expression will no longer report `CANCELLED` as missing just because the enum changed, because `default` absorbs the remaining constants. `default` is not wrong, but it reduces the compiler's ability to force the programmer to review the behavior when a new state is added.

**Distinguish statement from expression:** a **traditional `switch` statement** can be non-exhaustive, whereas a **`switch` expression** requires exhaustiveness. Therefore, the advice "an enum switch always catches every state" is too broad; the compiler benefit described above is clearest with a **switch expression without `default`**.

### `EnumMap` does not automatically detect missing keys at compile time

An `EnumMap<TaskState, String>` might only contain:

```java
EnumMap<TaskState, String> labels = new EnumMap<>(TaskState.class);
labels.put(TaskState.NEW, "New");
labels.put(TaskState.DONE, "Done");
```

The code above is **valid** even though `RUNNING` and `FAILED` are not mapped. Calling `labels.get(TaskState.FAILED)` returns `null`, and the compiler does not warn you that you forgot `FAILED`.

If `CANCELLED` is added later, the compiler also **does not require** you to update `EnumMap`. A `Map` is a **data structure**, not a control structure with exhaustiveness rules like a `switch` expression.

To achieve a similar level of protection, you need to **manually check for complete keys** at initialization time or in tests. For example, use `EnumSet.allOf(TaskState.class)` to get all constants and subtract the map's `keySet()`.

## 3. How Does `EnumMap` Differ from `HashMap` When Keys Are Enums?

If all keys belong to a single enum type, `EnumMap<K extends Enum<K>, V>` is specifically designed for this situation:

| Aspect | `EnumMap<TaskState, V>` | `HashMap<TaskState, V>` |
| --- | --- | --- |
| Key type | Keys of a specific enum type | Accepts any key type matching parameter `K` |
| Data organization | Specialized structure tied to enum constants | Hash table |
| Key iteration order | In **enum declaration order** | No guaranteed iteration order |
| Memory usage | Usually compact for a finite set of enum keys | Has hash structure overhead |
| Key access | Designed for efficient lookup, typically constant time | Typically average constant time |
| `null` key | Does not allow inserting via `put(null, ...)` | Allows one `null` key |
| `null` value | Allows storing `null` values | Allows storing `null` values |

`EnumMap` can be instantiated even when it has no entries yet:

```java
EnumMap<TaskState, String> labels =
        new EnumMap<>(TaskState.class);
```

Passing `TaskState.class` specifies the enum type of the keys. When using a constructor that takes a `Map`, the key type must be inferable; constructing from an empty map without sufficient type information can fail depending on the constructor and data. The clearest approach is to pass the enum class.

**Do not conclude that "`EnumMap` is always faster than `switch`".** A `switch` can be optimized by the compiler/JVM in various ways; `EnumMap` also performs lookups efficiently. Actual performance depends on the JDK, the size of the state set, usage patterns, JIT optimizations, and the nature of the work. When speed truly matters, benchmark the actual application flow rather than relying on a slogan.

## 4. When to Choose `switch` vs. `EnumMap`?

| Situation | Usually Preferred | Why |
| --- | --- | --- |
| Each state has **different logic** | `switch` | Easy-to-read control flow; supports blocks and `yield` |
| Must recognize **every enum constant at build time** | `switch` expression, without `default` | Compiler reports missing cases when a constant is added and recompiled |
| Enum is only mapped to **simple data values** | `EnumMap` | Clear data table; reduces repetitive boilerplate across places |
| Need to add/remove/modify mappings **at runtime** | Controlled `EnumMap` | Values corresponding to defined enums can be updated |
| Only a subset of states has mappings | `EnumMap` | An **intentionally incomplete** map can express a subset |
| Need multiple handlers looked up by state | `EnumMap<State, Function<...>>` | Separates dispatch data from implementation |
| Do not want to miss values when adding an enum constant | `switch` or `EnumMap` with validator/tests | Avoid using `getOrDefault` to silently hide missing-key errors |
| Performance optimization goal | Measure with a benchmark | No absolute answer based on syntax alone |

These are **design guidelines**, not mandatory language rules. For example, if each enum constant only returns a label, a `switch` can still be very clear; with many different mappings, `EnumMap` may be easier to maintain.

## 5. Missing Values, Fallbacks, and `null`

### Missing keys in a map

```java
EnumMap<TaskState, String> labels =
        new EnumMap<>(TaskState.class);
labels.put(TaskState.NEW, "New");

String a = labels.get(TaskState.DONE); // null
String b = labels.getOrDefault(TaskState.DONE, "UNKNOWN");
// b = "UNKNOWN"
```

`getOrDefault` only uses the fallback value if **there is no mapping for the key**. If the map has an **existing mapping whose value is `null`**, `getOrDefault` still returns `null`. This is an important distinction because `EnumMap` allows storing `null` values.

You can distinguish them with:

```java
if (labels.containsKey(TaskState.DONE)) {
    // Mapping exists (the value may be null).
} else {
    // No mapping exists at all.
}
```

If every state must have a non-`null` label, **check for complete keys and reject `null` values** when building the table or when reading. Do not assume that `get() == null` always has only one cause.

### `null` selector in `switch`

In Java 21, `null` can be handled explicitly:

```java
return switch (state) {
    case null -> "No state";
    case NEW -> "New";
    case RUNNING -> "Running";
    case DONE -> "Done";
    case FAILED -> "Failed";
};
```

If `case null` is omitted, a `switch` on an enum with a `null` selector normally throws `NullPointerException`; a plain `default` is not an equivalent substitute for `case null`.

### `null` key in `EnumMap`

`EnumMap.put(null, "x")` throws `NullPointerException`: you cannot insert an entry with a `null` key. For `get(null)`, the map finds no valid enum key and returns `null`. Therefore, if you want both the lookup method and the switch method to return `"No state"` for a null input, you need to check `state == null` **before** calling `get`.

The two APIs behave differently, and handling them uniformly is a program design decision, not an automatic default from the enum.

## 6. Preventing Missing States with `EnumSet` and an Unmodifiable Table

If a map must map **every** state, build and validate the table in one place:

```java
static Map<TaskState, String> buildLabels() {
    EnumMap<TaskState, String> result =
            new EnumMap<>(TaskState.class);

    result.put(TaskState.NEW, "New");
    result.put(TaskState.RUNNING, "Running");
    result.put(TaskState.DONE, "Done");
    result.put(TaskState.FAILED, "Failed");

    EnumSet<TaskState> missing = EnumSet.allOf(TaskState.class);
    missing.removeAll(result.keySet());

    if (!missing.isEmpty()) {
        throw new IllegalStateException("Missing states: " + missing);
    }
    return Collections.unmodifiableMap(result);
}
```

This is an **illustrative method** requiring imports for `Map`, `EnumMap`, `EnumSet`, and `Collections`. The full version is included in the program in Section 7.

How the check works:

1. `EnumSet.allOf(TaskState.class)` creates a set containing **all currently defined enum constants**.
2. `removeAll(result.keySet())` removes the constants that have already been mapped.
3. If any elements remain, those are the states with **missing keys**.
4. `Collections.unmodifiableMap(result)` returns a view that disallows modification through the exposed map variable. In the example, `result` is a local variable that does not escape through a mutable reference, so this view fits the read-only goal.

This is a **runtime check**, typically executed during class initialization, **not exhaustiveness proven by the compiler**. If an enum constant is added and forgotten in the map, the program can throw an error at initialization instead of silently producing a `null` label.

**Value validation:** a key check is not enough if `null` is allowed as a value. In a real-world table, validate each mapping with `Objects.requireNonNull(...)` or enforce a policy that rejects null values. The complete program uses fixed non-`null` strings.

For long mappings that are likely to change, writing a unit test that compares `EnumSet.allOf(...)` with `map.keySet()` is also useful. Do not only test a few familiar constants.

## 7. Complete Java 21 Program: Same Result via Two Approaches

Create the file **`EnumSwitchVsLookup.java`**:

```java
import java.util.Collections;
import java.util.EnumMap;
import java.util.EnumSet;
import java.util.Map;

public class EnumSwitchVsLookup {
    enum TaskState { NEW, RUNNING, DONE, FAILED }

    static String labelBySwitch(TaskState state) {
        return switch (state) {
            case null -> "No state";
            case NEW -> "New";
            case RUNNING -> "Running";
            case DONE -> "Done";
            case FAILED -> "Failed";
        };
    }

    private static Map<TaskState, String> buildLabels() {
        EnumMap<TaskState, String> result =
                new EnumMap<>(TaskState.class);

        result.put(TaskState.NEW, "New");
        result.put(TaskState.RUNNING, "Running");
        result.put(TaskState.DONE, "Done");
        result.put(TaskState.FAILED, "Failed");

        EnumSet<TaskState> missing =
                EnumSet.allOf(TaskState.class);
        missing.removeAll(result.keySet());

        if (!missing.isEmpty()) {
            throw new IllegalStateException("Missing states: " + missing);
        }

        return Collections.unmodifiableMap(result);
    }

    private static final Map<TaskState, String> LABELS = buildLabels();

    static String labelByMap(TaskState state) {
        if (state == null) {
            return "No state";
        }
        String label = LABELS.get(state);
        if (label == null) {
            throw new IllegalStateException("No label for " + state);
        }
        return label;
    }

    public static void main(String[] args) {
        for (TaskState state : TaskState.values()) {
            System.out.println(state + " -> switch="
                    + labelBySwitch(state)
                    + ", map=" + labelByMap(state));
        }

        System.out.println("null -> switch="
                + labelBySwitch(null)
                + ", map=" + labelByMap(null));

        EnumMap<TaskState, String> incomplete =
                new EnumMap<>(TaskState.class);
        incomplete.put(TaskState.NEW, "New");

        System.out.println("missing DONE = "
                + incomplete.get(TaskState.DONE));

        System.out.println("default DONE = "
                + incomplete.getOrDefault(TaskState.DONE, "UNKNOWN"));
    }
}
```

Compile and run with **JDK 21 or later** using Java 21 source level:

```bash
javac --release 21 EnumSwitchVsLookup.java
java EnumSwitchVsLookup
```

**Exact stdout:**

```text
NEW -> switch=New, map=New
RUNNING -> switch=Running, map=Running
DONE -> switch=Done, map=Done
FAILED -> switch=Failed, map=Failed
null -> switch=No state, map=No state
missing DONE = null
default DONE = UNKNOWN
```

Explanation:

- The four iterations of `TaskState.values()` visit the enum constants in declaration order; the outputs of both approaches match for the complete table.
- `labelBySwitch(null)` enters `case null`; `labelByMap(null)` has a guard at the start of the method. Both return `No state`.
- `incomplete` only has the key `NEW`. `get(DONE)` returns `null` without a compile error.
- `getOrDefault(DONE, "UNKNOWN")` returns the fallback value because the key `DONE` is not present in `incomplete`.
- `buildLabels()` includes an enum completeness check and returns an unmodifiable view, so the main table `LABELS` cannot be mutated through code that uses this variable.

The program demonstrates that both approaches can produce the **same functional output**, while their compiler guarantees and ways of detecting missing mappings are not the same.

## 8. What If Mapping to Actions Instead of Strings?

Not every state only needs to return a label. There are cases where you want to select a **handler function** based on the enum.

With `switch`, write the logic directly:

```java
enum Operation { DOUBLE, TRIPLE, NEGATE }

static int calculate(Operation op, int input) {
    return switch (op) {
        case DOUBLE -> input * 2;
        case TRIPLE -> input * 3;
        case NEGATE -> -input;
    };
}
```

This is an **illustrative snippet inside a class**.

With a map, you can store functions in an `EnumMap`:

```java
EnumMap<Operation, java.util.function.IntUnaryOperator> handlers =
        new EnumMap<>(Operation.class);

handlers.put(Operation.DOUBLE, n -> n * 2);
handlers.put(Operation.TRIPLE, n -> n * 3);
handlers.put(Operation.NEGATE, n -> -n);

int result = handlers.get(Operation.TRIPLE).applyAsInt(4);
// result = 12
```

Advantage of a handler map: execution strategies can be configured/swapped via data stored in the map, separating dispatch from action. However:

- You must ensure a handler exists for the state being processed; if `get(op)` returns `null` and you still call `applyAsInt`, a `NullPointerException` will be thrown.
- You should check handler types/contracts and thread-safety when mutating a shared map.
- If the set of operations is fixed and the logic is short, `switch` is usually clearer and provides exhaustiveness protection.
- If a state requires complex actions, you can extract a dedicated helper method; there is no need to use a handler map just to avoid a few `switch` lines.

**Do not confuse values in a map with pattern variables.** `EnumMap<Operation, IntUnaryOperator>` is a function lookup table. It does not carry the flow scoping of `case String text`, nor does it automatically become an exhaustive `switch`.

## 9. Readability and Maintainability When the Enum Changes

A decision should be based on **what ought to become an error when the enum changes**.

### When a new state must be handled

Suppose `CANCELLED` is added to `TaskState`. With a `switch` expression without `default`, when you recompile the code against the new enum, the compiler reports the missing case and forces you to choose an appropriate label/logic.

If using `EnumMap`, there are two deliberate choices:

- **Complete map:** a validator uses `EnumSet.allOf(TaskState.class)` and fails initialization if `CANCELLED` is missing.
- **Partial map:** missing keys are acceptable, but callers must handle `null` results or fallbacks transparently.

If a missing case is a serious bug, `getOrDefault(..., "Other")` can mask the problem and cause the new state to display incorrectly. Do not use a fallback just because you want the program to "always return a string".

### When the mapping is configuration that changes at runtime

A map is more flexible: you can select label translations by locale, enable/disable certain actions by feature flag, or build a different map from validated configuration. However, **the set of enum constants is still determined at compile time**; changing map contents at runtime **does not create new enum constants**.

If multiple independent translations are needed, you can use one `EnumMap` per language and check key completeness for each table. Simpler cases may fit `ResourceBundle` or the application's i18n system better. The key is to avoid silently creating incomplete mappings.

### A third option: behavior inside the enum itself

Java also allows defining data or methods inside an enum. For example:

```java
enum StateWithLabel {
    NEW("New"), RUNNING("Running"), DONE("Done");

    private final String label;

    StateWithLabel(String label) {
        this.label = label;
    }

    String label() {
        return label;
    }
}
```

This is a **standalone illustrative enum type**. When each constant is permanently tied to a label or a property of the state, this approach can be more concise than both `switch` and a map. However, if the mapping belongs to the presentation layer, language, or system-specific configuration, pushing it into the domain enum can reduce separation of concerns.

This lesson mainly compares `switch` with a map, but the enum property option is worth considering so you do not have to maintain an external table for attributes that truly belong to each constant itself.

## 10. Speed, Memory, and Safety: Avoid Absolute Conclusions

**On performance:**

- A `switch` on an enum is a control structure implemented by the compiler/JVM in an appropriately optimized way; there is no need to perform a lookup through a user-created `Map` object.
- `EnumMap` is designed for enum keys and is generally very efficient in both memory and lookup.
- Actual timing also depends on JIT, hot paths, branch actions, data layout, allocation, and runtime optimizations. A mapping that only runs during UI initialization is rarely worth trading clarity for a few nanoseconds.

**On change safety:**

- A `switch` expression without `default` helps detect missing enum constants upon **recompilation**. It is not a runtime configuration validation mechanism.
- A map is only equivalently safe for coverage requirements if you **have validators/tests** and handle missing or `null` values.
- `Collections.unmodifiableMap` prevents modification through the shared view, but it does not make every data structure it might wrap deeply immutable; if a reference to the underlying map still exists elsewhere, the underlying data can still be modified. The main example keeps the underlying map as a local variable that does not leak.

**On understandability:**

- With 3–5 cases having different conditions, `switch` is usually easier to read than a map containing complex lambdas.
- With dozens of pure data mappings, `EnumMap` or a configuration-based approach can be easier to manage than a long chain of `case` branches.
- Do not use `EnumMap` to hide logic with hard-to-control side effects; and do not turn every data mapping into a tangled `switch`.

## 11. Common Mistakes and How to Avoid Them

| Mistake / Misconception | Why It Is Wrong or Risky | How to Handle It |
| --- | --- | --- |
| Assuming `EnumMap` is automatically exhaustive | A map can miss keys and still compile | Use `EnumSet.allOf(...)`, validators, and unit tests |
| Assuming every `switch` on an enum is exhaustive | A traditional `switch` statement can omit branches | Use a `switch` expression when you want compiler checking |
| Adding `default` "just to be safe" | Can hide newly added enum states that were not considered | Omit `default` when every constant must have an explicit policy |
| Using `getOrDefault` to hide missing mappings | New data may carry the wrong label without raising an error | Clearly separate "missing is an error" from "missing is allowed" |
| Assuming `getOrDefault` replaces `null` values | If a key is mapped to `null`, it still returns `null` | Distinguish `containsKey` from the actual value |
| Calling `EnumMap.put(null, ...)` | `null` keys are not accepted | Check for `null` before inserting |
| Invoking a handler when the map lacks the key | `handlers.get(op)` can return `null` | Validate the key set and fail fast with a message |
| Choosing `HashMap` out of habit | Misses the specialized benefits of `EnumMap` | Consider `EnumMap<>(EnumType.class)` |
| Claiming one solution is always "faster" | JDKs and workloads differ | Benchmark in the actual target environment |
| Confusing an enum case constant with a type pattern | `case DONE` does not declare a typed variable | Distinguish enum constants from `case SomeType x` |

## 12. Design and Self-Check Checklist

When you need to convert an enum state into data or an action, ask yourself:

1. **Must all enum constants be handled?** If yes, prefer a `switch` expression without `default`, or a map with key-completeness verification.
2. **Does each state have logic or only a data value?** Different logic usually fits `switch`; tabular data usually fits `EnumMap`.
3. **Is a missing mapping an error or a valid fallback?** This is a business decision—do not let `getOrDefault` decide for you.
4. **Can `null` values appear?** Explicitly handle a `null` selector, `null` keys, and `null` map values.
5. **Can the mapping change at runtime?** If yes, a map/configuration can be more flexible, but type constraints and tests are still needed.
6. **If an enum constant is added, do you want the compiler or runtime to catch the error?** Consider the compile-time advantage of a `switch` expression.
7. **Is a performance comparison needed?** Only benchmark when it is genuinely on a hot path and the results could affect the decision.

### Question 1

Given `enum State { A, B, C }`, does the following code compile?

```java
static int code(State state) {
    return switch (state) {
        case A -> 1;
        case B -> 2;
    };
}
```

**Answer:** No. The `switch` expression is missing `C` and has no `default`. The compiler rejects it because it is not exhaustive.

### Question 2

If replaced with:

```java
EnumMap<State, Integer> codes = new EnumMap<>(State.class);
codes.put(State.A, 1);
codes.put(State.B, 2);
```

Does the map code compile? What does `codes.get(State.C)` return?

**Answer:** Yes. A map missing `C` is still valid; `get(C)` returns `null` when there is no mapping. If a missing key should be an error, you must check/validate it manually.

### Question 3

If `CANCELLED` is added to an enum that already has a `switch` expression with `default -> "Other"`, will the compiler force adding a separate branch for `CANCELLED`?

**Answer:** No. `default` is already treated as the handling path for any remaining values. This may be intentional or may cause a business requirement to be overlooked, depending on the case.

### Question 4

You want to get a `String` label for all states, but the label names depend on the language, and each translation can change via configuration. What should you choose?

**Answer:** An `EnumMap<TaskState, String>` per locale or a suitable i18n system will be more convenient than hard-coding a `switch` for each language. However, you must still check that all constants are present and reject empty/null mappings if labels are required.

**Key takeaway:** **A `switch` expression is logic whose coverage is checked by the compiler; an `EnumMap` is a flexible data table that requires separate completeness checking.** The two approaches are not strictly opposed. Choose based on the nature of the mapping, error-detection requirements when the enum changes, fallback policy, and maintainability.

## References

- [Java Language Specification 21 — §15.28 Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28).
- [Java Language Specification 21 — §14.11 Switch Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11).
- [Java SE 21 API — `EnumMap`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/EnumMap.html).
- [Java SE 21 API — `EnumSet`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/EnumSet.html).
- [OpenJDK JEP 361 — Switch Expressions](https://openjdk.org/jeps/361).
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).