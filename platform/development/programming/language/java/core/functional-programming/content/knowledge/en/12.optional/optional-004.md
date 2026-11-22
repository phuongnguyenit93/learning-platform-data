# Distinguishing a `map` Function Returning `null` from `flatMap` Returning `null` in `Optional`

In Java, `Optional<T>` represents a result that **has a value** or **has no value**. When using higher-order APIs, `Optional.map` and `Optional.flatMap` both invoke the transformation function only when the initial `Optional` has a value, but they **handle a `null` result from the transformation function completely differently**:

- **`optional.map(mapper)`**: if `mapper` returns `null`, the result is `Optional.empty()`, and it does not throw an exception just because the mapper result is null.
- **`optional.flatMap(mapper)`**: `mapper` is required to return **a non-null `Optional` object**. If the mapper is actually invoked and returns `null`, `flatMap` throws `NullPointerException`.
- If the source `Optional` **is empty**, neither calls the mapper, so the result remains `Optional.empty()`; this case does not expose `flatMap`'s “mapper returns null” bug.

The distinction lies in **the return type contract of the transformation function** and how `Optional` represents absence, not in `map` being “safer” in all situations.

## 1. Reading the Signatures to Understand the Essence

In Java 17, the two methods have the form:

~~~java
// API signatures for reference; not a standalone Java program.
public <U> Optional<U> map(
        Function<? super T, ? extends U> mapper);

public <U> Optional<U> flatMap(
        Function<? super T, ? extends Optional<? extends U>> mapper);
~~~

In `map`, the `mapper` function returns **a regular value `U`**. That value can be `null`, and the API converts it into an empty state using logic equivalent to `Optional.ofNullable(result)`.

In `flatMap`, `mapper` returns **an `Optional` wrapping `U`**. `flatMap` uses the returned `Optional` object itself to avoid multiple layers of nesting; it does not automatically turn a `null` `Optional` reference into `Optional.empty()`.

You can visualize **the case where the source has a value** with pseudocode:

~~~java
// Pseudocode: illustrates the idea, not copied from JDK source code.
Optional<U> mapLike(T value, Function<T, U> mapper) {
    return Optional.ofNullable(mapper.apply(value));
}

Optional<U> flatMapLike(T value,
                        Function<T, Optional<U>> mapper) {
    return Objects.requireNonNull(mapper.apply(value));
}
~~~

The two illustrative functions above are not the complete methods in the `Optional` class. On an empty source `Optional`, the mapper is not invoked. The **`mapper` parameter itself must be non-null**: passing `map(null)` or `flatMap(null)` directly is invalid and will throw `NullPointerException`, even when the source `Optional` is empty.

## 2. Runnable Example: `map` Accepts a Null Result, `flatMap` Does Not

Create the file `OptionalNullMappingDemo.java`:

~~~java
import java.util.Optional;

public class OptionalNullMappingDemo {
    public static void main(String[] args) {
        Optional<String> present = Optional.of("Java");
        Optional<String> absent = Optional.empty();

        Optional<Integer> mapNull = present.map(s -> null);
        System.out.println("map(null result)=" + mapNull);

        try {
            Optional<Integer> flatMapNull = present.flatMap(s -> null);
            System.out.println(flatMapNull);
        } catch (NullPointerException e) {
            System.out.println("flatMap(null result)=NullPointerException");
        }

        Optional<Integer> emptyMap = absent.map(s -> null);
        Optional<Integer> emptyFlatMap = absent.flatMap(s -> null);
        System.out.println("empty.map=" + emptyMap);
        System.out.println("empty.flatMap=" + emptyFlatMap);

        Optional<Integer> correct = present.flatMap(
                s -> Optional.ofNullable((Integer) null));
        System.out.println("correct.flatMap=" + correct);
    }
}
~~~

~~~bash
javac --release 17 OptionalNullMappingDemo.java
java OptionalNullMappingDemo
~~~

Output:

~~~text
map(null result)=Optional.empty
flatMap(null result)=NullPointerException
empty.map=Optional.empty
empty.flatMap=Optional.empty
correct.flatMap=Optional.empty
~~~

Key values to note:

1. `present.map(s -> null)` **returns `Optional.empty()`**, because the mapping result is null.
2. `present.flatMap(s -> null)` **throws `NullPointerException`** because the function ran and returned a null `Optional` reference. The print statement inside `try` does not execute.
3. `absent.flatMap(s -> null)` **does not throw an error** in this example because the mapper does not run when the source is empty; the result remains empty.
4. `present.flatMap(s -> Optional.ofNullable((Integer) null))` is valid because the mapper returns **an actual `Optional.empty()` object**, not a null reference variable.

Do not infer from `empty.flatMap(s -> null)` running successfully that a mapper returning null is valid. It simply was not invoked. Write tests with a present source to verify the mapper's contract.

## 3. `map` Returns `Optional.empty()` When an Extracted Field Is Null

A common case is a getter returning a nullable value. If you want to turn a nullable into an `Optional`, `map` does this naturally.

Create the file `NullableGetterDemo.java`:

~~~java
import java.util.Optional;

public class NullableGetterDemo {
    record Account(String id, String nickname) {}

    public static void main(String[] args) {
        Optional<Account> account =
                Optional.of(new Account("A-1", null));

        Optional<String> nickname = account.map(Account::nickname);
        String display = nickname.orElse("(chưa đặt tên)");

        System.out.println("nickname=" + nickname);
        System.out.println("display=" + display);
    }
}
~~~

~~~bash
javac --release 17 NullableGetterDemo.java
java NullableGetterDemo
~~~

Output:

~~~text
nickname=Optional.empty
display=(chưa đặt tên)
~~~

Here, `Account::nickname` returns `String`, so **`map` is the appropriate choice**. When nickname is null, absence is represented by `Optional.empty()`.

If a getter **is defined to return `Optional<String>`**, for example `Account::findNickname`, then `flatMap` is usually more appropriate to avoid creating `Optional<Optional<String>>`. You need to distinguish between a nullable getter and a getter that returns `Optional`.

## 4. `flatMap` Is Used to Avoid `Optional<Optional<T>>`

When the transformation function itself returns `Optional<U>`, using `map` preserves the inner `Optional` layer:

~~~java
Optional<Optional<Integer>> nested =
        Optional.of("42").map(s -> Optional.of(Integer.parseInt(s)));
~~~

This is an **illustrative snippet** inside a method with `import java.util.Optional`. The type of `nested` is `Optional<Optional<Integer>>`, which is inconvenient to use.

Using `flatMap` flattens the two layers:

~~~java
Optional<Integer> flat =
        Optional.of("42").flatMap(s -> Optional.of(Integer.parseInt(s)));
~~~

When the lambda returns `Optional.empty()`, `flatMap` returns empty completely normally. The problem only arises when **the reference variable pointing to the `Optional` object itself is null**.

Comparison table for `Optional.of("x")`:

| Transformation function | Called with `map` | Called with `flatMap` |
| --- | --- | --- |
| `s -> "y"` | `Optional["y"]` | Does not compile: `String` is not `Optional`. |
| `s -> null` | `Optional.empty()` | `NullPointerException` when mapper is invoked. |
| `s -> Optional.of("y")` | `Optional[Optional["y"]]` | `Optional["y"]`. |
| `s -> Optional.empty()` | `Optional[Optional.empty]` | `Optional.empty()`. |
| `s -> Optional.ofNullable(null)` | `Optional[Optional.empty]` | `Optional.empty()`. |

**Note:** the forms in the table are notations for `Optional` results for easy comparison; they are not constructor expressions you can write directly in Java. `map` and `flatMap` clearly distinguish two kinds of functions: `T -> U` versus `T -> Optional<U>`.

## 5. Adapting a Nullable Function into a Mapper for `flatMap`

You may have a legacy API that returns a regular value or null:

~~~java
// Illustrative contract: null means not found.
static String lookupEmail(String username) {
    return username.equals("an") ? "an@example.com" : null;
}
~~~

This function returns `String`, so use `map`:

~~~java
Optional<String> email = Optional.of("binh")
        .map(LegacyDirectory::lookupEmail);
~~~

**The two snippets above illustrate the signature and how to call it; `LegacyDirectory` needs to be fully declared in a real program.**

If the pipeline is already designed around `flatMap`, write an adapter that returns `Optional` using `ofNullable`:

~~~java
Optional<String> email = Optional.of("binh")
        .flatMap(name -> Optional.ofNullable(lookupEmail(name)));
~~~

The approach above resides in the same class that has the `lookupEmail` method. The difference is contractual:

- `map(name -> lookupEmail(name))`: converts `String` or null into `Optional<String>`.
- `flatMap(name -> Optional.ofNullable(lookupEmail(name)))`: converts the nullable result into `Optional<String>` **inside** the mapper, then returns the exact type `flatMap` requires.
- `flatMap(name -> lookupEmail(name))` where `lookupEmail` returns `String`: **does not compile**, because the mapper's return type is not an `Optional`.

If the API actually has a method returning `Optional<String>`, prefer `flatMap(directory::findEmail)` and ensure the `findEmail` method **never returns null**, returning `Optional.empty()` when not found.

### Standalone Example: Bridging a Nullable API and an Optional API

Create the file `OptionalAdapterDemo.java`:

~~~java
import java.util.Optional;

public class OptionalAdapterDemo {
    static String legacyLookup(String name) {
        return name.equals("an") ? "an@example.com" : null;
    }

    static Optional<String> safeLookup(String name) {
        return Optional.ofNullable(legacyLookup(name));
    }

    public static void main(String[] args) {
        Optional<String> absentByMap =
                Optional.of("binh").map(OptionalAdapterDemo::legacyLookup);
        Optional<String> absentByFlatMap =
                Optional.of("binh").flatMap(OptionalAdapterDemo::safeLookup);
        Optional<String> presentByFlatMap =
                Optional.of("an").flatMap(OptionalAdapterDemo::safeLookup);

        System.out.println("map=" + absentByMap);
        System.out.println("flatMap=" + absentByFlatMap);
        System.out.println("found=" + presentByFlatMap);
    }
}
~~~

~~~bash
javac --release 17 OptionalAdapterDemo.java
java OptionalAdapterDemo
~~~

Output:

~~~text
map=Optional.empty
flatMap=Optional.empty
found=Optional[an@example.com]
~~~

The `safeLookup` API guarantees returning a valid `Optional` even when the legacy system returns null; this approach turns `flatMap` into a safe composition step.

## 6. Avoid Confusing “`Optional.empty()`” with “a null `Optional` reference”

Both may imply “no value” in casual speech, but at the Java object level they are different:

~~~java
Optional<String> empty = Optional.empty();
Optional<String> invalid = null;
~~~

- `empty` is **an `Optional` object in the empty state**. You can call `empty.isPresent()`, `empty.orElse(...)`, and use it in `flatMap`.
- `invalid` is **a null reference**, not an `Optional`. Calling any instance method on it can throw `NullPointerException`.
- A good contract for a method declared to return `Optional<T>` is to return `Optional.empty()` when absent, **not null**.
- `Optional.of(null)` throws `NullPointerException`; `Optional.ofNullable(null)` returns `Optional.empty()`.
- A non-empty `Optional` does not hold null inside; `Optional.ofNullable` uses null to represent absence rather than storing null as a “present value”.

Do not fix a `flatMap` mapper returning null by wrapping `orElse` **after** `flatMap`:

~~~java
// Incorrect when findOptionalValue() can return a null reference:
// source.flatMap(x -> findOptionalValue(x)).orElse(fallback);
~~~

Because `NullPointerException` occurs **before** `orElse` is executed. You need to fix the `findOptionalValue` API to return `Optional.empty()`, or handle the null reference right at the source according to a clear contract.

## 7. Empty Source `Optional` Cases Can Hide Bugs

When the source is `Optional.empty()`, both `map` and `flatMap` skip the mapper. This is the core meaning of transformations on Optional, but it also has testing implications:

~~~java
// Illustrative snippet running inside a method:
Optional<String> empty = Optional.empty();

Optional<Integer> result =
        empty.flatMap(s -> {
            throw new IllegalStateException("should not run");
        });
// result == Optional.empty(), the lambda does not run.
~~~

Bugs inside the mapper can be hidden if tests only use an empty source. Proper testing should have at least three groups: (1) empty source, (2) present source with mapper returning `Optional.of(value)`, (3) present source with mapper returning `Optional.empty()`; you can add a test that intentionally returns null to confirm the API violates the contract and throws `NullPointerException`.

For `map`, you should have a test for the mapper returning null if null is a valid possibility for the API. At the same time, verify whether turning null into empty matches the business policy or is masking an unexpected data error.

## 8. Practice with Nested Data Layers

Suppose a `User` record may lack a `Profile`, and `Profile` may lack a `displayName`. You can use a chain of `map` calls with nullable getters: each step converts a null result into empty, and subsequent steps are skipped.

Create the file `OptionalNestedDataDemo.java`:

~~~java
import java.util.Optional;

public class OptionalNestedDataDemo {
    record Profile(String displayName) {}
    record User(String id, Profile profile) {}

    static Optional<User> findUser(boolean hasProfile) {
        return Optional.of(new User(
                "u-1", hasProfile ? new Profile(null) : null));
    }

    public static void main(String[] args) {
        String a = findUser(false)
                .map(User::profile)
                .map(Profile::displayName)
                .orElse("(ẩn)");

        String b = findUser(true)
                .flatMap(user -> Optional.ofNullable(user.profile()))
                .flatMap(profile ->
                        Optional.ofNullable(profile.displayName()))
                .orElse("(ẩn)");

        System.out.println("without profile=" + a);
        System.out.println("without name=" + b);
    }
}
~~~

~~~bash
javac --release 17 OptionalNestedDataDemo.java
java OptionalNestedDataDemo
~~~

Output:

~~~text
without profile=(ẩn)
without name=(ẩn)
~~~

These are two valid approaches that have different meanings at the API level:

- With getters returning nullable values, `map(User::profile).map(Profile::displayName)` is concise and correct: each null layer becomes empty.
- With functions or repositories returning `Optional<Profile>` and `Optional<String>`, use `flatMap` to avoid nesting Optionals.
- In the example using `flatMap` even though the getters are nullable, the lambda **wrapped the getter with `Optional.ofNullable`**. If replaced with `flatMap(User::profile)`, Java does not compile because `profile()` returns `Profile` instead of `Optional`.

Do not use `Optional.get()` unconditionally at the end of a pipeline: after a `map` step returning null or a `flatMap` step returning `Optional.empty()`, the result may be empty and `get()` throws `NoSuchElementException`. Prefer `orElse`, `orElseGet`, or `orElseThrow` with specific business semantics.

## 9. Distinguishing from `Stream.flatMap`

The name `flatMap` is used in many Java APIs, **but the behavior with a mapper returning null is not uniform**:

- `Optional.flatMap`: if an element is present and the mapper returns a **null `Optional` reference**, it throws `NullPointerException`.
- `Stream.flatMap`: the mapper returns a `Stream`; according to the Stream contract, if the mapped stream is null, it **is treated as an empty stream**.

Full example `StreamFlatMapNullDemo.java`:

~~~java
import java.util.List;
import java.util.stream.Stream;

public class StreamFlatMapNullDemo {
    public static void main(String[] args) {
        List<String> values = Stream.of("a", "b", "c")
                .flatMap(s -> s.equals("b") ? null : Stream.of(s))
                .toList();
        System.out.println(values);
    }
}
~~~

~~~bash
javac --release 17 StreamFlatMapNullDemo.java
java StreamFlatMapNullDemo
~~~

Output:

~~~text
[a, c]
~~~

Do not extrapolate from `Stream.flatMap` to `Optional.flatMap`, or vice versa. Always read the contract of the API itself. A clearer and more convenient practice when working with streams is to return `Stream.empty()` instead of null, even when the API allows null.

## 10. When to Choose `map` vs. `flatMap`?

| Function you are calling | Example signature | Method to use | When there is no data |
| --- | --- | --- | --- |
| Returns a regular, non-nullable value | `int length(String s)` | `map` | If the source is empty, the result is empty. |
| Returns a regular, nullable value | `String nickname(User u)` | `map` | `null` from the mapper becomes empty. |
| Returns Optional per contract | `Optional<User> find(String id)` | `flatMap` | Mapper returns `Optional.empty()`. |
| Returns `Optional` but sometimes returns null | `Optional<User> brokenFind(...)` | Fix the function's contract | `flatMap` will throw NPE when the mapper runs and returns null. |
| Intentionally want to keep nested Optional | `Optional<U> find(...)` | `map` | The result can be `Optional<Optional<U>>`. |

**Note on data and errors:** `map` automatically turns a null mapper result into empty; sometimes this is the right way to express missing data, and sometimes it hides an error that the business logic wants to detect. If the mapper **is not allowed** to return null, you can use `Objects.requireNonNull(...)` inside the mapper to fail fast instead of silently treating it as absent:

~~~java
// Illustrative snippet, used when nickname is required to always be non-null.
Optional<String> nickname = account.map(
        a -> java.util.Objects.requireNonNull(
                a.nickname(), "nickname must not be null"));
~~~

If the requirement is that nullable data is valid, use `Optional.map`'s default mapping behavior. If the requirement is a function returning `Optional`, design the mapper to always return **a non-null Optional**.

## 11. Practical Troubleshooting Checklist

1. Check whether the **source `Optional` is present or empty**. With an empty source, the mapper does not run and tests may not expose bugs.
2. Identify the actual return type of the mapper: `U`, nullable `U`, `Optional<U>`, or a potentially null `Optional<U>` reference?
3. If the mapper returns a nullable `U`, use `map`; null is interpreted as empty.
4. If the mapper returns `Optional<U>`, use `flatMap` and ensure it returns `Optional.empty()` when not found.
5. When consuming a legacy API that returns a nullable value but you want to compose via `flatMap`, wrap the value with `Optional.ofNullable(...)` **inside the mapper**.
6. Do not use `orElse` to patch an exception from `flatMap` that has already occurred, do not use `Optional.of(null)`, and do not return null from a method with signature `Optional<T>`.
7. Test present values, absent values, mapper returning empty, and cases where the mapper violates its contract.
8. Do not infer `Optional.flatMap`'s null handling from `Stream.flatMap`.

**Key takeaway:** for a source `Optional` with a value, **`map(x -> null)` returns `Optional.empty()`**, whereas **`flatMap(x -> null)` throws `NullPointerException`**. With `flatMap`, “no result” must be represented by **`Optional.empty()`**, i.e., a valid Optional object, not a null reference.