# Avoiding Unchecked `Optional.get()` and Understanding `null` Properly in Java

## 1. The Problem: A Value May Be Absent

In Java, a method that looks up data sometimes has no result. Historically, many APIs returned `null` to represent “not found”:

```java
User user = findUser("missing");  // May return null.
System.out.println(user.name()); // NullPointerException if user == null.
```

`User` and `findUser` here are only illustrative names, not a standalone program. `java.util.Optional<T>` expresses more clearly **a result that may be present or absent**. An `Optional<T>` has two states by contract:

- **Present:** `Optional.of(value)` with `value != null`.
- **Empty:** `Optional.empty()`, or `Optional.ofNullable(null)`.

The key point: **`Optional` does not hold a “`null` value” as a third present-value state.** If the provided data is `null`, using `ofNullable` produces `Optional.empty()`. However, a **reference variable of type `Optional<T>`** can still be assigned `null` if other code violates the contract; in that case, calling `isPresent()`, `map()`, or `orElse()` on that reference still causes a `NullPointerException`.

Another mistake is calling `optional.get()` without being sure a value is present. `get()` will throw `NoSuchElementException` if the `Optional` is empty. This lesson focuses on programming safely, readably, and expressing missing-data semantics accurately.

## 2. Creation Methods: `of`, `ofNullable`, `empty`

| Creation method | Input | Result |
| --- | --- | --- |
| `Optional.of("Java")` | Non-`null` | `Optional` containing `"Java"` |
| `Optional.of(null)` | `null` | Throws `NullPointerException` immediately upon creation |
| `Optional.ofNullable("Java")` | Non-`null` | `Optional` containing `"Java"` |
| `Optional.ofNullable(null)` | `null` | `Optional.empty()` |
| `Optional.empty()` | No input | Empty `Optional` |

Example:

```java
import java.util.Optional;

Optional<String> known = Optional.of("Java");
Optional<String> missing = Optional.ofNullable(null);
Optional<String> alsoMissing = Optional.empty();

System.out.println(known.isPresent());   // true
System.out.println(missing.isEmpty());    // true
System.out.println(alsoMissing.isEmpty()); // true
```

This snippet is meant to be placed inside a method or `jshell`. `isEmpty()` has been available since Java 11, so Java 17+ programs can use it normally.

**Choose `of` when the value is required by contract to be non-`null`.** If receiving `null` is a bug, `Optional.of(value)` helps detect the error early. **Choose `ofNullable` when the data source is allowed to return `null`**, such as legacy APIs, optional fields from a DTO, or external responses. Do not use `ofNullable` unconditionally to hide bugs in required data.

### Distinguishing three easily confused situations

```java
Optional<String> a = Optional.empty();            // Correct: an empty Optional.
Optional<String> b = Optional.ofNullable(null);   // Correct: also empty.
Optional<String> c = null;                        // Wrong in API design.
```

`a` and `b` are valid **Optional objects**, on which `isEmpty()` can be called. `c` is not an Optional object; `c.isEmpty()` throws `NullPointerException`. Therefore, a method declared to return `Optional<T>` should return **`Optional.empty()`**, not `null`:

```java
// DO:
Optional<String> findCode(boolean found) {
    return found ? Optional.of("A01") : Optional.empty();
}

// DON'T:
Optional<String> brokenFindCode(boolean found) {
    return found ? Optional.of("A01") : null;
}
```

Both snippets are illustrative methods; they need to be placed inside a class with `Optional` imported. A caller that assumes `Optional` is always non-`null` will fail with `brokenFindCode(false)`.

## 3. Why Is Unchecked `get()` Dangerous?

`Optional.get()` has the contract: **return the value if present; if empty, throw `NoSuchElementException`**.

```java
Optional<String> maybeName = Optional.empty();
// String name = maybeName.get(); // NoSuchElementException.
```

The compiler **does not warn** about the call above, because `get()` exists in the API and `NoSuchElementException` is an unchecked exception. The error only occurs at runtime with empty data.

The following manual check is valid:

```java
Optional<String> maybeName = Optional.of("Lan");
if (maybeName.isPresent()) {
    System.out.println(maybeName.get());
}
```

However, this approach is often not the most readable option. When every piece of code has to remember to call `isPresent()` before `get()`, it is easy to miss a branch or change code in a way that breaks safety. In most cases, you should express the intent directly using Optional operations: `map`, `flatMap`, `filter`, `ifPresent`, `ifPresentOrElse`, `orElse`, `orElseGet`, or `orElseThrow`.

> `get()` is not strictly forbidden. If there is **a verified invariant** that the Optional definitely has a value, `get()` can be functionally valid. However, `orElseThrow()` (zero-argument, Java 10+) clearly expresses the intent “a value must be present, otherwise fail” and is usually the clearer choice.

## 4. Choosing the Access API That Matches the Business Logic

| Need | Usage | What happens if empty |
| --- | --- | --- |
| Run an action if present | `ifPresent(value -> ...)` | Action is not run |
| Do A if present, B if empty | `ifPresentOrElse(action, emptyAction)` | Runs `emptyAction` |
| Get the value or a constant | `orElse("UNKNOWN")` | Returns `"UNKNOWN"` |
| Compute a fallback value only when empty | `orElseGet(() -> computeFallback())` | Calls supplier and returns result |
| Value must be present | `orElseThrow()` | Throws `NoSuchElementException` |
| Missing data must throw a domain error | `orElseThrow(() -> new IllegalArgumentException(...))` | Throws the exception created by supplier |
| Transform if a value is present | `map(Function)` | Keeps `Optional.empty()` |
| Transform with a function already returning Optional | `flatMap(Function)` | Keeps `Optional.empty()` |
| Keep the value only if it matches a condition | `filter(Predicate)` | Keeps empty state |
| Choose an alternative Optional | `or(() -> alternateOptional())` | Uses the Optional from supplier |
| Convert to a 0- or 1-element stream | `stream()` | Empty stream |

Example:

```java
Optional<String> maybe = Optional.ofNullable(null);

String display = maybe.orElse("N/A"); // "N/A"
String lazy = maybe.orElseGet(() -> "N/A"); // "N/A"

maybe.ifPresent(System.out::println); // Prints nothing.
maybe.ifPresentOrElse(
        System.out::println,
        () -> System.out.println("No value")
); // Prints "No value".
```

This is an illustrative snippet inside a method. Both `orElse` and `orElseGet` provide an alternative; the difference is **when the fallback is evaluated**, analyzed in a later section. `orElseThrow` is suitable when absence is an error that must be handled explicitly, while `ifPresent` is suitable for an optional action.

### `orElseThrow` reports errors with the right context

```java
String email = findEmail(userId)
        .orElseThrow(() ->
                new IllegalArgumentException("Email not found: " + userId));
```

`findEmail` and `userId` in this snippet are illustrative variables/methods. This style clearly states that **absence is not acceptable** for this request; it does not silently use `null` or an empty string as a fake email.

If `findEmail` can return a `null` `Optional` reference (violating the contract), `orElseThrow` can still cause a `NullPointerException`. Fix the source returning `Optional` first instead of stacking `Optional.ofNullable(optional)` calls everywhere.

## 5. Complete Java 17 Example and Deterministic Stdout

Problem: simulate looking up a user; one user has an email, one has a profile with a `null` email, and one ID does not exist. The program demonstrates proper `Optional` usage, handles `null` at the boundary, and compares access methods.

Create the file **`OptionalSafetyDemo.java`**:

```java
import java.util.List;
import java.util.Locale;
import java.util.NoSuchElementException;
import java.util.Optional;
import java.util.OptionalInt;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class OptionalSafetyDemo {
    record User(String id, String email) {}

    static Optional<User> findUser(String id) {
        return switch (id) {
            case "u1" -> Optional.of(
                    new User("u1", "  Lan@Example.com  "));
            case "u2" -> Optional.of(new User("u2", null));
            default -> Optional.empty();
        };
    }

    static Optional<String> normalizedEmail(User user) {
        return Optional.ofNullable(user.email())
                .map(String::trim)
                .filter(value -> !value.isEmpty())
                .map(value -> value.toLowerCase(Locale.ROOT));
    }

    static String expensiveFallback() {
        System.out.println("Fallback computed");
        return "fallback";
    }

    public static void main(String[] args) {
        System.out.println("Known: "
                + findUser("u1").map(User::id).orElse("missing"));

        System.out.println("Email u1: "
                + findUser("u1")
                    .flatMap(OptionalSafetyDemo::normalizedEmail)
                    .orElse("none"));

        System.out.println("Email u2: "
                + findUser("u2")
                    .flatMap(OptionalSafetyDemo::normalizedEmail)
                    .orElse("none"));

        System.out.println("Email u3: "
                + findUser("u3")
                    .flatMap(OptionalSafetyDemo::normalizedEmail)
                    .orElse("none"));

        String raw = null;
        System.out.println("ofNullable(null) empty: "
                + Optional.ofNullable(raw).isEmpty());

        try {
            Optional.of(raw);
        } catch (NullPointerException ex) {
            System.out.println("of(null): NullPointerException");
        }

        try {
            Optional.<String>empty().get();
        } catch (NoSuchElementException ex) {
            System.out.println("empty.get(): NoSuchElementException");
        }

        try {
            Optional.<String>empty().orElseThrow(
                    () -> new IllegalStateException("not found"));
        } catch (IllegalStateException ex) {
            System.out.println("orElseThrow: " + ex.getMessage());
        }

        findUser("u1").ifPresentOrElse(
                user -> System.out.println("Found: " + user.id()),
                () -> System.out.println("No user"));
        findUser("unknown").ifPresentOrElse(
                user -> System.out.println("Found: " + user.id()),
                () -> System.out.println("No user"));

        System.out.println("map null -> empty: "
                + Optional.of("x")
                    .map(value -> (String) null)
                    .isEmpty());

        try {
            Optional.of("x")
                    .flatMap(value -> (Optional<String>) null);
        } catch (NullPointerException ex) {
            System.out.println("flatMap null: NullPointerException");
        }

        String eager = Optional.of("READY")
                .orElse(expensiveFallback());
        String lazy = Optional.of("READY")
                .orElseGet(OptionalSafetyDemo::expensiveFallback);
        System.out.println("Eager: " + eager + ", lazy: " + lazy);

        List<String> ids = Stream.of("u1", "u2", "u3")
                .map(OptionalSafetyDemo::findUser)
                .flatMap(Optional::stream)
                .map(User::id)
                .toList();
        System.out.println("Found IDs: " + ids);

        OptionalInt zero = OptionalInt.of(0);
        System.out.println("OptionalInt zero present: "
                + zero.isPresent());
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac --release 17 OptionalSafetyDemo.java
java OptionalSafetyDemo
```

**Exact stdout:**

```text
Known: u1
Email u1: lan@example.com
Email u2: none
Email u3: none
ofNullable(null) empty: true
of(null): NullPointerException
empty.get(): NoSuchElementException
orElseThrow: not found
Found: u1
No user
map null -> empty: true
flatMap null: NullPointerException
Fallback computed
Eager: READY, lazy: READY
Found IDs: [u1, u2]
OptionalInt zero present: true
```

Walkthrough:

1. `findUser("u1")` returns an Optional containing a User; `map(User::id)` yields `"u1"`.
2. `normalizedEmail` reads the email via `ofNullable`, trims whitespace, and converts to lowercase using `Locale.ROOT`, so `"  Lan@Example.com  "` becomes `"lan@example.com"`.
3. `u2` has a User, but the email is `null`. `Optional.ofNullable(user.email())` creates an empty Optional; `flatMap` combines it with the User's Optional into an empty email Optional; `orElse("none")` returns `"none"`. `u3` has no User, which also produces `"none"`. **Two different situations can produce the same displayed result**, so if business logic needs to distinguish “no user” from “user has no email”, you must preserve an error status or check at each layer.
4. `Optional.of(raw)` with `raw == null` throws `NullPointerException` immediately upon creation. `Optional.empty().get()` throws `NoSuchElementException`, which is caught and its exception name is printed.
5. `map(value -> (String) null)` turns a present Optional into an empty Optional. `flatMap` does not accept a mapper that returns a **`null` Optional reference**, so it throws `NullPointerException`.
6. `orElse(expensiveFallback())` evaluates its argument before calling `orElse`, so it prints `Fallback computed` even though the Optional already holds `"READY"`. `orElseGet` only calls the supplier when the Optional is empty, so it does not print a second line.
7. `Optional.stream()` returns a 1-element stream if present, or an empty stream if absent. Therefore, from the list `u1,u2,u3`, only the first two Users are included in `ids` in encounter order.
8. `OptionalInt.of(0)` **has a value** of 0, because 0 is not an absence marker; `isPresent()` is `true`.

> The example intentionally has `User.email() == null` to demonstrate converting legacy data into `Optional` at the read boundary. You should not use `null` for required attributes and treat every data error by default as valid missing information.

## 6. `map` and `flatMap` Handle `null` Differently

### `Optional.map`: a `null` mapper output becomes empty

`Optional.map` transforms a present value using a `Function<T,U>`. If the input Optional is empty, the mapper is not called. If the mapper returns `null`, the result of `map` is `Optional.empty()` according to a contract similar to `ofNullable` on the mapper's result.

```java
Optional<String> code = Optional.of("A01");
Optional<Integer> length = code.map(String::length); // Has 3.

Optional<String> absent = code.map(value -> null);
System.out.println(absent.isEmpty()); // true
```

This example is placed inside a method with `Optional` imported. Using `map` is very convenient when chaining transformations that may accept or return nullable values:

```java
Optional<String> city = Optional.ofNullable(customer)
        .map(Customer::getAddress)
        .map(Address::getCity)
        .filter(s -> !s.isBlank());
```

`Customer`, `Address`, and `customer` are illustrative application types/variables; this snippet is not a standalone program. If `customer`, `address`, or `city` is null, the result stops in the empty state according to `map`'s contract. However, it **does not handle other exceptions** from getters or `filter`; those still propagate normally.

### `Optional.flatMap`: the mapper must return a real Optional

When the transformation function already returns `Optional<U>`, use `flatMap`:

```java
Optional<User> user = findUser("u1");

Optional<String> email =
        user.flatMap(OptionalSafetyDemo::normalizedEmail);
```

Because `normalizedEmail` returns `Optional<String>`, `flatMap` avoids a nested `Optional<Optional<String>>` type. However, the mapper must return a **non-null Optional object**:

```java
// WRONG: the mapper itself returns a null Optional reference.
Optional<String> broken = Optional.of("x")
        .flatMap(value -> (Optional<String>) null);
```

This snippet **compiles but throws `NullPointerException` at runtime**. Avoid this by following the contract: return `Optional.empty()` when absent, never `null`. `Optional.or(Supplier<Optional<T>>)` also requires the supplier to provide a valid (non-null) Optional.

### `filter` only keeps or discards a value

```java
Optional<String> valid =
        Optional.of("  ")
                .map(String::trim)
                .filter(s -> !s.isEmpty());

System.out.println(valid.isEmpty()); // true
```

`filter` invokes the `Predicate` only when a value is present. If the predicate returns `false`, the Optional becomes empty; if it returns `true`, the value is kept. `filter` does not turn `null` into a new value or generate an error message on its own.

## 7. Why Does `orElse` Sometimes Cause Unintended Side Effects?

The two snippets below can **return the same result but execute differently**:

```java
String a = Optional.of("READY").orElse(expensiveFallback());
String b = Optional.of("READY").orElseGet(
        OptionalSafetyDemo::expensiveFallback);
```

Assume `expensiveFallback()` is as in the complete program. On line `a`, Java **evaluates the argument** `expensiveFallback()` before calling `orElse`; the computed result is discarded because the Optional already has a value. On line `b`, `orElseGet` takes a `Supplier<String>`, running the supplier only if the Optional is empty.

If the fallback has to call an API, query a database, read a file, allocate a large object, or write logs, use `orElseGet` to avoid the cost/side effects when a result is already present.

```java
String cached = maybeCode.orElseGet(() -> loadDefaultCode());
```

This is an illustrative snippet with `maybeCode` and `loadDefaultCode` declared externally. **Do not assume the supplier will always succeed**: if the fallback throws an exception or returns `null`, that behavior still affects the caller. `orElse(null)` is valid in the API and can return `null` **out of the Optional**; if you want a non-null output, choose a clear fallback and contract.

## 8. `orElseThrow`: When Missing Data Is a Business Error

There are requests that cannot proceed if data is absent, such as payment processing needing to find an order. In that case, you should not pick a dummy fallback like `"UNKNOWN"`. Use:

```java
Order order = findOrder(id).orElseThrow(
        () -> new IllegalArgumentException("Order not found: " + id));
```

`Order`, `findOrder`, and `id` are illustrative business domain names. The call returns `Order` when present, or throws the exact specified exception when empty. If you choose the zero-argument `orElseThrow()`, the default exception is `NoSuchElementException`.

In business code, the exception type and message should match how the outer layer handles errors: a REST API might need to translate “not found” into HTTP 404, but `Optional` itself does not decide the HTTP status. Do not turn every missing-data case into `NullPointerException` or `NoSuchElementException` when the domain needs different information.

### `ifPresentOrElse` to perform an action in both branches

```java
findUser("u1").ifPresentOrElse(
        user -> System.out.println(user.id()),
        () -> System.out.println("No user"));
```

`ifPresentOrElse` does not return a value to assign. If you **need to compute a value** to use next, choose `map`/`orElseGet`/`orElseThrow`; avoid using a mutable variable outside the lambda to hold the result.

## 9. Do Not Use `Optional` to Hide Data Errors

A **not found** state is different from a **query failed** state:

- No User with the given ID: `Optional.empty()` may be appropriate.
- Database timeout or network error: do not return `Optional.empty()` and pretend “no User exists”.
- User exists but email is empty: returning `Optional.empty()` for the email may be fine if the email is allowed to be missing; distinguish it from an input validation error if email is a required field.
- Malformed input content: validate and report errors according to policy rather than turning every error into an empty Optional.

`Optional` expresses **the presence or absence of a value**, not the reason for a failure. If you need to return multiple states (succeeded, not found, rejected, temporarily failed), you can use a sealed interface/record Result, an exception, or another clearer return type.

Example:

```java
sealed interface LookupResult
        permits Found, NotFound, Failed {}

record Found(User value) implements LookupResult {}
record NotFound() implements LookupResult {}
record Failed(String message) implements LookupResult {}
```

This is an example of **type declarations** for a Java 17 application (requiring `User` to be declared appropriately). These types help callers distinguish “absent” from “source unreachable”, which a single `Optional.empty()` cannot convey.

## 10. `Optional` Should Not Be a `null` Reference

A method with the signature:

```java
Optional<User> findUserById(String id)
```

usually has an **implicit contract** that the return value **is never a `null` reference**. If no User exists, return `Optional.empty()`. When a client calls `findUserById(id).map(...)`, it can rely on the Optional object existing. Returning `null` from such a method defeats the main benefit of Optional.

This is especially dangerous with:

```java
// This is a broken API, not a recommended practice.
Optional<String> broken() {
    return null;
}

// broken().orElse("fallback") still throws NullPointerException.
```

To integrate with a legacy API that may return null, **convert immediately at the boundary**:

```java
String legacyValue = legacyService.getCode(); // May be null.
Optional<String> safe = Optional.ofNullable(legacyValue);
```

If the legacy API itself returns `Optional<String>` but sometimes returns `null`, **fix the legacy API** so it always returns a valid Optional. When it cannot be fixed yet, you can use this temporarily:

```java
Optional<String> normalized =
        Optional.ofNullable(legacyOptional)
                .orElseGet(Optional::empty);
```

`legacyOptional` is a variable of type `Optional<String>` that may currently be null; this is a compatibility workaround at **a boundary**, not a reason to design functions returning null Optionals in new code.

## 11. Where Should `Optional` Be Used in an API?

Following common JDK conventions, `Optional<T>` is best suited as a **return type** when there is a clear reason a method might not return a result. Some practical guidelines:

| Location | Recommendation |
| --- | --- |
| Return type of `findById` / `lookup` | Usually appropriate when “not found” is a normal outcome |
| Local variable for multi-step processing | Reasonable when using `map`, `flatMap`, `orElse...` |
| Method parameter | Usually unnecessary; consider overloads or a clearer contract |
| Field of an entity/DTO | Usually prefer an appropriate data model/validation to avoid serializer/ORM compatibility issues |
| Collection containing `Optional<T>` | Only when you need to distinguish per-element state; in many cases there is a clearer representation |
| Optional primitive types | `OptionalInt`, `OptionalLong`, `OptionalDouble` to avoid boxing when appropriate |

`Optional` is a **value-based class**; do not rely on identity `==`, `System.identityHashCode`, or synchronization locks on an Optional instance. Use `isPresent`/`isEmpty` and transformations instead of depending on object identity.

### `OptionalInt` and the value 0

`OptionalInt.of(0)` has the value 0, not an absent state. Only `OptionalInt.empty()` means no `int` is present. Similarly, `Optional<Boolean>` can hold `false` and still have `isPresent() == true`. Do not use default values such as 0, `false`, or an empty string as an “absent” marker if they are also valid data.

## 12. Common Mistakes and How to Fix Them

| Pattern / assumption | Problem | How to handle |
| --- | --- | --- |
| `optional.get()` immediately after receiving data | May throw `NoSuchElementException` | Use `orElse`/`orElseGet`/`orElseThrow`, `map`, or check explicitly |
| `Optional.of(nullableValue)` | Throws `NullPointerException` when null | Use `ofNullable` if null is allowed; keep `of` if null is a bug |
| `Optional.ofNullable(null).get()` | Still throws `NoSuchElementException` | `ofNullable` does not guarantee a value is present |
| Method returning `Optional<T>` actually returns `null` | Caller loses safety and may get an NPE | Return `Optional.empty()` |
| `optional.map(x -> null)` expecting an Optional “containing null” | `map` produces an empty Optional | Design the mapper/return type clearly |
| `optional.flatMap(x -> null)` | Throws `NullPointerException` | Mapper must return `Optional.empty()` or `Optional.of(...)` |
| `optional.or(() -> null)` | Supplier returns null, which is invalid | Supplier must return a valid Optional |
| `orElse(expensive())` when Optional has a value | `expensive()` is still called | Use `orElseGet(this::expensive)` if lazy evaluation is desired |
| Using `orElse(null)` then calling a method on the result | May cause an NPE after unwrapping | Choose a non-null fallback or handle absence |
| Returning `Optional.empty()` on database timeout | Hides the root cause of the error | Throw an appropriate error or return a Result with an error state |
| Unconditionally turning every null value into empty | May mask missing required-field bugs | Define the data contract and validate early |
| Comparing `optional == Optional.empty()` | Depends on unguaranteed identity | Use `isEmpty()` |
| Calling `get()` on `OptionalInt.empty()` via `getAsInt()` | Still throws `NoSuchElementException` | Use `orElse`/`orElseThrow` or check first |

## 13. Practice Exercises

1. Explain why `Optional.ofNullable(null).isEmpty()` is `true`, whereas `Optional.of(null)` throws `NullPointerException`.
2. Write `Optional<String> code = Optional.empty();` and then try `code.get()`. Identify the exception and fix it using `orElse("UNKNOWN")`.
3. Create an `Optional<User>` containing a User with a null email. Use `flatMap` with `normalizedEmail` to return an empty email Optional without throwing an exception.
4. Try `Optional.of("x").map(value -> (String) null)` and `Optional.of("x").flatMap(value -> (Optional<String>) null)`. Predict the difference and explain it.
5. Add a fallback method that prints `"fetching..."` before returning a result. Compare `orElse(fallback())` and `orElseGet(() -> fallback())` when the Optional already has a value.
6. Write `findOrder(id).orElseThrow(() -> new IllegalArgumentException("not found"))`. Distinguish a missing Order error from a failed database query.
7. From a list of IDs, use `map(this::findUser).flatMap(Optional::stream)` to collect the list of existing Users. Why can the resulting element count be smaller than the input ID count?
8. Suppose a legacy API returns `Optional<String>` or `null`. Write a boundary adapter to produce an always-valid Optional, then explain why the original API should be fixed.
9. Create `OptionalInt.of(0)` and `OptionalInt.empty()`. Check `isPresent` for each case. Why is 0 not “absent”?
10. Model a Result with three cases: “found”, “no data”, and “data source error”. Why is a single `Optional<User>` not enough to carry all those states?

## 14. Safety Checklist for `Optional`

- Does every method returning `Optional<T>` **always return an Optional object** instead of returning `null`?
- Has nullable input data been passed through `ofNullable` at the **right boundary**?
- Is `get()` called anywhere without proving the data is definitely present?
- When data is missing, is there a clear policy: skip, fallback, throw an error, or return a Result?
- When using `map`/`flatMap`, does the mapper have the right return type and can it return null?
- Does the fallback consume resources or have side effects; should `orElseGet` be used for lazy evaluation?
- Is “no data” being confused with “error while reading data”?
- Does anything rely on Optional object identity, or use dummy values like 0/`false` to indicate absence?
- Have you tested cases for **present, empty, null at the boundary, failing fallback, and failing mapper**?

**Remember:** `Optional` represents the presence or absence of a value, not a box that can “hold null” as a valid element. Unchecked `Optional.get()` can throw `NoSuchElementException`; `Optional.of(null)` throws `NullPointerException`; `ofNullable(null)` and `map` returning null produce an empty Optional; `flatMap` requires the mapper to return a **non-null** Optional. Choosing `map`, `flatMap`, `orElseGet`, and `orElseThrow` according to the intended semantics makes APIs clearer and reduces runtime errors.
