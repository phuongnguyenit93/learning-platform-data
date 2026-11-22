# Using Raw Types to Bypass Generic Limitations — Common Pitfalls in Java Pattern Matching

## 1. The problem: raw types do not solve generic limitations

When writing pattern matching in Java, the compiler sometimes rejects a check such as `Box<String>(...)` or `List<String>` against a value whose static type is only `Object`. A common "quick fix" is to drop `<String>` and use a **raw type** (`Box`, `List`), or to force a cast via an **unchecked cast**. That approach may allow a snippet to compile elsewhere, but it **does not restore type argument information at runtime** and can turn a type error that would be caught early into a `ClassCastException` at runtime.

This article focuses on that mistake in the context of **Java Core Pattern Matching**:

- Distinguish between `Box<String>`, `Box<?>`, and raw `Box`.
- Understand why type erasure limits `instanceof` checks, type patterns, and generic record patterns.
- See `rawtypes`/`unchecked` warnings, the risk of *heap pollution*, and deferred runtime failures.
- Use type patterns, record patterns, wildcards, generic APIs, or boundary data validation instead of raw types.
- Choose safe solutions when forced to interact with legacy libraries.

**Versions:** generics and raw types have existed since Java 5; type patterns for `instanceof` became standard in **Java 16** (JEP 394); **record patterns** and pattern matching for `switch` became standard in **Java 21** (JEP 440, JEP 441). The complete programs below use Java 21.

## 2. Three declarations that are identical at runtime but differ in type safety

Suppose we have a generic record:

```java
record Box<T>(T value) {}
```

We can declare:

```java
Box<String> typed = new Box<>("hello");
Box<?> unknownComponent = new Box<>("hello");
Box raw = new Box("hello"); // Raw type: should not be used in new code.
```

| Declaration | What does the compiler know about the component? | When should it be used? |
| --- | --- | --- |
| `Box<String>` | `value()` has type `String` by static contract | The API already knows the component is a string |
| `Box<?>` | `value()` can only be consumed as `Object` if there are no other bounds | Known to be a `Box`, but the type argument is unknown |
| `Box` (raw) | Bypasses type argument checking; `value()` after erasure has type `Object` | Mainly for compatibility at an unavoidable legacy boundary |

`Box<String>` and `Box<Integer>` are not two separate **runtime classes**. Java uses *type erasure*: type arguments such as `String` or `Integer` are used for static type checking, while their runtime class remains `Box`.

**Key difference:** `Box<?>` still tells the compiler that you are working with a generic type whose **type argument is unknown**, so unsafe operations are restricted. Raw `Box` removes that guardrail and allows certain unverified operations to slip through with warnings.

In Java, raw types are retained mainly for **migration compatibility with pre-generics code**, not because they are a safe escape hatch from generic limitations.

## 3. Type erasure: what can and cannot be checked?

Consider:

```java
Object input = new Box<>("java");
```

At runtime, we can confirm that `input` is an instance of the record class `Box`; however, the `Box` class alone **does not encode** the `String` type argument. Therefore, you cannot conclude that "every `Box` received is a `Box<String>`" merely from a runtime test on the outer object.

An example that is **invalid at compile time**, intentionally demonstrating the mistake:

```java
record Box<T>(T value) {}

static void incorrect(Object input) {
    // Invalid: requires an unchecked conversion Object -> Box<String>.
    if (input instanceof Box<String>(var text)) {
        System.out.println(text);
    }
}
```

With JDK 21, the compiler rejects using the record pattern `Box<String>(...)` when `input` is `Object`, because `Object` cannot be *checked-cast* safely to `Box<String>` with a concrete type argument. Changing the parameter to raw `Box` **does not fix this check**:

```java
static void alsoIncorrect(Box raw) {
    // Still invalid: raw Box cannot be verified as Box<String>.
    if (raw instanceof Box<String>(var text)) {
        System.out.println(text);
    }
}
```

Both are **error-demonstration snippets**, not runnable programs. The compiler message may look like "cannot be safely cast to Box<java.lang.String>".

Contrast this with the **valid** case:

```java
static void valid(Box<String> input) {
    if (input instanceof Box(var text)) {
        String strong = text; // Inferred static type: String.
        System.out.println(strong);
    }
}
```

When `input` has static type `Box<String>`, the compiler already knows the type argument from the API contract and can infer `text` as `String`. This is **type inference from static context**, not runtime inspection of the type argument via reflection.

**Rule for generic record patterns (Java 21):** declaring explicit type arguments in a record pattern is only valid when the source can be checked-cast to that record type without an unchecked conversion; a record pattern without type arguments uses the type inference mechanism specified in JLS §18.5.5.

## 4. Major pitfall: forcing a raw `Box` into `Box<String>` via unchecked conversion

The snippet below demonstrates what happens when you deliberately strip away type protection and then **make a false promise** to the compiler that the component is `String`.

Save to `RawTypeTrap.java`:

```java
public class RawTypeTrap {
    record Box<T>(T value) {}

    @SuppressWarnings({"rawtypes", "unchecked"})
    static void showFailure() {
        // For error demonstration only: do not do this in a real application.
        Box raw = new Box(42);
        Box<String> claimedStringBox = raw;

        System.out.println("raw=" + raw.value());

        try {
            String text = claimedStringBox.value();
            System.out.println(text);
        } catch (ClassCastException ex) {
            System.out.println("read-failed="
                    + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        showFailure();
    }
}
```

Run:

```bash
javac --release 21 RawTypeTrap.java
java RawTypeTrap
```

Output:

```text
raw=42
read-failed=ClassCastException
```

Step-by-step explanation:

1. The raw `Box` holds an `Integer` with value `42`.
2. The assignment `Box<String> claimedStringBox = raw` is an **unchecked conversion**: the compiler cannot verify the type argument of the source value.
3. The assignment completes **without checking** that `42` is a `String`, because the runtime class is still just `Box`.
4. At the point where `claimedStringBox.value()` is read into `String`, the compiler emits the necessary check/cast for the expected type. The actual value is `Integer`, resulting in `ClassCastException`.

`@SuppressWarnings` is used **only in this intentional failure example** so warnings do not clutter the demonstration. It does not make the data any safer. In real code, eliminate the raw conversion and **do not hide warnings just to get a clean build**.

Note: `ClassCastException` can occur **far after** the site of the unchecked conversion, making the bug hard to trace. That is the hazard of *heap pollution*: an expression has a parameterized type at compile time, yet the value it holds does not uphold the type argument contract.

## 5. Raw types combined with `var` in record patterns still lose type information

Some people assume that dropping the type argument and writing `Box(var value)` will make the compiler "look at the actual data" to know `value` is `String`. That is **incorrect**.

```java
record Box<T>(T value) {}

static void inspectRaw(Box raw) {
    if (raw instanceof Box(var item)) {
        Object value = item; // Valid.
        System.out.println(value);
    }
}
```

Because the `raw` variable does not preserve a concrete type argument, the compiler **cannot infer `item` as `String`** just because one runtime execution happens to hold a string. For `Box<T>` with no additional bound, the useful inferred type here is `Object`.

The following snippet is **invalid** immediately after that match:

```java
if (raw instanceof Box(var item)) {
    String text = item; // Error: Object cannot be assigned directly to String.
}
```

If you patch this with `(String) item`, you simply reintroduce the risk of `ClassCastException`. `var` is a **static type inference** feature, not a tool for "recovering generics after erasure".

For nested generic records, the same principle applies: type argument information discarded at the outer layer **does not magically reappear** when matching nested layers. Keep the generic types intact across calls and record components if you want the compiler to infer types deep inside.

## 6. Solution 1: preserve generic types in the API

When a method only handles a `Box<String>`, express that directly:

```java
record Box<T>(T value) {}

static void print(Box<String> input) {
    if (input instanceof Box(var text)) {
        String validatedByCompiler = text;
        System.out.println(validatedByCompiler.toUpperCase());
    }
}
```

This is an **illustrative snippet inside a class/scope where `Box` is already declared**, not a standalone file. The type of `text` is inferred as `String` from `Box<String>`.

If more general handling is needed, write a generic method:

```java
static <T> T unpack(Box<T> input) {
    return input.value();
}
```

There is no reason to use raw `Box` here. The `unpack` method preserves the relationship between the input and output types without any unchecked cast.

With nested records, inference still works across multiple levels:

```java
Box<Box<String>> nested =
        new Box<>(new Box<>("java"));

if (nested instanceof Box(Box(var word))) {
    String s = word; // Type String because the generic type was preserved.
    System.out.println(s);
}
```

The nested snippet above is **code within a context where `Box` is already declared**, using Java 21 record pattern syntax. The compiler infers from `Box<Box<String>>` to `Box<String>` and then to `String`; there is no need to fall back to a raw type for the pattern to work.

## 7. Solution 2: check the component with a type pattern instead of pretending to check the type argument

When the input **genuinely only has type `Object`**, sometimes there is no `Box<String>` contract to preserve. If the goal is to process a `Box` whose **actual component is a `String`**, use a record pattern with a **type pattern on the component**:

```java
if (input instanceof Box(String text)) {
    System.out.println(text.toUpperCase());
}
```

This is a two-step structural check on the record: `input` is an instance of record `Box`, and **the inner component** is a `String`. It **does not directly verify the erased type argument `T` of `Box<T>`**. For `record Box<T>(T value)`, this is a valid runtime solution for simple data that needs to be read.

Save to `ComponentPatternDemo.java`:

```java
import java.util.Locale;

public class ComponentPatternDemo {
    record Box<T>(T value) {}

    static void inspect(Object input) {
        if (input instanceof Box(String text)) {
            System.out.println("text="
                    + text.toUpperCase(Locale.ROOT));
        } else if (input instanceof Box(var component)) {
            System.out.println("other="
                    + (component == null
                            ? "null"
                            : component.getClass().getSimpleName()));
        } else {
            System.out.println("not-box");
        }
    }

    public static void main(String[] args) {
        inspect(new Box<>("java"));
        inspect(new Box<>(42));
        inspect(new Box<>(null));
        inspect("plain");
    }
}
```

```bash
javac --release 21 ComponentPatternDemo.java
java ComponentPatternDemo
```

Output:

```text
text=JAVA
other=Integer
other=null
not-box
```

**Why does `null` behave differently?**

- `Box(String text)` does not match when the component is `null`, because the type pattern `String text` here requires an actual `String` value.
- `Box(var component)` in this context can bind a `null` component; `var` does not turn `null` into `String`.
- If `input` itself is `null`, the outer record pattern `Box(...)` does not match.

This is a way to **check structure and actual runtime values** at a boundary receiving unknown data, unlike assigning raw `Box` to `Box<String>`.

## 8. Solution 3: `Box<?>` and wildcards when the type argument is unknown

For a `Box` whose `T` you do not know, declaring **`Box<?>`** is usually far more appropriate than raw `Box`:

```java
static void inspect(Box<?> input) {
    Object item = input.value();

    if (item instanceof String text) {
        System.out.println(text.length());
    } else {
        System.out.println("not a String");
    }
}
```

The compiler does not promise that `item` is a `String`; we only use `String` **after a valid type pattern**. This preserves the "unknown type parameter" semantics without breaking the generic contract.

`Box<?>` is not equivalent to `Box<Object>` for all write operations. The wildcard carries a **captured yet unknown type**; because of that, Java prevents many unsafe component assignments if `Box` is a mutable generic class.

If you need to read a component with a specific type relationship, you can use an upper bound:

```java
static void printNumber(Box<? extends Number> input) {
    Number value = input.value();
    System.out.println(value.doubleValue());
}
```

If you need to pass an `Integer` value into a generic consumer, consider a lower bound (`? super Integer`) following the PECS rule (**Producer Extends, Consumer Super**). Do not add wildcards merely as a trick to get past the compiler: set bounds according to the actual read/write relationship of the API.

## 9. `instanceof List<?>` is safer than `instanceof List<String>`

The same mistake frequently happens with Collections:

```java
// Does not compile when input is Object:
if (input instanceof java.util.List<String> names) {
    System.out.println(names.size());
}
```

The Java runtime cannot prove that every element of a `List` is a `String` from an erased type argument alone.

The right way to accept an arbitrary list is to use the **reifiable type** `List<?>`:

```java
if (input instanceof java.util.List<?> values) {
    System.out.println(values.size());
}
```

If business logic requires string contents, check **each element** rather than forcing the entire collection to `List<String>`.

Save to `ListPatternDemo.java`:

```java
import java.util.List;

public class ListPatternDemo {
    static void inspect(Object input) {
        if (input instanceof List<?> values) {
            for (Object value : values) {
                if (value instanceof String text) {
                    System.out.println("string=" + text);
                } else {
                    System.out.println("skip");
                }
            }
        } else {
            System.out.println("not-list");
        }
    }

    public static void main(String[] args) {
        inspect(List.of("a", 3, "b"));
        inspect("plain");
    }
}
```

```bash
javac --release 21 ListPatternDemo.java
java ListPatternDemo
```

Output:

```text
string=a
skip
string=b
not-list
```

`List<?>` only establishes that `input` is a `List`; **it does not verify the elements**. It is `value instanceof String text` that distinguishes each value. If the list contains `null`, the type pattern `String text` evaluates to `false` for that element.

## 10. Pattern matching with `switch`: classifying values instead of using raw casts

With Java 21, `switch` can use record patterns to branch on the component type. This lets you write consumers that handle heterogeneous data without unchecked casts.

Save to `SwitchBoxDemo.java`:

```java
public class SwitchBoxDemo {
    record Box<T>(T value) {}

    static String classify(Object input) {
        return switch (input) {
            case Box(String text) ->
                    "text:" + text;
            case Box(var item) ->
                    "box:" + (item == null
                            ? "null"
                            : item.getClass().getSimpleName());
            case null ->
                    "null-input";
            default ->
                    "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify(new Box<>("hello")));
        System.out.println(classify(new Box<>(24)));
        System.out.println(classify(new Box<>(null)));
        System.out.println(classify(null));
    }
}
```

```bash
javac --release 21 SwitchBoxDemo.java
java SwitchBoxDemo
```

Output:

```text
text:hello
box:Integer
box:null
null-input
```

Here, `case Box(String text)` handles the specific case first, while `case Box(var item)` covers the remaining `Box` values. **Order matters:** placing the broader `Box(var item)` case before the string case would shadow (*dominate*) the more specific case below, and the compiler would reject it.

`case null` handles a `null` selector explicitly. The pattern `Box(var item)` must not be interpreted as a guarantee that `item` carries a specific generic type at runtime.

When each variant has its own record type in a sealed hierarchy, prefer a strongly typed domain model with exhaustive `case` branches rather than mixing different payload types into a raw `Box`.

## 11. Checking nested record patterns from unknown data

Generic record patterns can be **nested**. If the input is `Object`, you cannot rely on an erased type argument at the outer layer; however, you can use patterns that check components at each level.

Suppose:

```java
record Box<T>(T value) {}
record Envelope<T>(T payload) {}
```

Approach:

```java
Object input = new Envelope<>(new Box<>("deep"));

if (input instanceof Envelope(Box(String text))) {
    System.out.println("nested=" + text);
}
```

Output in the case above:

```text
nested=deep
```

This is an **illustrative snippet within a scope where both records are declared**. The record pattern `Envelope(...)` first checks the wrapper itself; the `Box(...)` pattern checks the inner component; and `String text` checks the final component.

Data such as `Envelope<Box<Integer>>` will not pass the `String text` pattern, even though the outer container has the same runtime class `Envelope`. No unchecked cast is used.

**Remaining limitation:** checking each inspected component **does not mean validating an entire complex generic data structure**. For example, `Box<List<String>>` contains a collection whose elements must be checked individually if it originates from an untrusted data source.

## 12. Converting boundary data into a properly typed collection

A stronger approach than "cast and trust" is to **validate and copy** into a properly typed generic structure. When input may come from a legacy API or a deserializer that does not preserve generic contracts, perform this step in a single **adapter**.

Save to `SafeListAdapterDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class SafeListAdapterDemo {
    static List<String> readStrings(Object input) {
        if (!(input instanceof List<?> values)) {
            throw new IllegalArgumentException("not a list");
        }

        List<String> result = new ArrayList<>();

        for (Object item : values) {
            if (!(item instanceof String text)) {
                throw new IllegalArgumentException(
                        "non-string element");
            }

            result.add(text);
        }

        return List.copyOf(result);
    }

    public static void main(String[] args) {
        System.out.println("items="
                + readStrings(List.of("a", "b")));

        try {
            readStrings(List.of("a", 2));
        } catch (IllegalArgumentException ex) {
            System.out.println("error=" + ex.getMessage());
        }
    }
}
```

```bash
javac --release 21 SafeListAdapterDemo.java
java SafeListAdapterDemo
```

Output:

```text
items=[a, b]
error=non-string element
```

Here the adapter has a clear contract:

1. Accepts only objects that are `List<?>`.
2. Every element must match `String text`.
3. Valid data is **copied** into a new `List<String>`, avoiding dependence on the original mutable collection.
4. Invalid data is rejected at the boundary with a clear error.

If `null` is a permitted value in your business domain, define an explicit policy for it. The adapter above **rejects `null`** because `null` does not match `String text`, and `List.copyOf` also does not accept `null` elements.

This approach is not "recovering type arguments at runtime"; it is **proving and reconstructing a new container whose contents actually satisfy the desired type argument**.

## 13. When does `Class<T>` help with runtime checks?

For **a single component**, a `Class<T>` type token lets the caller specify the runtime type to check using `isInstance` and `cast`. For example:

```java
record Box<T>(T value) {}

static <T> java.util.Optional<T> findBoxComponent(
        Object input,
        Class<T> expected) {

    if (input instanceof Box(var item)
            && expected.isInstance(item)) {
        return java.util.Optional.of(expected.cast(item));
    }

    return java.util.Optional.empty();
}
```

This is an **illustrative snippet inside a class/scope containing `Box`**. With `expected = String.class`, Java verifies that the component is a `String` before converting; otherwise it returns `Optional.empty()` according to the logic above. This check does not need raw `Box`.

Limitation: `String.class` can check a concrete class; **there is no `List<String>.class` to fully verify all type arguments of a parameterized collection**. `Class<List>` or `List.class` only verifies the `List` class/interface, not that every element has type `String`.

If multi-level data validation is needed, you must traverse the container layers, check elements, and/or apply appropriate schema/validation logic.

## 14. What risks do raw types pose to type hierarchies and domains?

In a domain model using sealed interfaces, records, and pattern matching, raw generics often cause cascading problems:

- **Loss of API type safety:** a caller can pass a `Box<Integer>` into a raw `Box` variable and then perform an unchecked conversion to `Box<String>`.
- **Loss of pattern variable inference precision:** `Box(var component)` no longer knows the component is `String` once the static type has been made raw.
- **Reduced compiler assistance:** errors are caught at the consumption site instead of at the declaration/creation site.
- **More unchecked warnings or forced manual casts:** many call sites end up having to guarantee something the compiler cannot verify.
- **Obscured domain contracts:** for example, turning `Command<Result>` into raw `Command` makes it easy to mix up request and result types.
- **Deferred failures in consumers:** `ClassCastException` can surface inside a `switch`, service method, or mapper after passing through several layers.

A sealed hierarchy cannot by itself fix bugs introduced by raw generics: `sealed` restricts **the direct set of subtypes**, while generics preserve **type relationships between data inside classes/records**. Both mechanisms must be used properly in their respective roles.

## 15. Compiler warnings: use them to find bugs, not to hide them

When you suspect legacy code uses raw types, you can enable warnings:

```bash
javac --release 21 -Xlint:rawtypes -Xlint:unchecked MyClass.java
```

This is an **illustrative command** for the corresponding source file. `-Xlint:rawtypes` helps identify uses of raw generic types; `-Xlint:unchecked` helps identify conversions or operations not verified by the compiler. Not **every** occurrence of a raw type produces both warnings: exact behavior depends on context.

`@SuppressWarnings("unchecked")` **does not turn an unsafe cast into a safe one**. If you must support a legacy API:

1. Isolate the raw interaction inside a small adapter.
2. Explicitly check the object type and any verifiable elements.
3. Construct/copy into safely typed structures before exposing them to modern APIs.
4. Suppress warnings only at the narrowest audited scope, with a specific justification.
5. Write tests for valid types, wrong types, `null`, and mixed-type data.

Silencing all warnings by suppressing them across an entire package only makes new variants of the bug harder to spot.

## 16. Alternative selection table

| Situation | Avoid | Prefer |
| --- | --- | --- |
| Method already knows input is `Box<String>` | Changing parameter to raw `Box` to make pattern writing easier | Keep `Box<String>`; use `Box(var text)` |
| Method takes `Object`, needs a string inside `Box` | Trying `Box<String>(...)` or an unchecked cast | `instanceof Box(String text)` |
| Method takes a `List` with unknown elements | Casting raw `List` to `List<String>` | `List<?>` and check each element |
| Nested generic record with full static types | Making outer layers raw to avoid inference | Keep generic types and use nested record patterns |
| Untrusted JSON/API data | Trusting a `List<String>` cast | Validate schema and copy into a properly typed structure |
| Handling multiple shapes of `Box` | Collapsing into raw and casting everywhere | `switch` with type/record patterns that check components |
| Integrating with very old libraries | Spreading raw types across the domain | Adapter isolating raw usage, validating before returning generic APIs |
| Checking a single component via `Class<T>` | Assuming `T` is stored in `Box` at runtime | `expected.isInstance` / `expected.cast` |
| Wanting to silence `unchecked` warnings | Project-wide suppression | Improve generic contracts or suppress narrowly with justification |

## 17. Common misconceptions

1. **“Dropping `<String>` makes the compiler recognize the actual value is `String`.”** False: a raw type discards the type argument; it adds no runtime information.
2. **“Raw types and `<?>` are identical.”** False: wildcards preserve generic constraints so the compiler blocks many unsafe operations; raw types relax checks for legacy compatibility.
3. **“`instanceof Box<String>` checks every component using `String.class`.”** False: type erasure prevents direct type argument checks in contexts that require an unchecked conversion.
4. **“`Box(var s)` always infers `s` as the object's true runtime type.”** False: the compiler infers based on the static type of the pattern context.
5. **“Assigning a raw `Box` to `Box<String>` without error means it is safe.”** False: the failure may only appear when the component is accessed.
6. **“`@SuppressWarnings` eliminates the risk.”** False: it only hides the warning; it adds no runtime validation.
7. **“`List<?>` guarantees all elements have the same type.”** False: every element must still be treated as having an unknown type until checked or governed by another contract.
8. **“`Box(String s)` proves the type argument `T` of every reference to `Box` is `String`.”** False: it checks the matched component, not reconstructing all erased generic information.
9. **“Pattern matching eliminates all `ClassCastException`s.”** False: unchecked conversions or heap pollution from elsewhere can still cause failures later.
10. **“A `Class<T>` type token can check `List<String>`.”** False: `Class` does not hold the full parameterized type arguments of a container.
11. **“Raw types are the best option when generic code gets complex.”** False: it is usually better to refine `T` declarations, wildcard bounds, adapters, or API design.
12. **“Record patterns can deconstruct any ordinary class as if it were a record.”** False: record patterns apply only to matching record classes; they are not an arbitrary deconstruction mechanism for any class.

## 18. Checklist when reviewing a raw-type refactor

- Are there still `List`, `Map`, or `Box` declarations missing type arguments?
- Are they truly required for legacy compatibility, or can they become `List<?>`, `Map<?, ?>`, `Box<T>`?
- Is any unchecked conversion turning invalid data into an overly strong generic promise?
- If `instanceof` with a record pattern fails to compile, did you identify the **checked cast limitation** instead of working around it with a raw type?
- For `Object` or untrusted payloads, are **component values** checked with type patterns before use?
- For collections, is each element checked before returning `List<String>`?
- Is `(String)` being used anywhere merely to "compensate" for lost generic type information?
- Have `-Xlint:rawtypes -Xlint:unchecked` been enabled and the warnings reviewed?
- Have `null`, wrong types, nested records, invalid data inside collections, and `ClassCastException` scenarios been tested?
- When migrating an API from raw to generic, have callers relying on the old contract been updated or isolated behind an adapter?

**Conclusion:** Raw types are strictly a historical compatibility mechanism. In Java Pattern Matching, they **do not safely bypass type erasure**, cannot prove which type argument a `Box<T>` carries, and can push errors from compile time to runtime. **Preserve generic types in your APIs**, use **wildcards when the type argument is unknown**, use **type/record patterns to check components**, or **validate and copy data** at system boundaries instead of masking warnings with raw types.

## Official documentation

- [Oracle Java SE 21 — Record Patterns: Generic Records and Type Inference](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 394 — Pattern Matching for `instanceof`](https://openjdk.org/jeps/394)
- [JEP 441 — Pattern Matching for `switch`](https://openjdk.org/jeps/441)
- [Java Language Specification 21 — §4.8 Raw Types](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.8)
- [Java Language Specification 21 — §5.1.9 Unchecked Conversion](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.9)
- [Java Language Specification 21 — §14.30 Record Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [Java Language Specification 21 — §18.5.5 Record Pattern Type Inference](https://docs.oracle.com/javase/specs/jls/se21/html/jls-18.html#jls-18.5.5)
