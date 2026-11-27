# Lazy Evaluation, Single-Use, and Side Effects in Stream Pipelines — Java 17

The Java Stream API processes data through a chain of operations such as filtering, transforming, sorting, limiting, and aggregating. When reading a pipeline, you may see several chained calls:

```java
List<String> result = names.stream()
        .filter(name -> name.length() >= 3)
        .map(String::toUpperCase)
        .sorted()
        .toList();
```

However, operations in a pipeline do not necessarily run immediately when called. Most **intermediate operations** are lazily evaluated: they only describe the work to be done. Data traversal usually begins when a **terminal operation** such as `toList()`, `collect()`, `forEach()`, or `count()` is invoked.

A Stream is also designed for **single-use**. Once a terminal operation has executed or the stream is closed, that stream cannot be reused for another pipeline. Finally, functions passed into a pipeline should minimize side effects so results stay predictable, especially when running in parallel.

This lesson focuses on three properties essential to working with Collections and Streams in Java 17:

1. **Lazy evaluation:** when operations actually execute.
2. **Single-use:** why a stream cannot be traversed again.
3. **Side effects in pipelines:** why transformations and reductions should be preferred over mutating external state inside lambdas.

## 1. What Are the Parts of a Stream Pipeline?

A typical Stream pipeline consists of three parts:

- **Data source:** Collection, array, generator, or another data source.
- **Intermediate operations:** construct a new pipeline by describing operations such as `filter`, `map`, `sorted`, `distinct`, `limit`.
- **Terminal operation:** triggers execution and produces a result, a final side effect, or an aggregated value.

Example:

```java
List<String> names = List.of("An", "Binh", "Chi", "Dung");

List<String> result = names.stream()       // Source
        .filter(name -> name.length() > 2) // Intermediate
        .map(String::toUpperCase)          // Intermediate
        .toList();                         // Terminal

System.out.println(result);
```

Output:

```text
[BINH, DUNG]
```

You can visualize it as:

```text
Collection / Array
       |
       v
   stream()
       |
       v
 filter(predicate)      Intermediate operation
       |
       v
 map(function)          Intermediate operation
       |
       v
 toList()               Terminal operation
       |
       v
 Result is produced
```

Calling `filter` and `map` returns another Stream, allowing operations to be chained. They do not allocate a new intermediate Collection after each step. Only the terminal operation drives the stream to process data and produce the result.

## 2. What Is Lazy Evaluation?

**Lazy evaluation** means an intermediate operation does not perform its full work at the moment it is called. Instead, the Stream records the operation to perform and waits for the terminal operation to trigger the pipeline.

Example:

```java
import java.util.List;
import java.util.stream.Stream;

public class LazyDemo {
    public static void main(String[] args) {
        List<String> names = List.of("An", "Binh", "Chi");

        Stream<String> pipeline = names.stream()
                .filter(name -> {
                    System.out.println("filter: " + name);
                    return name.length() > 2;
                })
                .map(name -> {
                    System.out.println("map: " + name);
                    return name.toUpperCase();
                });

        System.out.println("Pipeline created");

        List<String> result = pipeline.toList();

        System.out.println("Result: " + result);
    }
}
```

Output in execution order:

```text
Pipeline created
filter: An
filter: Binh
map: Binh
filter: Chi
map: Chi
Result: [BINH, CHI]
```

When calling `stream()`, `filter()`, and `map()`, the program merely constructs the pipeline. The lambdas inside have not run yet. Once `toList()` is called, the stream starts traversing the source and executing the required steps.

Notice the log order: in a pipeline without global sorting requirements, operations can execute element-by-element: check one element, if it passes then transform it immediately, and move on to the next element. Do not assume a Stream runs all of `filter` across every element before running `map` across them.

## 3. Intermediate Operations and Terminal Operations

Distinguishing these two groups helps clarify when a pipeline actually executes.

### 3.1. Intermediate Operations

An intermediate operation accepts a Stream and returns another Stream. They are generally lazy.

Common operations:

| Operation | Role | Is it lazy? |
| --- | --- | --- |
| `filter(predicate)` | Keeps elements matching the condition. | Yes |
| `map(function)` | Transforms each element. | Yes |
| `flatMap(function)` | Turns each element into a child stream and flattens them. | Yes |
| `distinct()` | Removes duplicate elements per `equals()`. | Yes |
| `sorted()` | Sorts the elements. | Yes; requires processing data to determine order |
| `limit(n)` | Limits the number of output elements. | Yes, a short-circuiting intermediate operation |
| `skip(n)` | Skips a leading number of elements. | Yes |
| `peek(action)` | Performs an action as elements pass through the pipeline. | Yes; should not hold business logic with side effects |

An intermediate operation does not trigger the pipeline merely by being invoked. You can chain multiple steps before deciding to obtain the result.

### 3.2. Terminal Operations

A terminal operation ends the current pipeline and triggers processing.

| Operation | Result |
| --- | --- |
| `toList()` | Unmodifiable result list (Java 16+). |
| `collect(collector)` | Collects results via a Collector, e.g. `Collectors.toList()`. |
| `forEach(action)` | Performs an action on each element. |
| `forEachOrdered(action)` | Performs an action in encounter order if the source is ordered. |
| `count()` | Counts the number of elements. |
| `min(comparator)` / `max(comparator)` | Finds the minimum/maximum element. |
| `reduce(...)` | Combines elements into a single result. |
| `anyMatch(predicate)` | Checks whether at least one element matches. |
| `allMatch(predicate)` | Checks whether every element matches. |
| `noneMatch(predicate)` | Checks whether no element matches. |
| `findFirst()` / `findAny()` | Finds a single element. |

After a terminal operation, the stream has been consumed and cannot be used to build another pipeline.

### 3.3. Example Identifying the Trigger Point

```java
Stream<Integer> stream = List.of(1, 2, 3, 4).stream()
        .filter(number -> number % 2 == 0)
        .map(number -> number * 10);

// Up to here, the pipeline is only described.
// No terminal operation yet, so no elements have been traversed.

long count = stream.count(); // Terminal: triggers the pipeline.

System.out.println(count); // 2
```

No result list is produced by calling `filter` or `map` alone. Only when `count()` is called does the pipeline execute to determine the result.

## 4. Lazy Does Not Mean Every Operation Processes Elements One by One in the Same Way

Some operations can stream elements incrementally, while others need broader knowledge of the data.

- `filter` and `map` can usually process each element as it flows through the pipeline.
- `limit` can stop requesting new elements once enough have been received.
- `sorted` must determine the relative order of relevant elements before emitting results in sorted order.
- `distinct` must track previously seen values to eliminate duplicates.

Example:

```java
List<Integer> result = List.of(8, 2, 5, 1, 4).stream()
        .filter(number -> number % 2 == 0)
        .sorted()
        .limit(2)
        .toList();

System.out.println(result);
```

Output:

```text
[2, 4]
```

The pipeline outputs at most two elements after sorting. However, to know the two smallest even numbers, `sorted()` must examine enough input elements to determine ordering. Do not assume `limit(2)` always causes the Stream to read only two source elements.

**Lazy evaluation does not mean every pipeline can stop early.** Early termination depends on the operation types, pipeline order, and terminal operation.

## 5. Short-Circuiting: Stopping Once Enough Information Is Known

Some operations can stop traversal early once the result is determined.

### 5.1. Short-Circuiting Terminal Operations

The following terminal operations can short-circuit:

- `anyMatch`: stops upon finding a matching element.
- `allMatch`: stops upon finding a non-matching element.
- `noneMatch`: stops upon finding a matching element.
- `findFirst` and `findAny`: stop once an eligible element is found.

Example:

```java
import java.util.List;

public class ShortCircuitDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(1, 3, 4, 7, 9);

        boolean found = numbers.stream()
                .filter(number -> {
                    System.out.println("Checking: " + number);
                    return number % 2 == 0;
                })
                .anyMatch(number -> number > 2);

        System.out.println("Found: " + found);
    }
}
```

Output:

```text
Checking: 1
Checking: 3
Checking: 4
Found: true
```

Once the number 4 satisfies both the filter predicate and `anyMatch`, the terminal operation already knows the result is `true`. Elements 7 and 9 do not need to be processed.

### 5.2. Short-Circuiting Intermediate Operations

`limit(n)` is a short-circuiting intermediate operation: it caps the number of elements forwarded down the rest of the pipeline.

```java
List<Integer> firstThree = Stream.iterate(1, number -> number + 1)
        .filter(number -> number % 2 == 1)
        .limit(3)
        .toList();

System.out.println(firstThree);
```

Output:

```text
[1, 3, 5]
```

`Stream.iterate` creates an infinite source. The pipeline still completes because `limit(3)` lets only three elements pass through and `toList()` collects that finite count.

If you omit `limit(3)` and call `toList()` on an infinite stream, the operation will not terminate normally and may keep consuming resources.

## 6. A Stream Can Only Be Used Once

A Stream is not a Collection. It is a pipeline for processing data from a source.

Example:

```java
List<String> names = List.of("An", "Binh", "Chi");

Stream<String> stream = names.stream();

long count = stream.count();

// Cannot reuse a consumed stream:
List<String> result = stream.toList(); // Wrong
```

After `count()` is called, the stream has been consumed. Calling `toList()` afterward on the same stream is invalid. Reusing a consumed stream can lead to `IllegalStateException`; do not rely on every implementation detecting and reporting the error identically.

### Proper Way: Create a New Stream from the Source

If you need to perform two independent processing passes, call `stream()` again on the Collection:

```java
List<String> names = List.of("An", "Binh", "Chi");

long count = names.stream().count();

List<String> upperNames = names.stream()
        .map(String::toUpperCase)
        .toList();

System.out.println(count);
System.out.println(upperNames);
```

Output:

```text
3
[AN, BINH, CHI]
```

A Collection can still create multiple independent streams. Each new stream is a separate pipeline that can be consumed once.

### If You Need the Result Multiple Times, Store the Result Instead of the Stream

Example:

```java
List<String> names = List.of("An", "Binh", "Chi");

List<String> normalized = names.stream()
        .map(String::toUpperCase)
        .toList();

long count = normalized.size();
boolean hasAn = normalized.contains("AN");

System.out.println(count);
System.out.println(hasAn);
```

The collected result is a Collection that can be read multiple times. In this Java 17 example, `Stream.toList()` returns an unmodifiable list; if a modifiable list is needed, use `collect(Collectors.toCollection(ArrayList::new))` or an appropriate Collector.

## 7. Not Every Stream Source Can Be Recreated

Collections can usually have `stream()` called multiple times. However, some sources are designed for single consumption or tied to external resources.

For example, `Files.lines(path)` returns a Stream reading lines of a file and must be closed after use. Do not keep that stream around and try to reuse it.

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public class FileLinesDemo {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("notes.txt");

        try (var lines = Files.lines(path)) {
            List<String> nonBlank = lines
                    .filter(line -> !line.isBlank())
                    .toList();

            System.out.println(nonBlank);
        }
    }
}
```

Try-with-resources closes the stream and the underlying file resource upon completion.

If you need to process the file multiple times, open a new stream for each pass:

```java
long lineCount;

try (var lines = Files.lines(path)) {
    lineCount = lines.count();
}

List<String> matchingLines;

try (var lines = Files.lines(path)) {
    matchingLines = lines
            .filter(line -> line.contains("Java"))
            .toList();
}
```

Each call to `Files.lines(path)` creates a new stream. Do not reuse a closed or consumed stream.

## 8. What Is a Side Effect in a Lambda?

A function has a **side effect** when, beyond computing and returning a result, it alters external state or performs another observable action.

Examples of side effects:

- Modifying a variable outside the lambda.
- Adding/removing elements in another Collection.
- Writing to a file or database.
- Sending a network request.
- Writing logs or printing to the console.
- Mutating a shared mutable object.

A Stream can invoke lambdas to process each element, but embedding too many side effects inside `map` or `filter` makes pipelines hard to follow and error-prone.

### Anti-Pattern: Modifying an External Variable Inside map

```java
List<String> names = List.of("An", "Binh", "Chi");
List<String> result = new ArrayList<>();

names.stream()
        .map(name -> {
            result.add(name.toUpperCase());
            return name;
        })
        .toList();
```

Here `map` is used to append data to an external list, while the return value of `map` serves no purpose toward that goal. The pipeline can be written directly:

```java
List<String> result = names.stream()
        .map(String::toUpperCase)
        .toList();
```

A pure transformation takes a value and returns a new value without mutating external state.

### Anti-Pattern: Modifying the Source Collection While the Stream Is Traversing It

```java
List<String> names = new ArrayList<>(
        List.of("An", "Binh", "Chi")
);

names.stream()
        .filter(name -> {
            if (name.isBlank()) {
                names.remove(name); // Do not mutate the source being traversed.
            }
            return !name.isBlank();
        })
        .toList();
```

Modifying the source's structure while a pipeline is traversing it can cause `ConcurrentModificationException` or undefined behavior depending on the source/stream contract. Streams require behavioral parameters to be non-interfering with the source during processing.

If you want a new list containing only valid elements, use `filter` and collect the result:

```java
List<String> nonBlank = names.stream()
        .filter(name -> !name.isBlank())
        .toList();
```

If the real goal is removing elements from the Collection in place, use Collection APIs such as `removeIf` with an appropriate predicate, or make a copy before mutating. Do not mutate a source while its own stream is active.

## 9. Behavioral Parameters Should Be Stateless and Non-Interfering

The Stream API specifies two key requirements for functions passed into a pipeline:

- **Non-interfering:** the function does not modify the stream's data source while the pipeline is running.
- **Stateless:** the function's result does not depend on state that may change while processing other elements.

Example of a pure function:

```java
int length = "Java".length();

List<Integer> lengths = List.of("Java", "Stream", "API")
        .stream()
        .map(String::length)
        .toList();
```

Each element is processed independently. The result does not depend on which element ran earlier.

Example of a function depending on external state:

```java
int[] counter = {0};

List<Integer> indexes = List.of("A", "B", "C")
        .stream()
        .map(value -> counter[0]++)
        .toList();
```

In a sequential stream, this snippet might yield an ascending sequence as expected. However, the lambda's result depends on mutable state outside the pipeline. When switched to a parallel stream, execution order and shared state access may no longer match the original assumption.

A more controllable pipeline uses transformations whose output depends directly on input data, or aggregation operations designed for Streams.

## 10. Why Are Side Effects More Dangerous in Parallel Streams?

You can switch a sequential stream to parallel using `parallelStream()` or `parallel()`. When running in parallel, multiple elements can be processed across multiple threads.

If lambdas concurrently mutate a shared variable or mutable Collection, the program can suffer race conditions, lost updates, or nondeterministic results.

**Wrong — using a shared ArrayList in a parallel stream:**

```java
List<Integer> numbers = List.of(1, 2, 3, 4, 5);

List<Integer> results = new ArrayList<>();

numbers.parallelStream()
        .forEach(number -> results.add(number * 2));
```

`ArrayList` is not thread-safe. Multiple threads adding elements simultaneously can corrupt internal state or yield wrong results.

**Right — use collect so the Stream manages aggregation:**

```java
List<Integer> results = numbers.parallelStream()
        .map(number -> number * 2)
        .toList();
```

Here `map` transforms each element, and the terminal operation gathers results through the Stream's mechanism. There is no need to share a mutable list manually across threads.

If a Collector with a mutable result is needed:

```java
List<Integer> results = numbers.parallelStream()
        .map(number -> number * 2)
        .collect(Collectors.toList());
```

Collectors are designed to combine partial results from processing. Do not manually replace them with a shared external Collection.

## 11. Use reduce or collect Instead of External Counter Variables

When aggregation is needed, pick an operation that expresses the exact intent.

### Counting Elements

**Avoid:**

```java
int[] count = {0};

names.stream()
        .filter(name -> !name.isBlank())
        .forEach(name -> count[0]++);
```

**Prefer:**

```java
long count = names.stream()
        .filter(name -> !name.isBlank())
        .count();
```

### Summing

**Avoid:**

```java
int[] total = {0};

numbers.stream()
        .forEach(number -> total[0] += number);
```

**Prefer:**

```java
int total = numbers.stream()
        .mapToInt(Integer::intValue)
        .sum();
```

Or use `reduce`:

```java
int total = numbers.stream()
        .reduce(0, Integer::sum);
```

For integer addition, both give the same result within the non-overflow range. `mapToInt().sum()` clearly expresses numeric summation; `reduce` is useful for more general combinations.

### Grouping Data

Instead of mutating an external `Map` inside `forEach`, use a Collector:

```java
Map<Integer, List<String>> namesByLength = names.stream()
        .collect(Collectors.groupingBy(String::length));
```

The Collector describes the desired result and grouping logic. This style is generally safer when switching execution strategies between sequential and parallel.

## 12. Is `forEach` Always a Bad Side Effect?

No. `forEach` is a terminal operation designed to perform an action for each element. Side effects can be the primary goal of a pipeline, such as sending notifications or writing output rows.

However, distinguish between:

- Using `forEach` as an intentional **endpoint to perform an action**.
- Using `map` or `filter` to sneakily mutate external state when their return values are meaningless.

Example of a terminal action:

```java
names.stream()
        .filter(name -> !name.isBlank())
        .forEach(System.out::println);
```

The pipeline filters data and prints each result. This is valid usage when the goal is outputting data.

If encounter order is required, use `forEachOrdered`:

```java
names.parallelStream()
        .filter(name -> !name.isBlank())
        .forEachOrdered(System.out::println);
```

`forEachOrdered` guarantees the action runs in the encounter order of an ordered source. That does not mean all preceding steps run sequentially; elements may still be processed in parallel before the action is ordered.

If the action writes to files, makes network calls, or updates a database, consider error handling, transactions, rate limiting, and idempotency. Streams do not automatically make external side effects atomic.

## 13. Do Not Rely on `peek` for Business Logic

`peek` is primarily designed for observing elements flowing through a pipeline, commonly for debugging:

```java
List<String> result = names.stream()
        .filter(name -> !name.isBlank())
        .peek(name -> System.out.println("After filter: " + name))
        .map(String::toUpperCase)
        .toList();
```

When the pipeline actually traverses elements, the `peek` action may be called for those elements. However, do not use `peek` for mandatory business logic such as sending emails, writing to a database, or updating state.

One key reason: a Stream implementation may optimize a pipeline and elide executing certain behavioral parameters if doing so cannot affect the terminal operation's result. For example, given a source of known size and a pipeline containing only size-preserving operations, `count()` may read the size directly without traversing elements; in that case, the `peek` action may never execute.

Example you must not rely on for guaranteed logging:

```java
long count = List.of("A", "B", "C").stream()
        .peek(System.out::println)
        .count();
```

`count` is still 3, but do not rely on three lines being printed. Implementations are allowed to compute the count from the source without executing `peek` when skipping it does not alter the pipeline's result.

If you need logs for debugging observation, `peek` can be used as long as you accept it is not a guaranteed business execution point. If an action must run for every element, place it in an appropriate terminal operation or an explicit processing step.

## 14. Side Effects and Execution Order

Do not assume lambdas are called in the order you read the code, or exactly once per element in every pipeline.

With sequential streams, the encounter order of an ordered source is generally preserved in operations specified as order-preserving. However:

- Operations can be optimized.
- Short-circuiting can leave some elements unprocessed.
- Some operations can alter order, such as `unordered()`.
- Parallel streams can process elements on multiple threads and in different orders.
- Side effects inside lambdas are not guaranteed to execute once per element if the pipeline/terminal operation does not require it.

Example with `findAny()`:

```java
Optional<Integer> found = numbers.parallelStream()
        .filter(number -> number > 10)
        .findAny();
```

`findAny()` may return any element matching the condition. Do not write side effects in `filter` assuming a specific element will always be evaluated first.

If you need the first element in encounter order, use `findFirst()` on an ordered source:

```java
Optional<Integer> first = numbers.stream()
        .filter(number -> number > 10)
        .findFirst();
```

If order matters when performing an action, use an appropriate terminal operation such as `forEachOrdered`. Do not treat log order from one run as an ordering guarantee across all execution modes.

## 15. Stream Pipelines Should Not Interfere with Their Source

A pipeline should read a stable source while running. Adding or removing elements from the source inside a behavioral parameter violates the non-interference principle.

**Wrong:**

```java
List<Integer> values = new ArrayList<>(List.of(1, 2, 3, 4));

values.stream()
        .filter(value -> {
            if (value % 2 == 0) {
                values.remove(value);
            }
            return true;
        })
        .toList();
```

**Right — produce a new result:**

```java
List<Integer> oddValues = values.stream()
        .filter(value -> value % 2 != 0)
        .toList();
```

**Right — if the goal is removing directly from the Collection, use the Collection API:**

```java
values.removeIf(value -> value % 2 == 0);
```

`removeIf` removes matching elements on the Collection according to the predicate. Once source mutations are done, you can create a new stream for further processing.

## 16. Mutable Data Sources and Data Binding Timing

Streams from Collections usually reflect the source's data when the terminal operation begins, provided the source is not interfered with while the pipeline runs. Therefore, if you build a pipeline and mutate the Collection before invoking the terminal operation, the observed data may differ from when the pipeline was created.

Example:

```java
List<String> names = new ArrayList<>(List.of("An", "Binh"));

Stream<String> stream = names.stream()
        .map(String::toUpperCase);

// Modification happens before the terminal operation starts.
names.add("Chi");

List<String> result = stream.toList();

System.out.println(result);
```

For standard Collections like `ArrayList`, the created stream is late-binding: it binds to the source when the terminal operation begins. The example can include the element added before pipeline execution started.

Still, do not turn this behavior into a pattern of mutating the source during processing. Once a terminal operation is traversing the source, do not structurally interfere with that Collection. If a stable snapshot is needed, take a copy before constructing the pipeline:

```java
List<String> snapshot = List.copyOf(names);

List<String> result = snapshot.stream()
        .map(String::toUpperCase)
        .toList();
```

`List.copyOf` creates an unmodifiable list that disallows null elements. This is useful when you need a snapshot of element references; if the elements themselves are mutable objects, this copy is not a deep copy.

## 17. Separating Computation Logic from External Actions

A clean organizational pattern is splitting into two steps:

1. Use a Stream to filter, transform, and produce result data.
2. Use that result to perform intentional side effects.

For example, building a list of valid emails and then sending them:

```java
List<String> recipients = users.stream()
        .filter(User::isActive)
        .map(User::email)
        .filter(email -> email != null && !email.isBlank())
        .distinct()
        .toList();

for (String recipient : recipients) {
    mailService.sendWelcomeMessage(recipient);
}
```

The Stream produces the required data. The loop performs the email-sending action, making it easy to place retries, error logging, rate limiting, or per-recipient failure handling.

You do not always need two steps. But when side effects are critical, can fail, or require clear ordering/transactions, separating computation from action makes code easier to control.

## 18. Style Comparison Table

| Goal | Error-prone approach | Preferred approach |
| --- | --- | --- |
| Transform data | Mutate an external Collection inside `map`. | Return the new value from `map`. |
| Filter data | Remove source elements inside `filter`. | Use `filter` to build a new result, or `removeIf` before/after the pipeline. |
| Count | Increment an external counter inside `forEach`. | Use `count()`. |
| Sum | Add into a shared mutable variable. | Use `mapToInt().sum()` or `reduce()`. |
| Group data | Mutate an external Map inside a lambda. | Use `collect(groupingBy(...))`. |
| Build a result list | Add to an external ArrayList from a parallel stream. | Use `toList()` or `collect()`. |
| Debugging | Use `peek` for mandatory business logic. | Use `peek` only for temporary observation; place required side effects in an explicit step. |
| Run a pipeline twice | Call a terminal operation a second time on the same stream. | Create a new stream from the source or store the result Collection. |
| Check for matching element | Traverse everything and mutate a boolean variable. | Use `anyMatch()`. |
| Find first element | Mutate an external variable in `forEach` and try to stop. | Use `findFirst()` on an ordered source. |

## 19. Complete Example: Side-Effect-Free Pipeline and Pipeline with a Terminal Action

Suppose we have a list of transactions:

```java
import java.math.BigDecimal;

record Transaction(String account, BigDecimal amount, boolean approved) {
}
```

We need to compute the total amount of approved transactions for an account.

Using a Stream to aggregate:

```java
import java.math.BigDecimal;
import java.util.List;

public class TransactionSummary {

    static BigDecimal approvedTotal(
            List<Transaction> transactions,
            String account
    ) {
        return transactions.stream()
                .filter(Transaction::approved)
                .filter(tx -> tx.account().equals(account))
                .map(Transaction::amount)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
    }
}
```

The lambdas in the pipeline read data and produce a result. There is no external mutable sum variable outside the lambdas.

If you want to record each approved transaction in an audit log, treat that as an intentional terminal action:

```java
transactions.stream()
        .filter(Transaction::approved)
        .filter(tx -> tx.account().equals(account))
        .forEach(auditService::record);
```

When auditing requires exact-once semantics, design additional transaction, idempotency, or durable storage mechanisms. A Stream does not automatically guarantee an external action occurs exactly once in the face of retries, network errors, or business replays.

## 20. Practice Exercises

### Exercise 1 — Observe Lazy Evaluation

Create a `filter` and `map` pipeline with `System.out.println` inside the lambdas without calling a terminal operation yet. Observe that no logs appear. Then call `toList()` and record the log order.

### Exercise 2 — Short-Circuiting

Use `anyMatch()` on a list of numbers where an early element satisfies the condition. Print logs in the predicate to see which elements are checked. Explain why later elements may not be traversed.

### Exercise 3 — Single-Use Stream

Create a Stream from a Collection, call `count()`, and then try calling `toList()` on the same stream. Observe the error. Fix it by calling `collection.stream()` a second time.

### Exercise 4 — Replace Side Effects with reduce

Given:

```java
List<Integer> numbers = List.of(2, 4, 6, 8);
```

Write a version using an external array variable to sum the numbers, then rewrite it using `mapToInt().sum()` or `reduce()`. Compare the clarity of both approaches.

### Exercise 5 — Do Not Mutate Source Inside the Pipeline

Given an `ArrayList` containing even and odd numbers. Try writing `filter` without removing elements from the source. Create a new list containing only odd numbers. If you want to remove even numbers from the original list, use `removeIf` separately.

### Exercise 6 — Observe Limitations of peek

Create a pipeline from a Collection of known size and call `peek(System.out::println).count()`. Observe the output on your JDK. Explain why `peek` should not be used for mandatory actions, even if a particular run prints the logs.

### Exercise 7 — Parallel Streams and Shared State

Try adding results from `parallelStream()` into a shared `ArrayList`. Then replace it with `map(...).toList()`. Explain why the second approach better expresses transformation and result collection.

## 21. Quick Summary

| Concept | Key takeaway |
| --- | --- |
| Pipeline | Source + intermediate operations + terminal operation. |
| Lazy evaluation | Intermediate operations generally only describe work; the terminal operation triggers execution. |
| Terminal operation | Ends the current stream and consumes it. |
| Single-use | Do not run a second terminal operation on the same stream; create a new stream from the source if needed. |
| Short-circuiting | Can stop early once enough information is known, such as `anyMatch` or `findFirst`. |
| Stateless | Lambda output does not depend on state changing while processing other elements. |
| Non-interfering | Do not mutate the stream source while the pipeline is running. |
| Side effect | Modifying external state, I/O, or other observable actions. |
| Parallel stream | Can process multiple elements across multiple threads; avoid unprotected shared mutable state. |
| `reduce` and `collect` | Used to aggregate results instead of external mutable variables. |
| `peek` | Useful for temporary observation/debugging; do not use for mandatory business logic. |

**Core principle:** Treat a Stream as a pipeline describing how data is transformed. Intermediate operations are lazily evaluated, terminal operations trigger the pipeline, and each stream is consumed only once. Keep lambdas stateless, non-interfering, and minimize side effects; use `map`, `filter`, `reduce`, and `collect` to express computation, while placing external actions at explicit execution points.
