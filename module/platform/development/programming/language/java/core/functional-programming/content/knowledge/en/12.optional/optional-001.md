# Optional: Representing the Presence or Absence of a Result in Java

## 1. Lesson Objectives

A lookup operation does not always find data: there might be no user with a given ID, no contact email, or no maximum value in an empty set. If a method only returns `null`, the caller must remember to check for it, which easily leads to `NullPointerException`.

**`java.util.Optional<T>`** is a **container type that may or may not hold a non-null value**. It more clearly expresses the contract of “**a result that may be absent**”:

- **Present:** `Optional` contains a non-null value of type T.
- **Empty:** `Optional` contains no value.

After this lesson, you will be able to create `Optional` instances properly, read and transform values without blindly calling `get()`, chain multiple lookup operations using `map`/`flatMap`, use `orElse`/`orElseGet`/`orElseThrow`, work with `Stream` and `OptionalInt`, design sensible return contracts, and recognize common pitfalls.

## 2. What Is Optional, and What Is It Not?

`Optional<T>` is a final class in `java.util`. It is **not a T** and **not a collection holding multiple T values**. It represents at most **one** value of type T or an empty state.

Visualization:

~~~text
Optional<User>
    |
    +-- present --> contains a non-null User
    |
    +-- empty ----> no User
~~~

A method returning `Optional<User>` tells the caller that **they must handle the not-found case**. For example:

~~~java
Optional<User> findUserById(int id);
~~~

This is only an **illustrative signature**, assuming the `User` class exists; it is not a standalone Java program.

Important points:

- **Empty is not necessarily an error.** For example, “no search results found” can be a valid outcome.
- **Optional does not by itself describe the reason for absence.** Not found, unauthorized access, and database failure are three different situations; do not automatically turn all of them into `Optional.empty()`.
- **Optional does not replace every null value across the entire application.** It is especially useful as a **return type** where absence is an expected outcome.
- **Optional does not guarantee that the object inside is immutable.** If it holds a mutable object, methods on that object can still mutate its state.
- **Optional does not run asynchronously on its own.** It is an object describing the presence of a result, unlike `Future`/`CompletableFuture`, which represent work that may complete later.

### 2.1. Distinguishing Empty, Null, and Errors

| Situation | Usually Appropriate Representation | Meaning |
| --- | --- | --- |
| Finding a user by ID, but the user does not exist | `Optional.empty()` | No result, which may be normal |
| A legacy API returns null when data is missing | `Optional.ofNullable(value)` at the boundary | Converts null to empty |
| User enters an invalidly formatted ID | Validation result or appropriate exception | Invalid input |
| Database connection fails | Exception / error result with a cause | Operation failed; does not mean the user does not exist |
| Finding the maximum value in an empty stream | `OptionalInt.empty()` or `Optional<T>.empty()` | Aggregation with no elements |

Because `Optional` only has two states, when an application needs to record the **reason for failure**, create a result type with status and error information or throw an exception according to the contract.

## 3. Creating Optional: empty, of, and ofNullable

Java provides three basic factory methods:

~~~java
Optional<String> none = Optional.empty();
Optional<String> known = Optional.of("Java");
Optional<String> maybe = Optional.ofNullable(null);
~~~

Results:

- `none` is an empty Optional.
- `known` contains the string `"Java"`.
- `maybe` is an empty Optional because the argument is null.

### 3.1. Optional.of(value)

`Optional.of(value)` is used when **value is guaranteed to be non-null**. If null is passed, it **throws `NullPointerException` immediately at creation time**.

~~~java
String language = "Java";
Optional<String> result = Optional.of(language);

// Do not do this when the value might be null:
// Optional<String> wrong = Optional.of(null);
~~~

Using `of` expresses a strong expectation: a null at that point violates the contract and should be caught rather than silently treated as absent.

### 3.2. Optional.ofNullable(value)

`Optional.ofNullable(value)` is used when the source may return null:

~~~java
String legacyValue = null;
Optional<String> result = Optional.ofNullable(legacyValue);

System.out.println(result.isEmpty()); // true
~~~

This is the right tool for converting from a legacy API that may return null into Optional-based processing. It **does not inspect the content** of a string: `""` or `"   "` are still **non-null** strings and therefore will still be wrapped as present.

### 3.3. Optional.empty()

`Optional.empty()` explicitly states “no value”. When returning from a method, use:

~~~java
static Optional<String> findNickname(boolean available) {
    return available ? Optional.of("Lan") : Optional.empty();
}
~~~

This is an illustrative method that needs to be placed inside a class with `Optional` imported.

**Do not return `null` from a method whose return type is `Optional<T>`**: doing so forces the caller to null-check the Optional itself, defeating much of the contract's benefit.

## 4. Checking Presence or Absence

Methods:

- **`isPresent()`**: true if it contains a value.
- **`isEmpty()`**: true if it contains no value (Java 11+).
- **`ifPresent(Consumer<? super T>)`**: runs an action if a value is present.
- **`ifPresentOrElse(Consumer<? super T>, Runnable)`**: runs one of the two branches (Java 9+).

~~~java
Optional<String> name = Optional.of("An");

System.out.println(name.isPresent()); // true
System.out.println(name.isEmpty());   // false

name.ifPresent(value -> System.out.println("Hello " + value));
~~~

`isPresent()` is a check; it **does not extract the value**. You can write `if (opt.isPresent()) { use(opt.get()); }`, but when you simply need to process the result, `ifPresent`, `map`, `flatMap`, or `orElse...` usually makes the intent clearer and avoids scattering `get()` throughout the code.

### 4.1. Two Branches with Business Meaning

~~~java
Optional<String> nickname = Optional.empty();

nickname.ifPresentOrElse(
        value -> System.out.println("Name: " + value),
        () -> System.out.println("No nickname")
);
~~~

Output: `No nickname`. This is an example with a console-printing side effect. For computation functions that need to **return a value**, prefer `map` and an appropriate fallback method rather than writing into a mutable variable outside the lambda.

### 4.2. Optional Does Not Create a New Value When Only Checked

A common mistake is calling `isPresent` in multiple places and repeating the same lookup operation:

~~~java
// Avoid querying multiple times just to check and then read.
// if (repository.find(id).isPresent()) {
//     return repository.find(id).get();
// }
~~~

Between the two calls, the data may change, and it also wastes query cost. **Obtain one Optional**, process that exact value, and decide how to respond.

## 5. Safely Extracting Values: orElse, orElseGet, orElseThrow

### 5.1. orElse(defaultValue)

`orElse` returns the present value, or uses the default value when the Optional is empty:

~~~java
String display = Optional.<String>empty()
        .orElse("Khách vãng lai"); // "Khách vãng lai"
~~~

When calling `opt.orElse(expression)`, Java **evaluates expression before calling the method**, regardless of whether opt contains data or not. Therefore, if the fallback expression is expensive to compute or has side effects, it still runs even when not needed.

### 5.2. orElseGet(supplier)

`orElseGet` takes a `Supplier<? extends T>` and only calls `get()` when the Optional is empty:

~~~java
String value = Optional.of("Saved")
        .orElseGet(() -> loadDefaultName()); // Only call the fallback when empty.
~~~

This is an illustrative snippet that requires a `loadDefaultName()` method in context. Since the Optional contains `"Saved"`, the supplier **is not called**.

Clear comparison:

~~~java
String direct = known.orElse(expensiveFallback());
String lazy = known.orElseGet(() -> expensiveFallback());
~~~

In this example, `known` is assumed to be an `Optional<String>` and `expensiveFallback()` returns a `String`. With `orElse`, the fallback is evaluated eagerly beforehand. With `orElseGet`, the fallback is executed **only when needed**. If the fallback is just a cheap constant like `"N/A"`, `orElse` is completely reasonable.

### 5.3. orElseThrow()

`orElseThrow()` (no-arg, Java 10+) returns the value if present, otherwise throws `NoSuchElementException`. The overload taking a supplier lets you create an exception with business meaning:

~~~java
String required = Optional.of("ready").orElseThrow();

String user = Optional.<String>empty().orElseThrow(
        () -> new IllegalArgumentException("Missing user")
);
~~~

The second illustrative snippet **will throw** `IllegalArgumentException`; it is not an assignment that successfully creates the `user` variable.

Use `orElseThrow` when, by contract, **a value must exist at that point**. If not finding a value is a normal state, do not throw exceptions arbitrarily; choose a fallback or pass the Optional up to the calling layer.

### 5.4. Avoid Calling get() Without Checking

~~~java
Optional<String> value = Optional.empty();
// String invalid = value.get(); // Throws NoSuchElementException.
~~~

`get()` still exists to access a value when you are certain it is present, but the `Optional` type itself is a signal to consider the empty case. In modern Java, `orElseThrow()` expresses the “must be present” expectation more clearly, while `orElse`/`orElseGet` express fallbacks.

## 6. Transforming Optional with map

`map` applies a `Function<? super T, ? extends U>` **if the Optional currently holds a value**, then returns `Optional<U>`. If empty, the mapper is not called and the result remains empty.

~~~java
Optional<String> raw = Optional.of("  Java  ");

Optional<Integer> length = raw
        .map(String::strip)
        .map(String::length);

System.out.println(length.orElse(0)); // 4
~~~

Steps:

1. `raw` holds the string `"  Java  "`.
2. `String::strip` produces `"Java"`.
3. `String::length` yields int 4, boxed into an Integer inside `Optional<Integer>`.
4. `orElse(0)` returns 4.

If `raw = Optional.empty()`, `strip` and `length` do not run, and `orElse(0)` returns 0.

### 6.1. Mapper Returning null

By the contract of `Optional.map`, the mapper's result is wrapped as if by `Optional.ofNullable`. Thus, **if the mapper returns null, the result of map is Optional.empty()**:

~~~java
record Profile(String email) { }

Optional<Profile> profile =
        Optional.of(new Profile(null));

Optional<String> email =
        profile.map(Profile::email);

System.out.println(email.isEmpty()); // true
~~~

This is an illustrative snippet that needs to be placed inside a Java class with `Optional` imported. You do not need to manually call `ofNullable` inside `map` when the mapper already returns a nullable value.

This behavior **differs from flatMap**: `flatMap` requires the mapper itself to return a **non-null** `Optional` object, as explained next.

## 7. Keeping Only Matching Values with filter

`filter(Predicate<? super T>)` keeps the Optional intact if the contained value **satisfies the condition**; otherwise it returns empty.

~~~java
Optional<String> validCode = Optional.of(" A01 ")
        .map(String::strip)
        .filter(code -> !code.isBlank());

Optional<String> blankCode = Optional.of("   ")
        .map(String::strip)
        .filter(code -> !code.isBlank());

System.out.println(validCode.orElse("missing")); // A01
System.out.println(blankCode.isEmpty());         // true
~~~

`filter` does not convert the data type; it checks whether the current value should continue to be considered a valid result.

### 7.1. Separating Missing Values from Invalid Values

Some business requirements demand **reporting an error** if data is present but invalid. In that case:

~~~java
Optional<String> code = Optional.of("invalid");
Optional<String> accepted = code.filter(c -> c.startsWith("A"));
~~~

`accepted` is empty, but the caller **does not know why**: was there no code originally, or was a code present that failed the condition? If you need to distinguish these cases, use a result type that carries validation details instead of relying solely on Optional after filter.

## 8. Chaining Lookups with flatMap

`flatMap` is the solution when the mapper function **already returns `Optional<U>`**.

Suppose:

~~~java
static Optional<User> findUser(int id) { /* ... */ }
static Optional<String> findEmail(User user) { /* ... */ }
~~~

These two methods are only hypothetical signatures; the `/* ... */` bodies are not implemented.

If you use `map`:

~~~java
Optional<Optional<String>> nested =
        findUser(1).map(user -> findEmail(user));
~~~

The result is a **nested Optional inside an Optional**. To keep a single wrapper layer:

~~~java
Optional<String> email =
        findUser(1).flatMap(user -> findEmail(user));
~~~

`flatMap` invokes the function only when the first Optional contains a User; the function must return an `Optional<String>`. If the function returns `Optional.empty()`, the entire chain becomes empty.

### 8.1. Important Difference Regarding null

- `map(user -> null)` can return **Optional.empty()** via `ofNullable`.
- `flatMap(user -> null)` **throws NullPointerException** if the mapper is invoked, because `flatMap` does not accept a **null Optional return value**.
- `flatMap(user -> Optional.empty())` is the proper way to represent **no result** from an Optional-returning mapper.

Do not write methods declared to return `Optional<T>` that occasionally return null. A consistent contract must always return a **non-null Optional**, either present or empty.

## 9. Complete Java 17 Program: Looking Up Users and Potentially Absent Emails

Illustrative problem:

- ID 1 exists with an email that needs normalization.
- ID 2 exists, but its email is null in legacy data.
- ID 99 has no user.
- An order has a `userId` and needs to retrieve the owner's email.
- We need both to read individual results and to collect actual emails from a set of IDs.

Save the file **OptionalLessonDemo.java**:

~~~java
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import java.util.OptionalInt;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class OptionalLessonDemo {
    record User(int id, String name, String email) { }
    record Order(String code, int userId) { }

    static Optional<User> findUser(int id) {
        if (id == 1) {
            return Optional.of(
                    new User(1, " Lan ", " Lan@Example.com ")
            );
        }
        if (id == 2) {
            return Optional.of(new User(2, "An", null));
        }
        return Optional.empty();
    }

    static Optional<String> normalizedEmail(int id) {
        return findUser(id)
                .map(User::email)
                .map(String::strip)
                .filter(email -> !email.isBlank())
                .map(email -> email.toLowerCase(Locale.ROOT));
    }

    static Optional<String> ownerEmail(Order order) {
        return Optional.ofNullable(order)
                .flatMap(o -> normalizedEmail(o.userId()));
    }

    public static void main(String[] args) {
        System.out.println("lookup 1: "
                + findUser(1).isPresent());
        System.out.println("lookup 99 empty: "
                + findUser(99).isEmpty());

        System.out.println("email 1: "
                + normalizedEmail(1).orElse("<missing>"));
        System.out.println("email 2: "
                + normalizedEmail(2).orElse("<missing>"));
        System.out.println("email 99: "
                + normalizedEmail(99).orElseGet(() -> "no-email"));

        System.out.println("owner 1: "
                + ownerEmail(new Order("O-1", 1)).orElse("none"));
        System.out.println("owner 99: "
                + ownerEmail(new Order("O-2", 99)).orElse("none"));

        System.out.println("normalized name: "
                + findUser(1)
                        .map(User::name)
                        .map(String::strip)
                        .orElseThrow());

        findUser(2).ifPresentOrElse(
                user -> System.out.println("user 2: " + user.name()),
                () -> System.out.println("user 2: missing")
        );
        findUser(99).ifPresentOrElse(
                user -> System.out.println("user 99: " + user.name()),
                () -> System.out.println("user 99: missing")
        );

        long presentEmails = Stream.of(1, 2, 99)
                .map(OptionalLessonDemo::normalizedEmail)
                .flatMap(Optional::stream)
                .count();
        System.out.println("email count: " + presentEmails);

        OptionalInt max = IntStream.of(3, 8, 5).max();
        System.out.println("max: " + max.orElse(-1));
    }
}
~~~

Compile and run with **JDK 17 or later**:

~~~bash
javac OptionalLessonDemo.java
java OptionalLessonDemo
~~~

**Exact output:**

~~~text
lookup 1: true
lookup 99 empty: true
email 1: lan@example.com
email 2: <missing>
email 99: no-email
owner 1: lan@example.com
owner 99: none
normalized name: Lan
user 2: An
user 99: missing
email count: 1
max: 8
~~~

### 9.1. Explaining the States

1. **findUser(1)** returns an Optional containing a User, so `isPresent()` is true.
2. **findUser(99)** returns Optional.empty, so `isEmpty()` is true.
3. **normalizedEmail(1)** extracts the email, `strip()` removes whitespace, and `toLowerCase(Locale.ROOT)` normalizes it to `lan@example.com`.
4. **normalizedEmail(2)**: the User exists, but `email == null`; `map(User::email)` turns the result into empty, subsequent steps do not run, and `orElse("<missing>")` provides the fallback.
5. **normalizedEmail(99)**: the User lookup itself is already empty. `orElseGet` produces the `no-email` fallback when needed.
6. **ownerEmail** uses `flatMap` to chain a User lookup and an email lookup without creating `Optional<Optional<String>>`.
7. **ifPresentOrElse** chooses the corresponding action for User 2 (present) and User 99 (absent).
8. **Optional.stream()** returns a stream with one element when present and an empty stream when empty. After `flatMap(Optional::stream)`, out of the three IDs only ID 1 has an email, so `count() == 1`.
9. **IntStream.max()** returns `OptionalInt` because an empty stream has no maximum value. For 3, 8, 5, the result is 8.

The program simulates in-memory data so it produces deterministic output. In a real system, database/API lookups can fail: **do not convert every query error into empty** if the business logic must distinguish “not found” from “the system could not access the data”.

## 10. Optional.stream and Data Pipelines

Since Java 9, `Optional<T>.stream()` converts an Optional into:

- A stream with **one element** if present.
- A stream with **zero elements** if empty.

Example:

~~~java
List<Optional<String>> values = List.of(
        Optional.of("A"),
        Optional.empty(),
        Optional.of("B")
);

List<String> available = values.stream()
        .flatMap(Optional::stream)
        .toList();

System.out.println(available); // [A, B]
~~~

`Optional::stream` is especially useful when each record can transform into **0 or 1** valid values. In a pipeline, using `flatMap(Optional::stream)` unwraps the Optional layer while discarding elements that have no result.

If the input is a stream and the mapper returns Optional, you can write:

~~~java
List<String> emails = ids.stream()
        .map(thisService::lookupEmail)
        .flatMap(Optional::stream)
        .toList();
~~~

This is an **illustrative snippet**, requiring an `ids` variable and a `thisService` object with a matching `lookupEmail` method. You should not assume that lookups inside a pipeline are always safe for parallel execution; that depends on the repository, connections, side effects, and error policy.

## 11. Optional for Primitive Types

Java has three specialized Optional types:

| Type | When Present | Value Extraction Method |
| --- | --- | --- |
| **OptionalInt** | holds a primitive `int` | `getAsInt()` |
| **OptionalLong** | holds a primitive `long` | `getAsLong()` |
| **OptionalDouble** | holds a primitive `double` | `getAsDouble()` |

They avoid boxing when you only need to represent the presence or absence of a primitive value.

~~~java
OptionalInt maximum = IntStream.of(4, 9, 2).max();
System.out.println(maximum.orElse(-1)); // 9

OptionalInt none = IntStream.empty().max();
System.out.println(none.isEmpty());     // true
~~~

The primitive Optional APIs share many similarities, but **they are not identical to `Optional<T>`**. For instance, they do not provide the general `map`/`flatMap` methods that `Optional<T>` has; when you need a rich transformation pipeline, consider primitive Streams or another suitable data type.

**Important:** `OptionalInt.empty()` is not the number 0; `OptionalInt.of(0)` represents a value that is **present and equal to 0**. Do not use 0 or -1 to mean “absent” if they can be valid values, unless the business contract allows a sentinel.

## 12. When Should an API Return Optional?

A pragmatic rule: use `Optional<T>` as the **return type** if the absence of a result is an expected situation.

~~~java
Optional<User> findById(long id);
Optional<String> findNickname(User user);
Optional<Order> findLatestOrderFor(User user);
~~~

These are illustrative API signatures; the User/Order types are not defined for these signatures.

Naming should tell the caller **what might not exist**. For a repository, distinguish:

- `findById`: not found → Optional.empty.
- `getRequiredById` or `loadRequired`: missing data → exception per contract.
- `validate`: returns a validation result with a reason when needed, not necessarily an Optional.

When an API is guaranteed to have a value, returning **T** is usually simpler than `Optional<T>`. Do not wrap every method in Optional just to look “safer” when there is no genuine absence case.

### 12.1. Should Optional Be Used as a Parameter?

Example API:

~~~java
void sendMessage(Optional<String> nickname);
~~~

This is syntactically valid, but many conventional Java APIs are easier to use with overloads, explicit default values, or a request type containing optional fields. Callers have to construct an Optional when passing arguments, sometimes adding unnecessary wrapping. **There is no absolute ban** on using Optional as a parameter, but weigh the contract benefits against codebase conventions.

### 12.2. Should Optional Be Stored in a Field?

An `Optional<String>` field is valid in the language, but it is not inherently better than a String field with a clear contract or a dedicated model. `Optional` was designed primarily for **return results that may be missing**, not as a universal solution for every optional property in a DTO or entity.

Pay attention to compatibility issues with frameworks, mapping, and serialization. `Optional` **does not implement Serializable** in Java 17; do not assume an object containing an Optional field can be handled by default Java serialization without custom mechanisms.

## 13. A Present Value Does Not Mean a Valid Value

`Optional.of("")` and `Optional.of("   ")` are both present. If the business logic considers empty or whitespace-only strings invalid, handle it like this:

~~~java
Optional<String> normalized = Optional.ofNullable(input)
        .map(String::strip)
        .filter(text -> !text.isBlank());
~~~

This is a snippet in a context where a String variable `input` already exists. Strings that become empty after normalization will turn into Optional.empty.

However, if the application needs to report “string has an invalid format”, `filter` discards the reason. Separate **whether data exists** from **whether data is valid** when the business logic needs to distinguish those two questions.

### 13.1. Optional Does Not Make a Non-Null Value Immutable

~~~java
List<String> mutable = new ArrayList<>();
Optional<List<String>> holder = Optional.of(mutable);

mutable.add("A");
System.out.println(holder.orElseThrow()); // [A]
~~~

Optional holds a reference to the List; it does not deep-copy or lock the List's state. If multiple threads modify the collection concurrently, you need synchronization or appropriate immutable data structures.

## 14. Exception Handling and Error Boundaries

`Optional.empty()` only says **there is no result**. When a network or database API fails, “unable to look up” is usually different from “looked up and found nothing”. If you swallow every exception and return empty, the system may misinterpret an outage as a valid result.

Do not do the following if errors need to be reported:

~~~java
// Anti-pattern:
// try {
//     return repository.find(id);
// } catch (Exception ignored) {
//     return Optional.empty(); // Hides the query error.
// }
~~~

A better approach:

- If **the lookup succeeded but no record exists**, return empty.
- If **the input is invalid**, respond with a validation error.
- If **the system failed**, throw a meaningful exception or use an error-carrying result, depending on the caller's contract.
- If you need the reason for absence (e.g., “pending approval”, “locked”, “insufficient permissions”), use a `Result` or `Decision` type with explicit states rather than just Optional.

An `Optional<T>` can be combined with `CompletableFuture` for asynchronous tasks—for example, a future that eventually completes with `Optional<User>`—but the two classes represent **two different axes**: completion timing and result presence.

## 15. Common Mistakes

| Mistake | Consequence | How to Fix |
| --- | --- | --- |
| Calling `optional.get()` without checking | `NoSuchElementException` if empty | `orElse`, `orElseGet`, `orElseThrow`, `map`, or `ifPresent` |
| Using `Optional.of(nullable)` | May throw `NullPointerException` at creation time | `ofNullable` at nullable boundaries |
| Returning null from a method declared to return Optional | Callers still have to null-check | Always return `Optional.of`, `ofNullable`, or `empty` |
| Treating empty as a database exception | Masks outages and error causes | Separate “not found” from “lookup failed” |
| Using `map` for a function that already returns Optional | Creates `Optional<Optional<T>>` | Use `flatMap` |
| Returning null from a `flatMap` mapper | `NullPointerException` when invoked | Mapper must return a non-null Optional |
| Using `orElse(expensive())` thinking it is lazy | Fallback is still evaluated even when present | `orElseGet(() -> expensive())` |
| Using `Optional.of(0)` as empty | Confuses valid 0 with absence | Use `OptionalInt.empty()` or Optional.empty() |
| Using Optional to replace every parameter/field | Harder-to-read API, unnecessary wrapping | Prefer Optional for return results that may be absent |
| Believing Optional guarantees deep immutability | Inner object can still be mutable | Manage ownership or use immutable data |
| Putting side effects that must run inside `map` | Unpredictable pipeline, hard to test | Separate computation from intentional side effects |

## 16. How to Test Optional

For a method returning Optional, test at least **both states**:

1. Data found → Optional is present, value is correct.
2. Not found → Optional is empty, no exception thrown if that is the normal case.
3. Legacy data returns null → `ofNullable` or `map` converts it to empty as contracted.
4. `filter` excludes data that does not meet the condition.
5. `flatMap` avoids nested Optionals.
6. `orElseGet` executes the fallback only when empty.
7. `orElseThrow` throws the expected exception type when a value is required.
8. Real system errors are propagated properly, not conflated with empty.

Example testing the lazy behavior of `orElseGet` without needing a real service:

~~~java
java.util.concurrent.atomic.AtomicInteger calls =
        new java.util.concurrent.atomic.AtomicInteger();

String first = Optional.of("ready").orElseGet(() -> {
    calls.incrementAndGet();
    return "fallback";
});
String second = Optional.<String>empty().orElseGet(() -> {
    calls.incrementAndGet();
    return "fallback";
});

System.out.println(first);       // ready
System.out.println(second);      // fallback
System.out.println(calls.get()); // 1
~~~

This is an illustrative snippet that needs to be placed inside a class/method with `Optional` imported. `AtomicInteger` is only used to **count fallback invocations for the test**, not as a mandatory pattern for business logic. Verifying `calls == 1` shows that the supplier did not run when `first` was present.

## 17. Practice Exercises

### Exercise 1 — Converting null to Optional

A legacy API returns a nullable `String`. Convert it into an `Optional<String>`, trim whitespace, and treat an empty string as having no value.

**Suggested solution:**

~~~java
Optional<String> cleaned = Optional.ofNullable(legacyValue)
        .map(String::strip)
        .filter(value -> !value.isEmpty());
~~~

`legacyValue` is assumed to be an already-declared String variable. If null → empty; if `"  Java  "` → Optional containing `"Java"`; if `"   "` → empty.

### Exercise 2 — Choosing orElse or orElseGet

You have `Optional<String> cached`. To fetch a fallback via an expensive query **only when data is absent**, which method should you use?

**Answer:** `cached.orElseGet(() -> queryFallback())`. Do not use `cached.orElse(queryFallback())` if you want to avoid unnecessary queries, because the argument to `orElse` is evaluated beforehand.

### Exercise 3 — map or flatMap?

Given `Optional<User> user` and the method `Optional<String> findEmail(User u)`. To obtain `Optional<String>`, what should you use?

**Answer:**

~~~java
Optional<String> email = user.flatMap(thisService::findEmail);
~~~

This is a snippet with `user` and `thisService` already available. Using `map` in this situation would produce `Optional<Optional<String>>`.

### Exercise 4 — Distinguishing 0 from Absence

You have an inventory quantity lookup: a result of **0 is valid**, whereas **no such item** means absent. Should you return an `int` using 0 as a sentinel, or return `OptionalInt`?

**Answer:** `OptionalInt` (or a richer domain result type if needed) lets you distinguish **present and equal to 0** from **empty**. Do not use 0 as a not-found signal when 0 is a valid quantity.

### Exercise 5 — Designing an API Contract

Distinguish three situations for `findCustomer(id)`: customer does not exist, invalid ID, and database connection failure. Design the signature or response rules so they are not mixed together.

**Hint:** You can use `Optional<Customer>` for a successful lookup with no data, a validation exception/error result for an invalid ID, and a database exception/error result with a cause for query failures. For applications that need to return a structured result for every situation, use a project-defined `Result<Customer,Error>` type.

## 18. Key Takeaways

**Optional<T> represents a result that either has a non-null value or does not.** It helps a method's contract explicitly indicate the possibility of “not found”, but it does not replace error handling and does not turn mutable data into immutable data.

- **Create:** `empty()`, `of(nonNull)`, `ofNullable(nullable)`.
- **Check:** `isPresent()`, `isEmpty()`, `ifPresent(...)`, `ifPresentOrElse(...)`.
- **Handle presence/absence:** `orElse` (eager fallback), `orElseGet` (lazy fallback), `orElseThrow` (value required).
- **Transform:** `map` when the mapper returns a regular value; `flatMap` when the mapper already returns an Optional; `filter` when keeping only values that meet a condition.
- **Pipelines:** `Optional.stream()` to produce 0 or 1 element; `OptionalInt`/`OptionalLong`/`OptionalDouble` to represent primitive results that may be missing.

Return Optional when **absence is a valid outcome of the API**. Handle empty explicitly, do not call `get()` arbitrarily, and do not use empty to hide business errors or system failures.
