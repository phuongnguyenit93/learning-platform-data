# Generics in `Optional` and Type Relationships During Data Transformation (Java 17)

## 1. Problem: a value may be absent, yet its type still needs to be preserved

In Java, a lookup can **find** or **fail to find** data. Returning `null` directly forces callers to remember checks and easily causes `NullPointerException`:

```java
String name = repository.findName(id); // May be null.
System.out.println(name.length());      // May throw NullPointerException.
```

`java.util.Optional<T>` more clearly expresses that a result may be absent:

```java
Optional<String> name = repository.findName(id);
```

Here:

- `Optional` is a generic class.
- `T` is the type of **the contained value**, such as `String`, `User`, `Integer`.
- An `Optional<T>` can hold a non-null value of type `T`, or be **empty**.
- Callers handle presence/absence through APIs such as `map`, `flatMap`, `filter`, `orElseGet`, `orElseThrow`, and `stream`.

Generics questions arise when **transforming** data: an `Optional<User>` may need to become `Optional<String>`, or a transformation may already return `Optional<Profile>` and you must avoid producing `Optional<Optional<Profile>>`. To handle this well, you must understand **the type relationship between input, mapper, and output**, as well as the difference between `map` and `flatMap`.

This lesson covers Generics in Optional, Java 17 syntax, type inference, wildcard variance, collections of Optional, null handling, and common mistakes. The main example is a standalone program compiled/run with `javac --release 17 -Xlint:all` with verified stdout.

## 2. Recognizing the exact contract of `Optional<T>`

An `Optional<String>` **is not** a `String`. It is a container capable of holding a `String`.

```java
Optional<String> present = Optional.of("Java");
Optional<String> absent = Optional.empty();
```

To read it, you cannot assign directly:

```java
// Does not compile:
// String text = present;
```

You must explicitly choose a policy for when a value is present or empty, such as:

```java
String text = present.orElse("N/A");
```

As a result, the API no longer implicitly forces callers to guess whether a return value could be `null`.

### 2.1. Factory methods

| API | Input | If value is `null` | Result |
| --- | --- | --- | --- |
| `Optional.of(value)` | A reference **required to be non-null** | Throws `NullPointerException` | Optional with value |
| `Optional.ofNullable(value)` | Nullable reference | Returns `Optional.empty()` | Value or empty |
| `Optional.empty()` | Takes no input | Not applicable | Empty Optional |

Example:

```java
Optional<String> a = Optional.of("x");
Optional<String> b = Optional.ofNullable(null);
Optional<String> c = Optional.empty();
```

`b` and `c` are both empty. Do not compare identity with `==` to detect empty; use `isEmpty()`, `isPresent()`, or appropriate operations.

### 2.2. Optional is a value-based class

Java documentation describes `Optional` as a **value-based class**. Do not rely on identity, synchronize on Optional instances, or assume empty instances always share the same reference. Focus on **value/semantics** via Optional's API, not which wrapper object identity exists.

### 2.3. `Optional` does not replace every object or collection

If a natural result is “no elements”, an empty `List<T>` is usually clear enough. `Optional<List<T>>` introduces **two distinct states**:

- `Optional.empty()` — no list result.
- `Optional.of(List.of())` — a list result exists, and the list is empty.

Use this two-layer representation only when the distinction has domain meaning. Do not mechanically wrap every value in a codebase into `Optional<T>`.

## 3. `Optional<T>` is generically invariant

Java Generics are not automatically covariant simply because type arguments have a subtype relationship.

```java
Integer number = 7;
Number parent = number; // Valid.
```

Yet with a variable whose type is already fixed:

```java
Optional<Integer> integers = Optional.of(7);

// Does not compile:
// Optional<Number> numbers = integers;
```

`Optional<Integer>` is **not a subtype** of `Optional<Number>`. This is just like `List<Integer>` not automatically being a `List<Number>`.

### 3.1. Why does `Optional<Number> x = Optional.of(7)` compile?

This is an important detail about **generic method inference**:

```java
Optional<Number> numbers = Optional.of(7);
```

This line is **valid** on Java 17. `Optional.of` is a generic factory method:

```java
public static <T> Optional<T> of(T value)
```

When inferring `T`, the compiler can consider **the target type `Optional<Number>`** alongside the boxed `Integer` value. It picks a type argument satisfying both the call and assignment constraints.

That **does not make Java Generics covariant**. Once the result is stored in an `Optional<Integer>` variable, you cannot assign that variable directly to `Optional<Number>`.

Compare clearly:

```java
Optional<Number> direct = Optional.of(7); // Valid.

Optional<Integer> integers = Optional.of(7);
// Optional<Number> reassigned = integers; // Invalid.
```

This is the difference between **type inference when constructing a new generic value** and **subtyping between two already-fixed parameterized types**.

### 3.2. Use wildcards when you only need to read a supertype

If a method only needs to read a Number:

```java
static double doubled(Optional<? extends Number> input) {
    return input.map(n -> n.doubleValue() * 2).orElse(0.0);
}
```

Callers can pass `Optional<Integer>` or `Optional<Double>`:

```java
double a = doubled(Optional.of(7));
double b = doubled(Optional.of(1.5));
```

`? extends Number` expresses that the contained element is guaranteed to be some subtype of `Number`, matching a **producer** role: we read a `Number` and call `doubleValue()`.

Do not write `Optional<Number>` if the method really wants to accept Optionals of various subtypes without needing to mutate the wrapper/input value.

### 3.3. When you genuinely need `Optional<Number>`

You can transform explicitly:

```java
Optional<Integer> ints = Optional.of(7);
Optional<Number> numbers = ints.map(n -> (Number) n);
```

This **creates a new Optional in API terms**, not a covariant assignment between two already-typed generic variables. The lambda tells the compiler the mapper's return type is `Number`, yielding `U = Number` for `map`.

Another option in suitable contexts is a type witness or providing a target type when creating a new Optional. Never treat a type witness as a way to bypass prohibited generic relationships.

## 4. The generic signature of `map`: from `T` to `U`

In Java 17, the key signature on `Optional<T>` is:

```java
public <U> Optional<U> map(
        Function<? super T, ? extends U> mapper)
```

Broken into four parts:

1. `T` is the **current type** of the Optional.
2. `<U>` is the **new type parameter of method `map`**: the result type after transformation.
3. `Function<? super T, ? extends U>` takes a value compatible with `T` and returns a value compatible with `U`.
4. `Optional<U>` is the wrapper around the **transformed result**.

Example:

```java
Optional<String> name = Optional.of("Java");
Optional<Integer> length = name.map(String::length);
```

Before `map`: `T = String`.

Mapper: `String -> Integer` (the primitive `int` result is boxed).

After `map`: `U = Integer`, resulting in `Optional<Integer>`.

There are no casts in caller code. The compiler preserves type relationships via functional interfaces and generic type inference.

### 4.1. Why is Function's input `? super T`?

`? super T` lets the mapper accept **a supertype** of `T`, because the mapper acts as a **consumer** of the value supplied by Optional.

Example:

```java
Function<Object, String> stringify = Object::toString;
Optional<String> input = Optional.of("Java");

Optional<String> output = input.map(stringify);
```

Even though the mapper takes `Object`, it can handle a `String`. There is no need to force `Function<String,String>` when a `Function<Object,String>` already suffices.

### 4.2. Why is Function's output `? extends U`?

The mapper's result is a **producer** of `U`: it can return a compatible subtype rather than requiring every declaration's signature to return `U` literally.

This uses the **PECS** rule: *Producer Extends, Consumer Super*. However, PECS is a mnemonic for wildcard direction, not a substitute for understanding `Function` semantics and inference constraints.

### 4.3. A generic helper using `map`

```java
static <T, U> Optional<U> transform(
        Optional<T> input,
        Function<? super T, ? extends U> mapper) {
    return input.map(mapper);
}
```

Caller:

```java
Optional<Integer> length =
        transform(Optional.of("abc"), CharSequence::length);
```

Here `CharSequence::length` can accept String because String implements CharSequence. The result is boxed to `Integer`. Java 17 compiled this example and the program prints:

```text
transform=3
```

A generic helper design should still validate null input or null mapper per its own contract, rather than assuming generic type parameters automatically prevent null references.

## 5. `map` only executes the mapper when a value is present

With:

```java
Optional<String> name = Optional.of(" Java ");
Optional<String> normalized = name.map(String::strip);
```

The mapper receives `" Java "` and returns `"Java"`.

If the input is empty:

```java
Optional<String> empty = Optional.<String>empty();
Optional<Integer> result = empty.map(String::length);
```

`result` remains empty; the lambda/method reference is never invoked.

This enables writing pipelines where each step runs only when previous steps actually contain data. There is no need for nested `if (value != null)` checks just to pass results through sequential transformations.

### 5.1. What if `map` receives a null result?

A subtle difference:

```java
Optional<String> result =
        Optional.of("x").map(x -> (String) null);

System.out.println(result.isEmpty()); // true
```

`map` applies semantics equivalent to `ofNullable` on the **mapper's return value**: if the mapper returns `null`, the resulting Optional becomes empty. It does not create an `Optional` “containing null”.

However, if the **mapper argument itself is null**:

```java
// Invalid at runtime:
// Optional.of("x").map(null);
```

the method rejects a null mapper with `NullPointerException`. Distinguish “mapper returns null” from “mapper is null”.

### 5.2. `map` does not silently swallow exceptions

If the mapper throws `NumberFormatException`:

```java
Optional<Integer> number =
        Optional.of("not-an-int").map(Integer::parseInt);
```

the exception still propagates to the caller. Optional **does not** turn arbitrary exceptions into empty.

If “unparseable” is a normal business state, write a dedicated mapper or conversion helper that handles the error explicitly, e.g., returning `Optional<Integer>` and using `flatMap`.

## 6. `filter`: filtering without changing type `T`

Corresponding signature:

```java
public Optional<T> filter(Predicate<? super T> predicate)
```

`filter` simply tests a condition on the present value:

```java
Optional<String> candidate = Optional.of("  Java  ");

Optional<String> nonBlank = candidate
        .map(String::strip)
        .filter(s -> !s.isEmpty());
```

If the predicate returns true, the value is kept; if false, it becomes empty. If Optional is already empty, the predicate does not run.

**The result type remains `Optional<T>`**, unlike `map` which can change `T` to `U`.

Example:

```java
Optional<Integer> positive = Optional.of(7)
        .filter(n -> n > 0);
```

`positive` is `Optional<Integer>`; no new `U` is introduced by `filter`.

### 6.1. Order of operations matters

```java
Optional<String> cleaned = Optional.of("  ")
        .map(String::strip)
        .filter(s -> !s.isBlank());
```

The string `"  "` is stripped to `""`, then removed by filter. With a different pipeline or different condition, data may be handled differently. `map` and `filter` are not arbitrarily commutative.

## 7. `map` creates nested Optionals when the mapper already returns an Optional

Suppose we look up User details:

```java
record Profile(String city) {}
record User(String name, Optional<Profile> profile) {}

static Optional<User> findUser(int id) {
    if (id == 1) {
        return Optional.of(new User(
                "Lan", Optional.of(new Profile("Hanoi"))));
    }
    return Optional.empty();
}
```

You want to obtain `Profile` from `Optional<User>`.

If you use `map`:

```java
Optional<Optional<Profile>> nested =
        findUser(1).map(User::profile);
```

Because `User.profile()` **already returns `Optional<Profile>`**, generic inference on `map` resolves:

- Input `T = User`.
- Mapper result `U = Optional<Profile>`.
- Return `Optional<U> = Optional<Optional<Profile>>`.

Two layers of Optional mean two nested absence structures. This is usually **unnecessary** in data-lookup pipelines.

### 7.1. Distinguishing two `map` calls with the same method name

`Optional<User>.map(User::name)` makes sense if `User.name()` returns a `String`.

Yet `Optional<User>.map(User::profile)` produces a nested Optional if `User.profile()` returns `Optional<Profile>`.

The difference comes from **the actual return type of the mapper**; the compiler is not randomly adding an extra Optional layer.

## 8. `flatMap`: transformations that already return an Optional

Signature of `flatMap` in Java 17:

```java
public <U> Optional<U> flatMap(
    Function<? super T, ? extends Optional<? extends U>> mapper)
```

The most important points:

- The mapper accepts a `T`-compatible value.
- The mapper **must return an `Optional`** holding a `U`-compatible type.
- `flatMap` does not wrap an extra Optional layer; the final result is `Optional<U>`.

Example:

```java
Optional<Profile> profile =
        findUser(1).flatMap(User::profile);
```

Instead of `Optional<Optional<Profile>>`, we get `Optional<Profile>` directly.

To get the city:

```java
Optional<String> city = findUser(1)
        .flatMap(User::profile)
        .map(Profile::city);
```

The pipeline does three things statically:

1. `findUser(1)` has type `Optional<User>`.
2. `.flatMap(User::profile)` becomes `Optional<Profile>`.
3. `.map(Profile::city)` becomes `Optional<String>`.

If any step is empty, subsequent steps have no value to run on and the whole pipeline returns empty.

### 8.1. Why does `flatMap`'s signature have two `extends`?

`? super T` expresses that the mapper can accept a broader type than `T`.

`? extends Optional<? extends U>` expresses that the mapper can produce a valid subtype of the Optional container holding a subtype compatible with `U`. The signature supports varied mapper styles and subtype relationships without manual casts.

To use it effectively, you rarely need to memorize the signature verbatim; just remember **the Function must return an Optional** and the compiler infers `U` from the inner value's type.

### 8.2. `flatMap` rejects mappers returning null

Unlike `map`:

```java
Optional.of("x")
        .flatMap(s -> (Optional<String>) null);
```

on a non-empty Optional throws `NullPointerException`. `flatMap`'s mapper must return a non-null **Optional object**: either present or `Optional.empty()`.

To represent absence, return:

```java
Optional.<String>empty()
```

Do not return `null`.

### 8.3. `flatMap` is not just `map` with a different name

If the mapper returns a plain value, such as `Integer.parseInt(s)` of type `int`/`Integer`, use:

```java
Optional<Integer> number =
        Optional.of("7").map(Integer::parseInt);
```

Do not use:

```java
// Does not compile:
// Optional.of("7").flatMap(Integer::parseInt);
```

The compiler reports `int cannot be converted to Optional<? extends U>` because `flatMap`'s signature requires the mapper to return an Optional.

## 9. Choosing `map` or `flatMap` by mapper return type

| Initial type | Mapper | Use | Result type |
| --- | --- | --- | --- |
| `Optional<String>` | `String -> Integer` | `map` | `Optional<Integer>` |
| `Optional<User>` | `User -> String` | `map` | `Optional<String>` |
| `Optional<User>` | `User -> Optional<Profile>` | `map` | `Optional<Optional<Profile>>` |
| `Optional<User>` | `User -> Optional<Profile>` | `flatMap` | `Optional<Profile>` |
| `Optional<Profile>` | `Profile -> String` | `map` | `Optional<String>` |
| `Optional<T>` | `T -> boolean` | `filter` with `Predicate` | `Optional<T>` kept or empty |

A quick check:

- Mapper returns **`U`** → `map`, Optional wraps `U`.
- Mapper returns **`Optional<U>`** → `flatMap`, avoiding nested wrappers.
- Only testing true/false on `T` → `filter`.

Do not replace `flatMap` with `.map(...).get()` to “unwrap” an Optional. Calling `.get()` on empty throws `NoSuchElementException`, defeating the safe pipeline.

## 10. Transforming data across multiple Optional layers

Example finding a User's city:

```java
static Optional<String> cityFor(int id) {
    return findUser(id)
            .flatMap(User::profile)
            .map(Profile::city);
}
```

If `findUser(1)` has a User, Profile, and city, the result is `Optional.of("Hanoi")`.

If `findUser(9)` is empty, the result is empty. The caller chooses a fallback value:

```java
String city = cityFor(9).orElse("?");
```

If User exists while `profile()` is empty, `flatMap` also yields empty. This is a transformation chain **without** deeply nested if/else blocks.

### 10.1. Information about why a value is absent can be lost

An Optional pipeline typically records only “present” or “empty”; it does not explain:

- User does not exist.
- User exists, but has no Profile yet.
- Profile exists, but city was not provided.

If the application needs to distinguish these states for logging or API errors, `Optional<T>` may not suffice. Consider a domain result with status codes, a sealed hierarchy, or an application/library-provided Result/Either type.

### 10.2. Do not casually call Optional an “effect/exception monad”

`map`/`flatMap` provide a useful container-transformation model, yet Java's `Optional` does not automatically wrap checked exceptions, accumulate validation errors, or provide logging/transaction semantics. When those are needed, add appropriate abstractions rather than abusing `.orElse(null)`.

## 11. `Optional.or`: when the fallback is also an Optional

Java 9+ provides the method:

```java
public Optional<T> or(
    Supplier<? extends Optional<? extends T>> supplier)
```

If the current Optional has a value, it returns the current Optional. If empty, it calls the Supplier to obtain a **fallback Optional**, not just a `T` value.

```java
Optional<String> result = Optional.<String>empty()
        .or(() -> Optional.of("alternate"));
```

`result` is an `Optional<String>` holding `"alternate"`.

Distinguish:

- `orElse(T other)`: returns **T**; the fallback is evaluated before the call per Java rules.
- `orElseGet(Supplier<? extends T>)`: returns **T**; the Supplier is called only when empty.
- `or(Supplier<? extends Optional<? extends T>>)`: returns **Optional<T>**; the Supplier must return a non-null Optional when called.

`or` is useful for chaining fallback lookup sources:

```java
Optional<String> value = fromCache()
        .or(() -> fromDatabase());
```

This is an illustrative snippet where helpers `fromCache()` and `fromDatabase()` return compatible Optionals. If the cache has a value, the second supplier never runs.

## 12. `orElse` and `orElseGet`: eager vs. lazy

Suppose:

```java
Optional<String> existing = Optional.of("ready");
```

Two calls look similar in result:

```java
String a = existing.orElse(computeFallback());
String b = existing.orElseGet(() -> computeFallback());
```

Yet their evaluation differs:

- `orElse(computeFallback())`: Java must **evaluate the argument `computeFallback()` before calling** `orElse`, even when the Optional already has a value.
- `orElseGet(() -> computeFallback())`: passes a Supplier; `computeFallback()` runs only if the Optional is empty.

Example using a counter:

```java
AtomicInteger calls = new AtomicInteger();

String eager =
        existing.orElse(expensiveFallback(calls));
String lazy =
        existing.orElseGet(() -> expensiveFallback(calls));
```

If `expensiveFallback` increments the counter, after these two lines the counter is `1`. Both `eager` and `lazy` equal `"ready"`, yet the eager fallback executed once.

When:

```java
Optional.<String>empty()
        .orElseGet(() -> expensiveFallback(calls));
```

the supplier runs and the counter increases to `2`.

### 12.1. Simple rule of thumb

Use `orElse("N/A")` for constants or cheap, already-available values.

Use `orElseGet(this::expensiveLookup)` when the fallback requires computation, external system calls, logging, expensive object creation, or side effects that should happen only when empty.

`orElseGet` is not “always faster” in every case; the core difference is **when the fallback executes** and side-effect semantics.

### 12.2. `orElseThrow` when absence is an error

If the value must exist:

```java
String name = optionalName.orElseThrow(
        () -> new IllegalStateException("Name missing"));
```

And `optionalName.orElseThrow()` (Java 10+) throws `NoSuchElementException` if empty.

Use exceptions only when a missing value is genuinely exceptional under the contract; do not throw and immediately catch just to model a routine condition.

## 13. `ifPresent`, `ifPresentOrElse`, and `get()`

Sometimes instead of transforming an Optional into another Optional, you want to perform an action:

```java
optionalName.ifPresent(System.out::println);
```

`ifPresent` takes `Consumer<? super T>` and returns `void`. Do not use it in place of `map` when you want a transformed value for further steps.

Java 9+ provides:

```java
optionalName.ifPresentOrElse(
        value -> System.out.println(value),
        () -> System.out.println("missing"));
```

One action runs if present and a Runnable runs if empty.

`Optional.get()` returns the value when present but throws `NoSuchElementException` when empty. In new code, it is usually clearer to use `orElseThrow`, or transform via `map`/`flatMap` and handle fallback once at the boundary.

### 13.1. Anti-pattern: `isPresent()` followed by `get()` everywhere

```java
if (maybeUser.isPresent()) {
    User user = maybeUser.get();
    // ...
}
```

Not always wrong, yet for a simple transformation it can be clearer and more consistent as:

```java
Optional<String> name = maybeUser.map(User::name);
```

`map` keeps logic inside the pipeline without writing empty checks at every step. Use `ifPresent` when you genuinely want a side effect rather than transforming a return value.

## 14. `Optional.stream()` helps integrate with `Stream<T>`

Java 9+ added:

```java
Stream<T> stream()
```

- Present Optional → Stream with exactly **one** element.
- Empty Optional → empty Stream.

This makes flattening a stream of Optionals straightforward:

```java
List<Integer> found = Stream.of(
        Optional.of(2),
        Optional.<Integer>empty(),
        Optional.of(5))
    .flatMap(Optional::stream)
    .toList();
```

Java 17 prints:

```text
stream=[2, 5]
```

Here `Stream.flatMap` differs from `Optional.flatMap`, yet shares the same idea: the mapper produces a compatible structure, and `flatMap` merges resulting structures to avoid unnecessary nesting.

`Stream.toList()` was added in Java 16 and returns an unmodifiable list per API contract. If a mutable list is needed, choose a collector or explicitly copy.

### 14.1. `List<Optional<T>>` vs. `Optional<List<T>>`

`List<Optional<String>>` means **multiple positions**, where each position may hold or lack a string.

`Optional<List<String>>` means **the entire list result may be present or absent**, and when present, list elements are constrained by generic `String`.

To drop empty positions in `List<Optional<T>>`:

```java
List<String> names = optionals.stream()
        .flatMap(Optional::stream)
        .toList();
```

This snippet assumes `optionals` is `List<Optional<String>>`. It keeps present values and discards empty entries, thereby **losing information about which positions were originally missing**. If positions carry domain meaning, do not flatten this way without tracking indices or explicit state.

## 15. Runnable Java 17 example: Optional transformations and Generics

Create the file **`OptionalGenericsDemo.java`**:

```java
import java.util.List;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Function;
import java.util.stream.Stream;

public class OptionalGenericsDemo {
    record Profile(String city) {}
    record User(String name, Optional<Profile> profile) {}

    static Optional<User> findUser(int id) {
        if (id == 1) {
            return Optional.of(new User(
                    "  Lan  ", Optional.of(new Profile("Hanoi"))));
        }
        return Optional.empty();
    }

    static Optional<String> cityFor(int id) {
        return findUser(id).flatMap(User::profile)
                .map(Profile::city);
    }

    static <T, U> Optional<U> transform(
            Optional<T> input,
            Function<? super T, ? extends U> mapper) {
        return input.map(mapper);
    }

    static Optional<Number> toNumber(Optional<Integer> input) {
        return input.map(n -> (Number) n);
    }

    static double doubled(Optional<? extends Number> input) {
        return input.map(n -> n.doubleValue() * 2)
                .orElse(0.0);
    }

    static String expensiveFallback(AtomicInteger calls) {
        calls.incrementAndGet();
        return "fallback";
    }

    public static void main(String[] args) {
        Optional<String> raw = Optional.ofNullable("  Java  ");
        Optional<Integer> length = raw.map(String::strip)
                .filter(s -> !s.isEmpty())
                .map(String::length);
        System.out.println("length=" + length.orElse(-1));

        System.out.println("map-null-empty="
                + Optional.of("x")
                .map(x -> (String) null).isEmpty());

        Optional<Optional<Profile>> nested =
                findUser(1).map(User::profile);
        System.out.println("nested=" + nested.isPresent());
        System.out.println("city=" + cityFor(1).orElse("?"));
        System.out.println("missing-city=" + cityFor(9).orElse("?"));

        System.out.println("transform="
                + transform(Optional.of("abc"),
                        CharSequence::length).orElse(-1));

        System.out.println("number="
                + toNumber(Optional.of(7)).orElse(-1));
        System.out.println("covariant="
                + doubled(Optional.of(7)));

        List<Integer> values = Stream.of(
                Optional.of(2),
                Optional.<Integer>empty(),
                Optional.of(5))
                .flatMap(Optional::stream).toList();
        System.out.println("stream=" + values);

        Optional<String> restored = Optional.<String>empty()
                .or(() -> Optional.of("alternate"));
        System.out.println("or=" + restored.orElse("?"));

        AtomicInteger calls = new AtomicInteger();
        Optional<String> existing = Optional.of("ready");
        String eager = existing.orElse(expensiveFallback(calls));
        String lazy = existing.orElseGet(
                () -> expensiveFallback(calls));

        System.out.println("fallback=" + eager + ","
                + lazy + "," + calls.get());
        System.out.println("empty-lazy="
                + Optional.<String>empty()
                .orElseGet(() -> expensiveFallback(calls))
                + "," + calls.get());

        List<String> names = Stream.of("a", "", "bc")
                .map(OptionalGenericsDemo::nonBlank)
                .flatMap(Optional::stream).toList();
        System.out.println("names=" + names);

        try {
            Optional.of("x")
                    .flatMap(x -> (Optional<String>) null);
        } catch (NullPointerException e) {
            System.out.println("flatmap-null="
                    + e.getClass().getSimpleName());
        }

        try {
            Optional.ofNullable(null).orElseThrow();
        } catch (java.util.NoSuchElementException e) {
            System.out.println("empty-get="
                    + e.getClass().getSimpleName());
        }
    }

    static Optional<String> nonBlank(String text) {
        return Optional.ofNullable(text)
                .map(String::strip)
                .filter(x -> !x.isEmpty());
    }
}
```

Run from the directory containing the file:

```bash
javac --release 17 -Xlint:all OptionalGenericsDemo.java
java OptionalGenericsDemo
```

The program compiled successfully on Java 17 with zero warnings under `-Xlint:all`. **Exact stdout**:

```text
length=4
map-null-empty=true
nested=true
city=Hanoi
missing-city=?
transform=3
number=7
covariant=14.0
stream=[2, 5]
or=alternate
fallback=ready,ready,1
empty-lazy=fallback,2
names=[a, bc]
flatmap-null=NullPointerException
empty-get=NoSuchElementException
```

### 15.1. Reading `length=4`

`Optional.ofNullable("  Java  ")` is present, so `map(String::strip)` produces `"Java"`, `filter` retains the non-empty value, and `map(String::length)` transforms to `Optional<Integer>` holding `4`.

### 15.2. Reading `map-null-empty=true`

When the mapper in `map` returns null, the resulting Optional is empty. This is intentional behavior of `map`, not an Optional holding a null value.

### 15.3. Reading `nested=true`

`findUser(1).map(User::profile)` has type `Optional<Optional<Profile>>` because `profile()` already returns an Optional. `nested.isPresent()` being true means the outer Optional holds a value, **not proving the inner Optional is always present**. To get Profile directly, use `flatMap`.

### 15.4. Reading `city` and `missing-city`

`cityFor(1)` uses `flatMap` then `map`, returning `Hanoi`. `cityFor(9)` is empty right from the User lookup, so fallback `"?"` is used.

### 15.5. Reading `transform`, `number`, `covariant`

`transform` accepts `CharSequence::length` on String because the mapper has input wildcard `? super T`. `toNumber` turns `Optional<Integer>` into `Optional<Number>` via `map` without wrapper casts. `doubled(Optional<? extends Number>)` accepts an Optional holding Integer and returns `14.0`.

### 15.6. Reading `stream` and `names`

`Optional.stream()` turns each Optional into a 0- or 1-element stream. `flatMap(Optional::stream)` drops empty entries, producing `[2, 5]`. The `nonBlank` pipeline similarly drops blank strings, keeping `[a, bc]`.

### 15.7. Reading `fallback` and `empty-lazy`

With an Optional holding `"ready"`, `orElse`'s argument executes eagerly, incrementing the counter to 1 even though the fallback is unused. `orElseGet` on a present Optional does not invoke the Supplier. The next empty case does invoke the Supplier, increasing the counter to 2.

### 15.8. Reading the last two exceptions

`flatMap` rejects a mapper returning null, throwing `NullPointerException`. `orElseThrow()` on an empty Optional throws `NoSuchElementException`. These two errors have distinct causes and should not all be lumped into “Optional is broken”.

## 16. Intentionally non-compiling examples: understanding inference errors and type relationships

The following snippets are **separate files**; do not copy them into the main runnable program file.

### 16.1. `BadInvariant.java`: variable with an already-fixed type

```java
import java.util.Optional;

class BadInvariant {
    static void check() {
        Optional<Integer> integers = Optional.of(7);
        Optional<Number> numbers = integers;
    }
}
```

Run:

```bash
javac --release 17 BadInvariant.java
```

The compiler reports:

```text
error: incompatible types:
Optional<Integer> cannot be converted to Optional<Number>
```

This is **generic invariance**. Use `Optional<? extends Number>` for code that only reads Number, or use `map` if you genuinely need to convert the result to Optional<Number>.

Remember to distinguish this example from `Optional<Number> numbers = Optional.of(7)`, which **does compile** thanks to target-type inference.

### 16.2. `BadMapNested.java`: using `map` when the mapper returns Optional

```java
import java.util.Optional;

class BadMapNested {
    static Optional<Integer> make() {
        return Optional.of("7")
                .map(s -> Optional.of(Integer.parseInt(s)));
    }
}
```

Compile:

```bash
javac --release 17 BadMapNested.java
```

The compiler reports **incompatible bounds** for inference variable `U`. The mapper returns `Optional<Integer>`, so `.map(...)` creates `Optional<Optional<Integer>>`, rather than the `Optional<Integer>` required by the return type.

Fix to:

```java
return Optional.of("7")
        .flatMap(s -> Optional.of(Integer.parseInt(s)));
```

If the mapper simply returns `Integer`, using `map(Integer::parseInt)` is even simpler.

### 16.3. `BadFlatMap.java`: mapper does not return Optional

```java
import java.util.Optional;

class BadFlatMap {
    static Optional<Integer> make() {
        return Optional.of("7")
                .flatMap(Integer::parseInt);
    }
}
```

Compile:

```bash
javac --release 17 BadFlatMap.java
```

The compiler rejects it because the method reference produces `int`, which **cannot be converted to** `Optional<? extends U>` required by `flatMap`.

Fix with `map(Integer::parseInt)` since the mapper returns a plain value.

### 16.4. `BadMapType.java`: mismatched result type

```java
import java.util.Optional;

class BadMapType {
    static Optional<Integer> make() {
        return Optional.of("java")
                .map(String::toUpperCase);
    }
}
```

Run:

```bash
javac --release 17 BadMapType.java
```

`String::toUpperCase` returns `String`; the method declares `Optional<Integer>`. The compiler reports incompatible bounds on inference variable `U` with constraints `Integer` and `String`.

Either change the mapper to actually produce `Integer`, or change the return type to `Optional<String>` per design intent.

### 16.5. These errors differ from runtime exceptions

The four files above **do not compile**. They are type-system/inference errors. By contrast, a type-valid mapper throwing `NumberFormatException`, or `flatMap` returning null, is a **runtime** failure.

Therefore, when debugging, distinguish “the compiler could not infer a `U` satisfying constraints” from “the mapper ran and failed on input data”.

## 17. Type continuity across long pipelines

For a pipeline:

```java
Optional<String> city =
        findUser(id)
            .flatMap(User::profile)
            .map(Profile::city)
            .filter(s -> !s.isBlank());
```

you can write a type table after each step:

| Step | Static type | Meaning |
| --- | --- | --- |
| `findUser(id)` | `Optional<User>` | User may not exist |
| `.flatMap(User::profile)` | `Optional<Profile>` | User may not have a Profile |
| `.map(Profile::city)` | `Optional<String>` | City string if prior steps had values |
| `.filter(s -> !s.isBlank())` | `Optional<String>` | Excludes whitespace-only cities |
| `.orElse("Unknown")` | `String` | Turns Optional into a regular value with fallback |

Writing down static types step by step is a very effective diagnostic technique when `javac` reports incompatible inference bounds.

### 17.1. Refactor into local variables to read errors more easily

If a long chain:

```java
var result = a.flatMap(...).map(...).flatMap(...).filter(...);
```

produces confusing diagnostics, split it into:

```java
Optional<User> user = findUser(id);
Optional<Profile> profile = user.flatMap(User::profile);
Optional<String> city = profile.map(Profile::city);
```

The compiler will pinpoint errors closer to the step causing the type mismatch, while improving readability and testability.

### 17.2. Do not force every step into one Optional

If a step needs logging, collecting multiple errors, or asynchronous handling, a pure Optional chain may not express enough semantics. You can split the logic or switch abstractions. The goal is clear type relationships, not squeezing everything into a single statement.

## 18. Generic methods using `Optional<? extends T>` at API boundaries

Suppose a function only needs to read a number:

```java
static double doubled(Optional<? extends Number> input) {
    return input.map(n -> n.doubleValue() * 2)
            .orElse(0.0);
}
```

It accepts `Optional<Integer>`, `Optional<Long>`, and `Optional<Double>`, yet does not turn the input into `Optional<Number>` for assignment.

Another generic helper:

```java
static <T, U> Optional<U> transform(
        Optional<T> input,
        Function<? super T, ? extends U> mapper) {
    return input.map(mapper);
}
```

can preserve typed relationships between input and output. Still, sometimes writing `input.map(mapper)` directly is clearer; do not introduce a new generic abstraction if it adds no design value.

### 18.1. PECS in Optional

PECS helps remember:

- `? extends Number` in `Optional<? extends Number>`: producer of Number.
- `? super T` in `Function<? super T,...>`: mapper can consume `T`.
- `? extends U` in `Function<...,? extends U>`: mapper produces `U` or a subtype.
- `? extends Optional<? extends U>` in `flatMap`: mapper produces an Optional containing a type compatible with `U`.

PECS does not let you arbitrarily insert/mutate a value inside Optional; `Optional<T>` has no `set(T)`. Wildcards are used here for **type acceptability and inference**, not mutating container contents.

## 19. Avoid overusing `Optional<T>` in data and APIs

### 19.1. Optional fits potentially absent return results

A clear API example:

```java
Optional<User> findById(long id);
```

Callers are reminded to handle the not-found case. That is usually clearer than returning `User` with a vague doc comment saying “may be null”.

### 19.2. Think carefully before using Optional as a field or parameter

Many codebases prefer using Optional primarily as a **return type** and using regular domain types for fields/parameters, especially when serialization/ORM frameworks do not support Optional as desired. This is contextual design advice, not an absolute Java prohibition.

A constructor parameter `Optional<String>` can force callers to always wrap values, even when the policy could be expressed more cleanly via overloads or a config object. For persisted fields, verify framework support before using Optional.

### 19.3. Never return `null` instead of an empty Optional

A method returning `Optional<T>` should never return `null`:

```java
// Not recommended:
// return null;
```

If no value exists, return `Optional.empty()`. Returning null for the Optional wrapper itself strips callers of the guarantee to handle absence via `map`/`flatMap`.

### 19.4. Do not compare Optionals with `==`

Optional is value-based; use `equals`/state checks rather than identity comparison. Also never synchronize on an Optional object.

## 20. Debugging common errors and behaviors

| Symptom | Common cause | How to resolve |
| --- | --- | --- |
| `Optional<Integer> cannot be converted to Optional<Number>` | Generic invariance on a variable with fixed type argument | Use `Optional<? extends Number>` for read-only, or `map` to produce Optional<Number> |
| `inference variable U has incompatible bounds` after `map` | Mapper return type disagrees with expected output, or returns nested Optional | Write out types per step; choose `flatMap` or fix mapper/return type |
| `int cannot be converted to Optional<? extends U>` after `flatMap` | Mapper returns a plain value instead of Optional | Switch to `map`, or return an actual Optional |
| `NoSuchElementException` | Calling `get()`/`orElseThrow()` on empty | Pick a contract-appropriate fallback or handle empty first |
| `NullPointerException` at `Optional.of(null)` | `of` forbids null | Use `ofNullable` if null signifies absence |
| `NullPointerException` at `flatMap` | Null mapper argument or mapper returns null | Never return null; return `Optional.empty()` |
| `map` returns empty even though input is present | Mapper returns null | Check mapper logic; `map` wraps with ofNullable |
| Fallback executes side effects even when Optional is present | Using `orElse(expensiveCall())` | Use `orElseGet(() -> expensiveCall())` |
| Unwanted `Optional<Optional<T>>` | Using `map` with a mapper returning Optional | Use `flatMap` |
| Awkward handling of `List<Optional<T>>` | Each element has an absent state | Use `Optional.stream()` to keep present values if positions can be dropped |
| Chain hides why data is missing | Optional only tracks present/empty | Use a domain Result/error type if multiple error states are needed |

### 20.1. Using the compiler to locate type-relationship mistakes

A practical workflow:

1. Identify `T` of the Optional before transformation.
2. Identify the **exact** return type of the mapper.
3. If the mapper returns `U`, use `map`; if it returns `Optional<U>`, use `flatMap`.
4. Write the post-transformation type: `Optional<U>` or `Optional<Optional<U>>`?
5. Compare it against the method return type or assignment target.
6. If wildcards are used, analyze whether each is an input consumer or output producer.
7. Split long pipelines into explicitly typed variables.
8. Compile with `javac --release 17 -Xlint:all` and test present, empty, null input, wrong mapper, and exception cases.

## 21. Exercises with answers

### Exercise 1. How does `map` change types?

```java
Optional<String> name = Optional.of("Java");
var result = name.map(String::length);
```

**Question:** what is the static type of `result`?

<details>
<summary>Answer</summary>

`Optional<Integer>`. Input is String, mapper returns int (boxed to Integer), so generic method `<U> map(...)` infers `U = Integer`.

</details>

### Exercise 2. Which of the two assignments is valid?

```java
Optional<Number> a = Optional.of(7);

Optional<Integer> ints = Optional.of(7);
// Optional<Number> b = ints;
```

<details>
<summary>Answer</summary>

The first line is valid thanks to type inference with target type `Optional<Number>`. Assigning `ints` to `b` is invalid because Java Generics are invariant: `Optional<Integer>` is not a subtype of `Optional<Number>`.

</details>

### Exercise 3. Which transformation avoids nested Optionals?

```java
Optional<User> user = findUser(1);
```

If `User.profile()` returns `Optional<Profile>`, which method should you use?

<details>
<summary>Answer</summary>

Use `user.flatMap(User::profile)` to obtain `Optional<Profile>`. Using `map` would produce `Optional<Optional<Profile>>`.

</details>

### Exercise 4. Why is `flatMap(Integer::parseInt)` invalid?

<details>
<summary>Answer</summary>

`parseInt` returns `int`, whereas `flatMap` requires the mapper to return `Optional<? extends U>`. Use `map(Integer::parseInt)` if you want `Optional<Integer>`.

</details>

### Exercise 5. Do `map` and `flatMap` handle a mapper returning null the same way?

<details>
<summary>Answer</summary>

No. If `map`'s mapper returns null on a present Optional, the result becomes empty. `flatMap` requires the mapper to return a non-null Optional object; returning null throws `NullPointerException`.

</details>

### Exercise 6. When Optional already holds a value, which fallback is still evaluated?

```java
present.orElse(costly());
present.orElseGet(() -> costly());
```

<details>
<summary>Answer</summary>

`costly()` in `orElse(costly())` is evaluated before the call even when Optional is present. The Supplier in `orElseGet` is invoked only if Optional is empty.

</details>

### Exercise 7. How do `List<Optional<T>>` and `Optional<List<T>>` differ?

<details>
<summary>Answer</summary>

`List<Optional<T>>` represents multiple positions where each position may be missing. `Optional<List<T>>` means the entire list may be missing; when present, the list itself may be empty. The two data models are not equivalent.

</details>

### Exercise 8. Why does `Optional<? extends Number>` accept multiple Optional types?

<details>
<summary>Answer</summary>

The wildcard `? extends Number` accepts an Optional whose type argument is a subtype of Number such as Integer/Double; code can read the value as Number. It does not mean you can assign an `Optional<Integer>` variable directly to `Optional<Number>`.

</details>

### Exercise 9. What does `Optional.stream()` do on empty?

<details>
<summary>Answer</summary>

It returns a stream with zero elements; a present Optional produces a stream of one element. Thus `streamOfOptionals.flatMap(Optional::stream)` drops empty values.

</details>

### Exercise 10. Does Optional automatically catch parse errors?

<details>
<summary>Answer</summary>

No. `Optional.of("bad").map(Integer::parseInt)` still throws `NumberFormatException`. If parse failures need to become empty or an explicit error result, write dedicated exception-handling logic.

</details>

## 22. Conclusion

`Optional<T>` is not just a way to avoid `null`; combined with Generics, it establishes a contract of **a present or absent value of type T**, with compiler-checked transformations:

- `map(Function<? super T, ? extends U>)` turns `Optional<T>` into `Optional<U>`.
- `flatMap(Function<? super T, ? extends Optional<? extends U>>)` is used when the mapper **already returns an Optional**, avoiding nested Optionals.
- `filter(Predicate<? super T>)` tests a condition while preserving `Optional<T>`.
- `orElse` and `orElseGet` return `T` with different fallback evaluation timing; `or` returns an Optional.
- `Optional.stream()` integrates with the Stream API to extract present values.
- `Optional<Integer>` is not a subtype of `Optional<Number>`; wildcards and factory-method inference address different needs.

Identify **the data type before transformation, the mapper's return type, and the Optional type after transformation**. For long pipelines, split into explicitly typed variables so the compiler pinpoints errors accurately. Avoid abusing `get()`, unchecked casts, and `orElse(null)`; Optional's purpose is to express absence and type relationships clearly right in the API.