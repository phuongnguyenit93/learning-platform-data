# Handling Absent Results with ifPresent and orElseThrow

## 1. Why Can a Stream Result Be Absent?

In the **Java Stream API**, a pipeline describes reading data from a source, filtering with `filter`, transforming with `map`, and ending with operations such as `findFirst`, `findAny`, `min`, `max`, or `reduce`. Some terminal operations cannot guarantee always finding a value: the source may be empty, or every element may have been filtered out.

For example, finding the first paid order:

```java
import java.util.List;
import java.util.Optional;

record Order(String id, boolean paid) {}

List<Order> orders = List.of(
        new Order("O-01", false),
        new Order("O-02", true)
);

Optional<Order> found = orders.stream()
        .filter(Order::paid)
        .findFirst();

System.out.println(found); // Optional[Order[id=O-02, paid=true]]
```

If no order satisfies `Order::paid`, `findFirst()` returns **`Optional.empty()`**. It does not return a valid `Order` object and does not require manually creating a `null` value to represent absence.

`Optional<T>` is a container type that **may hold a single `T` value or no value**. In the **Optional in Stream Results** chapter, the two central operations of this lesson are:

- `ifPresent(Consumer)`: **perform an action if a value is present**; do nothing if absent.
- `orElseThrow(...)`: **retrieve the value if present**; throw an exception according to the chosen policy if absent.

These are two ways of handling results with different business meanings: an action that can be skipped when there is no data, or a requirement that data must be present to continue.

**Lesson goals:** identify which Stream results are Optionals, use `ifPresent`, `ifPresentOrElse`, and `orElseThrow` properly, distinguish them from `orElse`/`orElseGet`, handle `OptionalInt`/`OptionalLong`/`OptionalDouble`, and avoid `null` errors, side effects, or incorrect assumptions when pipelines run in parallel.

The complete examples use **Java 17+**. `Optional.ifPresent` and `Optional.orElseThrow(Supplier)` have existed since Java 8; `ifPresentOrElse` since Java 9; no-argument `Optional.orElseThrow()` since Java 10. `Stream.toList()` has existed since Java 16.

## 2. Terminal Operations That Return Optional

`Optional` appears when a result may legitimately not exist:

| Terminal operation | Return type | When is it empty? |
| --- | --- | --- |
| `findFirst()` | `Optional<T>` | Stream has no elements left. |
| `findAny()` | `Optional<T>` | Stream has no elements left. |
| `min(comparator)` | `Optional<T>` | Stream is empty. |
| `max(comparator)` | `Optional<T>` | Stream is empty. |
| `reduce(BinaryOperator<T>)` | `Optional<T>` | Stream is empty, with no identity. |
| `IntStream.min()` / `max()` | `OptionalInt` | Primitive stream is empty. |
| `LongStream.min()` / `max()` | `OptionalLong` | Primitive stream is empty. |
| `DoubleStream.average()` | `OptionalDouble` | No elements to compute the average. |

Conversely, not every terminal operation returns an Optional. For example, `count()` always returns `long` (`0` if empty); `collect(Collectors.toList())` produces a list, which may be empty; `reduce(identity, accumulator)` returns a value using `identity` as the starting point.

```java
List<Integer> values = List.of();

Optional<Integer> max = values.stream()
        .max(Integer::compareTo);
long count = values.stream().count();
int sumWithIdentity = values.stream()
        .reduce(0, Integer::sum);

System.out.println(max);             // Optional.empty
System.out.println(count);           // 0
System.out.println(sumWithIdentity); // 0
```

Each call to `values.stream()` creates a new Stream. **A Stream that has already run a terminal operation cannot be reused**; the `Optional` object itself produced after the terminal operation can be inspected or processed multiple times as needed.

## 3. ifPresent: Executing an Action Only When a Result Exists

Signature:

```java
void ifPresent(Consumer<? super T> action)
```

`ifPresent` takes a `Consumer`, i.e., a function that **accepts a value without returning a result**. If the Optional has a value, the consumer is invoked with that value; if empty, the consumer is not invoked.

```java
List<String> codes = List.of("A-01", "B-02", "A-03");

codes.stream()
        .filter(code -> code.startsWith("B-"))
        .findFirst()
        .ifPresent(code -> System.out.println("Found: " + code));

// Found: B-02
```

If you change the condition to `code.startsWith("X-")`, nothing is printed and **no exception is thrown** merely because the result is empty.

### Storing the Optional in a Variable to Clarify Intent

For logic that is not overly short, separating the search from the handling is often easier to maintain:

```java
Optional<String> firstMatching = codes.stream()
        .filter(code -> code.startsWith("A-"))
        .findFirst();

firstMatching.ifPresent(code -> {
    System.out.println("Matching code: " + code);
    // An event or notification may be recorded if business rules allow.
});
```

`ifPresent` is suitable when **not finding anything is also an acceptable state**, such as sending a notification only if a result exists, updating the UI only if a selection exists, or logging only when a record is found.

### Cannot Use ifPresent to Return a Value

Because the return type is `void`, the following code **does not compile**:

```java
// WRONG: ifPresent returns void.
// String id = firstMatching.ifPresent(System.out::println);
```

If you need to extract a value to return from a method, use `orElseThrow`, `orElse`, `orElseGet`, or keep Optional in the return type so the calling layer can decide. If you want to **transform** a present value, use `Optional.map` instead of trying to assign an outer variable from inside a consumer.

## 4. ifPresentOrElse: Handling Both Branches

`ifPresent` has no action when empty. If you must respond to both cases, from **Java 9** you can use:

```java
void ifPresentOrElse(Consumer<? super T> action, Runnable emptyAction)
```

Example:

```java
Optional<String> code = codes.stream()
        .filter(value -> value.startsWith("X-"))
        .findFirst();

code.ifPresentOrElse(
        value -> System.out.println("Found " + value),
        () -> System.out.println("Requested code not found")
);

// Requested code not found
```

The first branch is a `Consumer<String>`, receiving the found value. The second branch is a `Runnable`, taking no value; it runs only when the Optional is empty.

| Method | When a value is present | When no value is present | Returns a value? |
| --- | --- | --- | --- |
| `ifPresent(action)` | Calls `action(value)` | Does nothing | No, `void` |
| `ifPresentOrElse(action, emptyAction)` | Calls `action(value)` | Calls `emptyAction.run()` | No, `void` |
| `orElseThrow()` | Returns `value` | Throws `NoSuchElementException` | Yes, `T` |
| `orElseThrow(exceptionSupplier)` | Returns `value` | Throws exception created by supplier | Yes, `T` |

If the absent branch must **halt execution because mandatory data is missing**, `orElseThrow` expresses the intent more clearly than a consumer with side effects.

## 5. orElseThrow: Requiring Data to Be Present

There are two common forms on `Optional<T>`:

```java
T orElseThrow() // Java 10+

<X extends Throwable> T orElseThrow(
        Supplier<? extends X> exceptionSupplier) throws X
```

### 5.1. No-Argument orElseThrow()

`orElseThrow()` returns `T` if a value is present; if empty, it throws `NoSuchElementException`:

```java
List<String> names = List.of("An", "Bình", "Chi");

String firstLongName = names.stream()
        .filter(name -> name.length() >= 4)
        .findFirst()
        .orElseThrow();

System.out.println(firstLongName); // Bình
```

If you change the condition to `name.length() > 20`, no name matches and the terminal operation `findFirst` returns an empty Optional; when handling the Optional, `orElseThrow()` throws `NoSuchElementException`.

For projects needing to support Java 8 or Java 9, you can use the form with a supplier:

```java
String required = names.stream()
        .filter(name -> name.equals("Bình"))
        .findFirst()
        .orElseThrow(NoSuchElementException::new);
```

The snippet above requires `import java.util.NoSuchElementException;`.

### 5.2. orElseThrow(Supplier) With a Business-Meaningful Exception

When you need to clearly report which data is missing, provide an exception-creating function:

```java
String requestedCode = "X-01";

String foundCode = codes.stream()
        .filter(code -> code.equals(requestedCode))
        .findFirst()
        .orElseThrow(() -> new NoSuchElementException(
                "Code not found: " + requestedCode
        ));
```

The snippet above throws `NoSuchElementException` with the message `"Code not found: X-01"`. If the system has specialized exceptions such as `OrderNotFoundException` or `CustomerNotFoundException`, you can instantiate that exception type so the calling layer handles it appropriately.

**The supplier is only called when the Optional is empty.** When a value is present, the method returns the value without constructing an exception object. Therefore, you can include contextual information in the error message without paying the cost of building the exception on the success branch.

### Checked and Unchecked Exceptions

The generic signature of `orElseThrow(Supplier)` allows throwing both **checked** and **unchecked** exceptions. If the supplier creates a checked exception, the calling method must declare or catch that exception per Java rules:

```java
import java.io.FileNotFoundException;
import java.util.Optional;

static String requirePath(Optional<String> path)
        throws FileNotFoundException {
    return path.orElseThrow(
            () -> new FileNotFoundException("Missing input path")
    );
}
```

Use checked exceptions only when the business API wants to require the caller to handle them explicitly. For a missing record in an application, many systems choose a custom unchecked exception so the service or HTTP layer can decide the response.

## 6. Choosing ifPresent or orElseThrow by Business Meaning

No single method is always right for every Optional. Decide **whether absence is an error or not**:

| Situation | Suggested handling | Reason |
| --- | --- | --- |
| Look up an optional promotion code to print a notice | `ifPresent` | Without a promotion, processing can continue. |
| Display search status, even when there is no result | `ifPresentOrElse` | Both branches have display actions. |
| Read mandatory configuration before startup | `orElseThrow` | Missing configuration must fail the flow. |
| Look up an order by ID to execute a transaction | `orElseThrow(() -> ...)` | Missing order needs an exception with a clear message/type. |
| Compute average of potentially empty metrics | Handle `OptionalDouble` explicitly | Absence of samples is a valid data case to define. |
| Service API permits no record | Return `Optional<T>` | Caller has full context to choose behavior. |

Example with the same source but different business rules:

```java
Optional<String> maybeCoupon = List.of("WELCOME", "VIP").stream()
        .filter(code -> code.equals("VIP"))
        .findFirst();

// Optional code: apply if present.
maybeCoupon.ifPresent(code ->
        System.out.println("Applying promotion: " + code));

// Mandatory code: stop if missing.
String requiredCoupon = maybeCoupon.orElseThrow(
        () -> new IllegalStateException("Missing required promotion code")
);
```

Here both approaches work because the Optional has a value. However, the difference becomes immediately apparent when the `VIP` code does not exist.

## 7. How Does orElseThrow Differ From get, orElse, and orElseGet?

`Optional.get()` also retrieves the value or throws `NoSuchElementException` if empty. However, `orElseThrow()` communicates more clearly that absence is a considered state, while `orElseThrow(Supplier)` allows describing the error precisely.

Three methods are used when a value is needed:

```java
Optional<String> optional = Optional.of("primary");

String required = optional.orElseThrow();          // "primary"
String fallback = optional.orElse("default");      // "primary"
String computed = optional.orElseGet(() -> "fallback"); // "primary"
```

The primary difference is the **strategy when the Optional is empty**:

| Usage | Present | Empty |
| --- | --- | --- |
| `orElseThrow()` | Returns value | Throws `NoSuchElementException` |
| `orElseThrow(() -> new X(...))` | Returns value | Creates and throws exception `X` |
| `orElse(fallback)` | Returns value | Returns `fallback` |
| `orElseGet(supplier)` | Returns value | Calls supplier to create fallback value |

### Difference in When the Fallback Value Is Created

The argument to `orElse(...)` is a normal Java expression, so it **is evaluated immediately when the method is called**, even if the Optional already has a value:

```java
static String slowFallback() {
    System.out.println("Creating fallback value");
    return "fallback";
}

// Example within the same class:
Optional<String> present = Optional.of("ready");

String a = present.orElse(slowFallback());
// Prints "Creating fallback value" even though a is still "ready".

String b = present.orElseGet(() -> slowFallback());
// Does not call slowFallback() when Optional has a value.

String c = present.orElseThrow(
        () -> new IllegalStateException("No data"));
// Does not create an exception on the present branch.
```

Because `orElseGet` and `orElseThrow(Supplier)` use a supplier, the fallback computation or exception creation runs **on demand**. Do not choose `orElseThrow` when business rules allow a default value; conversely, do not assign a default value to mask missing mandatory data.

## 8. Combining filter, map, and Optional Before Handling the Result

`Optional` has its own `filter` and `map` to continue checking or transforming **a single potentially absent value**, not to restart the Stream:

```java
record Customer(String id, String email, boolean active) {}

List<Customer> customers = List.of(
        new Customer("C-01", "an@example.com", false),
        new Customer("C-02", " binh@example.com ", true),
        new Customer("C-03", "chi@example.com", true)
);

String email = customers.stream()
        .filter(Customer::active)
        .findFirst()                    // Optional<Customer>
        .map(Customer::email)           // Optional<String>
        .map(String::strip)
        .filter(value -> !value.isEmpty())
        .orElseThrow(() -> new IllegalStateException(
                "No valid email for an active customer"
        ));

System.out.println(email); // binh@example.com
```

Step-by-step explanation:

1. `filter(Customer::active)` filters the customer Stream.
2. `findFirst()` is a terminal operation and returns `Optional<Customer>`.
3. `Optional.map(Customer::email)` runs only if a customer is found; it produces `Optional<String>`.
4. `Optional.map(String::strip)` normalizes the email; `Optional.filter` removes empty strings.
5. `orElseThrow` throws an error only if any stage leads to an empty Optional.

One point to understand: when the mapper of **`Optional.map`** returns `null`, the result is `Optional.empty()`. Conversely, **`Stream.map`** can produce `null` elements; terminal operations `findFirst` or `findAny` can throw `NullPointerException` if the selected element is `null`.

If the Stream source data can contain `null`, specify how to handle it before searching:

```java
import java.util.Arrays;
import java.util.Objects;

List<String> rawNames = Arrays.asList(null, " An ", "Bình");

Optional<String> firstValid = rawNames.stream()
        .filter(Objects::nonNull)
        .map(String::strip)
        .filter(name -> !name.isBlank())
        .findFirst();

firstValid.ifPresent(System.out::println); // An
```

`Optional.of(null)` throws `NullPointerException`. `Optional.ofNullable(null)` creates `Optional.empty()`, but **do not re-wrap a result that already has type `Optional<T>` with `ofNullable`**.

## 9. OptionalInt, OptionalLong, and OptionalDouble

Primitive streams use specialized Optional forms so primitive numbers do not have to be boxed into `Integer`, `Long`, or `Double`:

```java
import java.util.OptionalInt;
import java.util.OptionalLong;
import java.util.OptionalDouble;
import java.util.stream.IntStream;
import java.util.stream.LongStream;
import java.util.stream.DoubleStream;

OptionalInt smallest = IntStream.of(7, 3, 9).min();
OptionalLong largest = LongStream.of(2L, 8L, 5L).max();
OptionalDouble average = DoubleStream.of(2.0, 4.0, 6.0).average();

smallest.ifPresent(value -> System.out.println("Smallest: " + value));
largest.ifPresent(value -> System.out.println("Largest: " + value));
average.ifPresent(value -> System.out.println("Average: " + value));

int minRequired = smallest.orElseThrow();        // 3
long maxRequired = largest.orElseThrow();        // 8
double averageRequired = average.orElseThrow();  // 4.0
```

For `OptionalInt`, `OptionalLong`, and `OptionalDouble`, `ifPresent` accepts `IntConsumer`, `LongConsumer`, and `DoubleConsumer`, respectively. The **no-argument** `orElseThrow()` forms exist since Java 10 and throw `NoSuchElementException` when empty.

They **do not have the `orElseThrow(exceptionSupplier)` overload** like `Optional<T>`. If you need a specialized exception from a primitive result, you can convert to an object Optional or handle the empty state in a business-meaningful API.

Example when wanting to throw a contextual error:

```java
OptionalInt quantity = IntStream.empty().max();

int requiredQuantity = quantity.stream()
        .boxed()
        .findFirst()
        .orElseThrow(() -> new IllegalStateException(
                "No quantity to select"
        ));
```

The illustration converts via `OptionalInt.stream()` (Java 9), `boxed()`, and then `Optional<Integer>` to use the overload with a supplier; this approach incurs a small boxing cost. When a special exception type is not needed, calling `quantity.orElseThrow()` directly is simpler.

### Case With No Numbers

```java
OptionalDouble noAverage = IntStream.empty().average();

noAverage.ifPresentOrElse(
        value -> System.out.println("Average: " + value),
        () -> System.out.println("No samples to compute average")
);

// No samples to compute average
```

`OptionalInt`, `OptionalLong`, and `OptionalDouble` also have `ifPresentOrElse` from Java 9. Choose a response matching business logic: a nonexistent average differs from an average equal to `0`.

## 10. findFirst, findAny, Order, and Parallel Processing

Whether a value is present or absent is one aspect; **which value is selected** is another aspect.

```java
List<Integer> numbers = List.of(2, 4, 6, 8);

Optional<Integer> first = numbers.stream()
        .filter(n -> n > 3)
        .findFirst(); // Optional[4]

Optional<Integer> any = numbers.parallelStream()
        .filter(n -> n > 3)
        .findAny();  // Could be 4, 6, or 8.
```

With a Stream that has an encounter order such as `List.stream()`, `findFirst` finds the first element in that order. `findAny` is allowed to pick any element; especially when running in parallel, **never rely on a fixed element**.

`orElseThrow` only decides what happens **when the Optional is empty**; it does not change the selection rule of `findAny`. If business logic requires prioritizing by date, largest value, or smallest ID, define the appropriate order or comparator first:

```java
int smallestGreaterThanThree = numbers.stream()
        .filter(n -> n > 3)
        .min(Integer::compareTo)
        .orElseThrow(); // 4
```

`ifPresent` is invoked **after the terminal operation returns an Optional**; the consumer on Optional itself is not a per-element parallel Stream operation. Do not place source mutations or logic relying on lambda invocation order directly inside `filter`/`map` of a parallel pipeline.

## 11. Complete Example: Finding Payments and Responding Per Business Logic

A payment management service has two needs:

- **Optional:** if a customer has a completed payment, print a notification about a found payment.
- **Mandatory:** when processing a specific payment lookup request, a matching payment must exist; if missing, throw a contextual error.

Java 17+ example:

```java
import java.util.List;
import java.util.NoSuchElementException;
import java.util.Optional;
import java.util.Comparator;

public class OptionalStreamResultDemo {
    record Payment(String id, String customerId, long cents, boolean successful) {}

    static Optional<Payment> findAnySuccessfulForCustomer(
            List<Payment> payments, String customerId) {
        return payments.stream()
                .filter(Payment::successful)
                .filter(payment -> payment.customerId().equals(customerId))
                .findFirst();
    }

    static Payment requireSuccessfulPayment(
            List<Payment> payments, String paymentId) {
        return payments.stream()
                .filter(payment -> payment.id().equals(paymentId))
                .filter(Payment::successful)
                .findFirst()
                .orElseThrow(() -> new NoSuchElementException(
                        "Successful payment not found: " + paymentId
                ));
    }

    public static void main(String[] args) {
        List<Payment> payments = List.of(
                new Payment("P01", "C01", 120_000L, true),
                new Payment("P02", "C02", 75_000L, false),
                new Payment("P03", "C01", 50_000L, true)
        );

        // Optional: if no result, skip the notification.
        findAnySuccessfulForCustomer(payments, "C01")
                .ifPresent(payment -> System.out.println(
                        "Payment found: " + payment.id()
                ));
        // Payment found: P01

        // Two-branch display when needing to handle absence as well.
        findAnySuccessfulForCustomer(payments, "C03")
                .ifPresentOrElse(
                        payment -> System.out.println(payment.id()),
                        () -> System.out.println("Customer C03 has no payments yet")
                );
        // Customer C03 has no payments yet

        // Mandatory: returns Payment or throws NoSuchElementException.
        Payment required = requireSuccessfulPayment(payments, "P03");
        System.out.println("Amount: " + required.cents()); // 50000

        // Another potentially empty result: successful payment with the largest amount.
        payments.stream()
                .filter(Payment::successful)
                .max(Comparator.comparingLong(Payment::cents))
                .ifPresent(payment -> System.out.println(
                        "Highest payment: " + payment.id()
                ));
        // Highest payment: P01
    }
}
```

Here, `findAnySuccessfulForCustomer` is a business method name illustrating payment existence: **internally it uses `findFirst`**, so if you want the name to reflect the exact algorithm, you can rename it to `findFirstSuccessfulForCustomer`. The important part is the contract returning `Optional<Payment>` so the caller decides whether absence is acceptable.

Observations:

1. `findFirst` on an ordered list picks the first matching payment, though it is not automatically **the newest** unless the list is sorted by time.
2. `ifPresent` only serves side actions when a result exists; when customer `C03` has no payments yet, the separate display action is placed in `ifPresentOrElse`.
3. `requireSuccessfulPayment` uses `orElseThrow` and a message containing the payment ID, so the caller can handle the exception more accurately.
4. `max` returns an Optional because after `filter` there may be no successful payments left.
5. The pipelines only read `payments`, without adding/removing elements while traversing. If the data is updated concurrently, an appropriate synchronization or snapshot mechanism is needed per business rules.

In a real application, do not treat looking up by `id` as guaranteeing access authorization; the service layer still must enforce permission checks and payment status rules according to system design.

## 12. Common Errors and How to Fix Them

| Error or symptom | Cause | How to handle it |
| --- | --- | --- |
| Calling `get()` and getting `NoSuchElementException` | Did not check whether Optional has a value. | Use `ifPresent` when optional, `orElseThrow` when mandatory. |
| Trying to assign a variable from `ifPresent` and failing to compile | `ifPresent` returns `void`. | Use `map`, `orElseThrow`, or return Optional. |
| No message printed when data is absent | `ifPresent` only handles the present branch. | Use `ifPresentOrElse` if both branches are needed. |
| Exception branch executes even when data is present | Constructed the exception beforehand causing side effects in another expression. | Put exception creation inside the supplier of `orElseThrow`. |
| `orElse(expensiveMethod())` calls the method despite having a value | Argument is evaluated before calling `orElse`. | Use `orElseGet` for lazily computed fallback values. |
| `findFirst` or `findAny` throws `NullPointerException` | Stream has a `null` element that gets selected. | Handle `null` before the terminal operation, such as `filter(Objects::nonNull)`. |
| `findAny` returns different elements | Does not guarantee choosing a fixed element, especially in parallel. | Use `findFirst` or `min`/`max` per business rules. |
| Calling `orElseThrow(Supplier)` on `OptionalInt` does not compile | Primitive Optionals do not have an overload taking a supplier. | Use `orElseThrow()` or handle specialized errors via an object Optional. |
| Misinterpreting an absent average as `0` | `average()` can return `OptionalDouble.empty()`. | Distinguish no samples yet from an actual result equal to 0. |
| Reusing a Stream after `findFirst` | The Stream has terminated and been consumed. | Create a new Stream from the source or process the obtained Optional result. |

## 13. Practice Exercise

Given a list of student scores:

```java
record Student(String code, int score, boolean active) {}

List<Student> students = List.of(
        new Student("SV01", 8, true),
        new Student("SV02", 4, false),
        new Student("SV03", 9, true)
);
```

Requirements:

1. Find the first active student, and use `ifPresent` to print the student's code if found.
2. Find the student with code `"SV99"`, and use `ifPresentOrElse` to print one of two messages.
3. Write a method `requireStudent` taking the list and student code, returning the student or throwing `NoSuchElementException` with a message containing the code.
4. Find the highest score of active students using a primitive stream; use `ifPresent` to print the result and `orElseThrow()` when the problem requires a score.
5. Try replacing `students` with an empty list and explain the behavior in each case.

**Reference solution:**

```java
students.stream()
        .filter(Student::active)
        .findFirst()
        .ifPresent(student -> System.out.println(student.code()));
// SV01

students.stream()
        .filter(student -> student.code().equals("SV99"))
        .findFirst()
        .ifPresentOrElse(
                student -> System.out.println("Found: " + student.code()),
                () -> System.out.println("SV99 not found")
        );
// SV99 not found

static Student requireStudent(List<Student> source, String code) {
    return source.stream()
            .filter(student -> student.code().equals(code))
            .findFirst()
            .orElseThrow(() -> new NoSuchElementException(
                    "Student not found: " + code
            ));
}

OptionalInt maxScore = students.stream()
        .filter(Student::active)
        .mapToInt(Student::score)
        .max();

maxScore.ifPresent(score -> System.out.println("Highest score: " + score));
int requiredMax = maxScore.orElseThrow(); // 9
```

The solution requires the corresponding `import` statements from `java.util` and `java.util.stream`; the `requireStudent` method is placed at class level, not declared inside `main`. With an empty list, the two `ifPresent` snippets take no action, `ifPresentOrElse` runs the absent branch, and both forms of `orElseThrow` throw an exception if invoked.

**Self-extension:** If the API distinguishes both "student not found" and "student has been deactivated", should you filter by status before `findFirst` or search by code first and then check status? The two approaches produce different error messages; choose based on the business contract, not merely on pipeline brevity.

## Takeaways

When a Stream terminal operation may fail to find an element, the result is typically `Optional<T>` or one of `OptionalInt`, `OptionalLong`, `OptionalDouble`. `ifPresent` fits **an optional action when a value exists**; `ifPresentOrElse` fits when you must respond on absence as well; `orElseThrow` fits when **a value is mandatory to proceed**. The supplier of `orElseThrow` constructs the exception only on the empty branch. Maintain the distinction between "no data" and "a value equal to 0", be careful with `null` and encounter order, and design exceptions according to business meaning rather than treating every empty result as an error by default.
