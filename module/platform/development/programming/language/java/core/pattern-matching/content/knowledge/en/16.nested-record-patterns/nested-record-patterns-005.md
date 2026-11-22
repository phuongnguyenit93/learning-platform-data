# Component Patterns with Sealed Types in Nested Record Patterns (Java 21+)

## 1. The Problem: A Record Component with a Sealed Type

In Java, a `record` can have a **component** declared with a `sealed interface` or `sealed class`. A sealed type restricts which types are permitted to extend or implement it. If the permitted types include concrete `record`s, we can use a **nested record pattern** to simultaneously:

1. Match the outer record.
2. Check which variant object the inner sealed component holds.
3. If that variant is a record, further deconstruct the inner record's components.
4. Bind the extracted values to pattern variables.

Example data structure:

```java
sealed interface Payload permits Text, Metric {}

record Text(String value) implements Payload {}
record Metric(int count) implements Payload {}

record Envelope(String id, Payload payload) {}
```

`payload` has a **declared type** of `Payload` (a sealed interface), but at runtime it may hold `new Text("OK")`, `new Metric(7)`, or `null`.

Instead of calling `envelope.payload()` and then manually checking types and casting, we can write:

```java
if (object instanceof Envelope(var id, Text(var text))) {
    System.out.println(id + " -> " + text);
}
```

This is a **nested record pattern**: `Envelope(...)` matches the outer record; `Text(var text)` matches **a record type permitted by the sealed interface** and extracts its `value` component. The variable `id` is inferred as `String`; `text` is also `String`.

**Key point:** `Payload` itself is just an interface, so **`Payload(...)` is not a valid record pattern**. We place the record pattern `Text(...)` / `Metric(...)` at the component position whose declared type is `Payload` because the runtime type of the component can be one of those records.

## 2. Matching Mechanism and the Role of `sealed`

Suppose the object under inspection is:

```java
new Envelope("M-2", new Metric(7))
```

When encountering `Envelope(var id, Metric(int n))`, Java sequentially:

1. Checks whether the outer object is an `Envelope` and is not `null`.
2. Extracts the components via `Envelope`'s accessors: `id()` and `payload()`.
3. Binds `id`; matches `payload` against the `Metric` record.
4. Extracts `Metric.count()`, binds `n = 7`; if all sub-patterns succeed, the branch is selected.

The pattern `Envelope(var id, Text(var text))` does not match this object because `payload` is a `Metric`, not a `Text`.

An important advantage of `sealed` in `switch` is **exhaustiveness analysis**. If `Payload` only permits `Text` and `Metric`, the following two branches can cover all **non-null values** of the component's permitted variants:

```java
return switch (envelope) {
    case Envelope(var id, Text(var text)) -> "Text: " + text;
    case Envelope(var id, Metric(int n)) -> "Metric: " + n;
};
```

The Java 21 compiler understands the relationship between the outer record, the component's sealed type, and its permitted subtypes. Therefore, with a closed set of variants, the `switch` can be considered exhaustive **without needing `default`**.

However, **compile-time exhaustiveness does not mean every `null` case is safely handled**: `new Envelope("X", null)` matches neither `Text(...)` nor `Metric(...)`. A `switch` accepted by the compiler can still throw a `MatchException` when encountering such a null component. An appropriate null-handling strategy is needed.

## 3. Complete Example: Child Records, Child Classes, and `null`

Save the following code as **`SealedPayloadPatternDemo.java`**. The example uses Java 21 or later, with no preview features required.

```java
public class SealedPayloadPatternDemo {

    sealed interface Payload permits Text, Count, Reject {}

    record Text(String value) implements Payload {}
    record Count(int value) implements Payload {}

    // A permitted branch of a sealed interface does not have to be a record.
    static final class Reject implements Payload {}

    record Envelope(String id, Payload payload) {}
    record Batch(Envelope envelope) {}

    static String explain(Envelope envelope) {
        return switch (envelope) {
            case null ->
                    "Envelope null";

            // var payload is a component pattern that also covers null.
            case Envelope(var id, var payload) when payload == null ->
                    id + ": payload null";

            // The component has type Payload, but the actual value is Text.
            case Envelope(var id, Text(var body)) ->
                    id + ": text=" + body;

            case Envelope(var id, Count(int count)) ->
                    id + ": count=" + count;

            // Reject is a regular class: use a type pattern, without (...).
            case Envelope(var id, Reject rejected) ->
                    id + ": reject";
        };
    }

    public static void main(String[] args) {
        System.out.println(
                explain(new Envelope("T-1", new Text("OK"))));

        System.out.println(
                explain(new Envelope("M-2", new Count(7))));

        System.out.println(
                explain(new Envelope("R-3", new Reject())));

        System.out.println(explain(new Envelope("E-4", null)));
        System.out.println(explain(null));

        // String value in Text can be null; var body receives null.
        System.out.println(
                explain(new Envelope("T-5", new Text(null))));

        // Two levels of nested records: Batch -> Envelope -> Count.
        Object candidate =
                new Batch(new Envelope("B-6", new Count(9)));

        if (candidate instanceof Batch(
                Envelope(var id, Count(int count)))) {
            System.out.println("Batch " + id + ": " + count);
        }
    }
}
```

Compile and run with JDK 21+:

```bash
javac --release 21 SealedPayloadPatternDemo.java
java SealedPayloadPatternDemo
```

Stdout:

```text
T-1: text=OK
M-2: count=7
R-3: reject
E-4: payload null
Envelope null
T-5: text=null
Batch B-6: 9
```

Explanation:

- `Payload permits Text, Count, Reject` locks down the list of direct subtypes. `Text` and `Count` are records (implicitly `final`); `Reject` is a regular `final` class.
- `Envelope(var id, Text(var body))` and `Envelope(var id, Count(int count))` both check the variant type and deconstruct the inner data.
- `Envelope(var id, Reject rejected)` only checks the type and binds the `Reject` object; `Reject(...)` syntax would be invalid because `Reject` is not a record.
- `case null` handles the `envelope` **selector** itself being null. It is different from the `envelope.payload()` **component** being null.
- `case Envelope(var id, var payload) when payload == null` catches a null component without dominating the other specific branches. `when` is the guard of the `switch` branch.
- `Text(var body)` accepts a `null` value for the `String value` component because the inferred type of `var body` covers that exact component type. Note: `Text(...)` still requires the `Text` object itself to be non-null.
- `Batch(Envelope(var id, Count(int count)))` illustrates multiple levels of nesting. If `Batch.envelope()` is null, the inner `Envelope(...)` pattern will not match.

## 4. `null`: Distinguishing Three Levels

When nested record patterns work with a sealed component, there are at least three places that can contain `null`:

| Location | Example | Meaning for Patterns |
| --- | --- | --- |
| Outer object | `explain(null)` | Does not match any `Envelope(...)` record pattern; `case null` can be used in `switch`. |
| Sealed component | `new Envelope("X", null)` | Does not match `Text(...)`, `Count(...)`, or `Reject rejected`; requires a null check or a pattern that covers null. |
| Component inside child record | `new Envelope("X", new Text(null))` | `Text(var body)` still matches; variable `body` receives `null`. |

The Java 21 rule is more nuanced than "no type pattern matches null": **a type pattern directly in the component list of a record pattern is *null-matching* when it covers the entire declared type of that component**. For example, at the `Payload payload` position, `var payload` or `Payload payload` can match null. In contrast, `Text t` at the same position does not cover all `Payload`s, so it does not match null. This is why the guard checking `payload == null` in the example works.

With a record pattern nested one level deeper, `Text(var body)` only requires the **`Text` object to be non-null**; `body` itself can be null. Do not confuse `Text(null)` with `null` in place of the entire `Text` object.

## 5. Exhaustiveness, Branch Order, and Changes to the Sealed Hierarchy

### Covering All Permitted Types

For a `switch` without `default` to be considered exhaustive, the compiler must deduce that the patterns cover every applicable variant of the sealed type. If you add a subtype:

```java
record Empty() implements Payload {}
```

then you must also update `permits` to include `Empty`, and update any `switch` statements that need the new branch, for example:

```java
case Envelope(var id, Empty()) -> id + ": empty";
```

If a new variant is not yet handled, a `switch` without an appropriate covering branch may be reported as **not exhaustive** upon recompilation. This is a benefit of modeling finite states with sealed types: model changes make missing branches easy to detect.

A `non-sealed` subtype allows its subclasses to extend it further; in that case, a type pattern matching that `non-sealed` type can be used to cover the entire corresponding branch of the hierarchy. Subtypes do not all have to be records.

### Branch Order Must Avoid Domination

An overly broad branch can make subsequent specific branches unreachable. For example:

```java
// Wrong: the first branch is too broad, covering both Text and Count.
// switch (envelope) {
//     case Envelope(var id, var payload) -> "Có Envelope";
//     case Envelope(var id, Text(var body)) -> body; // dominated
// };
```

Place specific branches first. If you need a broad branch only for a particular condition, add a guard such as `when payload == null`; a guarded branch does not automatically cover all values of `payload`.

Similarly, `case Envelope(var id, Count(int n)) when n > 0` only handles `Count` where `n > 0`. A single guarded branch like this does not cover `Count(0)` or `Count(-1)`; you must add a branch to handle the remaining values if you want the `switch` to be exhaustive.

### Exhaustive Does Not Mean Immune to Runtime Errors

When a sealed component holds `null`, subtype branches cannot match; if there is no appropriate handling branch, an exhaustive `switch` can throw `MatchException`. `MatchException` can also occur due to mismatches between compiled class versions (for example, the sealed hierarchy changed while the code containing the `switch` has not been recompiled). These cases are distinct from compile-time errors caused by missing branches.

## 6. Common Pitfalls and Practical Usage

1. **Using a sealed interface as a record pattern:** `Envelope(Payload(var x))` is invalid because `Payload` is not a record. Use `Envelope(var p)` to extract the general component, `Envelope(Text(var x))` to deconstruct a record variant, or `Envelope(Payload p)` if you want to bind it with the interface type.
2. **Forgetting a permitted subtype:** If `permits` includes a regular class, you cannot write only record branches and assume all variants are handled. You must add the corresponding type pattern or an appropriate fallback branch.
3. **Confusing `null` at multiple levels:** `case null` handles the selector; it does not automatically handle `new Envelope("X", null)`. You also need to distinguish a null child record from null inside a child record's component.
4. **Placing a broad pattern before a narrow pattern:** An unguarded `Envelope(var id, var payload)` will cover cases that need specific handling, causing a dominated case error when specific branches are declared afterward.
5. **Misunderstanding `var`:** `var` in a record pattern performs **static type** inference from the component declaration, not a dynamic type that changes on its own. In `Envelope(var id, var payload)`, the compiler knows `id` has type `String` and `payload` has type `Payload`.
6. **Assuming `sealed` always replaces data validation:** `sealed` restricts the type hierarchy structure, but it does not guarantee that component values are non-null, business-valid, or free of exceptions when accessors are called.

Nested record patterns are especially useful for branching data models such as success/failure results, event messages, syntax trees, or workflow states. Using `sealed` on a component lets the compiler know which variants can appear, while record patterns let you express the exact data structure you want to deconstruct.

**Takeaway:** When a record has a sealed-type component, place the **pattern of each concrete subtype** at the component position. For record subtypes, you can deconstruct deeply with `Subtype(...)`; for regular classes, use a type pattern. Check exhaustiveness, `null` handling, and branch ordering so the code is correct at both compile time and runtime.

### References

- Oracle Java 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440
- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
- Java SE 21 API — MatchException: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/MatchException.html
