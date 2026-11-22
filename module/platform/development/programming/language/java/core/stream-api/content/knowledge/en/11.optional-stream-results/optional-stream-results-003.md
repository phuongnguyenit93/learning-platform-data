# Choosing Default Values with orElse and orElseGet

## 1. Why Do Stream Results Often Need a Default Value?

In the **Optional in Stream Results** chapter of **JAVA_STREAM_API**, terminal operations such as `findFirst()`, `findAny()`, `min()`, `max()`, or `reduce(BinaryOperator)` may fail to find any element. Because a Stream can become empty after `filter`, Java cannot always return a valid `T` object. These terminal operations use `Optional<T>` to represent a result **with or without a value**.

When business logic requires always receiving a value to continue processing, we must decide on a fallback policy. Two familiar methods are:

- `orElse(defaultValue)`: uses a fallback value that **has already been evaluated** before calling the method.
- `orElseGet(supplier)`: **invokes the fallback-producing function** only if the Optional is actually empty.

This is part of declarative programming with lazy pipelines, `filter`, `map`, `reduce`, and `collect`: choosing when a result may be missing, when substitution is allowed, and when computing the replacement incurs cost or side effects.

~~~text
Stream source ─► filter / map / ... ─► findFirst / max / reduce ─► Optional<T>
                                                                 │
                                    ┌────────────────────────────┴────────────────────────────┐
                                    ▼                                                         ▼
                             Optional has value                                        Optional.empty()
                                    │                                                         │
                           Take present value                                          Use fallback value
                                    │                                                         │
                                    └────────────────────────────┬────────────────────────────┘
                                                                 ▼
                                                           T (no longer Optional)
~~~

**Key point:** When an Optional has a value, both methods usually return the same value. The notable difference lies in **when the fallback expression is executed**.

The examples in this lesson use Java 17+, although `Optional.orElse` and `Optional.orElseGet` have existed since Java 8.

## 2. Creating an Optional From a Stream Result

Example finding the first customer name matching a condition:

~~~java
import java.util.List;
import java.util.Optional;

public class FindCustomer {
    public static void main(String[] args) {
        List<String> customers = List.of("An", "Bình", "Chi");

        Optional<String> found = customers.stream()
            .filter(name -> name.startsWith("B"))
            .findFirst();

        Optional<String> missing = customers.stream()
            .filter(name -> name.startsWith("Z"))
            .findFirst();

        System.out.println(found);   // Optional[Bình]
        System.out.println(missing); // Optional.empty
    }
}
~~~

Common cases:

| Terminal operation | Result type | Why can it be empty? |
| --- | --- | --- |
| `findFirst()` | `Optional<T>` | No elements, or no element passes the filter. |
| `findAny()` | `Optional<T>` | No matching element. |
| `min(comparator)` | `Optional<T>` | Stream has no elements. |
| `max(comparator)` | `Optional<T>` | Stream has no elements. |
| `reduce(BinaryOperator)` | `Optional<T>` | No values to combine. |
| `IntStream.min()`, `IntStream.max()` | `OptionalInt` | Primitive stream is empty. |
| `IntStream.average()` | `OptionalDouble` | No numbers to compute the average. |

Not every terminal operation returns an Optional. For instance, `count()` returns `long` (equal to 0 if empty), `IntStream.sum()` returns `int` (equal to 0 if empty), and `reduce(identity, accumulator)` directly returns the value corresponding to `identity` when the Stream is empty.

## 3. Syntax and Key Differences Between orElse and orElseGet

Two method signatures on `Optional<T>`:

~~~java
T orElse(T other);

T orElseGet(Supplier<? extends T> supplier);
~~~

`orElse` accepts **a value `T`**. `orElseGet` accepts **a Supplier** capable of producing `T` when invoked.

~~~java
import java.util.Optional;

Optional<String> found = Optional.of("Bình");
Optional<String> missing = Optional.empty();

String a = found.orElse("Guest");
String b = missing.orElse("Guest");

String c = found.orElseGet(() -> "Guest");
String d = missing.orElseGet(() -> "Guest");

// a = "Bình", b = "Guest"
// c = "Bình", d = "Guest"
~~~

With simple literals, the result does not differ. The difference appears when **the default value has to be computed**:

| Condition | `optional.orElse(createDefault())` | `optional.orElseGet(() -> createDefault())` |
| --- | --- | --- |
| Optional has a value | `createDefault()` **is still called**; the fallback result is discarded | Supplier **is not called** |
| Optional is empty | `createDefault()` is called, returning the fallback result | Supplier is called to produce the fallback result |
| Fallback is a literal/constant | Concise, easy-to-read syntax | Can be used, though unnecessary |
| Fallback costs CPU, I/O, or has side effects | Risk of redundant execution | Avoids fallback execution when a result already exists |

The reason is **Java's argument evaluation mechanism**: before calling `orElse(...)`, Java finishes evaluating the passed expression. With `orElseGet(...)`, the argument is a Supplier object (usually expressed as a lambda or method reference); **the Supplier body** only executes if the Optional is empty.

## 4. Demonstrating Eager vs. Lazy With a Runnable Example

~~~java
import java.util.Optional;

public class EagerVsLazy {
    static String buildDefault() {
        System.out.println("Creating fallback value");
        return "Guest";
    }

    public static void main(String[] args) {
        Optional<String> found = Optional.of("An");

        String eager = found.orElse(buildDefault());
        System.out.println("orElse = " + eager);

        String lazy = found.orElseGet(EagerVsLazy::buildDefault);
        System.out.println("orElseGet = " + lazy);
    }
}
~~~

Output:

~~~text
Creating fallback value
orElse = An
orElseGet = An
~~~

Even though `found` already contains `"An"`, `buildDefault()` is still called to prepare the argument for `orElse`. The `orElseGet` call does not run `buildDefault()` because the Optional has a value.

Change `found` to `Optional.empty()`:

~~~java
Optional<String> missing = Optional.empty();

String fromElse = missing.orElse(buildDefault());
String fromGet = missing.orElseGet(EagerVsLazy::buildDefault);

// Both receive "Guest".
// buildDefault is called once for each invocation on the empty Optional.
~~~

Do not confuse **creating the lambda** with **executing the lambda body**: the expression `() -> buildDefault()` is evaluated into a Supplier before the method call, but the `buildDefault()` action only happens when the Optional is empty.

### Correct Syntax When the Fallback Is a Method

~~~java
// Called immediately, even if Optional has a value:
String eager = found.orElse(buildDefault());

// Only called when Optional is empty:
String lazyByLambda = found.orElseGet(() -> buildDefault());
String lazyByReference = found.orElseGet(EagerVsLazy::buildDefault);
~~~

`orElseGet(buildDefault())` **is invalid** here because `buildDefault()` returns `String`, whereas `orElseGet` requires a `Supplier<? extends String>`.

## 5. Business Scenario: Creating an Expensive Default Object

Suppose a system processes a list of requests and needs to find a priority request. If no matching request exists, the system creates a default object. Creating it can be costly when tied to configuration lookups, external service calls, or multi-step calculations.

The standalone example below uses logging to show when the fallback function runs:

~~~java
import java.util.List;
import java.util.Optional;

public class RequestFallback {
    record Request(String id, int priority) {}

    static Request createDefaultRequest() {
        System.out.println("Creating default request");
        return new Request("DEFAULT", 0);
    }

    static Request choose(List<Request> requests) {
        Optional<Request> selected = requests.stream()
            .filter(request -> request.priority() >= 5)
            .findFirst();

        return selected.orElseGet(RequestFallback::createDefaultRequest);
    }

    public static void main(String[] args) {
        List<Request> requests = List.of(
            new Request("R-01", 2),
            new Request("R-02", 9),
            new Request("R-03", 5)
        );

        System.out.println(choose(requests)); // Request[id=R-02, priority=9]
        System.out.println(choose(List.of())); // Logs creating default, then DEFAULT
    }
}
~~~

When `R-02` is found, the default request creation function **does not run**. When the list is empty, the Supplier runs to create the object.

If replaced with:

~~~java
return selected.orElse(createDefaultRequest());
~~~

then the fallback object is created **every time `choose` runs**, even when `selected` contains a value. In a real application, this can lead to redundant network requests, unnecessary file opens, or even unwanted extra records written if the default-creating function has side effects.

**Rule of thumb:** When the fallback needs to call a function or construct an expensive object, `orElseGet` usually expresses the intent "create only when missing" accurately.

## 6. Multiple Fallback Policies: From Ready Values to Fallback Sources

There are multiple levels of fallback. Choose based on **business meaning**, not just return type.

### 6.1. Fixed, Cheap, and Immutable Values

~~~java
String label = items.stream()
    .filter(text -> !text.isBlank())
    .findFirst()
    .orElse("No data");
~~~

In this example, `items` is a `List<String>` from the calling context. The string literal is already available, so `orElse` is the simple choice.

### 6.2. Fallback Value Computed From Current Data

~~~java
import java.time.LocalDate;
import java.util.Optional;

Optional<LocalDate> latestDate = dates.stream().max(LocalDate::compareTo);

LocalDate chosen = latestDate.orElseGet(LocalDate::now);
~~~

The example assumes `dates` is a `List<LocalDate>`. `LocalDate.now()` is only called when there are no dates. For applications that need testability or explicit time zones, you can pass a `Clock` into the class and use `LocalDate.now(clock)` inside the Supplier.

### 6.3. Querying Cache Then Database Sequentially

Sometimes both sources can **lack a value**. `Optional.or(...)` (Java 9+) preserves the Optional type until the final fallback decision:

~~~java
import java.util.Optional;

Optional<String> fromCache = Optional.empty();

String displayName = fromCache
    .or(() -> lookupFromDatabase())
    .orElseGet(() -> "Guest");
~~~

`lookupFromDatabase()` in the example is an application-defined method returning `Optional<String>`. `Optional.or` only calls the Supplier when the preceding Optional is empty; the result of `or(...)` is still **`Optional<String>`**, while `orElseGet(...)` directly returns **`String`**.

You cannot use `orElseGet(() -> lookupFromDatabase())` directly when the function returns `Optional<String>`, because the Supplier of `orElseGet` must return **`String`**. If you want to fall back directly from a query returning Optional, you can use:

~~~java
String displayName = fromCache.orElseGet(
    () -> lookupFromDatabase().orElse("Guest")
);
~~~

In systems with side effects such as writing data, sending requests, or billing, `orElseGet` only manages **when the fallback runs**; it **does not automatically guarantee transactions, idempotency, or single execution across different requests**.

## 7. Combining With `findFirst`, `findAny`, and `max`

### 7.1. `findFirst` When the First Element Is Needed

~~~java
import java.util.List;

List<Integer> scores = List.of(40, 75, 90, 60);

int firstHighScore = scores.stream()
    .filter(score -> score >= 70)
    .findFirst()
    .orElse(-1);

System.out.println(firstHighScore); // 75
~~~

With an ordered source such as `List`, `findFirst` takes the first matching element. If no element matches, it returns `Optional.empty()`; `orElse(-1)` converts it to a sentinel value per application convention.

### 7.2. `findAny` When Picking Any Element Is Enough

~~~java
int anyHighScore = scores.parallelStream()
    .filter(score -> score >= 70)
    .findAny()
    .orElse(-1);
~~~

`findAny` does not promise to choose the first element, especially during parallel processing. The fallback value `-1` is only used when **no element** satisfies the condition. If business logic strictly requires "the first", use `findFirst` with a deterministically ordered source.

### 7.3. `max` and Fallback When There Is No Data

~~~java
import java.util.Comparator;
import java.util.List;

record Product(String sku, long price) {}

List<Product> products = List.of(
    new Product("PEN", 10_000L),
    new Product("BOOK", 45_000L)
);

Product mostExpensive = products.stream()
    .max(Comparator.comparingLong(Product::price))
    .orElseGet(() -> new Product("NONE", 0L));

// Product[sku=BOOK, price=45000]
~~~

`max` returns an Optional because the source may be empty. Think carefully before introducing a dummy product into business data: a fallback is useful when the model allows "no product", yet sometimes an empty Optional result should be preserved so the system can display an "out of stock" state.

## 8. `reduce`: Receiving Optional When There Is No Identity

`reduce(BinaryOperator<T>)` returns `Optional<T>`, unlike the variant with identity.

~~~java
import java.util.List;
import java.util.Optional;

List<Integer> values = List.of(10, 20, 30);

Optional<Integer> combined = values.stream()
    .reduce(Integer::sum);

int total = combined.orElse(0);
System.out.println(total); // 60

int emptyTotal = List.<Integer>of().stream()
    .reduce(Integer::sum)
    .orElse(0);

System.out.println(emptyTotal); // 0
~~~

If `0` is truly an appropriate **identity element** for addition, you can use the `reduce(identity, accumulator)` variant:

~~~java
int total = values.stream().reduce(0, Integer::sum);
int emptyTotal = List.<Integer>of().stream().reduce(0, Integer::sum);

// total = 60; emptyTotal = 0
~~~

The combining operation must satisfy associativity, identity, and non-interference requirements if you want correct results on a parallel stream. Do not arbitrarily use a sentinel like `-1` for a sum operation if `-1` could be mistaken for real data.

In many numeric cases, `mapToInt(...).sum()` is more direct than `reduce` on `Stream<Integer>` and avoids boxing.

## 9. Primitive Optionals: Do orElse and orElseGet Work?

Yes. `OptionalInt`, `OptionalLong`, and `OptionalDouble` all support both ways of getting default values, but the corresponding Supplier type is a **primitive functional interface**.

| Optional type | `orElse` takes | `orElseGet` takes | Returns |
| --- | --- | --- | --- |
| `OptionalInt` | `int other` | `IntSupplier` | `int` |
| `OptionalLong` | `long other` | `LongSupplier` | `long` |
| `OptionalDouble` | `double other` | `DoubleSupplier` | `double` |

Example aggregating a result from `IntStream`:

~~~java
import java.util.OptionalInt;
import java.util.stream.IntStream;

OptionalInt max = IntStream.of(10, 40, 20).max();

int value = max.orElse(0);
System.out.println(value); // 40

int missing = IntStream.empty()
    .max()
    .orElseGet(() -> -1);

System.out.println(missing); // -1
~~~

With `OptionalDouble` returned by `average()`:

~~~java
import java.util.stream.DoubleStream;

double avg = DoubleStream.of(2.0, 4.0, 6.0)
    .average()
    .orElse(Double.NaN); // 4.0

double defaultAvg = DoubleStream.empty()
    .average()
    .orElseGet(() -> 0.0); // 0.0
~~~

The value `0.0` can mislead readers into confusing "no observations" with "average equals 0". If distinguishing the two states matters, **keep `OptionalDouble`** instead of turning it into a number.

### Cost of Fallback With Primitive Optionals

~~~java
static int computeDefault() {
    System.out.println("Computing default int value");
    return 42;
}

// Inside the calling method:
int value = OptionalInt.of(5).orElse(computeDefault()); // Still computes 42.
int lazy = OptionalInt.of(5).orElseGet(() -> computeDefault()); // Not called.
~~~

This still follows Java's argument evaluation rule, regardless of whether the type is reference or primitive.

## 10. orElse, orElseGet, orElseThrow, and ifPresentOrElse

Each method serves a different purpose:

| API | When Optional has a value | When Optional is empty | Return type |
| --- | --- | --- | --- |
| `orElse(value)` | Returns the present value | Returns `value` | `T` |
| `orElseGet(supplier)` | Returns the present value, does not call Supplier | Calls Supplier to get fallback | `T` |
| `orElseThrow()` | Returns the present value | Throws `NoSuchElementException` | `T` |
| `orElseThrow(exceptionSupplier)` | Returns the present value | Calls Supplier to create and throw exception | `T` |
| `ifPresentOrElse(action, emptyAction)` | Executes action | Executes emptyAction | `void` |
| `or(optionalSupplier)` | Keeps current Optional | Gets replacement Optional from Supplier | `Optional<T>` |

### Missing Data Is an Error: Use orElseThrow

~~~java
import java.util.List;

List<String> ids = List.of("A100", "B200");

String required = ids.stream()
    .filter(id -> id.equals("B200"))
    .findFirst()
    .orElseThrow(
        () -> new IllegalStateException("Required code not found")
    );

System.out.println(required); // B200
~~~

If `"B200"` is replaced with a nonexistent ID, the Supplier then creates the exception. Do not fabricate dummy data to mask violations of an important constraint: when data is mandatory, an exception or an error-representing result type is usually more appropriate.

### Only an Action Needed, No T Return Value: Use ifPresentOrElse

~~~java
import java.util.Optional;

Optional<String> matched = Optional.empty();

matched.ifPresentOrElse(
    value -> System.out.println("Found: " + value),
    () -> System.out.println("Not found")
);
~~~

`ifPresentOrElse` does not return a replacement value; it dispatches two actions. If the goal is to obtain a `String` and pass it into a pipeline or return it from a method, `orElse` or `orElseGet` is more suitable.

## 11. Common Mistakes

### 11.1. Calling an Expensive Function Inside orElse Thinking It Only Runs When Empty

~~~java
// A fallback-creating function with side effects still runs even if result has a value:
String selected = result.orElse(loadFromRemoteService());

// Only calls the service when result is empty:
String selectedLazy = result.orElseGet(() -> loadFromRemoteService());
~~~

In this snippet, `result` is `Optional<String>`, and `loadFromRemoteService()` is an application-defined function returning `String`. This is the most important mistake to avoid.

### 11.2. Computing the Fallback Outside the Lambda Thinking orElseGet Delays It

~~~java
String fallback = loadFromRemoteService(); // Service already called here.
String selected = result.orElseGet(() -> fallback);
~~~

The snippet above still calls the service on every execution, even when `result` has a value. To truly defer it, place **the expensive call** inside the Supplier:

~~~java
String selected = result.orElseGet(() -> loadFromRemoteService());
~~~

### 11.3. Using orElse(null) and Forgetting to Handle null

~~~java
import java.util.Optional;

Optional<String> missing = Optional.empty();

String name = missing.orElse(null); // name == null
~~~

`Optional.orElse(null)` is valid because `orElse` can return null, yet it forfeits the benefit of representing "present/absent" with Optional and can lead to `NullPointerException` later.

`orElseGet(() -> null)` can also return null. Neither method **has an obligation to guarantee a non-null result**. If you need a valid value, produce a valid fallback or use `orElseThrow`.

### 11.4. Passing a null Supplier

~~~java
Optional<String> value = Optional.empty();

// Do not do this: an empty Optional needs to invoke Supplier, so it throws NPE.
// String text = value.orElseGet(null);
~~~

Although an Optional with a value might not dereference the Supplier, passing null is unclear usage and breaks easily when data changes. Always pass a valid Supplier.

### 11.5. Using get() Without Knowing Whether Optional Has a Value

~~~java
Optional<String> result = List.<String>of().stream().findFirst();

// result.get(); // Throws NoSuchElementException.
String display = result.orElse("No data yet");
~~~

`get()` is only safe when a value is guaranteed, yet the design is usually better if the missing-data strategy is expressed directly via `orElse`, `orElseGet`, or `orElseThrow`.

### 11.6. Defaulting Without Matching Business Semantics

~~~java
double average = DoubleStream.empty()
    .average()
    .orElse(0.0);
~~~

The number `0.0` in the example is not an observation whose average equals 0; it is **a substitution rule when there are no observations**. Name and document the policy clearly. If distinguishing them is necessary, retain `OptionalDouble` until the presentation or final handling step.

### 11.7. Relying on findAny Order on a Parallel Stream

~~~java
String chosen = List.of("A", "B", "C").parallelStream()
    .findAny()
    .orElse("DEFAULT");
~~~

`orElse` only handles an empty Optional; it **does not make the result of `findAny` deterministic in order**. When the requirement is the first element, use `findFirst` on a source with an appropriate encounter order.

## 12. Understanding Two Layers of Laziness: Stream and Supplier

An important point of the pipeline lifecycle: **Stream laziness** and **fallback laziness** are two separate things.

~~~java
import java.util.List;
import java.util.Optional;

List<Integer> numbers = List.of(1, 2, 3);

Optional<Integer> match = numbers.stream()
    .filter(n -> n > 1)
    .findFirst(); // Terminal operation has already run.

int selected = match.orElseGet(() -> expensiveFallback());
~~~

In the example, `expensiveFallback()` is a function returning `int` provided by the application. `findFirst()` is a terminal operation: it has **executed enough of the pipeline** to find a result or determine that none exists. Afterward, `orElseGet` decides whether to invoke the fallback.

~~~text
Create Stream
    │
    ├─ filter/map/...        (describe lazy pipeline)
    │
    └─ findFirst()           (run terminal, return Optional)
             │
             ├─ Has value ───► orElseGet(...) ──► return present value
             │                                    do not run Supplier
             │
             └─ Empty ───────► orElseGet(...) ──► run Supplier
                                                  return fallback
~~~

`orElseGet` **does not postpone** an already-executed terminal operation. If the pipeline uses an I/O source like `Files.lines`, you still must close the Stream properly with `try-with-resources`. Likewise, the Supplier may touch a database or other resources; the Stream API does not automatically manage the lifecycle of those resources.

Additionally, a terminal operation like `findFirst` can stop early; avoid relying on side effects of `map`, `peek`, or `filter` to count every source element accurately. Whether the fallback runs is a separate matter after the terminal operation returns an Optional.

## 13. Testing: Proving the Fallback Runs Only When Missing

The following snippet is a standalone example requiring no external testing library. `AtomicInteger` is used as a **counter in the test**, not as a shared variable inside callbacks of a parallel Stream.

~~~java
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;

public class OptionalFallbackCheck {
    public static void main(String[] args) {
        AtomicInteger calls = new AtomicInteger();

        String present = Optional.of("FOUND")
            .orElseGet(() -> {
                calls.incrementAndGet();
                return "DEFAULT";
            });

        if (!present.equals("FOUND") || calls.get() != 0) {
            throw new AssertionError("Supplier must not run when a value is present");
        }

        String missing = Optional.<String>empty()
            .orElseGet(() -> {
                calls.incrementAndGet();
                return "DEFAULT";
            });

        if (!missing.equals("DEFAULT") || calls.get() != 1) {
            throw new AssertionError("Supplier must run when Optional is empty");
        }

        String eager = Optional.of("FOUND")
            .orElse(createDefault(calls));

        if (!eager.equals("FOUND") || calls.get() != 2) {
            throw new AssertionError("orElse argument must be evaluated before the call");
        }

        System.out.println("PASS");
    }

    private static String createDefault(AtomicInteger calls) {
        calls.incrementAndGet();
        return "DEFAULT";
    }
}
~~~

The test proves the exact difference in **fallback execution**, rather than only comparing final outputs. In large applications, search policies, fallbacks, and side effects should be separated into independently testable functions.

## 14. Quick Selection by Requirement

| Need | Usually suitable solution | Explanation |
| --- | --- | --- |
| Fixed default string | `orElse("UNKNOWN")` | Clear and has no significant fallback computation cost. |
| Create object only when missing | `orElseGet(MyType::new)` | Avoids creating unused objects. |
| Call external service only when missing | `orElseGet(this::loadFallback)` | Avoids redundant I/O when a result already exists. |
| Sources A and B both return Optional | `optionalA.or(this::lookupB)` | Keeps the result as an Optional for further chaining. |
| Missing data is not allowed | `orElseThrow(...)` | Expresses the constraint without hiding errors. |
| Only need to run two action branches | `ifPresentOrElse(...)` | No need to produce a return value. |
| Result from `IntStream.max` | `OptionalInt.orElse/orElseGet` | Returns `int` directly. |
| No average and average of 0 must differ | Keep `OptionalDouble` | Avoids losing business information. |
| Unsure if result source is ordered | Consider `findFirst` and an ordered source | Fallback does not change how the Stream picks elements. |

## 15. Self-Check Questions

1. **Does `Optional.of("A").orElse(expensive())` call `expensive()`?** Yes. Java arguments are evaluated before calling `orElse`.
2. **Does `Optional.of("A").orElseGet(() -> expensive())` call `expensive()`?** No. The Supplier only runs if the Optional is empty.
3. **When Optional is empty, do the two fallback approaches return different results?** If both produce the same value, the result is the same; the difference is how and when the fallback value is provided and computed.
4. **When you want a fallback already available as a constant, which should you choose?** Usually `orElse`.
5. **Is `orElseGet(() -> database.find(id))` valid when `database.find` returns `Optional<Customer>` and the current Optional has type `Optional<Customer>`?** No, because the Supplier of `orElseGet` must return `Customer`. If the fallback query returns an Optional, consider `or(...)`.
6. **Does `orElseGet` keep `findFirst()` from running until the fallback is needed?** No. `findFirst` is a terminal operation that already returned the Optional before `orElseGet` was called.
7. **Does `OptionalInt` have `orElseGet`?** Yes, it takes an `IntSupplier` and returns `int`.
8. **When a mandatory record is missing, should you create a dummy record?** Usually no. Use `orElseThrow` or an explicit error model per the business contract.
9. **Does `orElseGet(() -> null)` guarantee avoiding null?** No. The Supplier can return null; fallback design should control that.
10. **Does `findAny` on a parallel stream cause `orElse("DEFAULT")` to pick the first element?** No. `findAny` makes no guarantee to return the first element.

**Takeaway:** `orElse` is suitable when **the default value already exists or is very cheap**, whereas `orElseGet` is suitable when **the default value needs to be computed or fetched only when the Optional is empty**. The difference comes from how Java evaluates arguments versus Suppliers, not from whether the Stream runs sequentially or in parallel. Always choose a fallback matching business semantics, keep the Optional if the missing-data state matters, and use `orElseThrow` when a missing result is unacceptable.
