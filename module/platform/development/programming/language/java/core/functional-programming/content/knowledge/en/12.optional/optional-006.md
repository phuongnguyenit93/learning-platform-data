# Optional.or(), orElseThrow(), and Choosing How to Handle Missing Values

## Objectives

`Optional<T>` in `java.util` represents a result **that may hold a non-`null` value or no value**. When an `Optional` is empty, an application should not always return a default constant: in some cases it needs to look up another source, in other cases it needs to report an error, skip the work, or terminate the processing flow.

This lesson focuses on two groups of operations:

- `or(Supplier<? extends Optional<? extends T>>)`: **continue searching for another `Optional`** when the first source is empty.
- `orElseThrow()` and `orElseThrow(Supplier<? extends X>)`: **retrieve a required value** or throw an exception when no value is present.

After this lesson, you will be able to distinguish between APIs for handling “no value”, choose an appropriate fallback mechanism, predict when a Supplier is invoked, use checked exceptions properly, and avoid `null` bugs, wrong-layer exceptions, or unnecessary queries.

## 1. Understanding Optional Before Choosing a Handling Branch

An `Optional<String>` is commonly created in three ways:

```java
import java.util.Optional;

Optional<String> present = Optional.of("An");
Optional<String> absent = Optional.empty();
Optional<String> possiblyAbsent = Optional.ofNullable(null);
```

- `Optional.of(value)` creates an Optional containing `value` and throws `NullPointerException` if `value == null`.
- `Optional.ofNullable(value)` creates an Optional with a value when `value != null`, or an empty Optional when `value == null`.
- `Optional.empty()` creates an empty Optional.

An `Optional` is not a “box containing `null`”: if it is empty, there is no element inside. This allows an API to express that data was not found using an intentional state, rather than leaving every caller to guess what `null` means.

Consider the business logic of finding a display name:

1. First, look up the name configured specifically for the user.
2. If not present, try the name in the backup profile.
3. If still not present, either use a valid default name or throw an exception depending on correctness requirements.

**The final choice must be based on business logic.** An optional field such as a nickname can return a default; a required transaction identifier should not silently receive a fake ID.

## 2. Optional.or(): Finding Another Optional on Demand

The signature of `or` (available since Java 9) is:

```java
public Optional<T> or(
    Supplier<? extends Optional<? extends T>> supplier);
```

This is the API signature for explanation, not a method redefinition in the application. `Supplier` belongs to `java.util.function`; its function descriptor is `() -> Optional<? extends T>`.

How it works:

1. If the Optional **already has a value**, return the existing Optional and **do not call** `supplier.get()`.
2. If the Optional is **empty**, call `supplier.get()` to obtain a fallback Optional.
3. The fallback Optional may **have a value or remain empty**.
4. A `null` Supplier or a `null` returned Optional is invalid; in particular, when the Supplier is called and returns `null`, `or` throws `NullPointerException`.

Illustrative example:

```java
Optional<String> local = Optional.empty();

Optional<String> result = local.or(
        () -> Optional.of("backup")
);

System.out.println(result.orElseThrow()); // backup
```

Conversely:

```java
Optional<String> local = Optional.of("primary");

Optional<String> result = local.or(() -> {
    System.out.println("Đọc nguồn dự phòng");
    return Optional.of("backup");
});

System.out.println(result.orElseThrow()); // primary
```

In the second case, the line `Đọc nguồn dự phòng` is **not printed** because the first Optional already has a value. This is a **lazy fallback**: the fallback task is placed inside the lambda body and only runs when needed.

The snippets above are standalone illustrations for each scenario; you need to declare/import `Optional` and place them inside a valid method.

### 2.1. Why Does or() Accept an Optional Instead of a Value T?

`or` does not simply provide a replacement value. It allows **preserving the presence/absence semantics** when trying a fallback source:

```java
Optional<String> result = Optional.<String>empty()
        .or(() -> Optional.empty());

System.out.println(result.isEmpty()); // true
```

If the fallback source also has no data, the result remains an empty Optional for subsequent layers to decide. For a processing chain with multiple sources, this is more useful than forcing an assumed `String` immediately.

`orElseGet(Supplier<? extends T>)` differs from `or`: it returns **`T`** directly, not an Optional. Writing `optional.or(() -> "backup")` does not compile because the lambda returns a `String`, whereas `or` requires the Supplier to return an `Optional`. Writing `optional.or(() -> Optional.of("backup"))` is correct.

## 3. Fallback Source Chains: Priority-Ordered Fallback

Suppose a program has the following data lookup methods:

```java
Optional<User> findInSession(String id);
Optional<User> findInDatabase(String id);
Optional<User> findInArchive(String id);
```

These are **illustrative signatures** only; the `User` class and the methods must be implemented in a real application. They can be combined as:

```java
Optional<User> user = findInSession(id)
        .or(() -> findInDatabase(id))
        .or(() -> findInArchive(id));
```

With this flow:

- If the session has the `User`, neither the database nor the archive is called.
- If the session is empty and the database has the `User`, the archive is not called.
- Only when both of the first two sources are empty is the archive called.
- If all three are empty, the final result is `Optional.empty()`.

**The order of sources is very important:** the result carries a priority policy of session → database → archive. If reading from the database or archive is resource-intensive, `or` also helps avoid unnecessary calls.

### Do Not Accidentally Evaluate the Fallback Eagerly

```java
// Wrong for lazy intent: the method already ran to create the variable.
Optional<User> backup = findInDatabase(id);
Optional<User> result = findInSession(id).or(() -> backup);
```

This snippet may compile inside a suitable method, but `findInDatabase(id)` has already executed **before** `or` decides whether the data is needed. To defer it, place the lookup call inside the lambda:

```java
Optional<User> result = findInSession(id)
        .or(() -> findInDatabase(id));
```

Similarly, if you pre-create a Supplier whose data was already loaded before creating it, the Supplier does not make that operation lazy.

## 4. orElseThrow(): When a Value Is Required

### 4.1. The No-Argument Overload

Method:

```java
public T orElseThrow();
```

Available since **Java 10**. If the Optional has a value, it returns that value. If empty, it throws `NoSuchElementException`, which is an **unchecked exception** in `java.util`.

```java
String title = Optional.of("Java").orElseThrow();
// title is "Java".

Optional.<String>empty().orElseThrow();
// Throws NoSuchElementException.
```

These are two separate illustrative expressions. There is no fallback mechanism in the no-argument overload: it declares that the caller **requires a value to be present**.

`Optional.get()` also returns the value or throws `NoSuchElementException` when empty. In modern code, `orElseThrow()` generally communicates the intent “missing data is an error” more clearly than the name `get()`, especially when read alongside `or` and `orElseGet`.

**Do not overuse** `orElseThrow()` everywhere just to unwrap an Optional. If an empty Optional is a normal business state, throwing an exception is not the best choice.

### 4.2. The Overload Accepting an Exception Supplier

General signature:

```java
public <X extends Throwable> T orElseThrow(
        Supplier<? extends X> exceptionSupplier) throws X;
```

This overload has been available since **Java 8**. When the Optional has a value, the Supplier **is not called** and the value is returned. When empty, the Supplier is called to provide a `Throwable` object, which is then **thrown**.

```java
String token = maybeToken.orElseThrow(
        () -> new IllegalStateException("Token bắt buộc")
);
```

Given a declared `maybeToken` of type `Optional<String>`, the expression above:

- Returns the string when a token is present.
- When empty, creates and throws an `IllegalStateException` with a specific message.

By passing an **exception-creating Supplier**, the program can defer creating the exception until it is actually needed. This both expresses the error policy and avoids allocating unnecessary exception objects when data exists.

### 4.3. Checked Exceptions and throws X

An important benefit of the Supplier overload is that it can **throw a checked exception of a specific type**:

```java
static String requireToken(Optional<String> source)
        throws java.io.IOException {
    return source.orElseThrow(
            () -> new java.io.IOException("missing token")
    );
}
```

The example above illustrates a complete method that must be placed in a class with `Optional` imported. Because the Supplier creates an `IOException`, calling `orElseThrow` can throw that checked exception. The enclosing method must declare `throws IOException` or catch the exception.

**Common point of confusion:** `Supplier.get()` **does not declare any checked exceptions**. In the example, the lambda **does not throw `IOException` itself from its body**; it **returns an `IOException` object** for `Optional.orElseThrow` to throw. That is why this overload is compatible with `Supplier<? extends X>` even though `get()` has no `throws` clause.

Do not confuse the following two forms:

```java
// Correct: the lambda returns an IOException object.
() -> new java.io.IOException("missing")

// Wrong when assigned to Supplier<IOException>: the body throws checked IOException
// from Supplier.get() itself, which does not declare throws.
() -> { throw new java.io.IOException("missing"); }
```

The two lambdas above are merely **illustrative snippets that require an appropriate target type**. They demonstrate the difference between **creating and returning an exception** versus **throwing an exception from the Supplier body**.

### 4.4. A Supplier Returning null Is an Error

If the Optional is empty and the exception supplier returns `null`, the program has no valid Throwable object to throw; a `NullPointerException` occurs.

```java
Optional.<String>empty()
        .orElseThrow(() -> null); // NPE
```

Do not use a Supplier returning null to express “no need to report an error”. If emptiness is normal, choose `orElse`, `orElseGet`, `ifPresentOrElse`, or return the Optional depending on the contract.

## 5. Comparing Options When No Value Is Present

| Need | Method | When Optional is empty | Return type |
| --- | --- | --- | --- |
| Need to search another source while keeping Optional | `or(supplier)` | Calls Supplier providing another **Optional** | `Optional<T>` |
| Have a precomputed fallback value | `orElse(value)` | Returns the fallback value | `T` |
| Need to compute a fallback value on demand | `orElseGet(supplier)` | Calls Supplier providing `T` | `T` |
| Missing value is an error, no custom message needed | `orElseThrow()` | Throws `NoSuchElementException` | `T` or exception |
| Missing value is a specific business error | `orElseThrow(exceptionSupplier)` | Calls Supplier to create exception, then throws it | `T` or exception |
| Perform two action branches without returning T | `ifPresentOrElse(action, emptyAction)` | Runs `Runnable` in the empty branch | `void` |
| Only process when a value is present | `ifPresent(action)` | Does nothing | `void` |
| Want to emit 0 or 1 element into a Stream | `stream()` | Creates an empty Stream | `Stream<T>` |

**`orElse` is not lazy with respect to its argument expression.** Java evaluates the argument before entering the method:

```java
String result = optional.orElse(expensiveDefault());
```

`expensiveDefault()` still runs even if `optional` already has a value. Conversely:

```java
String result = optional.orElseGet(() -> expensiveDefault());
```

The Supplier body only runs when the Optional is empty. These snippets are illustrative, assuming `optional` and `expensiveDefault()` already exist in the surrounding context.

**Regarding `null`:** `orElse(null)` and `orElseGet(() -> null)` can return null when the Optional is empty; whereas `or(() -> null)` violates the contract and throws NPE when the Supplier is called. `orElseThrow(() -> null)` also raises NPE in the empty branch. Avoid using null as a “fallback result” if the caller expects a meaningful value.

## 6. Java 17 Program: or(), orElseThrow(), and the Empty Branch

The following example uses `AtomicInteger` to count how many times Suppliers run, proving that the fallback is truly lazy and illustrating both checked and unchecked exceptions.

Create the file **`OptionalFallbackDemo.java`**:

```java
import java.io.IOException;
import java.util.NoSuchElementException;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;

public class OptionalFallbackDemo {
    static Optional<String> fromBackup(AtomicInteger calls) {
        calls.incrementAndGet();
        return Optional.of("backup");
    }

    static String requireToken(Optional<String> source) throws IOException {
        return source.orElseThrow(() -> new IOException("missing token"));
    }

    public static void main(String[] args) {
        AtomicInteger backupCalls = new AtomicInteger();
        Optional<String> first = Optional.empty();

        Optional<String> found = first.or(() -> fromBackup(backupCalls));
        System.out.println("Found: " + found.orElseThrow());
        System.out.println("Backup calls: " + backupCalls.get());

        Optional<String> existing = Optional.of("primary");
        String chosen = existing
                .or(() -> fromBackup(backupCalls))
                .orElseThrow();
        System.out.println("Existing: " + chosen);
        System.out.println("Backup calls after existing: " + backupCalls.get());

        AtomicInteger exceptionCalls = new AtomicInteger();
        String safe = existing.orElseThrow(() -> {
            exceptionCalls.incrementAndGet();
            return new IllegalArgumentException("required");
        });
        System.out.println("Safe: " + safe);
        System.out.println("Exception suppliers: " + exceptionCalls.get());

        try {
            Optional.<String>empty().orElseThrow();
        } catch (NoSuchElementException e) {
            System.out.println("Empty: " + e.getClass().getSimpleName());
        }

        try {
            requireToken(Optional.empty());
        } catch (IOException e) {
            System.out.println("Checked: " + e.getMessage());
        }

        try {
            Optional.<String>empty().or(() -> null);
        } catch (NullPointerException e) {
            System.out.println("Null Optional supplier: "
                    + e.getClass().getSimpleName());
        }

        Optional<String> notFound = Optional.<String>empty()
                .or(Optional::empty);
        System.out.println("Still empty: " + notFound.isEmpty());
    }
}
```

Compile and run with **JDK 17 or newer**:

```bash
javac OptionalFallbackDemo.java
java OptionalFallbackDemo
```

Standard output:

```text
Found: backup
Backup calls: 1
Existing: primary
Backup calls after existing: 1
Safe: primary
Exception suppliers: 0
Empty: NoSuchElementException
Checked: missing token
Null Optional supplier: NullPointerException
Still empty: true
```

### Mapping Code to Output

1. `first` is empty, so `first.or(...)` calls `fromBackup`, incrementing `backupCalls` to `1`, and returns an Optional containing `"backup"`. `found.orElseThrow()` retrieves the string successfully.
2. `existing` contains `"primary"`, so `or` **does not call** `fromBackup`. The fallback call count remains `1`.
3. `existing.orElseThrow(exceptionSupplier)` sees a value is present, so it does not run the Supplier body and does not increment `exceptionCalls`. `safe` is `"primary"`.
4. `Optional.empty().orElseThrow()` throws `NoSuchElementException`; `catch` prints the class name without depending on a default message that could change.
5. `requireToken(Optional.empty())` calls the Supplier to create `IOException("missing token")`, then throws `IOException`; `main` catches it and prints `Checked: missing token`.
6. `Optional.empty().or(() -> null)` expects the Supplier to provide an Optional but receives null, raising `NullPointerException`. The program catches it to continue.
7. `Optional.empty().or(Optional::empty)` remains empty; `Optional::empty` is a method reference to the static factory returning an empty Optional.

This is a **standalone** program with no network operations or external data. Each branch is structured so the output is deterministic. `AtomicInteger` is used as an observation counter in the example; it does not mean `Optional.or` carries state or caches results on its own.

## 7. Choosing Fail-Fast or Fallback Based on Data Semantics

### 7.1. Missing Value Is a Normal Case

Looking up an optional filter, nickname, or secondary description may not succeed without being an error. Common appropriate approaches:

```java
String displayName = nickname.orElse("Guest");
```

or:

```java
nickname.ifPresent(name -> System.out.println("Tên: " + name));
```

or keep the Optional at the data layer:

```java
Optional<String> nickname = repository.findNickname(userId);
return nickname;
```

These are **separate** illustrative snippets, assuming `nickname`, `repository`, `userId`, and the enclosing method's return type are appropriately declared. Keep the Optional when the caller has the right to decide the missing-data policy; do not force the repository to pick a fake name that distorts the meaning of the result.

### 7.2. A Business-Meaningful Fallback Source Exists

A system might look up a user in the order of session, cache, and then database:

```java
Optional<User> user = session.find(userId)
        .or(() -> cache.find(userId))
        .or(() -> database.find(userId));
```

If all three sources are valid and share the same `Optional<User>` model, `or` clearly expresses **trying the next source only when the previous one has no value**. Be aware that results from each source may have different freshness, that a source access failure is not the same as “not found”, and that I/O may throw exceptions.

Do not catch all exceptions and convert them into `Optional.empty()` to force the pipeline to continue, unless the policy truly treats an access error as “no data”. Losing a database connection is different from a user not existing.

### 7.3. Missing Data Violates a Contract

For example, a required configuration key or an entity that the API guarantees must exist:

```java
User user = repository.findRequiredUser(userId)
        .orElseThrow(() ->
                new IllegalStateException("User not found: " + userId));
```

This is illustrative code. If a missing user is a **caller input error**, you can use `IllegalArgumentException`; if it is a **violated system invariant**, you can choose `IllegalStateException`; in a service with its own error hierarchy, you can create a domain exception. Choose the exception type based on the **API contract** rather than habit.

In HTTP APIs, many applications translate a “not found” error into HTTP 404 at the boundary layer; the domain layer should not depend on HTTP if it is also used in CLI or batch processing. `orElseThrow` is the decision point for “missing data cannot proceed”, while returning the appropriate response is handled by the proper layer.

### 7.4. Want to Try Another Source When One Source Fails with an Error?

`or` is only called when the Optional is **empty**; it does not automatically catch exceptions from the preceding source:

```java
Optional<User> user = primary.find(id)
        .or(() -> secondary.find(id));
```

If `primary.find(id)` throws an exception, the expression does not produce an Optional result and `secondary.find(id)` is not called through `or`. If fallback is also required on network failure, you must design a separate catch/retry/error-translation policy. Do not equate “empty” with “failed”.

## 8. Combining with map(), flatMap(), filter(), and stream()

### 8.1. Avoiding Nested Optionals

Suppose:

```java
Optional<User> user = findUser(id);
```

If `User.getNickname()` returns `Optional<String>`, use `flatMap` to avoid creating `Optional<Optional<String>>`:

```java
Optional<String> nickname = user
        .flatMap(User::getNickname)
        .or(() -> findGlobalNickname(id));
```

This is illustrative code; `User` and the lookup methods must be defined. Here `flatMap` transforms from an Optional of User to an Optional of nickname. `or` then provides a fallback Optional **of the same value type String**.

If you use `map(User::getNickname)` with a method returning `Optional<String>`, the result has the type `Optional<Optional<String>>`, which is not the desired final shape. This is one of the reasons learners find it difficult to compose Optional chains.

### 8.2. filter() Makes an Optional Empty When the Condition Is Not Met

```java
Optional<String> active = Optional.of("  ")
        .filter(value -> !value.isBlank())
        .or(() -> Optional.of("Guest"));

System.out.println(active.orElseThrow()); // Guest
```

`filter` does not transform the value; instead, it keeps or discards the value according to a `Predicate`. Because an all-whitespace string is invalid for a display name, the result after filter is empty, causing `or` to be called.

### 8.3. stream() for Collection Processing

Since Java 9, `Optional.stream()` converts a present Optional into a single-element Stream and an empty Optional into an empty Stream:

```java
List<Optional<String>> candidates = List.of(
        Optional.empty(),
        Optional.of("An"),
        Optional.of("Mai")
);

List<String> names = candidates.stream()
        .flatMap(Optional::stream)
        .toList(); // [An, Mai]
```

This illustrative snippet requires importing `List` and `Optional`. This technique is suitable when you want to **collect all present values**; unlike `or`, which is used to pick the first source with a value in priority order. Do not replace `or` with processing an entire Stream if the business logic only needs the first source and wants to avoid calling expensive sources.

## 9. Distinguishing Programming Errors from Missing-Value States

### 9.1. Optional Does Not Replace Null Checks at Every Layer

`Optional.ofNullable(raw)` is useful at boundaries with legacy APIs that may return null. However, the mere existence of Optional does not guarantee that every object, collection, or field is valid on its own. In particular, `or` expects **the Supplier to return an Optional object, not null**; methods designed to return Optional should adhere to the contract of never returning null.

Incorrect example:

```java
Optional<String> result = Optional.<String>empty()
        .or(() -> null); // throws NullPointerException
```

Fix:

```java
Optional<String> result = Optional.<String>empty()
        .or(Optional::empty); // still empty, valid
```

If a legacy source may return a null `String`, wrap it properly:

```java
Optional<String> result = Optional.<String>empty()
        .or(() -> Optional.ofNullable(legacyLookup()));
```

The snippets above are illustrative; `legacyLookup()` must be defined in a real program.

### 9.2. Do Not Use Exceptions for High-Frequency Normal Control Flow

Repeatedly calling `orElseThrow()` and catching `NoSuchElementException` in a loop processing millions of absent results can incur overhead and obscure intent. If emptiness is a normal case, use `ifPresent`, `ifPresentOrElse`, `orElse`, or `stream`; only throw an exception when you genuinely **cannot continue properly**.

### 9.3. Do Not Unconditionally Wrap Exceptions into Optional.empty()

A helper doing:

```java
try {
    return repository.load(id);
} catch (Exception e) {
    return Optional.empty();
}
```

is an illustrative snippet that can hide network errors, authorization failures, or data corruption. When passed through `or`, the next source may be called even though the real cause is a broken system, creating behavior that is hard to monitor. Only convert specific exceptions into “no data” when business logic allows it and technical errors remain observable.

### 9.4. Do Not Confuse “a Supplier That Throws” with “a Supplier That Creates an Exception”

`orElseThrow(() -> new IOException("missing"))` creates an IOException object for `orElseThrow` itself to throw, which is why the enclosing method needs to declare `throws IOException`. However, a lambda body like `() -> { throw new IOException("missing"); }` is incompatible with `Supplier<IOException>` because `Supplier.get` does not declare any checked exceptions. This is a difference in **functional contract**, not just syntax.

## 10. Execution Timing and Performance

| Expression | Evaluates fallback task when Optional has a value? | When Optional is empty? |
| --- | --- | --- |
| `opt.or(() -> findBackup())` | No | Calls `findBackup()`, receives Optional |
| `opt.orElse(expensiveValue())` | Yes, to compute the argument | Value is already computed, returns that result |
| `opt.orElseGet(() -> expensiveValue())` | No | Calls Supplier to create value T |
| `opt.orElseThrow(() -> new DomainException())` | No | Creates and throws exception |
| `opt.orElseThrow()` | No Supplier | Throws NoSuchElementException |

In every branch, **expressions outside the lambda body** are still evaluated in standard Java order. If you want to defer database access, place that work **inside the Supplier**. If you already called the database beforehand and captured a value, it is no longer a lazy fallback.

Actual optimization depends on the cost of creating the value and how often the Optional is empty. If the fallback is just a constant `"Guest"`, `orElse("Guest")` is simple and easy to read. If the fallback requires I/O or expensive computation, `orElseGet` or `or` can avoid unnecessary work. Do not replace all code with lambdas just to be “functional” if doing so makes the business flow harder to read.

## 11. Guarantees and Limitations in Multithreaded Environments

`Optional` is a value-based class; do not rely on the identity of an Optional object for synchronization locking, `==` reference comparison, or cache management. Compare data by value or business contract rather than instance identity.

`Optional.or` does not guarantee that a supplier can be called safely in a concurrent environment if the Supplier itself uses mutable state. Creating/evaluating the fallback happens when you invoke the method under normal semantics, without automatically switching to another thread. If multiple threads share data or a cache, synchronization must be designed where the data is mutated.

Avoid assuming that fallback ordering solves all race conditions: data can change between sources or between a lookup and the subsequent action. For operations requiring atomicity or transactions, use appropriate database/caching APIs rather than relying solely on Optional expressions.

## 12. Common Mistakes

1. **Writing `or(() -> "backup")`:** Wrong return type; `or` requires a Supplier returning `Optional<T>`, not `T`.
2. **Returning `null` from `or`'s Supplier:** Violates the contract; when called, it causes `NullPointerException`.
3. **Believing `or` always calls the fallback source:** False when the Optional already has a value; the Supplier is not called in that branch.
4. **Computing the fallback before the lambda:** `Optional<T> backup = expensive(); opt.or(() -> backup)` already executed `expensive()` eagerly.
5. **Confusing `orElseThrow()` with `orElseGet()`:** One throws an exception when empty, the other returns a value created by a Supplier.
6. **Using `orElseThrow` when missing data is normal:** Exceptions should express genuine errors; avoid using them as routine control flow.
7. **Using `orElseThrow(() -> null)`:** When empty, it causes NPE instead of producing a useful business error type.
8. **Forgetting to declare checked exceptions:** `orElseThrow(() -> new IOException(...))` may require `throws IOException` or `try/catch` in the caller.
9. **Using `map` when the mapper already returns an Optional:** Easily creates nested Optionals; consider `flatMap`.
10. **Treating a data source error as not found:** `or` does not catch errors; converting technical errors into Optional.empty() must follow explicit rules.
11. **Choosing the wrong missing-data strategy:** A display string can have a default, but a security token or transaction key must report an appropriate error.
12. **Equating Optional with nullability:** An empty Optional is different from a `null` Optional reference; an API returning Optional should never return `null`.

## 13. Self-Check Exercises

**Exercise 1.** For `Optional.of("A").or(() -> Optional.of("B"))`, what is the result? Is the Supplier called?

**Exercise 2.** For `Optional.<String>empty().or(Optional::empty)`, what is the final state? Why is no exception thrown?

**Exercise 3.** Write a pipeline that tries `findLocal(id)`, `findCache(id)`, and then `findRemote(id)` only when the previous sources are empty. At the end of the pipeline, if still not found, throw `IllegalStateException` with a message containing `id`.

**Exercise 4.** Distinguish the result and execution cost of `opt.orElse(expensive())` versus `opt.orElseGet(() -> expensive())` when the Optional already has a value.

**Exercise 5.** Write a method that accepts `Optional<String>` and forces the caller to handle `IOException` if the value does not exist.

**Exercise 6.** Why is `Optional.empty().or(() -> null)` not a valid way to mean “no fallback source”? What is the correct way to keep the Optional empty?

**Exercise 7.** In `Optional.of("ready").orElseThrow(() -> new IllegalStateException())`, does the exception supplier create an exception object?

**Exercise 8.** A repository call to the database fails due to a timeout and returns Optional.empty(). If a subsequent `or` reads from a cache, what might this design hide?

**Exercise 9.** `Optional<User>` has a method `getNickname()` returning `Optional<String>`. Use `flatMap` and then `or` to get a fallback nickname without creating a nested Optional.

**Exercise 10.** Given a `List<Optional<String>>` containing 2 present Optionals and one empty Optional, use `Optional::stream` to obtain a `List<String>` containing only the 2 strings.

### Answer Key

1. Returns an Optional containing `"A"`; the Supplier is not called.
2. Returns a valid empty Optional; the Supplier returned an `Optional.empty()` object, not null.
3. `findLocal(id).or(() -> findCache(id)).or(() -> findRemote(id)).orElseThrow(() -> new IllegalStateException("Not found: " + id))`.
4. `orElse` evaluates `expensive()` before the call; `orElseGet` does not call the Supplier when a value is already present.
5. `static String require(Optional<String> x) throws IOException { return x.orElseThrow(() -> new IOException("missing")); }`; requires importing `Optional` and `IOException` in the class containing the method.
6. Because `or` requires another Optional; use `.or(Optional::empty)`.
7. No; the Supplier body does not run when a value is present.
8. Hides connection/timeout errors and makes the cache fallback look like a valid result of a normal lookup.
9. `user.flatMap(User::getNickname).or(() -> findFallbackNickname())`, assuming those methods are appropriately defined.
10. `items.stream().flatMap(Optional::stream).toList()`.

## Conclusion

When `Optional` is empty, **choose the handling strategy according to the business contract**:

- Use **`or()`** to try another source while continuing to represent the result as `Optional<T>`.
- Use **`orElseThrow()`** when a missing value is an error and `NoSuchElementException` is already clear enough.
- Use **`orElseThrow(exceptionSupplier)`** when you need a business-meaningful exception or a specific checked exception.
- Use **`orElse`, `orElseGet`, `ifPresentOrElse`, or `stream`** when a missing value is allowed and no error needs to be thrown.

The key differences lie in **the fallback value type, when the Supplier is executed, and the meaning of the empty state**. Understanding these points helps you write Java code that is readable and avoids unnecessary I/O, wrong-layer exceptions, and handling branches that do not reflect application requirements.
