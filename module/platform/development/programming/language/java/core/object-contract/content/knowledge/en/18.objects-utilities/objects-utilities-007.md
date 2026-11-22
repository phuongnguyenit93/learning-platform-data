# `Objects.requireNonNullElse()` and `Objects.requireNonNullElseGet()` in Java

The two static methods `java.util.Objects.requireNonNullElse()` and `Objects.requireNonNullElseGet()` help select **a replacement value when the primary value is `null`**. Both guarantee that the returned result is **non-`null`**, yet they differ in **when the fallback value is created**: `requireNonNullElse()` accepts a pre-evaluated value, whereas `requireNonNullElseGet()` accepts a `Supplier` and calls `get()` only when actually needed.

This difference matters when creating the fallback takes time, allocates memory, reads configuration, calls a service, or has side effects. Understanding the argument evaluation rules and `null` checks helps prevent subtle bugs even when the primary value is always present.

Both APIs have existed since **Java 9** and work normally on Java 17+.

## 1. Signatures and return contract

General signatures:

```java
public static <T> T requireNonNullElse(T obj, T defaultObj);

public static <T> T requireNonNullElseGet(
        T obj, Supplier<? extends T> supplier);
```

`Supplier` lives in `java.util.function.Supplier`. Both methods return **the received reference** or **the fallback reference**, without copying objects or mutating the primary parameter's state.

| Case | `requireNonNullElse(obj, defaultObj)` | `requireNonNullElseGet(obj, supplier)` |
| --- | --- | --- |
| `obj != null` | Returns `obj` | Returns `obj`; does not call `supplier.get()` |
| `obj == null` | Returns `defaultObj` if non-`null` | Calls `supplier.get()` and returns the result if non-`null` |
| `obj == null`, fallback is `null` | Throws `NullPointerException` | Throws `NullPointerException` if supplier is `null` or `get()` returns `null` |
| `obj != null`, passed fallback is `null` | Still returns `obj` | Still returns `obj`, even when the passed supplier is `null` |
| Fallback is expensive to *create* | The argument-creating expression is evaluated before the method runs | The `get()` body runs only if `obj == null` |
| Called repeatedly when `obj == null` | Uses the fallback object passed in that call | May re-run `get()` on every call; does not auto-cache |

**Note on `null` handling:** A non-null fallback value is required **when it needs to be used**. If `obj` is already non-`null`, both methods can return the result without validating the unused fallback.

`requireNonNullElseGet()` is not a "synchronized version", not a caching API, and does not automatically handle `Optional`. It simply defers calling `Supplier.get()`.

## 2. `requireNonNullElse()` — a ready-made fallback value

Simple example:

```java
String displayName =
        Objects.requireNonNullElse(userName, "Guest");
```

This is an **illustrative code snippet**, assuming `userName` is a `String` variable and `java.util.Objects` has been imported. If `userName` is non-`null`, the method returns that string itself; if it is `null`, it returns `"Guest"`.

Two things must be distinguished:

1. **The `defaultObj` parameter is a value, not a deferred computation.** By Java's rules, every argument expression of a method call is evaluated before the method begins executing.
2. **Whether the fallback is returned still depends on `obj`.** The fallback value may be created and then unused.

Example:

```java
String value = Objects.requireNonNullElse(
        "Available", createExpensiveDefault());
```

Here `createExpensiveDefault()` **still runs** to produce the second argument, even though the resulting `value` is `"Available"`. If the fallback-creating function throws an exception, the exception occurs **before** `requireNonNullElse()` even gets a chance to pick the primary value.

This does not mean passing `"Guest"` or a cheap constant is always a problem. `requireNonNullElse()` is usually the **simplest** choice when the fallback already exists or is very cheap.

## 3. `requireNonNullElseGet()` — computing fallback when needed

Corresponding syntax:

```java
String displayName = Objects.requireNonNullElseGet(
        userName, () -> createExpensiveDefault());
```

This is also an **illustrative code snippet**. Java still **evaluates the `Supplier`-creating expression** before the call (for instance, creating the lambda object or calling a function that returns a supplier); however, **the lambda body**, i.e., `createExpensiveDefault()`, does not run if `userName != null`.

A method reference can be passed:

```java
String name = Objects.requireNonNullElseGet(
        userName, ConfigDefaults::loadDefaultName);
```

`ConfigDefaults::loadDefaultName` is a syntax example, assuming class `ConfigDefaults` has a suitable method returning a non-null `String`. The method reference only describes a deferred call; it does not automatically cache or validate the result until `get()` is called.

**Selection rule:** if the fallback data needs computation and can be skipped when the primary value is present, `requireNonNullElseGet()` clearly expresses *lazy fallback* intent.

## 4. Java 17+ program demonstrating eager and lazy evaluation

Save the entire program into **`ElseTimingDemo.java`**:

```java
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

public class ElseTimingDemo {
    private static String fallback(AtomicInteger calls) {
        int number = calls.incrementAndGet();
        return "fallback-" + number;
    }

    public static void main(String[] args) {
        AtomicInteger calls = new AtomicInteger();

        String eagerPresent = Objects.requireNonNullElse(
                "provided", fallback(calls));
        String lazyPresent = Objects.requireNonNullElseGet(
                "provided", () -> fallback(calls));

        System.out.println("eager present: " + eagerPresent);
        System.out.println("lazy present: " + lazyPresent);
        System.out.println("calls after present: "
                + calls.get());

        String eagerAbsent = Objects.requireNonNullElse(
                (String) null, fallback(calls));
        String lazyAbsent = Objects.requireNonNullElseGet(
                (String) null, () -> fallback(calls));

        System.out.println("eager absent: " + eagerAbsent);
        System.out.println("lazy absent: " + lazyAbsent);
        System.out.println("calls after absent: "
                + calls.get());
    }
}
```

Compile and run:

```bash
javac ElseTimingDemo.java
java ElseTimingDemo
```

Exact output:

```text
eager present: provided
lazy present: provided
calls after present: 1
eager absent: fallback-2
lazy absent: fallback-3
calls after absent: 3
```

**Explanation:**

- The first time, `"provided"` is non-null, yet the `fallback(calls)` expression of `requireNonNullElse()` still runs: the counter increases to `1`. The method result is still `"provided"`.
- `requireNonNullElseGet("provided", () -> fallback(calls))` does not call `get()`, so the counter stays unchanged.
- When the primary argument is null, both APIs must obtain a fallback value. The eager call computes `"fallback-2"` beforehand, and the lazy call computes `"fallback-3"` inside the supplier.
- The code uses `AtomicInteger` to count calls in an easily observable way; **this is not proof that `Objects` automatically synchronizes fallback creation**. There are no multithreaded calls in this example.

If you are only passing a constant or an already available fallback variable, `requireNonNullElse()` remains correct and readable. Choose `requireNonNullElseGet()` mainly because of the cost or side effects of computing the fallback, not because it is inherently "more modern".

## 5. `null` checks: both APIs require a non-null final result

Both methods have `requireNonNull` in their names because **the value after selection must be non-`null`**. Easily confused results:

```java
Objects.requireNonNullElse("ready", null); // Returns "ready".
Objects.requireNonNullElse(null, null);    // Throws NullPointerException.
```

Similarly:

```java
Objects.requireNonNullElseGet("ready", null); // Returns "ready".
Objects.requireNonNullElseGet(null, null);    // Throws NullPointerException.
Objects.requireNonNullElseGet(null, () -> null); // Throws NullPointerException.
```

The lines above are **standalone illustrative expressions**; some calls with only `null` literals need explicit typing in real programs to avoid type inference or overload errors. The section below uses explicit casts and catches exceptions.

### 5.1. Program testing null cases

Create the file **`NullFallbackDemo.java`**:

```java
import java.util.Objects;
import java.util.function.Supplier;

public class NullFallbackDemo {
    private static void run(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + ": OK");
        } catch (NullPointerException ex) {
            System.out.println(label + ": NPE");
        }
    }

    public static void main(String[] args) {
        System.out.println("unused null value: "
                + Objects.requireNonNullElse(
                        "ready", (String) null));
        System.out.println("unused null supplier: "
                + Objects.requireNonNullElseGet(
                        "ready", (Supplier<String>) null));

        run("needed null value", () -> {
            Objects.requireNonNullElse(
                    (String) null, (String) null);
        });
        run("needed null supplier", () -> {
            Objects.requireNonNullElseGet(
                    (String) null, (Supplier<String>) null);
        });
        run("supplier returned null", () -> {
            Objects.requireNonNullElseGet(
                    (String) null, () -> null);
        });
    }
}
```

Run:

```bash
javac NullFallbackDemo.java
java NullFallbackDemo
```

Stdout:

```text
unused null value: ready
unused null supplier: ready
needed null value: NPE
needed null supplier: NPE
supplier returned null: NPE
```

**Analysis:** when `"ready"` exists, no fallback is needed, so neither a `null` fallback nor a `null` supplier causes an error. When the primary argument is missing, neither API permits returning `null`; the supplier must also be present and produce a non-null result.

On modern JDKs, `NullPointerException` may include a detailed message, but you should not write logic depending on message contents or assume identical error messages across every runtime. The exception type matters more than the message.

**Difference from `?:` or `if`:** both APIs select a fallback and **assert non-null**. If the application wants the result to remain allowed to be null, use a conditional branch or an API whose contract accepts null, instead of trying to return null via `requireNonNullElseGet()`.

## 6. When the fallback has exceptions or side effects

Suppose `loadDefaultFromNetwork()` makes a network call, reads a config file, or fetches data from cache. Then the choice of method directly affects cost and correctness:

| Scenario | `requireNonNullElse(value, load())` | `requireNonNullElseGet(value, () -> load())` |
| --- | --- | --- |
| `value` is non-null, `load()` is slow | **Still runs** before the call | **Does not run** the supplier body |
| `value` is non-null, `load()` throws a runtime exception | The call fails before entering `Objects` | No exception arises from `load()` |
| `value` is null, `load()` returns validly | Uses the already computed result | Calls `get()` and uses the result |
| `value` is null, `load()` throws an exception | Exception from `load()` propagates | Exception from `get()` propagates |
| `value` is null, `load()` returns null | `Objects` throws `NullPointerException` | `Objects` throws `NullPointerException` after `get()` |
| `value` is null across multiple calls | Each argument expression may be evaluated again | Each call may invoke `get()` again |

`Supplier.get()` does not handle retries automatically, does not swallow exceptions, and does not enforce timeout policies. If the fallback involves I/O, decide clearly how to behave when the service is unavailable. `Supplier.get()` also declares no checked exceptions, so operations throwing checked exceptions must be caught, wrapped, or designed under a different API transparently.

Subtle note: the expression **creating the supplier** is still evaluated even if the primary value is non-null:

```java
Supplier<String> supplier = createSupplier();
String result = Objects.requireNonNullElseGet(value, supplier);
```

If `createSupplier()` is expensive or has side effects, it already ran **before** `requireNonNullElseGet()`. The laziness here only defers **calling `get()`**, with no magic that defers every expression used as an argument.

## 7. `requireNonNullElseGet()` does not auto-cache and is not auto-thread-safe

Example:

```java
String first = Objects.requireNonNullElseGet(
        null, () -> new String("fallback"));
String second = Objects.requireNonNullElseGet(
        null, () -> new String("fallback"));
```

Each call can create a new object because the supplier is invoked on **every call needing a fallback**. Two results may be equal by `equals()` yet not be the same reference. This snippet only illustrates API behavior, not a `String` creation technique to use: normally you can return the literal `"fallback"`.

If multiple threads call this on null data:

- Each thread can invoke its supplier; `Objects` **does not guarantee single-time initialization across the entire application**.
- Any shared state read/written by the supplier requires an appropriate synchronization mechanism. A lambda or method reference itself does not make internal operations thread-safe.
- If default-created data must be shared or cached once, design a separate caching/initialization component (`synchronized`, lazy holder pattern, or suitable structure), and have the supplier fetch data from that component.
- Do not expect `Objects.requireNonNullElseGet()` to resolve a race between a mutating value and reading it: at call time, Java simply receives **the value of the argument expression**. Synchronizing source state remains the application's responsibility.

When a lambda captures outer local variables, those variables must be `final` or **effectively final** per Java rules. For mutable object fields, continue considering thread safety and state observation timing.

## 8. Relationship with `Objects.requireNonNull()` and `Optional`

The three `Objects` methods serve different intents:

| API | Intent |
| --- | --- |
| `Objects.requireNonNull(value)` | **Requires `value` itself to exist**; if null, throws `NullPointerException` |
| `Objects.requireNonNullElse(value, fallback)` | Allows primary value to be null, uses **already evaluated** fallback, final result non-null |
| `Objects.requireNonNullElseGet(value, supplier)` | Allows primary value to be null, creates fallback **when needed**, final result non-null |

`Optional.ofNullable(value).orElse(fallback)` and `.orElseGet(supplier)` have similarities regarding **eager/lazy**, yet are not exact drop-in replacements:

- `Optional.orElse(...)` returns the passed value and `Optional.orElseGet(...)` returns the supplier's result when the optional is empty; they **can return null** if the fallback is null.
- The two `Objects.requireNonNullElse*()` methods **do not allow the final result to be null**.
- `Optional` fits when an API already models presence/absence with `Optional<T>` or needs other transformations; `Objects` is leaner when only picking a replacement value for a nullable reference.
- `Optional.ofNullable(value).orElseGet(supplier)` also does not auto-cache; it simply calls the supplier when the value is empty.

Do not use `Objects.requireNonNullElse(value, fallback)` to convert **empty strings**, whitespace-only strings, empty lists, or 0 into default values. Those values are **non-`null`**, so they are kept as-is. If business rules want to handle empty or blank strings, write a separate condition.

## 9. Generic types and practical collection example

Both methods are generic over `<T>`. `requireNonNullElseGet()` takes `Supplier<? extends T>`, allowing the supplier to produce a subtype of the desired result type:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

List<String> existing = null;

List<String> items = Objects.requireNonNullElseGet(
        existing, ArrayList::new);
items.add("Java");
```

This is an **illustrative code snippet**, not a standalone Java file since statements appear outside a method. When `existing` is null, the method reference `ArrayList::new` creates an `ArrayList<String>` compatible with `List<String>`. If `existing` is non-null, its reference is returned intact.

However, returning a mutable `ArrayList` is not a safe default decision for every API. If callers are not allowed to modify the collection, use an immutable fallback such as `List::of` (when the type fits), while clearly documenting the mutability/immutability of the returned value. If `existing` may be a mutable list while the fallback is immutable, the API could have **two different mutability modes** depending on null; consider the design contract carefully.

Example using an existing singleton fallback:

```java
List<String> safeItems = Objects.requireNonNullElse(
        existing, List.of());
```

`List.of()` returns an immutable collection; although the argument expression is still evaluated before the call, Java may use a shared instance for an empty list. Eager/lazy describes **when an expression is evaluated**, not a claim that memory is necessarily allocated on every call.

## 10. Common mistakes

1. **Using `requireNonNullElse(value, expensive())` and assuming `expensive()` only runs when null.** Every argument in a Java call is evaluated beforehand; use a supplier if computation needs to be deferred.
2. **Believing `requireNonNullElseGet()` ensures the default computation runs only once.** It can invoke `get()` on every call, including concurrently across threads.
3. **Letting the supplier return `null` assuming the API preserves null.** When the fallback is needed, a null result is rejected with `NullPointerException`.
4. **Assuming a null supplier always fails immediately.** If the primary value is non-null, the supplier is unused and may be null while still returning that primary value.
5. **Ignoring side effects of creating the supplier.** The `get()` body is deferred; the expression creating the supplier is still evaluated under Java rules.
6. **Assuming a lambda implies thread-safe.** The supplier's body can read/write shared state and still requires synchronization.
7. **Using these to normalize empty strings or empty collections.** Both APIs only check for `null`, not emptiness.
8. **Using a mutable fallback without stating it clearly.** The result may be the old object itself or a new mutable object; the API neither copies nor protects data automatically.
9. **Hiding business errors with unconditional defaults.** If data is mandatory, `Objects.requireNonNull(value)` may be more accurate than silently using a fallback.
10. **Switching from eager to lazy while forgetting exception behavior changes.** If the fallback previously always ran and threw errors even when unused, `requireNonNullElseGet()` skips that error when `obj` is non-`null`; this is a behavioral change that must be evaluated deliberately.

## 11. Quick selection checklist

- [ ] Is `value == null` acceptable? If not, use `requireNonNull(value)`.
- [ ] If acceptable, is the fallback guaranteed **non-`null`**? If not, the two `requireNonNullElse*()` methods are unsuitable.
- [ ] Does the fallback already exist or cost very little to compute? Prefer `requireNonNullElse(value, fallback)`.
- [ ] Does the fallback involve I/O, computation, allocation, or side effects? Prefer `requireNonNullElseGet(value, () -> computeFallback())`.
- [ ] Can the supplier throw exceptions, access shared state, or return a mutable object? Define the policy and ensure synchronization if needed.
- [ ] Does the result need to be cached/shared? Design a dedicated mechanism, because `Objects` does not cache.
- [ ] Have you tested `value != null`, `value == null`, null fallback, null supplier, and supplier returning null?
- [ ] Are you confusing `null` with empty strings/empty lists or actually wanting a different normalization rule?

**Key takeaway:** `Objects.requireNonNullElse(value, fallback)` uses an **already-evaluated fallback value**; `Objects.requireNonNullElseGet(value, supplier)` **invokes the supplier only when `value == null`**. Both guarantee a **non-null return value** or throw `NullPointerException` when a valid result cannot be produced. Choose the method based on the cost, side effects, and contract of the fallback.