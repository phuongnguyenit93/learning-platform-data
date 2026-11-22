# Avoiding Type Parameters That Appear Only Once Without Creating a Needed Relationship

## Lesson Objectives

When designing a Java Generic API, a common mistake is declaring `<T>` for every method that touches a generic type, even when `T` does not help constrain any information. For example:

```java
static <T> void printValues(List<T> values) {
    for (T value : values) {
        System.out.println(value);
    }
}
```

This method only **reads and prints** elements. If the exact `T` does not need to be known, the signature is usually clearer when written as:

```java
static void printValues(List<?> values) {
    for (Object value : values) {
        System.out.println(value);
    }
}
```

**Principle:** Only name a type variable `T` when that name carries useful information: linking multiple type positions, constraining a type meaningfully, expressing the result type in terms of the input, or enabling a safe internal operation that an external wildcard cannot express directly. If `T` appears only once and creates no necessary constraint, a wildcard or a regular supertype is usually easier to read.

However, this is a **design guideline (heuristic), not an absolute ban**. There are notable exceptions: wildcard capture helpers, generic factories returning empty collections, type inference based on return targets, and important type bounds. Do not mechanically replace every `<T>` appearing once with `?`.

After this lesson, you will be able to:

- Distinguish a type parameter **with meaningful constraints** from one that merely complicates the signature.
- Choose correctly among `Object`, `List<?>`, `List<? extends Number>`, `List<? super T>`, and `List<T>`.
- Explain why `<T> void print(List<T>)` is often excessive, whereas `<T> void append(List<? super T>, T)` expresses a real type relationship.
- Recognize cases where `T` is present in **input and output**, in callbacks, or in `Comparable<? super T>` bounds.
- Understand why `<T> List<T> emptyTyped()` is still useful even though it takes no `T` from input parameters.
- Understand wildcard capture: public API `List<?>`, private implementation using `<T>` to read and write back **the same unknown element type**.
- Know the risks of changing public API signatures: source compatibility, generic reflection metadata, overloads/overrides, and binary descriptors.
- Verify Java 17 examples using `javac`/`java`/`javap`.

This lesson belongs to the **API Design** topic in Java Core — Generics, targeting Java 17+. Complete programs were actually run with `javac -Xlint:all`; other snippets include notes about context and compilability.

## 1. A type parameter is a variable expressing a **type relationship**

In a generic method:

```java
static <T> T identity(T input) {
    return input;
}
```

the same `T` appears in both the parameter and the return type. If the caller passes `String`, the compiler can infer a result type tied to the input type:

```java
String s = identity("Java");
Integer n = identity(42);
```

The meaning of `T` is not merely "the method works with many types". It expresses that **the output value has the same static type inferred from the input value**.

A non-generic function:

```java
static Object identityObject(Object input) {
    return input;
}
```

can return that exact same object, yet the return type is only `Object`. Callers wanting `String` typically have to cast or use other logic. Thus `identity(T)` has a relationship worth preserving and should not replace `T` with `Object`.

Contrast this with the method:

```java
static <T> void display(T value) {
    System.out.println(value);
}
```

Here, if the method only passes `value` to `println(Object)` and has no other parameters or result to constrain, we can simply write:

```java
static void display(Object value) {
    System.out.println(value);
}
```

Both illustrate the same intent: "accept an object and print". Differences in overloading/type inference may exist in a complex API; evaluate the concrete signature, yet **generic `T` adds no practical guarantee** in this simple implementation.

## 2. Read the role of types before counting occurrences

A starting table:

| Signature | Does `T` create an essential relationship? | Suggested design |
| --- | --- | --- |
| `<T> void print(List<T> data)` | No, if only read as `Object` | `void print(List<?> data)` |
| `<T> boolean containsNull(List<T> data)` | No, if only inspecting elements | `boolean containsNull(List<?> data)` |
| `<T extends Number> double sum(List<T> xs)` | Usually no, if only `Number`s are needed | `double sum(List<? extends Number> xs)` |
| `<T> T identity(T x)` | Yes: input → return | Keep `<T>` |
| `<T> void append(List<? super T> dst, T value)` | Yes: `dst` accepts `value` | Keep `<T>` |
| `<T> long countIf(List<? extends T> src, Predicate<? super T> test)` | Yes: predicate must accept source elements | Keep `<T>` |
| `<T> List<T> repeat(T x, int n)` | Yes: result element type follows `x` | Keep `<T>` |
| `<T> List<T> emptyTyped()` | Meaningful with target typing even if appearing once | Can keep `<T>` |
| `private <T> void swapCaptured(List<T> xs,...)` | Meaningful in the **method body** via wildcard capture | Do not replace mechanically |

You must inspect **the public contract + usage in the body + type inference goals**. Counting the character `T` is a code-review signal, not sufficient proof to refactor automatically.

## 3. Why is `List<?>` usually right when read-only?

Java generics are **invariant**. Even though `String extends Object`:

```java
List<String> names = List.of("Lan", "Minh");
// List<Object> objects = names; // Compile-time error.
```

`List<String>` is not a subtype of `List<Object>`. If a signature accepts:

```java
static void print(List<Object> values)
```

then the method does **not** directly accept a `List<String>` or `List<Integer>` variable.

If the method only needs to iterate and requires no constraint between two type positions:

```java
static void print(List<?> values) {
    for (Object value : values) {
        System.out.println(value);
    }
}
```

then it safely accepts `List<String>`, `List<Integer>`, `List<Dog>`, and many other list kinds.

The `?` means "some element type that the caller does not need to name publicly"; the compiler does **not** assume it is `Object` to allow arbitrary writes. When reading, values can be used as `Object`.

**Important:** `List<?>` is not synonymous with an immutable list. Depending on the implementation, operations like `clear()`, `remove(int)`, or `iterator().remove()` may mutate structure. What the compiler restricts is **adding an arbitrary non-null value** because the true element type is unknown.

`List<?>` should not be called an absolute "read-only list". It is **a view with an unspecified element type**, useful for observational operations.

## 4. `Object` or wildcard? Do not treat them as interchangeable

For a single standalone value needing no type relationship:

```java
static void log(Object event)
```

is clearer than `static <T> void log(T event)` when the body only calls `String.valueOf` or `System.out.println`.

However, for **containers**, `List<Object>` is completely different from `List<?>`:

```java
static void inspect(List<?> source) {
    for (Object x : source) System.out.println(x);
}
```

accepts many `List<E>`, whereas:

```java
static void inspectObjects(List<Object> source) {
    for (Object x : source) System.out.println(x);
}
```

only accepts references compatible with `List<Object>` (and subtypes under the corresponding class/type-parameter relationship). It does not directly accept `List<String>` due to invariance.

A quick rule:

- **One standalone object:** `Object` if there are no other type constraints.
- **A generic structure whose element does not need naming:** `List<?>`, `Collection<?>`, `Class<?>`, etc.
- **A source only read as a specific supertype:** `List<? extends Number>`.
- **A link between multiple type positions:** type variable `T`.

## 5. If only reading `Number`, let the wildcard express it

A commonly seen design:

```java
static <T extends Number> double sum(List<T> source) {
    double total = 0;
    for (T n : source) total += n.doubleValue();
    return total;
}
```

In this method, the caller does not receive back a value of type `T`, nor is there a second parameter constrained by `T`. The method only needs `Number.doubleValue()`.

It can be written as:

```java
static double sum(List<? extends Number> source) {
    double total = 0;
    for (Number n : source) total += n.doubleValue();
    return total;
}
```

It accepts `List<Integer>`, `List<Double>`, or lists of other `Number` subtypes, and clearly states it **needs a source supplying `Number`s**.

Do not change it to `List<Number>` if you still want to accept `List<Integer>`, due to Java generic invariance. Do not use raw `List` and cast each element manually when a wildcard already expresses the intent.

For untrusted data, `List<? extends Number>` is a **compile-time commitment of the source reference**, not a mechanism to validate a raw collection that has already suffered heap pollution. That is a separate issue to handle at data boundaries.

## 6. Program A — Minimalist APIs and APIs needing type relationships

Create the file **`ApiSignatureDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Predicate;

public class ApiSignatureDemo {
    static void printValues(List<?> source) {
        for (Object value : source) {
            System.out.println("item: " + value);
        }
    }

    static boolean containsNull(List<?> source) {
        for (Object value : source) {
            if (value == null) return true;
        }
        return false;
    }

    static double sum(List<? extends Number> source) {
        double total = 0;
        for (Number number : source) {
            total += number.doubleValue();
        }
        return total;
    }

    static <T> long countIf(
            List<? extends T> source,
            Predicate<? super T> predicate) {
        long count = 0;
        for (T value : source) {
            if (predicate.test(value)) count++;
        }
        return count;
    }

    static <T> void append(List<? super T> target, T value) {
        target.add(value);
    }

    static <T> List<T> repeat(T value, int times) {
        if (times < 0) {
            throw new IllegalArgumentException("times");
        }
        List<T> result = new ArrayList<>();
        for (int i = 0; i < times; i++) {
            result.add(value);
        }
        return List.copyOf(result);
    }

    public static void main(String[] args) {
        List<String> words =
                List.of("Java", "Generic", "API");

        printValues(List.of("A", "B"));
        System.out.println("null: " + containsNull(words));
        System.out.println("sum: " + sum(List.of(2, 3.5)));

        Predicate<CharSequence> longText =
                s -> s.length() >= 4;
        System.out.println("long words: "
                + countIf(words, longText));

        List<Number> numbers = new ArrayList<>();
        append(numbers, Integer.valueOf(10));
        append(numbers, Double.valueOf(2.5));
        System.out.println("target: " + numbers);

        System.out.println("repeat: " + repeat("ok", 3));
    }
}
```

Compile and run:

```bash
javac -Xlint:all ApiSignatureDemo.java
java ApiSignatureDemo
```

**Verified stdout on Java 17:**

```text
item: A
item: B
null: false
sum: 5.5
long words: 2
target: [10, 2.5]
repeat: [ok, ok, ok]
```

The program compiles with zero warnings under `-Xlint:all`.

### Analysis of the group not needing `<T>`

`printValues(List<?>)` carries no dedicated element type into another parameter or return type: reading as `Object` suffices.

`containsNull(List<?>)` only inspects each element and returns `boolean`, needing no named type parameter at all.

**A Java detail worth remembering:** do not implement `containsNull` by assuming `source.contains(null)` always returns a boolean. Some list implementations from `List.of(...)` reject `null` lookups and can throw `NullPointerException`. That is why the example **iterates elements** and compares with `== null` to yield a clear result per the method's contract.

`sum(List<? extends Number>)` only needs to read elements as `Number`, so the bound can live on the wildcard rather than a named type variable.

### Analysis of the group **genuinely needing** `<T>`

`countIf` connects two parameters:

```java
List<? extends T> source
Predicate<? super T> predicate
```

`source` supplies values used as `T`, while `predicate` can **consume** those `T` values. For example, `List<String>` works safely with `Predicate<CharSequence>` because the predicate accepts a supertype of `String`. Removing `T` leaves the method unable to express the constraint between the element type and the callback type.

`append` connects the element type `T` to be written with a target accepting `T`:

```java
List<? super T> target
T value
```

With `List<Number>`, both `Integer` and `Double` are safe choices in appropriate calls. You cannot carelessly replace `T` on the target with `?`, because through `List<?>` the compiler forbids adding non-null values of unknown type.

`repeat(T,int)` connects the input of type `T` to the output `List<T>`: the caller receives a list containing the exact type inferred from `value`. This is a valuable input–output commitment.

**`null` policy:** `repeat` uses `List.copyOf`, so it does not support `null` as an element. This is a property of the example implementation, independent of choosing `T` or a wildcard.

## 7. Why does `countIf` need `? super T` on the callback?

Read the call in Program A:

```java
Predicate<CharSequence> longText =
        value -> value.length() >= 4;

long result = countIf(words, longText);
```

`words` is `List<String>`. Every `String` can be used as a `CharSequence`. If a predicate accepts any `CharSequence`, it can certainly evaluate any `String`.

The signature:

```java
static <T> long countIf(
        List<? extends T> source,
        Predicate<? super T> predicate)
```

is the relational **PECS** version:

- `source` **produces** values of `T` → `? extends T`.
- `predicate` **consumes** values of `T` → `? super T`.

The `T` pair is not decorative; it forces both parameters to align properly. This is a classic example of a useful generic method even though it does not return `T`.

### When might `T` not be needed for a callback?

If the requirement is simply "read `Object` and print", you do not need a complex generic callback:

```java
static void dump(List<?> values) {
    for (Object value : values) System.out.println(value);
}
```

But if callers pass typed callbacks, preserve appropriate constraints instead of lowering everything to `Object` and using unchecked casts.

## 8. Uses of a type variable can span **logical positions**, not just multiple parameters

It is not only relationships between two method parameters that are worth keeping. The following are also valid reasons:

**Input → return:**

```java
static <T> T identity(T value) {
    return value;
}
```

**Input → element type of returned collection:**

```java
static <T> List<T> singleton(T value) {
    return List.of(value);
}
```

**Input from multiple sources → one destination kind:**

```java
static <T> void copyInto(
        java.util.Collection<? extends T> source,
        java.util.Collection<? super T> destination) {
    for (T item : source) destination.add(item);
}
```

These are illustrative method snippets that can be placed in a class with appropriate imports. In `copyInto`, `T` links producer and consumer; that is why the type variable cannot simply be removed if the compiler is to maintain the same flexible contract.

**A bound referencing `T` itself** is also meaningful, such as:

```java
<T extends Comparable<? super T>>
```

which states that every `T` can be compared to values of kind `T` via an appropriate `Comparable` interface. It is not like a `<T>` merely naming one argument with no relationship used by the method.

## 9. Do not forget the major exception: wildcard capture helpers

The rule "if `T` appears once, use `?`" **must not be mechanically applied** to generic helpers meant to **capture a wildcard**.

For example, the caller passes `List<?>`; you need to swap two elements. Because the concrete element type is unknown, Java rejects arbitrary writes such as:

```java
static void badSwap(List<?> items, int i, int j) {
    // items.set(i, items.get(j)); // Error because the two expressions are captured independently.
}
```

The snippet above illustrates the unsafe operation commented out. At the public API level, `List<?>` remains the right contract: callers do not need to know the element type. Yet **internally**, we need to bind the value read out with the element type of **the same list**.

The solution is a helper with its own type variable:

```java
static void swapAny(List<?> items, int i, int j) {
    swapCaptured(items, i, j);
}

private static <T> void swapCaptured(
        List<T> items, int i, int j) {
    T first = items.get(i);
    items.set(i, items.get(j));
    items.set(j, first);
}
```

On the public method, callers see `List<?>`. When `swapCaptured(items, ...)` is called, the compiler uses **wildcard capture conversion** to assign the name `T` to one specific—unknown yet consistent—element type for **that helper call**.

Inside the helper:

- `items.get(i)` has type `T`.
- `items.set(i, ...)` accepts a value of type `T`.
- A value retrieved from **`items` itself** can be written back safely.

Even though in the helper's **signature** `T` may appear only in `List<T>`, the **body** uses `T` to preserve the read–write relationship. This is a **meaningful exception** to the "appears once" heuristic.

## 10. Program B — Wildcard capture in implementation

Create the file **`WildcardCaptureDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class WildcardCaptureDemo {
    static void swapAny(List<?> items, int i, int j) {
        swapCaptured(items, i, j);
    }

    private static <T> void swapCaptured(
            List<T> items, int i, int j) {
        T first = items.get(i);
        items.set(i, items.get(j));
        items.set(j, first);
    }

    static void duplicateFirst(List<?> items) {
        duplicateCaptured(items);
    }

    private static <T> void duplicateCaptured(List<T> items) {
        if (!items.isEmpty()) {
            T first = items.get(0);
            items.add(first);
        }
    }

    public static void main(String[] args) {
        List<String> words =
                new ArrayList<>(List.of("left", "right"));
        swapAny(words, 0, 1);
        System.out.println("swapped: " + words);

        duplicateFirst(words);
        System.out.println("duplicated: " + words);

        List<Integer> nums =
                new ArrayList<>(List.of(1, 2));
        swapAny(nums, 0, 1);
        System.out.println("numbers: " + nums);
    }
}
```

Run:

```bash
javac -Xlint:all WildcardCaptureDemo.java
java WildcardCaptureDemo
```

**Verified stdout:**

```text
swapped: [right, left]
duplicated: [right, left, right]
numbers: [2, 1]
```

The compiler emits no warnings when using `-Xlint:all`.

### Why is `duplicateFirst` safe?

`duplicateFirst(List<?>)` does not know whether the element type is `String`, `Integer`, or another class. The helper `duplicateCaptured(List<T>)` retrieves an element `T` from **that exact list** and appends **that same element** back. It does not fabricate a new value of unknown type.

The public contract still prevents callers from adding an arbitrary `Object`, yet the implementation can use capture conversion to perform **internally consistent operations**.

Generic capture itself does not make a mutable list immutable or vice versa. If `items` is an immutable list created by `List.of`, `set`/`add` can throw `UnsupportedOperationException`. The example uses `new ArrayList<>(...)` so those operations are valid.

Additionally, `swapAny` requires valid indices; out-of-range indices can cause `IndexOutOfBoundsException`. That is a normal condition of list operations, not a generics bug.

### Should you write your own swap helper in production?

The standard library already provides `Collections.swap(List<?>, int, int)`, so the example here is meant to **illustrate capture**. In production code, prefer standard APIs when appropriate; do not maintain duplicate utilities without a specific reason.

## 11. Second exception: `T` appearing only in the return type can still be useful

A generic factory may **take no parameters involving `T` at all**, yet still carry a type parameter for callers to infer from the target type:

```java
static <T> List<T> emptyTyped() {
    return List.of();
}
```

Example:

```java
List<String> words = emptyTyped();
List<Integer> numbers = MyApi.<Integer>emptyTyped();
```

The second line is an illustration where `MyApi` should be replaced by the class declaring `emptyTyped`.

You cannot simply change the return type to `List<?>` and keep the same utility:

```java
// List<String> names = someMethodReturningListWildcard();
```

`List<?>` cannot be directly assigned to `List<String>` without type-constraint evidence, whereas `List<T>` from a generic factory can be chosen by the compiler from the target type.

In a factory that **stores no elements**, like `List.of()`, creating an empty collection is safe for any `T`. This is why the standard library has generic factories such as `Collections.emptyList()`.

**Limitation to understand:** "`T` only in the return type" does not allow an implementation to conjure an arbitrary `T` object without a trustworthy data source or factory. A method:

```java
// Must not fake safety with an unchecked cast:
// static <T> T magic() { return (T) new Object(); }
```

can create a broken contract and cause `ClassCastException` at the caller. Only use return-only generics when the implementation has grounds to uphold the contract (such as an empty list, validated data, or a valid typed source).

## 12. Program C — Return-only generics, factories, and self-bounds

Create the file **`ReturnOnlyTypeDemo.java`**:

```java
import java.util.Collections;
import java.util.List;
import java.util.function.Supplier;

public class ReturnOnlyTypeDemo {
    static <T> List<T> emptyTyped() {
        return List.of();
    }

    static <T> T fromFactory(Supplier<? extends T> factory) {
        return factory.get();
    }

    static <T extends Comparable<? super T>> T minimum(
            List<? extends T> source) {
        if (source.isEmpty()) {
            throw new IllegalArgumentException("empty");
        }

        T best = source.get(0);
        for (T candidate : source) {
            if (candidate.compareTo(best) < 0) {
                best = candidate;
            }
        }
        return best;
    }

    public static void main(String[] args) {
        List<String> names = emptyTyped();
        List<Integer> ids =
                ReturnOnlyTypeDemo.<Integer>emptyTyped();

        System.out.println("empty strings: " + names);
        System.out.println("empty integers: " + ids);
        System.out.println("library empty: "
                + Collections.<String>emptyList());

        String message = fromFactory(() -> "ready");
        System.out.println("factory: " + message);
        System.out.println("minimum: "
                + minimum(List.of(5, 2, 9)));
    }
}
```

Run:

```bash
javac -Xlint:all ReturnOnlyTypeDemo.java
java ReturnOnlyTypeDemo
```

**Verified stdout:**

```text
empty strings: []
empty integers: []
library empty: []
factory: ready
minimum: 2
```

The program compiled with `-Xlint:all` with zero warnings.

### Three different reasons why `T` is necessary

1. **`emptyTyped()`**: via target typing, callers receive `List<String>`, `List<Integer>`, etc. in a type-safe manner because an empty list holds no mistyped elements. The type variable here links to no input, yet still expresses a useful output contract.
2. **`fromFactory(Supplier<? extends T>)`**: ties the type produced by the factory to the return value type. There is a callback output → method output relationship.
3. **`minimum`**: uses the bound `T extends Comparable<? super T>` to ensure `T` values can be compared, while preserving the element type in the result. You cannot merely change the return type to `Object` and keep the original type promise.

**Takeaway rule:** Do not mechanically count occurrences of `T` in text. Ask: "What is this type variable proving to the caller or to the body?"

## 13. A type parameter used in a bound can also carry an important contract

Example:

```java
static <T extends Comparable<? super T>> T minimum(
        List<? extends T> source)
```

`Comparable<? super T>` allows `T` values to validly compare themselves with `T` through an appropriate type argument of `Comparable`.

If the return type were changed to `Comparable<?>` or `Object`, callers would lose the concrete element type. If the `Comparable` constraint were removed, the compiler would no longer know `compareTo` is available.

This illustrates another reason to keep a type parameter: **constraining the behavior/capabilities of values and the type relationships among them**.

However, you should also not put `<T extends Comparable<? super T>>` on a method that only does `System.out.println(value)` when comparability is never used. Bounds make sense when the API or body **genuinely needs** the operations they promise.

## 14. When is `? extends` needed, and when is `? super` needed?

PECS — *Producer Extends, Consumer Super* — is the guide for choosing wildcards based on data direction:

| Position | Purpose | Usually appropriate signature |
| --- | --- | --- |
| Source only read as values of type `T` | Producer | `Collection<? extends T>` |
| Destination receiving values of type `T` | Consumer | `Collection<? super T>` |
| Callback accepting `T` | Consumer of `T` | `Predicate<? super T>`, `Consumer<? super T>` |
| Callback returning values used as `R` | Producer of `R` | `Function<? super T, ? extends R>` |
| Only iterating elements as `Object` | No need to name element type | `Collection<?>` |
| Need to constrain same element type in multiple places | Named `T` relationship | Generic method with `<T>` |

Do not replace **just any** `List<T>` with `List<?>` merely because it is shorter. If the method needs to **add a value `T`**, or transfer elements from a source to a compatible destination, the name `T` can be crucial.

Conversely, `<T>` is not a "bonus point" for generality if it proves no relationship. A readable `List<?>` signature is sometimes **stronger in design**, because it avoids exposing an unnecessary type variable.

## 15. Risks of switching to `List<Object>` or raw `List`

Two common off-target alternatives:

```java
static void print(List<Object> source)
```

and:

```java
static void print(List source)
```

The `List<Object>` form does not accept a `List<String>` variable due to invariance. The raw `List` form strips type arguments, brings `rawtypes` warnings, and opens the door to unchecked operations in complex code.

The appropriate form for read-only inspection:

```java
static void print(List<?> source)
```

both accepts many element types and keeps the compiler enforcing allowed limits on the data.

When a specific element kind is needed for reading, such as `Number`, choose `List<? extends Number>` instead of raw `List` plus manual casts. When exact `String` elements are needed, a `List<String>` signature can still be the right contract: not every API should use wildcards.

## 16. Negative tests: the compiler must reject improper usages

Create the file **`InvalidApiSignatures.java`**. This file **intentionally fails to compile**:

```java
import java.util.List;

public class InvalidApiSignatures {
    static void use(List<?> items) {
        items.add("bad");
    }

    static void assign(List<String> names) {
        List<Object> objects = names;
    }

    static <T> void wronglySet(
            List<T> items, Object replacement) {
        items.set(0, replacement);
    }
}
```

Run:

```bash
javac InvalidApiSignatures.java
```

With the Java compiler used for verification, three related errors appear:

```text
error: incompatible types: String cannot be converted to CAP#1
error: incompatible types: List<String> cannot be converted to List<Object>
error: incompatible types: Object cannot be converted to T
3 errors
```

**Analysis:**

1. `items.add("bad")` through `List<?>`: the compiler does not know the actual element type and cannot guarantee this string is allowed to be added.
2. `List<Object> objects = names`: generic invariance forbids the assignment; even though `String` is a subtype of `Object`, the two list types do not have that relationship.
3. `items.set(0,replacement)`: an arbitrary `Object` is not guaranteed to be `T`. Even a method naming `T` still forbids writing mistyped data.

**Remember:** removing a redundant type variable does not relax all checks. Wildcards still enforce safety constraints, and the compiler rejects operations that the source data cannot prove.

## 17. Another perspective: type variables form "type equations"

You can model some contracts as equations:

```text
identity:
    Input = T
    Output = T

repeat:
    Input = T
    Output elements = T

append:
    Source value = T
    Destination accepts any supertype of T

countIf:
    Source supplies T
    Predicate accepts any supertype of T

printValues:
    Source supplies some unknown element type
    Output = void
    No connection requiring a named T

sum:
    Source supplies subtypes of Number
    Output = primitive double
    No connection requiring original subtype T
```

If **naming** a type can be replaced with a simple data-direction description without losing information callers need, that type parameter may not belong in the public signature.

If removing the type name loses the ability to constrain two positions, weakens the return type, or breaks operations needing the same element type in the implementation, keeping the type parameter is justified.

## 18. Public API vs. implementation detail

A public method should generally expose **minimal internal detail**, while still fulfilling its contract:

```java
public static void process(List<?> input)
```

suffices if it only iterates and does not need to retain an element type name.

In the internal implementation, a private generic helper may be needed for capture:

```java
private static <T> void processCaptured(List<T> input)
```

This is not a contradiction: the **public contract** and the **implementation algorithm** operate at different levels of expressiveness.

Benefits of a minimalist public API:

- Readers do not have to hunt for "what does `T` constrain?" when it actually has no such job.
- Generic inference has fewer points to resolve.
- Javadoc focuses on what callers can genuinely rely on.
- Avoids exposing a meaningless type parameter as part of the API contract.

Yet a public API should not be simplified to the point where callers lose generic results or cross-parameter relationships. The shortest signature is not always the best signature.

## 19. Be careful when refactoring already-published APIs

When refactoring a method:

```java
public static <T> void printValues(List<T> values)
```

into:

```java
public static void printValues(List<?> values)
```

the change may preserve an equivalent **erased JVM descriptor**:

```text
(Ljava/util/List;)V
```

However, **do not conclude from having the same descriptor that changing a public API is always harmless**. There are multiple compatibility layers:

- **Source compatibility:** Some overload resolution, method references, type inference, or source-level declarations may depend on the old generic form.
- **Binary compatibility:** In simple cases, the same erased descriptor may let already-compiled code keep linking, yet you must examine the full signature, return type, inheritance, and bridge methods.
- **Reflection metadata:** `getGenericParameterTypes()` and the generic `Signature` change between `List<T>` and `List<?>`. Reflection-based frameworks can observe the difference.
- **Override/overload:** When changing signatures in a generic hierarchy, check overriding rules and post-erasure name clashes.
- **Documentation/semantic contract:** API users may interpret the old type parameter as a promise about type relationships even if the implementation did not exploit it.

For public libraries, compile **downstream callers** and run compatibility tests before changing signatures. Do not change it just because an IDE warns "type parameter used once" if the API has many users.

### Two overloads cannot differ only by wildcard vs. generic parameter with the same erasure

You cannot define two methods in the same class differing only between `List<T>` and `List<?>` with the same name and remaining parameters, because both erase to `List`. Example of an **invalid** design:

```java
// Cannot coexist in the same class:
// static <T> void process(List<T> data) {}
// static void process(List<?> data) {}
```

The compiler will report a name clash due to identical erasure. Wildcards do not create a distinct runtime overload.

## 20. Inspecting erased signatures with `javap`

After compiling `ApiSignatureDemo.java`:

```bash
javap -p -s ApiSignatureDemo
```

Excerpt from the verified run:

```text
static void printValues(java.util.List<?>);
  descriptor: (Ljava/util/List;)V

static boolean containsNull(java.util.List<?>);
  descriptor: (Ljava/util/List;)Z

static double sum(java.util.List<? extends java.lang.Number>);
  descriptor: (Ljava/util/List;)D

static <T> long countIf(
    java.util.List<? extends T>,
    java.util.function.Predicate<? super T>);
  descriptor: (Ljava/util/List;Ljava/util/function/Predicate;)J

static <T> void append(java.util.List<? super T>, T);
  descriptor: (Ljava/util/List;Ljava/lang/Object;)V

static <T> java.util.List<T> repeat(T, int);
  descriptor: (Ljava/lang/Object;I)Ljava/util/List;
```

In bytecode, generic types and wildcards in method descriptors use erased types such as `List`, `Predicate`, and `Object`. The generic `Signature` metadata can retain `T`/`?` so the compiler and reflection can inspect the declaration.

**Therefore:** the same erased descriptor does **not** mean source-level generic contracts are equivalent. The compiler still enforces generic type checking in source code. The useful constraints in `countIf`, `append`, and `repeat` remain vital even though bytecode does not generate a specialized method for each `T`.

## 21. Code review questions to ask

When you see a method declaring `<T>`, check in order:

1. **Where in the signature** does `T` appear? One input, multiple inputs, return, callback, bound?
2. Does the caller receive back a value or collection whose type is **inferred from input**?
3. Does `T` constrain a **producer** with a **consumer**?
4. Does the body need to **keep the same element type** to read and write back into the same container (wildcard capture)?
5. If `T` is removed, can the compiler still guarantee what the caller needs?
6. If only reading as `Object`, can `List<?>` or `Object` be used more clearly?
7. If only an upper bound `Number` is needed, can `? extends Number` be used without exposing `T`?
8. If the method returns a generic empty/factory value, is `T` needed for target typing?
9. Do any overloads/overrides, Java reflection, or frameworks depend on the old metadata?
10. To what extent will that change affect caller code, binary descriptors, or the generic `Signature`?

**There is no rule "if `T` appears twice, it is always valid".** A `T` appearing multiple times without constraining anything useful can still be a sign of confusing design. Conversely, a capture helper has a `T` in its internal signature that the body needs.

## 22. Easy-to-make mistakes

**Mistake 1 — "Having `<T>` always makes an API more type-safe."** A generic type variable adds no guarantee on its own if it links nothing important. `print(List<?>)` can express the contract more accurately and clearly than `<T> print(List<T>)`.

**Mistake 2 — "`T` appearing only once is a compile error."** Incorrect; many such signatures are completely valid. This is a design and readability issue, not a syntax rule.

**Mistake 3 — "Every single-occurrence `<T>` should be replaced with `?`."** Incorrect, because wildcard capture helpers and generic factories returning types from target context are cases worth keeping.

**Mistake 4 — "Replacing `List<T>` with `List<Object>` is simplest."** That can break accepting `List<String>` because Java generics are invariant. For read-only inputs, `List<?>` or `List<? extends Bound>` is usually more appropriate.

**Mistake 5 — "`List<?>` is immutable."** It disallows adding non-null elements of unknown type through that reference, yet a mutable list can still have elements removed or swapped via capture or other operations.

**Mistake 6 — "If a method does not return `T`, `<T>` is definitely unnecessary."** `countIf`/`append` still need `T` to constrain parameters, even though their return types are `long` or `void`.

**Mistake 7 — "A factory `<T> List<T> empty()` is redundant because it takes no input."** Incorrect: it can provide a typed empty list from the target context, preserving `List<String> x = empty()`.

**Mistake 8 — "A wildcard capture helper is unreasonable because `T` is only in `List<T>`."** The helper may need `T` in its body to write back values read from the same list without unchecked casts.

**Mistake 9 — "`? extends T` allows adding any `T`."** No. When a list produces subtypes of `T`, the compiler does not know the actual subtype to permit adding an arbitrary `T`. Use `? super T` when the list is a destination receiving `T`.

**Mistake 10 — "Use raw types to avoid inference issues."** Raw types strip generic constraints, lead to unchecked warnings, and can cause late `ClassCastException`. Fix the signature to match data roles instead of abandoning generic checks.

**Mistake 11 — "Any generic/wildcard refactor keeping the same erased descriptor is fully compatible."** Not true in all contexts; generic reflection, source-level inference, hierarchies, and contracts can change. A compatibility review is required.

**Mistake 12 — "A variable named `T` proves the input belongs to a distinct runtime class `T`."** Type erasure means generic types have no specialized runtime class per type argument. Type parameters express compile-time constraints.

## 23. Exercises and answers

### Exercise 1 — Choosing a signature when only displaying data

An API only iterates and prints `List<E>`, using no relationship with the result or any other parameter. Choose:

```java
static <T> void show(List<T> xs)
static void show(List<?> xs)
static void show(List<Object> xs)
```

**Answer:** `show(List<?>)` is usually clearest. `List<Object>` is too restrictive for `List<String>`/`List<Integer>`; `<T>` contributes no important relationship in this situation.

### Exercise 2 — When should input/output be constrained?

```java
static <T> T identity(T x) { return x; }
```

Should the return type be changed to `Object`?

**Answer:** no, if you want callers to retain the type inferred from `x`. `T` links the parameter and the result; changing it to `Object` weakens the static contract.

### Exercise 3 — Needing `T` despite returning void

```java
static <T> void append(List<? super T> dst, T value)
```

Is `T` actually needed?

**Answer:** yes. It constrains the type of value inserted with what the destination list can accept. You cannot replace `dst` with `List<?>` and add an arbitrary non-null `value`.

### Exercise 4 — Upper bound only for reading

A method sums `doubleValue()` of elements without returning data of type `T`. Compare:

```java
<T extends Number> double sum(List<T> values)
double sum(List<? extends Number> values)
```

**Answer:** the second option usually expresses the exact need with fewer type variables, while accepting lists of `Number` subtypes.

### Exercise 5 — Capture exception

Why is `private static <T> void swapCaptured(List<T> list,...)` useful when the public method accepts `List<?>`?

**Answer:** the helper uses `T` to keep consistent the element type retrieved from and written back into **the same list**; wildcard capture supplies a name for the unknown element type in a single call.

### Exercise 6 — Return-only factory

`static <T> List<T> empty()` takes no `T` in its inputs. Should it be replaced with `List<?>`?

**Answer:** no, if you want `List<String> names = empty()` to be verified by the compiler. `T` represents the element type chosen by the caller via target typing; an empty list is a safe implementation.

### Exercise 7 — Type inference of a predicate

`List<String> data` and `Predicate<CharSequence> predicate`. Why does `countIf(List<? extends T>,Predicate<? super T>)` accept that pair?

**Answer:** `String` can be used as `CharSequence`; the predicate accepts a supertype of the source elements. `T` connects the two parameters to express this condition.

### Exercise 8 — Overloading after erasure

Can you define both overloads simultaneously:

```java
<T> void handle(List<T> list)
void handle(List<?> list)
```

?

**Answer:** no, if they have the same method name and same remaining parameters; the erased parameter type of both is `List`, causing a name clash.

### Exercise 9 — Method only reading `Object`

`static <T> void audit(T event)` only calls `System.out.println(event)`. Is there a simpler option?

**Answer:** `static void audit(Object event)` is usually enough. No type variable is needed because there is no relationship across multiple type positions.

### Exercise 10 — Preventing confusion between `List<?>` and `List<Object>`

Why can `List<String>` be passed to `show(List<?>)` but not to `show(List<Object>)`?

**Answer:** `?` is a wildcard accepting an unknown element type via capture, whereas `List<Object>` is a concrete parameterization. Java generics are invariant.

### Exercise 11 — Binary and reflection

A public method `<T> void print(List<T>)` is changed to `void print(List<?>)`. Can the two methods share the same erased descriptor? Can it be changed without testing?

**Answer:** the descriptor can be the same `(Ljava/util/List;)V`, yet the generic `Signature` and source-level contract differ; overloads/inheritance/frameworks may be affected. Downstream callers and compatibility must be checked.

### Exercise 12 — Designing a transform API

You need to accept a list containing subtypes of `T`, transform each element with a `Function` accepting `T` or a supertype, and return `List<R>` where the mapper can produce subtypes of `R`. Which signature fits?

```java
static <T, R> List<R> map(
        List<? extends T> source,
        Function<? super T, ? extends R> mapper)
```

**Answer:** this is the way to express a safe, flexible contract: `source` is a producer of `T`, `mapper` is a consumer of `T`/producer of `R`, and the result has element type `R`. Both type variables are necessary because they link multiple type positions.

## 24. Generic API design checklist

- [ ] Can I explain precisely which positions `T` links?
- [ ] If the method only inspects any container, have I considered `List<?>`?
- [ ] If the method only inspects a subtype of `Number`, have I considered `? extends Number`?
- [ ] If the method only takes one object without returning/comparing by the same type, is `Object` enough?
- [ ] If the output must preserve the type from input, have I kept `<T>`?
- [ ] If a producer/consumer relationship is needed, have I chosen `? extends T`/`? super T` correctly?
- [ ] If elements must be written back into the same unknown-type list, have I used a capture helper instead of an unchecked cast?
- [ ] If a generic factory returns an empty collection, have I kept a useful typed output for callers?
- [ ] If there is a bound `Comparable<? super T>`, does the API actually use comparability?
- [ ] Have raw types and unprovable casts been avoided?
- [ ] Have I verified both subtype sources and supertype callbacks with `javac`?
- [ ] If it is a published API, have I checked generic `Signature`, callers, overloads, and compatibility?
- [ ] Do not treat `List<?>` as immutable or `List<Object>` as a supertype of `List<String>`.
- [ ] I only shorten signatures **when no required type relationship is lost**, rather than refactoring mechanically.

## Conclusion

A named type parameter like `T` earns its place when it **conveys a constraint**: connecting input to output, connecting source to destination/callback, expressing a self-bound, or enabling wildcard capture in the implementation. If a method only uses one element kind in a single position with no further constraints, a **wildcard `?`** or a concrete supertype like `Object`/`Number` usually makes the API easier to understand.

Therefore, **"avoid type parameters that appear only once" is a guiding heuristic, not a text-replacement rule**. Always examine the public contract, method body, generic return-only factories, capture helpers, and compatibility before modifying. Good design neither maximizes the count of `<T>` nor minimizes them at all costs — it expresses **the exact type relationships callers need the compiler to protect**.