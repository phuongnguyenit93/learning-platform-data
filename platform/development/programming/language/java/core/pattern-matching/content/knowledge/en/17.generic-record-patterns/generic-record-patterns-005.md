# Nested generic record patterns in Java 21

## 1. What is a nested generic record pattern?

A **nested generic record pattern** is a record pattern nested inside another record pattern, where one or more of the records carry generic type parameters (`T`, `L`, `R`, etc.). Java can **deconstruct multiple levels** and **infer the types of pattern variables** from the declared type at each level.

Consider a simple record:

```java
record Box<T>(T value) {}
```

`Box<String>` has a `value` component of type `String`; `Box<Box<String>>` has a component that is a `Box<String>`. Given a variable with static type `Box<Box<String>>`, you can write:

```java
Box<Box<String>> nested = new Box<>(new Box<>("Java 21"));

if (nested instanceof Box(Box(var text))) {
    // The compiler infers that text has type String.
    System.out.println(text.toUpperCase());
}
```

This is **two nested record patterns**: the outer `Box(...)` deconstructs a `Box<Box<String>>`; the inner `Box(var text)` deconstructs the `Box<String>` component to extract the string. The syntax is neither a constructor call nor a new `Box<Box<...>>` type. It describes matching against existing data.

Notably, you **do not need to write explicit type arguments** on either record pattern: the compiler uses the type information of the matched expression to infer them. Record patterns became a standard feature in **Java 21** under JEP 440; code using this syntax compiles with JDK 21 or later without `--enable-preview`.

## 2. Separating three concepts: generics, nesting, and pattern matching

A nested generic record pattern combines three mechanisms with distinct roles:

| Mechanism | Question it answers | Example |
| --- | --- | --- |
| Generic record | What type does the component hold according to its declaration? | `record Box<T>(T value) {}` |
| Nested record | Is there another record inside a record? | `Box<Box<String>>` |
| Record pattern | Does the value match the record structure and its subpatterns? | `Box(Box(var text))` |

Given:

```java
record Box<T>(T value) {}

Box<Box<String>> outer = new Box<>(new Box<>("hello"));
```

the static type of `outer` is `Box<Box<String>>`. When evaluating `outer instanceof Box(Box(var text))`:

1. **Outer level:** the type of the matched target is `Box<Box<String>>`. The `Box(...)` pattern infers the corresponding type argument to be `Box<String>`.
2. **Component extraction:** Java invokes the `value()` accessor of the outer `Box`. The component value has static type `Box<String>`.
3. **Inner level:** the second `Box(...)` pattern infers its type argument to be `String`, then extracts the component of the inner record.
4. **Leaf variable:** `var text` is inferred as `String`. If both levels match, `text` is bound and available in the matching branch.

Because `text` is inferred as `String`, the expression `text.toUpperCase()` is valid **at compile time**. For a component of type `Integer`, the compiler similarly infers `Integer`; no manual casting is needed at each level.

No “full generic cast via reflection” happens at runtime. **Type argument information is used for static type analysis**, while runtime matching checks the checkable record types and applies patterns to each component.

## 3. Complete example: `Box<Box<String>>`

Save as `NestedBoxDemo.java`:

```java
import java.util.Locale;

public class NestedBoxDemo {
    record Box<T>(T value) {}

    public static void main(String[] args) {
        Box<Box<String>> nested =
                new Box<>(new Box<>("Java 21"));

        if (nested instanceof Box(Box(var text))) {
            String typed = text; // Compiles: text is String.
            System.out.println("nested=" + typed.toUpperCase(Locale.ROOT));
        }
    }
}
```

Run with JDK 21 or later:

```bash
javac --release 21 NestedBoxDemo.java
java NestedBoxDemo
```

Output:

```text
nested=JAVA 21
```

From left to right, the two `Box` patterns in `Box(Box(var text))` correspond to the two record levels. If you write:

```java
if (nested instanceof Box(var inner)) {
    // inner has type Box<String>; this only deconstructs one level.
}
```

then `inner` is **the entire inner record**, not the string yet. By contrast, `Box(Box(var text))` goes one level deeper and exposes the `String` component.

You can specify the type arguments of each pattern explicitly when they are safe in the static context:

```java
if (nested instanceof Box<Box<String>>(Box<String>(var text))) {
    System.out.println(text);
}
```

When `nested` is declared with the exact type `Box<Box<String>>`, this is an explicit way to write it. However, `Box(Box(var text))` is usually more concise, easier to refactor, and lets the compiler perform inference.

## 4. Multi-type-parameter example: `Envelope<Pair<String, Integer>>`

A generic record can have **multiple type parameters** and be nested as a component of another record. Declare:

```java
record Pair<L, R>(L left, R right) {}
record Envelope<T>(String id, T payload) {}
```

For `Envelope<Pair<String, Integer>>`, the pattern `Envelope(var id, Pair(var state, var retries))` infers `id` and `state` as `String`, and `retries` as `Integer`.

Standalone program `NestedPairDemo.java`:

```java
public class NestedPairDemo {
    record Pair<L, R>(L left, R right) {}
    record Envelope<T>(String id, T payload) {}

    public static void main(String[] args) {
        Envelope<Pair<String, Integer>> message =
                new Envelope<>("msg-7", new Pair<>("READY", 3));

        if (message instanceof Envelope(
                var id,
                Pair(var state, var retries))) {

            String eventId = id;
            String status = state;
            int nextRetry = retries + 1; // Unboxes Integer -> int.

            System.out.println(eventId + " | " + status
                    + " | next=" + nextRetry);
        }
    }
}
```

```bash
javac --release 21 NestedPairDemo.java
java NestedPairDemo
```

Output:

```text
msg-7 | READY | next=4
```

**Level-by-level inference:**

- `message` has type `Envelope<Pair<String, Integer>>`.
- `Envelope(...)` receives two components as declared: `id` of type `String`, and `payload` of type `Pair<String, Integer>`.
- `Pair(...)` unpacks `payload` into two components: `left` of type `String`, and `right` of type `Integer`.
- `var` only declares a pattern variable and infers its corresponding type; it **does not convert** a value from one type to another. Specifically, `retries + 1` uses Java's ordinary unboxing mechanism.

If there is another generic level, you nest another record pattern:

```java
record Box<T>(T value) {}
record Pair<L, R>(L left, R right) {}
record Envelope<T>(String id, T payload) {}

Envelope<Pair<Box<String>, Integer>> job =
        new Envelope<>("job-9", new Pair<>(new Box<>("ok"), 4));

if (job instanceof Envelope(
        var id,
        Pair(Box(var token), var retries))) {
    // token: String; retries: Integer; id: String.
    System.out.println(id + " | " + token
            + " | retries=" + retries);
}
```

The snippet above illustrates this **within a Java scope where the records are already declared**. The output when the branch matches is:

```text
job-9 | ok | retries=4
```

Nesting can go deeper when the data model requires it, but you should use clear component/variable names to avoid turning the pattern into a hard-to-read single line.

## 5. Type inference depends on the static type of the input

The compiler **does not inspect runtime values** to guess that an object happens to hold a `String`. It gets its information from the declared type at the site where the pattern is used.

### With static type information

```java
Box<Box<String>> known = new Box<>(new Box<>("safe"));

if (known instanceof Box(Box(var value))) {
    String text = value; // Valid.
}
```

The compiler has enough information to infer that `value` is `String`.

### Knowing only `Object`

```java
Object unknown = new Box<>("hello");

if (unknown instanceof Box(var data)) {
    // data has type Object; cannot call data.toUpperCase() yet.
    System.out.println(data.getClass().getSimpleName());
}
```

Even though `unknown` happens to hold a `Box<String>` at runtime, `data` in the pattern above is inferred with static type `Object`. Writing `String name = data;` will cause a **compile-time error** because `Object` cannot be automatically assigned to `String`.

If the real goal is to check that the *component value* is a string, use a **type pattern** at the component position:

```java
if (unknown instanceof Box(String text)) {
    System.out.println(text.toUpperCase());
}
```

The pattern `Box(String text)` applies a `String` type check to the **current component**. It does not claim that the runtime verifies the full type argument of every `Box<T>` in the system; what is checked is whether the **component value** matches that type pattern.

This helps distinguish two statements:

- **“The compiler knows `T` is `String` from the `Box<String>` declaration.”** This is static type information.
- **“The runtime distinguishes `Box<String>` from `Box<Integer>` solely by its type argument.”** This is generally false due to **type erasure**.

## 6. Type erasure and `instanceof` limits with generic records

Java generics use **type erasure**. Typically, `Box<String>` and `Box<Integer>` share the same runtime class `Box`; you cannot rely on the runtime class of `Box` to verify every type argument.

Illustrative snippet that **does not compile**, intentionally showing the error:

```java
record Box<T>(T value) {}

static void invalid(Object unknown) {
    if (unknown instanceof Box<String>(var text)) {
        System.out.println(text);
    }
}
```

With `unknown` of type `Object`, the compiler cannot perform the safely checked cast to `Box<String>` that the pattern above requires. Similarly, if the target has raw type `Box`, `raw instanceof Box<String>(var text)` can also be rejected because it would require an unchecked conversion. This is an intentional limitation of generic record patterns, not a bug in `var`.

Instead, when you actually need to determine from an `Object` that the component value is a `String`, you can write:

```java
static void inspect(Object unknown) {
    if (unknown instanceof Box(String text)) {
        System.out.println("String component: " + text);
    }
}
```

`Box(String text)` checks the `Box` record and **further checks that the component is a `String`**. For multi-level data that lacks static generic information, you should describe and check components at the appropriate levels rather than forcing an unverifiable parameterized type.

**Do not use raw types or unchecked casts just to “force” the compiler to accept a pattern.** If a generic structure actually holds data that violates its type promise, the program can fail when consuming the value after matching. Prefer preserving accurate generic types in your APIs and models, or use component type patterns when receiving data across an `Object` boundary.

## 7. Wildcards and generics in nested records

Generic record patterns can also work when the input is declared with a wildcard whose upper bound still provides the necessary information:

```java
record Box<T>(T value) {}

static void printNested(Box<? extends Box<String>> input) {
    if (input instanceof Box(Box(var text))) {
        String value = text; // The inferred type is still String.
        System.out.println(value);
    }
}
```

`? extends Box<String>` states that the outer component is a subtype compatible with `Box<String>`. Because `Box` is a record and records are implicitly `final`, this example remains a valid generic declaration that lets the compiler propagate the bound into the inner level. When a wildcard no longer carries information about the specific component, `var` infers a more general type; you cannot arbitrarily assume `String`.

This is why you should read the **complete type declaration**, including wildcards and bounds, before concluding what type a pattern variable has.

## 8. `null` at the outer level, inner level, and `var` variables

A record pattern does not match `null`, even when that record pattern is nested inside another. However, a record's component can be `null`; a `var` type pattern placed directly at a component position can be **null-matching**.

Save as `NestedNullDemo.java`:

```java
public class NestedNullDemo {
    record Box<T>(T value) {}

    public static void main(String[] args) {
        Box<Box<String>> missingInner = new Box<>(null);
        Object missingOuter = null;

        System.out.println("nested="
                + (missingInner instanceof Box(Box(var text))));

        System.out.println("direct="
                + (missingInner instanceof Box(var inner)));

        System.out.println("outer="
                + (missingOuter instanceof Box(var inner)));

        if (missingInner instanceof Box(var child)) {
            System.out.println("childIsNull=" + (child == null));
        }
    }
}
```

```bash
javac --release 21 NestedNullDemo.java
java NestedNullDemo
```

Output:

```text
nested=false
direct=true
outer=false
childIsNull=true
```

Explanation:

- `missingInner` is a valid `Box`, but its component is `null`. `Box(Box(var text))` fails at the **inner `Box(...)` pattern** because a record pattern does not accept `null`.
- `Box(var inner)` matches the outer `Box`; `var inner` binds the `null` component in this case.
- `missingOuter` is `null`, so the outer `Box(...)` pattern fails immediately.

Therefore, when a nested generic structure has optional components, make a clear choice: either use a nested pattern that **requires the child record to be present**, or bind the child record to a variable to handle `null` yourself.

## 9. Nested generic record patterns in `switch`

`switch` in Java 21 allows record patterns in `case` branches. Like `instanceof`, the type arguments of a generic record pattern can be inferred from context.

Save as `NestedSwitchDemo.java`:

```java
public class NestedSwitchDemo {
    record Pair<L, R>(L left, R right) {}
    record Envelope<T>(String id, T payload) {}

    static String describe(Envelope<Pair<String, Integer>> input) {
        return switch (input) {
            case null -> "empty";

            case Envelope(var id, Pair(var label, var count))
                    -> id + ":" + label + "/" + count;

            default -> "missing payload";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(
                new Envelope<>("r1", new Pair<>("ok", 2))));
        System.out.println(describe(new Envelope<>("r2", null)));
        System.out.println(describe(null));
    }
}
```

```bash
javac --release 21 NestedSwitchDemo.java
java NestedSwitchDemo
```

Output:

```text
r1:ok/2
missing payload
empty
```

`case Envelope(var id, Pair(var label, var count))` only matches when the selector is an `Envelope` and its `payload` component matches the `Pair(...)` record pattern. With a `null` payload, Java takes `default`; with a `null` selector, Java takes `case null`.

Note: if a `switch` can receive `null` without an appropriate `case null` branch, Java can throw a `NullPointerException`. And do not assume a nested branch will always match just because its static type is right: a `null` component will still cause the corresponding record pattern to fail.

## 10. What does a nested pattern do at runtime?

For `Envelope(var id, Pair(var state, var retries))` on an `Envelope<Pair<String, Integer>>`, you can picture the steps as:

1. Check that the input value is not `null` and is an instance of the `Envelope` record.
2. Retrieve each component of the record via its corresponding **accessor** (`id()` and `payload()`).
3. Bind `id`; then test the `payload` value against the `Pair(...)` record pattern.
4. If `payload` is non-`null` and matches `Pair`, retrieve `left()` and `right()` and bind `state` and `retries`.
5. Once all subpatterns match, the program can use the pattern variables in the matching branch.

This is **a recursive matching operation**, not a call to the `Envelope(...)` or `Pair(...)` constructors. Nor does it create copies of the records during matching.

Explicitly written accessors in a record are still invoked by Java during matching. Therefore, design accessors to be stable and avoid unpredictable side effects. If an accessor throws an exception while a record pattern retrieves a component, matching terminates abnormally (per the Java 21 specification, via `MatchException` wrapping the underlying cause), rather than simply returning `false`.

With deeply nested patterns, **do not rely on the order or number of accessor calls as a business contract**. Use patterns to describe structure and keep side-effecting logic in separate application code.

## 11. Variable scope and combining conditions

Pattern variables exist wherever Java determines that matching has succeeded (*flow scoping*). For example, inside a method where `Envelope<Pair<String, Integer>>` is known:

```java
if (message instanceof Envelope(var id, Pair(var state, var retries))
        && retries > 0) {
    System.out.println(id + ": " + state);
}
```

On the right-hand side of `&&`, the variables have already been established by the pattern on the left, so `retries` can be used there. This works thanks to **short-circuit evaluation**: if matching fails, Java does not evaluate the remaining condition.

Do not read `id`, `state`, or `retries` outside the scope where the compiler guarantees they are definitely assigned. For a nullable `Integer` component, the comparison `retries > 0` unboxes `Integer` and can throw a `NullPointerException`; add an appropriate check if your model permits `null` data.

## 12. Common mistakes and fixes

| Mistake or misconception | Explanation and fix |
| --- | --- |
| Thinking `Box(Box(var x))` calls a constructor twice | These are two record patterns matching against an existing value |
| Thinking `var` always infers the exact runtime type | The type of `var` is based on the **static type**; with an `Object` input, generic type arguments may no longer be specific |
| Checking an `Object` with `Box<String>(...)` | The `String` type argument cannot always be verified past type erasure; use a subpattern such as `Box(String text)` when you need to check the value |
| Using raw `Box` and expecting strict nested generic inference | Raw types lose type guarantees; keep full `Box<T>` in your APIs |
| Putting the wrong number of components in a pattern | The number of pattern components must match the record's declared components |
| Assuming a generic record pattern verifies every type argument at runtime | Runtime only performs valid type tests for the record and its subpatterns |
| Using `Box(Box(var x))` when the inner component can be `null` | The inner record pattern does not match `null`; to handle it separately, use `Box(var inner)` and check it |
| Using pattern variables outside the matching branch | Pattern variables follow Java's flow scoping rules |
| Using this feature with `--release 17` | Nested record patterns were standardized in Java 21; with JDK 21+, use `--release 21` |
| Writing a pattern for a regular class that has a `value()` method like a record | Record patterns require the type to be a **record class**; a matching accessor name is not enough |

## 13. Choosing the right nesting depth

Use nested generic record patterns when:

- The data is naturally modeled as nested records and the generic types are clearly declared.
- You need to access components across multiple levels in an `if` or `switch` branch.
- You want static type checking from the compiler and fewer manual casts.
- Nullable levels are clearly defined in the data design.

If a pattern has too many levels, is hard to name, or contains complex business conditions, split reading the child records into clearer steps. For example, you can match `Envelope(var id, var payload)` and handle `payload` in the next block. This still leverages generic types and makes `null` checks easier.

**Rule of thumb:** `Box(Box(var text))` deconstructs two levels, and Java infers `text` from **the static generic type at each level**. The pattern also obeys record checks, subpatterns, `null` rules, and flow scoping; it is not an arbitrary runtime check of erased type arguments.

## Official references

- [Oracle Java SE 21 — Record Patterns: Generic Records, Type Inference, and Nested Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [Java Language Specification 21 — §14.30 Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [Java Language Specification 21 — §18.5.5 Record Pattern Type Inference](https://docs.oracle.com/javase/specs/jls/se21/html/jls-18.html#jls-18.5.5)
