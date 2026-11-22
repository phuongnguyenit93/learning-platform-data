# `map()`, `flatMap()`, and `filter()` on `Optional` in Java

`Optional<T>` represents a result **that may or may not have a value**. Instead of repeatedly checking for `null` and then calling methods on the inner value, Java provides three key operations for building functional-style processing pipelines:

- `map(...)`: **transforms** a present value from `T` to `U`.
- `flatMap(...)`: **transforms and flattens** when the processing function already returns an `Optional<U>`.
- `filter(...)`: **keeps or discards** a value based on a condition.

All three operations only apply the provided function **when the Optional has a value**. If it is `Optional.empty()`, the result remains empty and the mapper/predicate is not called. They return another `Optional`, allowing multiple steps to be chained without directly accessing absent data.

## 1. Foundation: present and absent states

`java.util.Optional<T>` is a value container class, commonly used as the **return type** of methods that might not find a result. For example:

~~~java
Optional<String> a = Optional.of("Java");       // Has a value
Optional<String> b = Optional.empty();         // No value
Optional<String> c = Optional.ofNullable(null); // No value
~~~

The snippet requires `import java.util.Optional;` and must be placed inside a method.

Distinguishing the factory methods:

| Creation method | Behavior |
| --- | --- |
| `Optional.of(value)` | `value` must be non-`null`; `null` causes the call to throw `NullPointerException` |
| `Optional.ofNullable(value)` | If `value == null`, returns `Optional.empty()`; otherwise, has a value |
| `Optional.empty()` | Creates an empty `Optional` |

`Optional` is not a multi-element collection; it holds at most **one** value. It is also **not designed to hold `null`**: `Optional.empty()` represents absence, whereas `Optional.of(null)` is invalid. When a pipeline ends, you can use `orElse(...)`, `orElseGet(...)`, `orElseThrow(...)`, or `ifPresent(...)` depending on how the application consumes the result.

At the type level, `Optional<T>` carries both the present/absent state. `map`, `flatMap`, and `filter` steps propagate this state through the chain, expressing intent clearly and reducing `if (x != null)` branches.

## 2. `map()`: transforming the content if present

General signature of the instance method:

~~~java
<U> Optional<U> map(Function<? super T, ? extends U> mapper)
~~~

`Function` is a functional interface with the method `U apply(T value)`. If the Optional contains `T`, `map` calls the mapper exactly once on that value and wraps the result in `Optional<U>`. If the input is empty, the mapper is **not called**, and the result is empty.

Example:

~~~java
Optional<String> source = Optional.of("  java  ");

Optional<Integer> length = source
        .map(String::trim)    // Optional<String> containing "java"
        .map(String::length); // Optional<Integer> containing 4
~~~

`String::trim` is a method reference equivalent to `s -> s.trim()`; `String::length` is equivalent to `s -> s.length()`. `map` not only transforms data but also allows changing the type from `Optional<String>` to `Optional<Integer>`.

### When the mapper returns null

A common point of confusion: `Optional.map` **accepts a mapper that produces a `null` result**, and converts that result into `Optional.empty()` (behaving like applying `ofNullable` to the value returned by the mapper).

~~~java
Optional<String> result = Optional.of("x")
        .map(value -> (String) null);
// result = Optional.empty()
~~~

This does **not** mean `null` is a valid value inside an Optional. If the mapper result is null, the pipeline becomes empty; subsequent `map` calls do not run their mappers.

Distinction: passing `null` as the `mapper` argument itself in `map(null)` is invalid and causes `NullPointerException`. When the Optional is empty, a valid mapper is skipped and not executed to produce a new value.

### Extracting an object's property

Suppose we have `record Account(String name, String email, boolean active) {}` and a method `findAccount(id)` returning `Optional<Account>`:

~~~java
Optional<String> displayName = findAccount("a")
        .map(Account::name);

String visibleName = displayName.orElse("Guest");
~~~

This is an **illustrative snippet**, not a standalone program. The full runnable example with `record Account` and `findAccount` is provided in section 5. `map` only reads the name when an Account is present; if no account is found, `displayName` is empty and `orElse("Guest")` provides the default value.

## 3. `filter()`: keeping or discarding a value

Signature:

~~~java
Optional<T> filter(Predicate<? super T> predicate)
~~~

`Predicate<T>` has the SAM `boolean test(T value)`. For an Optional with a value:

- Predicate returns `true` → Optional **keeps** the existing value.
- Predicate returns `false` → returns `Optional.empty()`.
- Predicate throws an exception → the exception is propagated; `filter` does not turn errors into empty.

For an empty Optional, the predicate does not run and the result remains empty.

Example:

~~~java
Optional<String> accepted = Optional.of("Java")
        .filter(s -> s.length() >= 4); // Optional[Java]

Optional<String> rejected = Optional.of("Java")
        .filter(s -> s.length() > 10); // Optional.empty
~~~

`filter` **does not transform** a `String` into another `String`. It is a check step to decide whether to keep the value. If you want to modify the string, use `map`; if you want to check the string and discard it if it fails, use `filter`.

Conditions can be chained together:

~~~java
Optional<String> validCode = Optional.of(" ab-123 ")
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .filter(s -> s.startsWith("ab-"));
// validCode contains "ab-123"
~~~

Here `map` cleans the value, the first `filter` discards empty strings, and the second `filter` keeps strings with the right prefix. If one filter returns false, subsequent functions do not run because the Optional is already empty.

## 4. `flatMap()`: avoiding `Optional<Optional<U>>` when the result is also an Optional

Signature:

~~~java
<U> Optional<U> flatMap(
        Function<? super T, ? extends Optional<? extends U>> mapper)
~~~

`flatMap` is used when the mapper already expresses **the possibility of absence** via an `Optional<U>`. It takes the Optional returned by the mapper and returns it as a flat Optional, without wrapping it in another Optional layer.

Suppose:

~~~java
static Optional<String> normalizedEmail(Account account) {
    return Optional.ofNullable(account.email())
            .map(String::trim)
            .filter(email -> !email.isBlank())
            .map(email -> email.toLowerCase(Locale.ROOT));
}
~~~

`normalizedEmail` is placed in the class containing `record Account` in the section 5 program; it requires importing `java.util.Optional` and `java.util.Locale`. The method returns `Optional<String>` because the email may be null or a blank string.

Starting from `Optional<Account>`:

~~~java
Optional<Account> account = findAccount("a");

Optional<Optional<String>> nested =
        account.map(OptionalPipelineDemo::normalizedEmail);

Optional<String> flat =
        account.flatMap(OptionalPipelineDemo::normalizedEmail);
~~~

`map` wraps the mapper's result in a new Optional, so the resulting type is **`Optional<Optional<String>>`**. `flatMap` returns the Optional produced by the mapper directly, so the type is **`Optional<String>`**.

To see the wrapping layers:

~~~text
map:     Optional<Account> -> Optional<Optional<String>>
flatMap: Optional<Account> -> Optional<String>
~~~

Concrete example with the data in section 5:

~~~text
map:     Optional[Optional[an@example.com]]
flatMap: Optional[an@example.com]
~~~

When the input value is empty, `flatMap` does not call the mapper and returns empty. When the mapper returns `Optional.empty()`, `flatMap` returns empty. **When the mapper actually returns `null`**, `flatMap` throws `NullPointerException`. This differs from `map`, where **a null return value** is converted to empty. If a legacy data source might return null, wrap the value with `Optional.ofNullable(...)` inside the mapper instead of returning null.

### Rule for choosing `map` or `flatMap`

Look at **the function's return type**:

| Function passed in | Method to use | Result type from `Optional<T>` |
| --- | --- | --- |
| `T -> U` | `map` | `Optional<U>` |
| `T -> Optional<U>` | `flatMap` | `Optional<U>` |
| `T -> boolean` | `filter` | `Optional<T>` |

For example, `Account::name` returns `String`, so use `map(Account::name)`. Meanwhile, `OptionalPipelineDemo::normalizedEmail` returns `Optional<String>`, so use `flatMap(...)`. Checking the signature properly avoids having to call `orElseThrow()` twice just to unwrap two unnecessary Optional layers.

Note: `Optional`'s `flatMap` flattens **one Optional layer returned by the mapper**. It does not have the same meaning as `Stream.flatMap`: with Stream, one element can produce multiple output elements, whereas with Optional there is still at most one value.

## 5. Complete example: map → filter → flatMap, Java 17+

Save the program to **`OptionalPipelineDemo.java`**:

~~~java
import java.util.Locale;
import java.util.Optional;

public class OptionalPipelineDemo {
    record Account(String name, String email, boolean active) {}

    static Optional<Account> findAccount(String id) {
        return switch (id) {
            case "a" -> Optional.of(new Account("An", " AN@EXAMPLE.COM ", true));
            case "b" -> Optional.of(new Account("Binh", null, false));
            default -> Optional.empty();
        };
    }

    static Optional<String> normalizedEmail(Account account) {
        return Optional.ofNullable(account.email())
                .map(String::trim)
                .filter(email -> !email.isBlank())
                .map(email -> email.toLowerCase(Locale.ROOT));
    }

    public static void main(String[] args) {
        Optional<Account> found = findAccount("a");

        String name = found.map(Account::name).orElse("Guest");
        Optional<Optional<String>> nested = found.map(OptionalPipelineDemo::normalizedEmail);
        Optional<String> flattened = found.flatMap(OptionalPipelineDemo::normalizedEmail);
        Optional<String> eligible = found
                .filter(Account::active)
                .flatMap(OptionalPipelineDemo::normalizedEmail);

        System.out.println("name=" + name);
        System.out.println("nested=" + nested);
        System.out.println("flat=" + flattened);
        System.out.println("eligible=" + eligible.orElse("none"));
        System.out.println("inactive=" + findAccount("b")
                .filter(Account::active)
                .flatMap(OptionalPipelineDemo::normalizedEmail)
                .orElse("none"));
        System.out.println("absent=" + findAccount("missing")
                .map(Account::name)
                .orElse("Guest"));

        System.out.println("length=" + Optional.of("Java")
                .map(String::length).orElse(0));
        System.out.println("nullMap=" + Optional.of("x")
                .map(value -> (String) null));
        System.out.println("filtered=" + Optional.of(4)
                .filter(number -> number > 10));
    }
}
~~~

Compile and run:

~~~bash
javac OptionalPipelineDemo.java
java OptionalPipelineDemo
~~~

**Exact stdout on Java 17+:**

~~~text
name=An
nested=Optional[Optional[an@example.com]]
flat=Optional[an@example.com]
eligible=an@example.com
inactive=none
absent=Guest
length=4
nullMap=Optional.empty
filtered=Optional.empty
~~~

Explanation:

1. `findAccount("a")` returns an active Account with an uppercase email containing extra whitespace.
2. `map(Account::name)` turns `Optional<Account>` into `Optional<String>`; then `orElse("Guest")` extracts `"An"`.
3. `map(OptionalPipelineDemo::normalizedEmail)` wraps the resulting Optional one more time, creating `Optional<Optional<String>>`, whereas `flatMap(...)` keeps exactly one layer.
4. `filter(Account::active)` keeps active Accounts before extracting the email. `findAccount("b")` returns an inactive Account, so the filter discards it; the email mapper does not run; the fallback prints `none`.
5. `findAccount("missing")` returns empty, so `Account::name` is not called; the result is `Guest`.
6. `map(String::length)` turns the string `"Java"` into the number `4`, and `map(value -> null)` returns empty; `filter(number -> number > 10)` discards `4`.

The example also demonstrates using `record` and switch expressions (both supported on JDK 17), method references, lambdas, and `Locale.ROOT` for consistent case normalization of technical identifiers. For user names or natural-language text, specific locale rules should be considered.

## 6. Execution order, short-circuiting, and consuming the result

Consider the expression:

~~~java
Optional<String> finalEmail = findAccount(id)
        .filter(Account::active)
        .flatMap(OptionalPipelineDemo::normalizedEmail)
        .filter(email -> email.endsWith("@example.com"));
~~~

This is a snippet placed in the example class, with `id` as a defined `String` variable. Step-by-step processing in order:

1. `findAccount(id)` returns an Optional.
2. `filter(Account::active)` only checks if an Account is present.
3. `flatMap(...)` only runs if the Account is still present, and may produce empty because the email is null/blank.
4. `filter(email -> ...)` only runs if the normalized email is present.

**No value is automatically restored** after an Optional becomes empty. Mappers and predicates of subsequent steps will be skipped. To provide a replacement value, use a consuming or fallback operation at the end such as `orElseGet(...)` or `or(...)`.

An important point: `Optional.map`/`flatMap`/`filter` operations on a present Optional execute their functions **eagerly when called**; they are not lazy pipelines like intermediate operations on `Stream`. Short-circuiting here means **skipping mappers/predicates when the Optional is empty**, not deferring all processing until `orElse` is called.

Ways to read the result:

~~~java
String emailOrDefault = finalEmail.orElse("unknown");
String emailOrComputed = finalEmail.orElseGet(() -> computeFallback());
String mustHaveEmail = finalEmail.orElseThrow();
finalEmail.ifPresent(System.out::println);
~~~

This is an illustrative snippet in a context with `finalEmail` and `computeFallback()`. `orElse("unknown")` takes a precomputed default; `orElseGet(supplier)` **only calls the supplier when empty**. If `computeFallback()` is expensive or has side effects, avoid `orElse(computeFallback())` because the method argument is evaluated beforehand, even when the Optional has a value. The zero-argument `orElseThrow()` throws `NoSuchElementException` if empty. `ifPresent(...)` only runs the consumer when a value exists.

You can also write:

~~~java
Optional<String> preferred = Optional.<String>empty()
        .or(() -> Optional.of("backup"));
~~~

`or(...)` (Java 9+) takes a supplier returning `Optional<String>` and provides an alternative Optional **only when empty**. It preserves the Optional model instead of extracting a raw value; this is useful if you want to continue chaining `map` or `filter` afterward.

## 7. Comparison with manual null-checking code

Suppose `repository.findById(id)` returns `Optional<Account>`, and `normalizedEmail(Account)` returns `Optional<String>`. Without a pipeline, you would have to manually check multiple levels and decide on missing-data states. With a pipeline:

~~~java
Optional<String> email = repository.findById(id)
        .filter(Account::active)
        .flatMap(this::normalizedEmail)
        .filter(value -> value.endsWith("@example.com"));
~~~

This is an **illustrative snippet inside an instance method**, requiring a `repository` variable and a corresponding `normalizedEmail` method; it is not a standalone runnable program. The pipeline form expresses: *find account → accept only active accounts → get optional email → accept only emails in the required domain*.

When there is no result, `email` is empty; it is neither `null` nor a default empty string. At the API boundary, the application can return HTTP 404, use a fallback, or record not-found according to the business contract. Avoid automatically treating every empty as an error: a false filter and absent source data can carry different meanings; if you need to distinguish the reasons, use a richer result type than `Optional`, such as a sealed result type or an intentional exception.

## 8. Common mistakes and how to fix them

### 8.1. Using `map` when the mapper already returns `Optional`

~~~java
Optional<Optional<String>> nested =
        findAccount("a").map(OptionalPipelineDemo::normalizedEmail);
~~~

The result has two layers. If the goal is just `Optional<String>`, use `flatMap`:

~~~java
Optional<String> flat =
        findAccount("a").flatMap(OptionalPipelineDemo::normalizedEmail);
~~~

Both snippets need to be placed within the scope of the example class. Do not force-cast `Optional<Optional<String>>` to `Optional<String>` as that will cause a type error; the right approach is choosing the appropriate operator.

### 8.2. Using `flatMap` for a function returning a regular value

~~~java
// Type mismatch: Account::name returns String, not Optional<String>.
// Optional<String> name = findAccount("a").flatMap(Account::name);

// Correct:
Optional<String> name = findAccount("a").map(Account::name);
~~~

`flatMap` requires the mapper to return an `Optional` itself (not a raw value). Conversely, `map` wraps the raw value automatically, including converting a null result to empty.

### 8.3. Returning null from a mapper used with `flatMap`

~~~java
// Wrong when a value is present: mapper returns null, flatMap throws NullPointerException.
// Optional<String> wrong = Optional.of("a").flatMap(x -> null);

// Correct: mapper returns an Optional, never null.
Optional<String> safe = Optional.of("a")
        .flatMap(x -> Optional.ofNullable((String) null));
~~~

Do not confuse `Optional.ofNullable(null)` with `null`. The former is a valid Optional that is empty; the latter is not an Optional.

### 8.4. Calling `get()` before the pipeline processes

~~~java
// Risky: if the account does not exist, get() throws NoSuchElementException.
// String unsafe = findAccount("missing").get().name();

// No need to unwrap Optional first:
String safeName = findAccount("missing")
        .map(Account::name)
        .orElse("Guest");
~~~

Use `orElseThrow(...)` when a value is **required** and you want the error stated clearly; use `orElseGet(...)` when you need to compute a fallback. Calling `isPresent()` followed by `get()` repeatedly usually defeats the purpose of a pipeline and duplicates conditional branches.

### 8.5. Confusing `filter` with data transformation

`filter(s -> s.trim())` will not compile because `Predicate` must return `boolean`, not `String`. If you need to normalize and then check, write:

~~~java
Optional<String> result = Optional.of("  ok ")
        .map(String::trim)
        .filter(s -> !s.isBlank());
~~~

### 8.6. Expecting every exception to turn into empty

`Optional` does not automatically catch exceptions inside a mapper or predicate. If `Integer.parseInt(...)` encounters malformed input, it still throws `NumberFormatException`. Handle errors at the responsible layer (or provide a parse function with an `Optional<Integer>` contract), then combine it with `flatMap`. Do not arbitrarily hide all programming errors as empty.

### 8.7. Performing side effects inside `map` or `filter`

The primary purpose of `map` is transformation, and `filter` is deciding whether to keep or discard a value. You should not write mappers that mutate external state, send emails, or write to a database just to take advantage of the pipeline running. Side effects can make behavior hard to understand and test, especially when multiple calls are reused. To perform an action with a present value, `ifPresent(...)` or explicit handling at the boundary is a clearer choice.

### 8.8. Ambiguity when a value is absent

The chain `findAccount(id).filter(Account::active)` returns empty both when **there is no account** and when the account is **inactive**. If the calling layer needs to distinguish "does not exist" from "locked/inactive", a plain Optional does not store the reason. In that case, design a status type or a different result contract; you cannot infer the cause from `isEmpty()` alone.

### 8.9. Using `Optional` at the wrong boundaries

`Optional` is well suited as a return type when a result may be absent, especially in behavioral APIs. It is not necessary to use it for every field, constructor parameter, or JPA field: some frameworks do not serialize/bind/persist Optional as expected; follow the conventions and contracts of the specific API/framework. Never let a method declared as `Optional<T>` return `null` itself: always return `Optional.of(...)`, `ofNullable(...)`, or `empty()`.

## 9. Quick-choice table

| Goal | Example | Result |
| --- | --- | --- |
| Turn `Optional<String>` into its length | `Optional.of("Java").map(String::length)` | `Optional[4]` |
| Turn a null mapper result into empty | `Optional.of("x").map(x -> (String) null)` | `Optional.empty` |
| Keep a number when it meets a condition | `Optional.of(4).filter(x -> x > 2)` | `Optional[4]` |
| Discard a number when it fails a condition | `Optional.of(4).filter(x -> x > 10)` | `Optional.empty` |
| Call a `T -> Optional<U>` function | `findAccount("a").flatMap(OptionalPipelineDemo::normalizedEmail)` | `Optional<String>` |
| Call a `T -> U` function | `findAccount("a").map(Account::name)` | `Optional<String>` |
| Read value or fallback | `someOptional.orElse("default")` | `String` |
| Compute fallback only when empty | `someOptional.orElseGet(() -> computeFallback())` | `String` |

A good Optional pipeline should clearly express: **transform with `map`, combine potentially absent steps with `flatMap`, keep/filter with `filter`, and then consume the Optional according to the business contract**. The return type of the passed-in function is the deciding criterion for choosing the right operator; the empty state continues to propagate without manual null branches.