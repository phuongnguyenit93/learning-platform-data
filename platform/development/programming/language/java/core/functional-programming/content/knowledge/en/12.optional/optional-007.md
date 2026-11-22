# Optional.ifPresent() and ifPresentOrElse() in Java

## 1. Goal: handling the two states of present or empty

`Optional<T>` in `java.util` represents a **container that may or may not hold a value of type `T`**. Instead of retrieving the value with `get()` and manually handling the risk of `NoSuchElementException`, we can provide an action for Java to invoke **only when a value is present**, or two actions to handle **both the present and empty cases**.

Two methods to master:

~~~java
void ifPresent(Consumer<? super T> action)

void ifPresentOrElse(Consumer<? super T> action, Runnable emptyAction)
~~~

- **`ifPresent(action)`**: if the `Optional` contains a value, executes `action.accept(value)`; if empty, **does nothing**.
- **`ifPresentOrElse(action, emptyAction)`**: if it contains a value, executes `action.accept(value)`; if empty, executes `emptyAction.run()`. In a call that completes normally, only **one of the two branches** is chosen.
- Both have a return type of **`void`**: they are meant for **performing actions**, typically updating the UI, printing messages, logging, or calling a service, **not for returning a transformed value**.

`ifPresent` has existed since **Java 8**. `ifPresentOrElse` was added in **Java 9**, so both are available in **Java 17+**.

**Key takeaway:** `ifPresent` expresses "**if present, do this**", while `ifPresentOrElse` expresses "**if present, do this; if not, do that**".

## 2. SAM signatures: why does the present branch take an argument while the empty branch does not?

`Consumer<T>` is a functional interface with the SAM:

~~~java
void accept(T value);
~~~

It takes one value and returns no result. Therefore, `Optional<String>.ifPresent` can use:

~~~java
Optional<String> name = Optional.of("An");
name.ifPresent(value -> System.out.println("Xin chào " + value));
~~~

Meanwhile, `Runnable` is a functional interface with the SAM:

~~~java
void run();
~~~

It takes no arguments and returns no result. Because when an `Optional` is **empty** there is no value to pass, the second branch of `ifPresentOrElse` uses `Runnable`:

~~~java
Optional<String> name = Optional.empty();
name.ifPresentOrElse(
        value -> System.out.println("Xin chào " + value),
        () -> System.out.println("Không tìm thấy tên")
);
~~~

The snippets in this section are **illustrations for use inside a method**, requiring `import java.util.Optional`. There is no `main` method, so they are not standalone runnable programs.

**Comparison of callback types:**

| Part of the call | Required type | Needs the Optional's value? | Example |
|---|---|---|---|
| `ifPresent(action)` | `Consumer<? super T>` | Yes, one parameter `T` | `value -> save(value)` |
| First branch of `ifPresentOrElse` | `Consumer<? super T>` | Yes, one parameter `T` | `value -> show(value)` |
| Empty branch of `ifPresentOrElse` | `Runnable` | No, no parameters | `() -> showMissing()` |

`<? super T>` allows a `Consumer` to accept `T` or a suitable supertype. When using a typical lambda, the `value` parameter is inferred from the `Optional<T>` type. `Runnable` is not generic because it does not need any value from the `Optional`.

## 3. When is each branch executed?

Suppose:

~~~java
Optional<String> present = Optional.of("Java");
Optional<String> absent = Optional.empty();
~~~

There are four scenarios:

| Method | Optional has a value | Optional is empty |
|---|---|---|
| `ifPresent(action)` | Calls `action` once | Does not call `action` |
| `ifPresentOrElse(action, emptyAction)` | Calls `action` once, does not call `emptyAction` | Does not call `action`, calls `emptyAction` once |

This only describes **callback selection when the method is called**. If the callback itself calls other functions, starts a separate thread, or throws an exception, those internal behaviors must be analyzed separately.

With `Optional.ofNullable(null)`, the result is `Optional.empty()`. `Optional` itself does not hold a `null` value to pass into the `action` branch. To create a non-empty Optional, use `Optional.of(nonNullValue)` or `Optional.ofNullable(possiblyNullValue)`.

Note: `Optional.of(null)` throws `NullPointerException` **immediately when creating the Optional**, not when `ifPresent` runs. Do not confuse an Optional creation error with an error inside the callback.

### 3.1. Runnable program: observing both branches

Save the file **`OptionalBranchDemo.java`**:

~~~java
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;

public class OptionalBranchDemo {
    public static void main(String[] args) {
        Optional<String> present = Optional.of("  Java  ");
        Optional<String> empty = Optional.empty();

        AtomicInteger presentCalls = new AtomicInteger();
        AtomicInteger emptyCalls = new AtomicInteger();

        present.ifPresent(value -> {
            presentCalls.incrementAndGet();
            System.out.println("ifPresent=" + value.trim());
        });

        empty.ifPresent(value -> {
            presentCalls.incrementAndGet();
            System.out.println("never printed");
        });

        present.ifPresentOrElse(
                value -> {
                    presentCalls.incrementAndGet();
                    System.out.println("present=" + value.trim());
                },
                () -> {
                    emptyCalls.incrementAndGet();
                    System.out.println("never printed");
                }
        );

        empty.ifPresentOrElse(
                value -> {
                    presentCalls.incrementAndGet();
                    System.out.println("never printed");
                },
                () -> {
                    emptyCalls.incrementAndGet();
                    System.out.println("empty fallback");
                }
        );

        System.out.println("calls=" +
                presentCalls.get() + "/" + emptyCalls.get());
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac OptionalBranchDemo.java
java OptionalBranchDemo
~~~

Exact stdout:

~~~text
ifPresent=Java
present=Java
empty fallback
calls=2/1
~~~

**Analysis:**

1. `present.ifPresent(...)` invokes the action, so the `presentCalls` counter increments to `1`.
2. `empty.ifPresent(...)` does not invoke the action, so the line `never printed` does not appear.
3. `present.ifPresentOrElse(...)` runs the callback receiving `value`, bringing the `presentCalls` counter to `2`; it does not run `emptyAction`.
4. `empty.ifPresentOrElse(...)` has no value to pass to the first callback; it runs `emptyAction` and increments `emptyCalls` to `1`.
5. The final line is `calls=2/1`, confirming that one branch is chosen rather than both branches running.

`AtomicInteger` in this example is only used as an easily observable counter; there is **no requirement** to use atomics to call `ifPresent` or `ifPresentOrElse`. This is a sequential program.

## 4. Choose `ifPresent` when no "absent" branch is needed

`ifPresent` is suitable when absence is a normal situation and the application **needs no other action**:

~~~java
// Illustrative code snippet with existing variables.
maybeUser.ifPresent(user -> auditLogger.record(user));
selectedId.ifPresent(id -> highlightRow(id));
maybeEvent.ifPresent(event -> eventBus.publish(event));
~~~

These examples depend on `maybeUser`, `selectedId`, `maybeEvent`, and application-defined services. The meaning is: **if a value is present, perform the operation; if not, skip it**.

When the callback simply calls a single method with the received argument, a method reference can be used:

~~~java
maybeUser.ifPresent(auditLogger::record);
~~~

The form `auditLogger::record` expresses the action clearly, but it **does not change** when the callback is triggered, how many times it is called, or whether it may have side effects.

Do not use `ifPresent` just to hide a "not found" case that must be handled. If absence requires a warning, a business error, a different UI state, or metrics tracking, `ifPresentOrElse` or another appropriate API makes the intent clearer.

### When "doing nothing" is the right behavior

For example, a filter may return an optional item; if present, we display it. If absent, the UI is already in its default state and needs no update. `ifPresent` states the business logic accurately without creating an empty `else` branch just to satisfy a pattern.

However, if the system needs to record a "no result found" case for auditing purposes, silently skipping it may be a bug. Decide based on business requirements before choosing the API.

## 5. Choose `ifPresentOrElse` when both states require an action

A user-lookup application might need to **display information if found** and **show a separate message if not found**:

~~~java
lookupUser(id).ifPresentOrElse(
        user -> showUser(user),
        () -> showNotFound(id)
);
~~~

This is an illustrative snippet. `lookupUser` is assumed to return `Optional<User>`; the methods `showUser` and `showNotFound` are defined by the application.

The first argument is `Consumer<User>`: when a user is present, the callback receives that `User`. The second argument is `Runnable`: when absent, the callback receives no user; if `id` is needed, the lambda **captures** `id` from the enclosing scope.

Captured local variables must be `final` or *effectively final*. If `id` is reassigned after creating the lambda in the same scope, the code may fail to compile. This is a lambda capture rule, not specific to `Optional`.

### 5.1. Runnable program: handling lookup results

Save the file **`OptionalUserDemo.java`**:

~~~java
import java.util.Optional;
import java.util.OptionalInt;
import java.util.function.Consumer;

public class OptionalUserDemo {
    record User(String name, int points) {}

    public static void main(String[] args) {
        Optional<User> found = Optional.of(new User("Mai", 85));
        Optional<User> missing = Optional.empty();

        Consumer<User> showUser = user ->
                System.out.println(
                        "user=" + user.name() + ",points=" + user.points()
                );

        Runnable showMissing = () ->
                System.out.println("user=not found");

        found.ifPresentOrElse(showUser, showMissing);
        missing.ifPresentOrElse(showUser, showMissing);

        int score = found.map(User::points).orElse(0);
        String selected = missing
                .map(User::name)
                .orElseGet(() -> "guest");

        System.out.println("score=" + score);
        System.out.println("selected=" + selected);

        OptionalInt count = OptionalInt.of(4);
        count.ifPresentOrElse(
                value -> System.out.println("count=" + value),
                () -> System.out.println("no count")
        );
    }
}
~~~

Run:

~~~bash
javac OptionalUserDemo.java
java OptionalUserDemo
~~~

Stdout:

~~~text
user=Mai,points=85
user=not found
score=85
selected=guest
count=4
~~~

**Learning points:**

- The same `Consumer<User>` and `Runnable` can be reused across multiple different `Optional<User>` instances.
- `found.ifPresentOrElse` calls `showUser.accept(user)`; `missing.ifPresentOrElse` calls `showMissing.run()`.
- When **a value is needed**, the program switches to `map(...).orElse(...)` or `map(...).orElseGet(...)` instead of trying to extract a result from `ifPresentOrElse`.
- `OptionalInt` is the specialized version for primitive `int`. `OptionalInt.ifPresentOrElse(IntConsumer, Runnable)` selects branches in the same way, but the value-receiving callback uses `IntConsumer` instead of `Consumer<Integer>`.
- The `User` record is used to represent data concisely; records are a standard feature in Java 16+, suitable for JDK 17.

## 6. Both methods return `void`: do not use them to compute a result

This is the most important distinction between `ifPresent`/`ifPresentOrElse` and value-producing APIs.

**Wrong:**

~~~java
// INTENTIONALLY WRONG: ifPresentOrElse returns void, not String.
// String label = maybeName.ifPresentOrElse(
//         name -> name,
//         () -> "unknown"
// );
~~~

Besides the method returning `void`, the lambdas here also do not express `Consumer<String>`/`Runnable` actions as intended. If you need a string, use an API that **returns a result**:

~~~java
String label = maybeName
        .map(String::trim)
        .orElseGet(() -> "unknown");
~~~

The snippet above is illustrative, assuming `maybeName` is `Optional<String>`. `map` transforms the value when present, while `orElseGet` uses `Supplier<String>` to provide a fallback when empty.

API selection table:

| Need | Suitable API | Result type |
|---|---|---|
| If present, perform an action | `ifPresent(Consumer)` | `void` |
| Present or empty both need different actions | `ifPresentOrElse(Consumer, Runnable)` | `void` |
| If present, transform the value | `map(Function)` | `Optional<U>` |
| If present, keep if condition is met | `filter(Predicate)` | `Optional<T>` |
| Get value if present, use fixed value if empty | `orElse(T)` | `T` |
| Get value if present, compute fallback only if empty | `orElseGet(Supplier<? extends T>)` | `T` |
| Throw an exception if no value is present | `orElseThrow()` or `orElseThrow(Supplier<? extends X>)` | `T` |

`ifPresent` and `ifPresentOrElse` are **terminal operations that end a processing branch with an action**. Because they do not return an `Optional`, they do not support chaining like `optional.ifPresent(...).map(...)`.

When choosing an API, ask: "**Do I need to do something, or do I need to get a new value?**" If you need a value, avoid abusing a mutable holder just to pull it out of a callback.

## 7. Common mistakes when migrating from `if/else` to Optional

### 7.1. Calling `get()` first and checking afterward

~~~java
// INTENTIONALLY WRONG when Optional may be empty:
String value = optional.get();
if (value != null) {
    consume(value);
}
~~~

`optional.get()` throws `NoSuchElementException` if empty, so the `value != null` check provides no protection. Assuming `optional` is an existing `Optional<String>`, the right solution when only an action is needed is:

~~~java
optional.ifPresent(value -> consume(value));
~~~

If an action is needed for the absent branch:

~~~java
optional.ifPresentOrElse(
        value -> consume(value),
        () -> reportMissing()
);
~~~

The methods `consume` and `reportMissing` are application-defined; all three snippets are illustrative and not standalone runnable code.

### 7.2. Using `isPresent()` followed by `get()` in every case

~~~java
if (optional.isPresent()) {
    consume(optional.get());
} else {
    reportMissing();
}
~~~

This approach **can be correct**, but it is usually more verbose than `ifPresentOrElse` callbacks. Switching to callbacks makes the actions tied to the two states clearer and avoids calling `get()` manually.

However, a plain `if/else` statement can still be reasonable if the flow is complex, requires a `return` from the **enclosing method**, `break`/`continue` in a loop, or if nested callbacks make the logic hard to read. The goal is not to replace every `if` with a lambda, but to express behavior clearly.

### 7.3. Confusing `Runnable` with `Consumer` in the empty branch

**Wrong because the empty callback takes no arguments:**

~~~java
// INTENTIONALLY WRONG: emptyAction must be a Runnable with 0 parameters.
// optional.ifPresentOrElse(
//         value -> System.out.println(value),
//         missing -> System.out.println(missing)
// );
~~~

Correct:

~~~java
optional.ifPresentOrElse(
        value -> System.out.println(value),
        () -> System.out.println("empty")
);
~~~

In the empty branch, there is no `value`. To use external data such as a request ID, capture that variable inside `() -> reportMissing(requestId)`.

### 7.4. Expecting lambdas to run both branches automatically

Both callback arguments are **created/evaluated** when the method is called, but the **callback body** is only executed according to the chosen branch. This is an important distinction:

~~~java
// Correct: only perform the expensive work when no value is present.
optional.ifPresentOrElse(
        value -> show(value),
        () -> log(buildExpensiveMessage())
);
~~~

If you previously wrote `String message = buildExpensiveMessage();` and then merely captured `message` in the lambda, building the string already happened **before** knowing whether the Optional was empty.

A receiver-bound method reference like `service::handle` can also evaluate the receiver expression when creating the reference; do not assume all parts of the call are automatically deferred, even though the callback body has not run yet.

### 7.5. Using a callback to assign to an external variable

~~~java
// Avoid complex or invalid design patterns:
// String result = null;
// optional.ifPresent(v -> result = v); // Local variable is not effectively final.
~~~

Local variables captured by a lambda must be `final` or *effectively final*. Using an `AtomicReference` or a single-element array just to get a result out of `ifPresent` usually makes code harder to understand. If the problem requires returning a value, `orElse`, `orElseGet`, or `map` is the right API for the job.

### 7.6. Using `ifPresent` and forgetting an important absent case

If an empty result means "the order does not exist" and the user must be notified, `ifPresent` can miss a required branch. `ifPresentOrElse` makes both states visible in one place.

Conversely, if the empty branch truly needs to do nothing, writing `ifPresentOrElse(action, () -> {})` just adds noise to the code. Choose `ifPresent(action)`.

## 8. When a callback throws an exception or has side effects

### 8.1. Exceptions are not swallowed or redirected to the other branch

`ifPresent` and `ifPresentOrElse` **are not exception-handling mechanisms**. If the chosen callback throws an unchecked exception, that exception propagates to the caller; the other branch **does not automatically run as a fallback**.

~~~java
Optional<String> value = Optional.of("bad");

value.ifPresentOrElse(
        text -> { throw new IllegalStateException("failed:" + text); },
        () -> System.out.println("empty action")
);
~~~

This is illustrative. The call throws `IllegalStateException` and does not print `empty action`, because the Optional **has a value**. If you want to handle errors inside a callback, you must use an appropriate `try/catch` block.

The SAMs `Consumer.accept` and `Runnable.run` do not declare checked exceptions. If a callback performs I/O that can throw `IOException`, you need to handle the checked exception inside the lambda or design another API with a suitable exception contract; you cannot let it escape unhandled from these two SAMs.

### 8.2. Ordering and number of side effects

For a normal Optional created via the Java API, a call to `ifPresent` or `ifPresentOrElse` selects the appropriate callback and invokes it once. However, **inside** the callback it may mutate objects, write logs, call APIs, or launch asynchronous work.

~~~java
optional.ifPresent(user -> repository.save(user));
~~~

This illustrative snippet can cause a data-writing side effect when a value is present. `Optional` does not make the operation pure, does not automatically protect transactions, and does not provide retries or thread safety.

Do not use a callback just to increment a counter and rely on it instead of a return value, when a clearer value-returning API exists.

## 9. `null` and `null` callbacks: edge cases to know

`Optional.empty()` does not contain `null` as a value passed to `Consumer`. However, the `action` or `emptyAction` parameter **may accidentally be passed as null**.

According to the API contract:

- `ifPresent(null)` throws `NullPointerException` **if the Optional has a value** and needs to invoke the action.
- `ifPresentOrElse(null, someRunnable)` throws `NullPointerException` **if the Optional has a value**.
- `ifPresentOrElse(someConsumer, null)` throws `NullPointerException` **if the Optional is empty**.
- The callback of the unchosen branch is not called; therefore, passing a null callback does not necessarily fail immediately if that branch does not run. Even so, **never pass null for a callback**: when the input state changes, the error can surface unexpectedly.

Another point is the **input value**:

~~~java
Optional<String> empty = Optional.ofNullable(null);
Optional<String> present = Optional.of("data");
~~~

`empty.ifPresent(v -> ...)` does not invoke the lambda; `present.ifPresent(v -> ...)` passes `"data"`. Do not use `Optional.of(null)` to represent an empty Optional, because that call itself will throw an exception.

## 10. Do you need `ifPresentOrElse` if you are on Java 8?

`ifPresentOrElse` is only available since **Java 9**. In Java 8, you can still use:

~~~java
if (optional.isPresent()) {
    optional.ifPresent(value -> show(value));
} else {
    showMissing();
}
~~~

This example is illustrative, though it can be written more concisely by extracting the value and handling it in a simple `if/else` structure. Do not invent complex nested callbacks just to emulate `ifPresentOrElse` in Java 8.

If the application runs on Java 17+, `ifPresentOrElse` expresses the two callbacks directly and is usually the clear choice when both actions are needed. If supporting Java 8, use `if` or other constructs supported by that version.

### Distinguishing `Optional<T>` and primitive Optionals

Java has `OptionalInt`, `OptionalLong`, and `OptionalDouble`. They have `ifPresent` using `IntConsumer`, `LongConsumer`, and `DoubleConsumer`; in Java 9+, they also have `ifPresentOrElse` with a primitive consumer and `Runnable`.

~~~java
OptionalInt count = OptionalInt.of(3);
count.ifPresentOrElse(
        number -> System.out.println(number * 2),
        () -> System.out.println("no number")
);
~~~

The illustrative snippet above prints `6` when run and avoids boxing the integer for the `IntConsumer` parameter. There is no difference in branch-selection logic, only in **the data type and the consumer's SAM**.

## 11. Quick selection guide for projects

| Scenario | Recommendation | Reason |
|---|---|---|
| If data is present, send event; if missing, ignore | `ifPresent` | Only one action is needed |
| If user is present, display; if missing, notify | `ifPresentOrElse` | Two clear action branches |
| If data is present, convert to DTO | `map` | Need to transform and keep the result as Optional |
| Get value if present, use default string if empty | `orElse` or `orElseGet` | Need a result of type `T` |
| Missing value is a business error | `orElseThrow` | Need a value or an exception |
| If value is present, save to repository | `ifPresent` (if appropriate for business logic) | Callback expresses a side effect |
| If empty, call service to create fallback and return object | `orElseGet` | Supplier creates the value only when missing |
| No lambda needed, complex flow requiring return/break | Plain `if/else` | Easy to control flow in the enclosing method |

**Review technique:** before writing a callback, ask "do I need an **action** or a **value**?"; then ask "does the empty state need handling?". These two questions are usually enough to pick the right API without overusing `Optional`.

## 12. Self-check questions

1. Does `Optional.empty().ifPresent(action)` execute `action`?
2. Which callback does `Optional.of("x").ifPresentOrElse(action, emptyAction)` execute?
3. Why does `ifPresentOrElse` take a `Runnable` for the empty branch instead of a `Consumer<T>`?
4. When you want to produce a `String` from an Optional value or a fallback, is `ifPresentOrElse` appropriate?
5. Which Java version introduced `ifPresentOrElse`? Which Java version introduced `ifPresent`?
6. If the present-branch callback throws `IllegalStateException`, does the empty branch run next?
7. Does `Optional.of(null)` create an empty Optional?
8. If an Optional has a value, does passing `null` as `emptyAction` necessarily throw an error immediately at the call site? Should you pass `null`?
9. What functional interface does `OptionalInt.ifPresentOrElse` use for the present branch?

**Suggested answers:**

1. No, the Optional is empty so the action is not called.
2. Only `action`, because a value is present.
3. Because there is no value of type `T` to pass, so the empty branch is a zero-argument operation.
4. No: both `ifPresent` and `ifPresentOrElse` return `void`; use `map` combined with `orElse`/`orElseGet` or `orElseThrow` as required.
5. `ifPresent` since Java 8; `ifPresentOrElse` since Java 9.
6. No; the exception propagates out, and the fallback does not run automatically.
7. No; `of(null)` throws `NullPointerException`, use `ofNullable(null)`.
8. Not necessarily; the empty branch is not selected. However, passing a null callback is unsafe and should be avoided.
9. `IntConsumer` for the branch with an integer, `Runnable` for the empty branch.

## 13. Official documentation

- [Java SE 17 API — Optional<T>](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html): `ifPresent`, `ifPresentOrElse`, `map`, `orElse`, `orElseGet`.
- [Java SE 17 API — Consumer<T>](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Consumer.html): contract `void accept(T)`.
- [Java SE 17 API — Runnable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runnable.html): contract `void run()`.
- [Java SE 17 API — OptionalInt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/OptionalInt.html): primitive value branch uses `IntConsumer`.

**Remember:** `ifPresent(Consumer)` handles **only when a value is present**; `ifPresentOrElse(Consumer, Runnable)` handles **one of the two branches, present or empty**. Both **return `void`**, so use them only when you need to perform an action. When you need to create or retrieve a result, switch to APIs like `map`, `orElseGet`, or `orElseThrow`.