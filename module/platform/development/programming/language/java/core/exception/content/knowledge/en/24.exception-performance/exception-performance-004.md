# Do Not Build Expensive Messages Before an Error Is Needed

When a Java application validates data millions of times, most calls usually succeed. If the program eagerly builds a long diagnostic message before determining whether an error occurred, **valid** calls still pay the cost of string formatting, converting objects to text, reading metadata, or memory allocation. The solution is to keep the required check intact while **deferring message construction until the error branch actually executes**.

This lesson covers **Performance** in **Java Core – Exception**, applicable to Java 17+. It explains argument evaluation, using `if` properly, `Objects.requireNonNull` with `Supplier<String>`, `Optional.orElseThrow`, conditional logging, preserving diagnostic quality, and how to benchmark properly.

## 1. Where Does the Cost Come From?

Consider the following call:

```java
Objects.requireNonNull(account,
        "account không hợp lệ: " + expensiveDiagnostic());
```

In Java, **argument expressions are evaluated before the method is invoked**. Therefore, `expensiveDiagnostic()` can run even when `account` is non-`null` and `Objects.requireNonNull` returns successfully. The method receives an already-prepared `String`, so it has no way to skip building that string on its own.

Tasks that need to be clearly separated:

| Task | Purpose | Should it run on the happy path? |
|---|---|---|
| Condition check | Determine whether the input is valid | **Yes**, if required by the contract |
| Error message construction | Explain why the condition failed | **No**, if no error is raised yet |
| Throwable instantiation | Create the exception object and its usual stack trace information | **No**, if no error is raised yet |
| Logging | Send data to the diagnostic system | Depends on log level, policy, and actual outcome |

A comparison like `amount < 0` is usually cheap. A message that invokes a JSON serializer, iterates over thousands of items, or accesses dynamic metadata can be far more expensive. The program needs to pay the cost of building a message on the **error path**, but it should not pay that same cost on the **success path**.

Standard flow:

```text
Receive value
    |
    v
Check condition
    | true                      | false
    v                           v
Continue, no message built     Build required message
                                |
                                v
                         Create/throw exception
```

**Do not skip validation to optimize.** Failing to check a value can cause the application to accept invalid data. We are only moving the work used for **error diagnostics** to where it is actually needed.

## 2. Building the Message Inside an `if` Branch

This is a very clear pattern:

```java
if (quantity < 0) {
    throw new IllegalArgumentException(
            "quantity=" + quantity + ", state=" + describeState());
}
```

The code above is an **illustrative snippet**; `quantity` and `describeState()` must exist in the method. If `quantity >= 0`, `describeState()` is not called at all. This is guaranteed by **Java control-flow semantics**, without needing to bet on JIT optimizations.

Compare this with the eager construction pattern:

```java
String message = "quantity=" + quantity
        + ", state=" + describeState();

if (quantity < 0) {
    throw new IllegalArgumentException(message);
}
```

Here, the message is built even when `quantity` is valid. If validation runs inside a loop or a high-frequency API, unnecessary overhead can accumulate.

### Standalone Program: Counting Message Builds

File `LazyErrorMessageDemo.java`:

```java
public class LazyErrorMessageDemo {
    private static int builds;

    static String describe(int amount) {
        builds++;
        return "amount âm: " + amount;
    }

    static void validate(int amount) {
        if (amount < 0) {
            throw new IllegalArgumentException(describe(amount));
        }
    }

    public static void main(String[] args) {
        validate(10);
        System.out.println("valid builds = " + builds);

        try {
            validate(-3);
        } catch (IllegalArgumentException error) {
            System.out.println("error = " + error.getMessage());
        }

        System.out.println("all builds = " + builds);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac LazyErrorMessageDemo.java
java LazyErrorMessageDemo
```

Output:

```text
valid builds = 0
error = amount âm: -3
all builds = 1
```

`validate(10)` still checks the condition but does **not** call `describe`. Only when `validate(-3)` fails does the program build the message and throw `IllegalArgumentException`.

The counter in the example only helps verify **evaluation timing**, not a benchmark. It runs on the `main` thread; do not put an unsynchronized global counter into a multithreaded system to measure production performance.

## 3. `Objects.requireNonNull` and `Supplier<String>`

Java has two notable overloads:

```java
static <T> T requireNonNull(T obj, String message)

static <T> T requireNonNull(
        T obj, java.util.function.Supplier<String> messageSupplier)
```

The first overload takes an already-built `String`. The second overload takes a **message-producing function**; if `obj != null`, `Supplier.get()` is **not called**. If `obj == null`, the method invokes the supplier to obtain the message and throws `NullPointerException`.

Example:

```java
Objects.requireNonNull(user,
        () -> "Không có user, request=" + expensiveContext());
```

This is an illustrative snippet. `expensiveContext()` only runs when `user` is actually `null`. If the message is already a string constant like `"user không được null"`, the `String` overload is simple and usually good enough; there is no need to turn every constant into a lambda.

### Standalone Program: Eager vs. Lazy

File `RequireNonNullMessageDemo.java`:

```java
import java.util.Objects;

public class RequireNonNullMessageDemo {
    private static int builds;

    static String message() {
        builds++;
        return "user không được null";
    }

    public static void main(String[] args) {
        String value = "Lan";

        Objects.requireNonNull(value, message());
        System.out.println("eager = " + builds);

        builds = 0;
        Objects.requireNonNull(value, () -> message());
        System.out.println("lazy valid = " + builds);

        try {
            Objects.requireNonNull(null, () -> message());
        } catch (NullPointerException error) {
            System.out.println("lazy error = " + error.getMessage());
        }
        System.out.println("lazy invalid = " + builds);
    }
}
```

Run:

```bash
javac RequireNonNullMessageDemo.java
java RequireNonNullMessageDemo
```

Output:

```text
eager = 1
lazy valid = 0
lazy error = user không được null
lazy invalid = 1
```

In the eager call, `message()` runs before `requireNonNull` even though `value` is valid. In the lazy call, the lambda does not execute for a non-`null` `value`. With `null`, the supplier runs exactly once and the message is attached to `NullPointerException`.

A few important limitations:

- `requireNonNull` uses **`NullPointerException`**; do not switch to this API if the method's contract requires `IllegalArgumentException` or another business exception.
- `Supplier.get()` can throw an exception. If building the message fails, the caller may observe the **error from the supplier**, masking the original null error.
- A supplier returning `null` will produce a `NullPointerException` with a null message. Do not assume the API will automatically generate a helpful message.
- A lambda can capture variables and objects; creating/capturing a lambda does not always have zero cost. The clearest benefit is **not running expensive diagnostic work** on the valid path.
- Avoid having the supplier perform I/O or network queries. When the system has already encountered an error, building the message must be as reliable and fast as possible.

## 4. `Optional.orElseThrow`: Deferring Exception Creation Too

Sometimes not only the message, but **the exception object itself** does not need to exist on the happy path. `Optional.orElseThrow(Supplier<? extends X>)` takes a supplier that **creates an exception**, invoking it only when the `Optional` is empty.

```java
String name = maybeName.orElseThrow(
        () -> new IllegalStateException(
                "Không tìm thấy tên cho id=" + id));
```

This is an illustrative snippet: `maybeName` is an `Optional<String>`, and `id` is already declared. If the `Optional` has a value, Java returns that value without creating an `IllegalStateException`.

### Standalone Program

File `OptionalThrowLazyDemo.java`:

```java
import java.util.Optional;

public class OptionalThrowLazyDemo {
    private static int exceptionsBuilt;

    static IllegalStateException missing() {
        exceptionsBuilt++;
        return new IllegalStateException("không tìm thấy hồ sơ");
    }

    public static void main(String[] args) {
        String value = Optional.of("OK")
                .orElseThrow(() -> missing());

        System.out.println("value = " + value);
        System.out.println("after present = " + exceptionsBuilt);

        try {
            Optional.<String>empty().orElseThrow(() -> missing());
        } catch (IllegalStateException error) {
            System.out.println("missing = " + error.getMessage());
        }

        System.out.println("after empty = " + exceptionsBuilt);
    }
}
```

Run:

```bash
javac OptionalThrowLazyDemo.java
java OptionalThrowLazyDemo
```

Output:

```text
value = OK
after present = 0
missing = không tìm thấy hồ sơ
after empty = 1
```

A **no-argument** `Optional.orElseThrow()` also exists and throws `NoSuchElementException` when empty. Use the supplier overload when you want a custom exception type and message; choose an error type that matches the contract.

Do not confuse this with:

```java
String value = optional.orElse(expensiveFallback());
```

`orElse` takes an already-evaluated **value**, so `expensiveFallback()` still runs when the `Optional` has a value. If you want a lazy fallback, use:

```java
String value = optional.orElseGet(() -> expensiveFallback());
```

The last two snippets are illustrative examples with `optional` of type `Optional<String>` and `expensiveFallback()` returning `String`. `orElseGet` applies to a **fallback value**, whereas `orElseThrow` applies when **a missing value is an error**. What they have in common is that the supplier is only used when needed.

## 5. `IllegalArgumentException` Has No Constructor Taking a Supplier

In Java 17, the commonly used constructors are:

```java
new IllegalArgumentException(String message)
new IllegalArgumentException(String message, Throwable cause)
```

`IllegalArgumentException` has no standard `IllegalArgumentException(Supplier<String>)` constructor. Writing:

```java
throw new IllegalArgumentException(() -> expensiveMessage());
```

is **invalid**. If you need this exception type, simply place message construction inside the false branch:

```java
if (count <= 0) {
    throw new IllegalArgumentException(
            expensiveMessageFor(count));
}
```

This is an illustrative snippet. There is no need to create a custom exception class just to defer string computation. An `if` statement can be both fast and easy to maintain.

If a project has many checks sharing the same contract, you can write a helper that accepts a supplier:

```java
static void requirePositive(
        int count, java.util.function.Supplier<String> message) {
    if (count <= 0) {
        throw new IllegalArgumentException(message.get());
    }
}
```

This is a **valid method that can be placed in a class**. Usage:

```java
requirePositive(itemsCount,
        () -> "Số phần tử không hợp lệ: " + itemsCount);
```

The snippet using `itemsCount` is illustrative. A helper is only useful when it clarifies a reusable rule; avoid adding complex abstractions if there is only a single call site.

Do not overlook supplier safety: it can be `null`, return `null`, or throw an error. Also distinguish between deferring **message** creation and deferring **validation**: you must evaluate the condition at the right time, on data in the right state.

## 6. Long Strings, `String.format`, and `formatted(...)`

Three common ways to build messages:

```java
"amount=" + amount

String.format("amount=%d", amount)

"amount=%d".formatted(amount)
```

`String.formatted` has been available since Java 15 and works on Java 17. All of them create a string when **the expression is evaluated**. If placed inside the error branch, they do not build a message on the success path:

```java
if (actual < min || actual > max) {
    throw new IllegalArgumentException(
            "actual=%d ngoài khoảng [%d, %d]"
                    .formatted(actual, min, max));
}
```

This is an illustrative snippet inside a method that already has `actual`, `min`, and `max`.

For small costs like concatenating two integers, **clarity** is usually more important than micro-optimization. `String.format` has its own formatting and pattern-parsing overhead; however, debating `"x=" + x` versus `.formatted(x)` matters little when an error only happens once per million requests.

Larger costs usually come from:

| Message source | Why can it be expensive? | Alternative |
|---|---|---|
| Iterating over a large collection | Builds long strings, many allocations | Only take the count or a few safe IDs |
| JSON serialization | Traverses object graph, formats | Do not serialize everything in an exception |
| Entity `toString()` | May traverse deep relationships or trigger lazy-loading | Print only necessary, stable fields |
| Reading stack/context | Collects large structures | Only do this on error and when needed |
| DB/network lookup | I/O can hang or fail further | Avoid using in messages |
| Complex date/locale formatting | Parser/formatter overhead | Use an appropriate formatter, inside the error branch |

In modern Java, string concatenation with `+` is well-optimized by the JVM in many situations; manually replacing everything with `StringBuilder` is rarely a valuable first step. **Eliminate unnecessary work** first, then profile the hot path to decide whether to optimize specific expressions.

## 7. Bad Example: Serializing Data Into a Message Before Checking

Suppose the program must validate an order quantity. The approach below can do useless work:

```java
String fullDump = orders.stream()
        .map(Object::toString)
        .collect(java.util.stream.Collectors.joining(", "));

if (quantity < 0) {
    throw new IllegalArgumentException(
            "quantity sai, orders=" + fullDump);
}
```

This is an **illustrative snippet** with `orders` and `quantity` already in scope. Even when `quantity >= 0`, all of `orders` is still iterated over and converted to text. A huge message can also cause log ingestion costs and data leaks.

In many situations, you only need:

```java
if (quantity < 0) {
    throw new IllegalArgumentException(
            "quantity âm: " + quantity
            + ", orderCount=" + orders.size());
}
```

If you need a few elements for diagnostics, limit the number of items, protect sensitive data, and only do it inside the error branch.

A high-quality message usually states **the violated constraint, the field name, and a few safe values**, rather than dumping the state of the entire application.

## 8. Conditional Logging and Exception Messages Are Two Different Mechanisms

Lazy logging is also related to performance, but it differs from building exception messages.

Example using an SLF4J-style logger framework:

```java
logger.debug("Request {} đã hoàn thành", requestId);
```

This is an **integration snippet** and will not run standalone without adding the library/logger. Placeholders usually allow the logger to defer string formatting when the log level is not enabled. However, Java semantics still apply: expressions passed as **arguments** are evaluated before the call takes place.

Example:

```java
logger.debug("Payload: {}", expensiveSerialize(payload));
```

Even when `DEBUG` logging is disabled, `expensiveSerialize(payload)` is still executed to produce the argument. Guard it if the logging API allows:

```java
if (logger.isDebugEnabled()) {
    logger.debug("Payload: {}", expensiveSerialize(payload));
}
```

The code above is an integration example, depending on the logger and previously defined variables. Some modern logging APIs support supplier/lazy arguments, but you must check the **exact version's** contract and not assume every framework understands `Supplier`.

For **validation**, never write:

```java
if (logger.isDebugEnabled() && invalid) {
    throw new IllegalArgumentException("đầu vào sai");
}
```

Because when `DEBUG` is disabled, the `invalid` condition may not be checked and the error will be ignored. **Application correctness must not depend on logging configuration.**

## 9. A Message Supplier Must Be Safe Even When the System Is Failing

A *lazily* built message can save work on the happy path yet still cause serious trouble if it performs I/O or mutates state.

Example to avoid:

```java
if (user == null) {
    String accountName = remoteApi.lookupAccount();
    throw new IllegalArgumentException(
            "Không thấy user thuộc account " + accountName);
}
```

This is an **illustrative snippet**. If `remoteApi.lookupAccount()` times out or throws a new exception, the caller may only see the network error, while the original null error is masked. If the lookup function has side effects, merely building the message can alter data.

A more stable choice:

```java
if (user == null) {
    throw new IllegalArgumentException(
            "user bắt buộc, requestId=" + requestId);
}
```

This is also an illustrative snippet, with `requestId` safely prepared. If collecting additional information is mandatory, use a telemetry system at the boundary with clear time budgets and safety rules.

Some practical notes:

- Do not call a DB or HTTP endpoint just to build an error string.
- Do not call `toString()` on objects that may trigger unexpected lazy-loading.
- Limit message length and strip secrets (passwords, tokens, keys, PII).
- Do not use a `Supplier.get()` that can throw checked/unchecked exceptions without a policy.
- If you must wrap an exception at a higher layer, **preserve the cause** using `new IllegalStateException("...", original)` when appropriate.

Deferring message construction avoids wasted work; it is not a license to turn the message into an expensive or unreliable operation.

## 10. Do Not Pre-Instantiate Throwable Objects

Beyond the message, creating an exception usually involves filling in the stack trace. Therefore, you should not instantiate a `Throwable` ahead of time before knowing whether an error occurred:

```java
IllegalStateException cachedError =
        new IllegalStateException("không hợp lệ");

// Check much later:
if (invalid) {
    throw cachedError;
}
```

This is a **discouraged** illustrative snippet. The exception is created even when `invalid` is `false`. If the same exception is reused multiple times, the stack trace may reflect the original creation site rather than where the error actually occurred, making investigation harder.

Replace with:

```java
if (invalid) {
    throw new IllegalStateException("không hợp lệ");
}
```

Create and throw the exception when the condition is actually violated. Similarly, do not use exceptions as ordinary control-flow values inside hot loops (for example, throwing an exception for an expected outcome like "not found in cache" every time). When failure is a normal high-frequency state, consider an API returning `Optional`, a status code, or an appropriate result type.

Be cautious with techniques that **disable stack traces** to speed up exceptions: they can destroy diagnosability, especially in production. First optimize **when errors are created** and **when messages are built**, and only benchmark special trade-offs if truly necessary.

## 11. Standalone Example: Evaluation Order Does Not Depend on JIT Optimizations

File `MessageEvaluationOrderDemo.java`:

```java
import java.util.Objects;

public class MessageEvaluationOrderDemo {
    private static int calls;

    static String diagnostics() {
        calls++;
        return "diagnostic #" + calls;
    }

    static void eager(String value) {
        Objects.requireNonNull(value, diagnostics());
    }

    static void lazy(String value) {
        Objects.requireNonNull(value, () -> diagnostics());
    }

    public static void main(String[] args) {
        eager("OK");
        lazy("OK");
        System.out.println("after valid = " + calls);

        try {
            lazy(null);
        } catch (NullPointerException error) {
            System.out.println("caught = " + error.getMessage());
        }

        System.out.println("all calls = " + calls);
    }
}
```

Run:

```bash
javac MessageEvaluationOrderDemo.java
java MessageEvaluationOrderDemo
```

Exact output:

```text
after valid = 1
caught = diagnostic #2
all calls = 2
```

The body of `diagnostics()` increments a counter, so the JIT cannot pretend the eager call has no side effects. The example clarifies semantics rather than showing how many nanoseconds faster lazy is.

Do not use a non-thread-safe counter like this across multiple workers; it is only for verifying single-threaded order.

## 12. Benchmarking Properly: Lazy Does Not Always Mean Faster

The benefit of a lazy message depends on **message construction cost** and **error frequency**. With a string constant:

```java
Objects.requireNonNull(value, "value không được null");
```

there is no expensive formatting work to avoid. A lambda may bring no measurable benefit and can even make the code noisier.

A serious measurement should separate the following cases:

| Scenario | What to measure |
|---|---|
| Valid input, expensive eager message | Wasted cost on the happy path |
| Valid input, lazy message | Cost of the condition and lambda construction |
| Invalid input, eager message | Cost of formatting and exception creation |
| Invalid input, lazy message | Cost of invoking supplier, formatting, and exception creation |

When reliable numbers are needed, prefer tools like **JMH** with warmup, multiple forks, non-constant data, properly consumed results, and realistic error rates. Do not take a few `System.nanoTime()` readings and draw firm conclusions about nanoseconds/op because JIT, escape analysis, GC, the OS, and dead-code elimination can all skew measurements.

Observe **allocation rate and GC** as well, not just time. A useless message on a hot path can increase memory pressure even when single-call latency is hard to notice. However, if profiling shows the cost is lower than maintaining a new abstraction, prefer readable code.

If most transactions **fail**, lazy message construction may not help much. You need to fix the root cause of the errors or design normal results so exceptions are not abused.

## 13. Risk of Reading Stale/Late Data in a Multithreaded Environment

A supplier captures objects and **reads state when invoked**, not necessarily when the lambda is created:

```java
Objects.requireNonNull(user,
        () -> "activeTasks=" + sharedTasks.size());
```

This is an illustrative snippet. If `sharedTasks` changes concurrently, the observed value depends on when `get()` runs. With the `Objects.requireNonNull` overload, the supplier is called immediately during the call when the value is null, so the time gap is usually small; however, other utilities may **store the supplier and invoke it later**, making the timing difference significant.

If a message needs a consistent snapshot, you can save safe values at the check point or use the synchronization mechanism required by the contract. Do not defer a required check until the data has changed state. **Defer diagnostic formatting**, not the condition protecting correctness.

Also consider the lifetime of lambda captures: a supplier held in a long-lived object can extend the lifetime of the entire captured object graph. Do not use `Supplier` casually as a message cache for every request.

## 14. Common Mistakes

### Building the Message Before Checking

Wrong:

```java
String details = expensiveDescribe(input);
if (invalid) {
    throw new IllegalArgumentException(details);
}
```

Right when `details` is only for the error:

```java
if (invalid) {
    throw new IllegalArgumentException(expensiveDescribe(input));
}
```

These are illustrative snippets with application-defined variables/functions.

### Thinking `Objects.requireNonNull(value, expensive())` Is Lazy

It is not. It selects the **String** overload, so `expensive()` has already run before the call. You must pass a supplier to the corresponding overload:

```java
Objects.requireNonNull(value, () -> expensive());
```

### Thinking the Message Is Always the Biggest Cost

Throwable instantiation usually involves the stack trace; throwing many exceptions for normal flow can be more expensive than optimizing message expressions. Focus on redesigning the hot path before writing custom formatters.

### Using a Lazy Supplier That Makes External Queries

The supplier only runs on error, which is precisely when you should not open new connections or cause new failures. Keep messages simple and based on already-available data.

### Switching All Validation to `Objects.requireNonNull`

It only checks `null` and throws `NullPointerException`. Do not use it to replace business conditions that require `IllegalArgumentException`, a checked exception, or a custom exception.

### Using a Logger Placeholder While Still Serializing the Argument

```java
logger.debug("Object={}", serialize(largeObject));
```

Java evaluates `serialize` before entering the logger. If you do not want it to run when `DEBUG` is disabled, use a guard or the library's standard lazy argument API.

### Using Unbounded `toString()` Messages

A large object graph or one with circular references can produce a huge string, fail, or leak data. Only display useful information of bounded size.

### Disabling Stack Traces to Make Benchmarks Look Good

This is a major diagnostic trade-off. Do not optimize before having real metrics and a clear policy on what needs to be preserved in errors.

### Confusing Checking With Message Creation

Data-protection conditions must still run at the right time. Do not defer validation on the grounds that "it usually doesn't fail"; only defer **work unnecessary in the valid state**.

## 15. Quick Decision Table

| Need | Appropriate approach |
|---|---|
| Check a condition and throw a custom error | `if (invalid) throw new ...(...)` |
| `Objects.requireNonNull` with an expensive message | `Objects.requireNonNull(value, () -> message())` |
| `Optional` missing data should throw an exception | `optional.orElseThrow(() -> new ...(...))` |
| `Optional` needs an expensive fallback value | `optional.orElseGet(() -> compute())` |
| Format multiple fields only when condition fails | Place formatting in the error branch |
| Logging with expensive arguments when level is off | Guard or logger-supported supplier |
| Expected errors occur too frequently | Revisit API/control flow; do not abuse exceptions |
| Want to prove it is faster | Profile or use JMH with realistic success/failure ratios |

To review a piece of code, ask: "If the data is **valid**, is any function that only serves errors still being called?" If the answer is yes, move that work into the error branch or use a supplier-accepting overload. Then verify that the exception type and message when **an error actually occurs** remain correct.

## 16. Production Adoption Checklist

- Input checks are still performed with the right conditions and timing.
- No expensive `String.format`, `.formatted`, JSON, or `toString()` is built on the valid path.
- `Objects.requireNonNull`'s `Supplier<String>` overload is used **in the right places**, not confused with the `String` overload.
- `Optional.orElseThrow` is used when missing data is an error; do not create the exception before knowing the `Optional` is empty.
- Messages are safe, have no business side effects, require no network/DB calls, and do not leak secrets.
- Exception type, message, cause, and caller behavior on error are preserved after optimization.
- Throwables are not cached or reused out of context.
- Log messages are not eagerly evaluated by Java arguments when the level is off.
- Benchmarks/monitoring are sufficient before applying more complex optimizations.

**Remember:** Java evaluates method arguments before invocation. Therefore, **do not build expensive error messages when the check path can still succeed**. Put message-building work inside the error branch or use a real `Supplier` API; keep full diagnostic information when an error occurs, and only optimize deeply after collecting metrics.
