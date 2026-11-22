# Do Not Replace Every Loop with a Stream When Control Flow Needs Clarity

## Goals

The Java Stream API encourages **declaring what to compute** rather than describing step-by-step data traversal. For example, `filter`, `map`, and `collect` are great for filtering, transforming, and collecting results. However, **not every loop should be converted into a Stream**. When an algorithm has multiple control-flow branches, needs `break`, `continue`, `return`, per-element exception handling, state-machine updates, or tight resource management, a `for`/`while` loop can express intent more accurately and be easier to test.

The core point of this lesson is **choosing the tool that makes meaning clearest**, not judging code by line count or “modern” syntax. A Stream with complex side effects and shared state does not automatically become good functional design; a clear loop with local variables is not automatically bad design either.

After this lesson, you will:

- Distinguish declarative data operations from control-flow orchestration.
- Know when `filter/map/flatMap/collect` and Stream terminal operations make code clearer.
- Compare `break/continue/return` with `takeWhile/filter/findFirst/anyMatch`, understanding contract differences.
- Identify cases—error handling, retries, nested loops, transactions, or finite-state machines—where direct control structures should be preferred.
- Avoid using `forEach` as a harder-to-read version of `for`.
- Check laziness, short-circuiting, encounter order, parallel execution, side effects, and resources.
- Run a Java 17 program containing both Stream and loop approaches, with verified stdout.

## 1. Streams and Loops Solve Different Kinds of Problems

### 1.1. Loops: Describing an Orchestration Process

Loops often express a procedure: check a condition, skip a step, stop the whole process, transition state, or exit a method.

```java
int total = 0;

for (int value : values) {
    if (value < 0) break;
    if (value == 0) continue;
    total += value;
}
```

This is an **illustrative snippet**, requiring `values` to be declared as an appropriate collection of numbers. The meaning is direct:

1. Stop when encountering the first negative number.
2. Skip zero values.
3. Sum the positive values seen before the stopping point.

`break` stops **the current loop**, `continue` skips the rest of the current iteration, and `return` can return a result and exit **the enclosing method**. These three tools are very useful when an algorithm is described as an ordered sequence of decisions.

### 1.2. Streams: Describing a Transformation Chain

Given an existing dataset and a clear goal, a Stream lets you describe the steps:

```java
int total = values.stream()
        .filter(value -> value > 0)
        .mapToInt(Integer::intValue)
        .sum();
```

This snippet only computes **the sum of all positive values in the entire source**; it is **not equivalent** to the loop above if the source has a negative sentinel value followed by positive numbers. This is an easy mistake when “translating syntax” without checking the algorithm's contract.

If the requirement truly is to stop at the first negative number on a source with encounter order, Java 9+ provides `takeWhile`:

```java
int total = values.stream()
        .takeWhile(value -> value >= 0)
        .filter(value -> value != 0)
        .mapToInt(Integer::intValue)
        .sum();
```

With source `[4,0,8,-1,16,32]`, both the loop and the `takeWhile` pipeline yield **12**. Still, a Stream should only be chosen if those declarative steps let readers understand the stopping rule immediately.

**Important:** on an **unordered** source, `takeWhile` has different semantics when the initial condition has no clear order: it does not necessarily represent “all elements before the stop marker” in a business order. When you need “before the first marker”, you need a source with encounter order or explicit orchestration.

## 2. Do Not Turn Every Statement in a `for` Loop into a Stream Call

A common mistake is seeing:

```java
for (Item item : items) {
    if (!item.isActive()) continue;
    send(item);
}
```

and immediately replacing it with:

```java
items.stream()
        .filter(Item::isActive)
        .forEach(this::send);
```

Both snippets are **illustrative only**: `Item` and `send` must be defined by the application. The pipeline can read well if `send` is an independent operation, elements do not affect each other, no early exit is needed, and the error policy of the external action is clear. But if `send` calls a network API, needs retries, rollbacks, stopping after errors, order control, and checkpointing, then `for` usually expresses those steps much more directly.

There is no rule saying “see `for`, replace with `stream`”. Ask yourself:

- Is this **data transformation** or **process orchestration**?
- Do we need to stop, skip, retry, or return from the method immediately?
- Is there state that changes depending on previous elements?
- Can every callback be independent and side-effect-free?
- Is the desired outcome a collection, summary statistics, or mandatory external system actions?

The answers determine the choice.

## 3. `break`: Stopping a Loop Is Not the Same as `filter`

`filter(predicate)` decides **which elements are kept**; it does not mean “stop the whole pipeline when an element fails the condition”. With source:

```java
List<Integer> values = List.of(4, 0, 8, -1, 16, 32);
```

The loop stopping at `-1` gives sum `12`; whereas:

```java
int different = values.stream()
        .filter(n -> n >= 0)
        .mapToInt(Integer::intValue)
        .sum(); // 60
```

The value `60` comes from `4+0+8+16+32`. This is a **different problem** because `filter` drops the negative number but keeps processing subsequent elements.

With an ordered source, `takeWhile(n -> n >= 0)` takes the contiguous prefix while the predicate holds and stops at the first non-matching element. Thus:

```java
int correct = values.stream()
        .takeWhile(n -> n >= 0)
        .mapToInt(Integer::intValue)
        .sum(); // 12
```

In this example, `filter(n -> n != 0)` is unnecessary for summing because adding 0 does not change the value; add that filter only if you want to explicitly express “skip zero readings” or later steps need them excluded.

### When `takeWhile` Is Not Necessarily Simpler

If the stopping condition depends on state changing across multiple steps—for example, “stop after seeing BEGIN, then ACK, then an error within 30 seconds”—writing a predicate closing over mutable state to force `takeWhile` can make code hard to understand, hard to test, and unsuitable for parallel streams. A loop with state variables, a `break` condition, and a comment describing the invariant is usually better.

Do not use `filter`, `peek`, or `map` merely as a way to hide `break` inside side effects or exceptions.

## 4. `continue`: When Is `filter` Equivalent?

If the only behavior is **skipping elements that do not need processing** and remaining elements are processed independently, `continue` can be expressed with `filter`:

```java
for (String name : names) {
    if (name.isBlank()) continue;
    result.add(name.strip());
}
```

A data-equivalent pipeline, when `names` contains non-null Strings:

```java
List<String> result = names.stream()
        .filter(name -> !name.isBlank())
        .map(String::strip)
        .toList();
```

Both snippets are **two illustrative options** with `names` and `result` declared in their own context. The pipeline clarifies the function: drop blank names → strip whitespace → build List. This is a case where Streams often win in readability.

However, compare the exact order of operations. If `"   "` must be treated as blank, you can normalize first and then filter:

```java
List<String> result = names.stream()
        .map(String::strip)
        .filter(name -> !name.isEmpty())
        .toList();
```

If the source contains `null`, `String::strip` and `isBlank` can throw `NullPointerException`. You must decide whether to filter, throw, or replace values; do not treat switching to a Stream as automatic null handling.

### `continue` Is Not Equivalent to `return` in a Lambda

You cannot put `continue` inside a lambda body and expect it to continue an outer loop:

```java
// Does not compile: continue has no enclosing loop here.
items.forEach(item -> {
    if (skip(item)) continue;
});
```

A `return;` inside a `Consumer<T>` lambda only finishes **the current lambda invocation**; it does not exit the enclosing method or stop `forEach` from traversing. Trying to simulate `continue` with `return` in a lambda can be very misleading if the code has multiple branches.

## 5. `return`: Exiting a Method with a Loop, Returning `Optional` with a Stream

A common scenario is scanning in order to find the first eligible task. Loop:

```java
static Optional<String> firstReadyLoop(List<Task> tasks) {
    for (Task task : tasks) {
        if (task.cancelled()) continue;
        if (task.priority() >= 8) return Optional.of(task.id());
    }
    return Optional.empty();
}
```

This snippet uses the `Task` record fully defined in the main program.

The equivalent Stream version when the source has encounter order:

```java
static Optional<String> firstReadyStream(List<Task> tasks) {
    return tasks.stream()
            .filter(task -> !task.cancelled())
            .filter(task -> task.priority() >= 8)
            .map(Task::id)
            .findFirst();
}
```

Here the Stream is quite clear because **it only selects one element**, with no complex state. `findFirst` is a short-circuiting terminal operation: on an ordered stream, it returns the first matching record. If no task matches, it returns `Optional.empty()`.

Things to keep in mind:

- `findAny` is **not equivalent** to `findFirst` if priority/source order matters.
- `findFirst` does not automatically replace a loop that writes state and performs rollbacks before returning.
- If `Task.id()` returns `null`, `map(Task::id).findFirst()` can throw NPE because `Optional` cannot hold null. A clear data contract is required.
- Do not call `stream().forEach(...)` expecting a `return` inside the callback to exit the method.

## 6. Control Flows That Benefit from Loops

### 6.1. Handling Per-Line Errors and Continuing

Suppose an application receives ordered string data. It needs to:

1. Stop reading when encountering `STOP`.
2. Skip blank lines.
3. Parse integer lines and add to the total.
4. Record unparseable lines in an error list with line numbers, **without stopping the whole batch**.

A loop expresses this directly:

```java
int sum = 0;
boolean stopped = false;
List<String> errors = new ArrayList<>();

for (int i = 0; i < raw.size(); i++) {
    String value = raw.get(i).strip();

    if (value.equals("STOP")) {
        stopped = true;
        break;
    }
    if (value.isEmpty()) continue;

    try {
        sum += Integer.parseInt(value);
    } catch (NumberFormatException e) {
        errors.add("Line " + (i + 1) + ": " + value);
    }
}
```

This illustrative snippet assumes `raw` is a `List<String>` without nulls; the complete code is in the program section. The loop clearly shows: stopping point, line number, error-catching region, and continue-on-error policy.

You could design a Stream producing success/failure `ParseResult`s and `collect` both kinds; that can also be valid. But if keeping a Stream short requires capturing mutable `sum` and `errors` variables, using `AtomicInteger` for the sum, throwing exceptions from `map` to simulate `break`, and looking up indices via external state, that is usually **artificial syntactic sugar**.

### 6.2. Stateful Workflows

A list of commands:

```text
BEGIN
ADD 3
ADD 2
ROLLBACK
BEGIN
ADD 7
COMMIT
```

needs a state machine:

- `BEGIN` opens a new transaction.
- `ADD n` increases the uncommitted value.
- `ROLLBACK` discards the uncommitted value.
- `COMMIT` finalizes the value into the total.
- Any command in the wrong state must be rejected.

For this kind of logic, `for` combined with `switch` and `active/pending/committed` variables expresses **the order of state transitions** transparently. Converting it into `map` with hidden mutable state inside a lambda does not make the rules more accurate, and `parallelStream` would break command-order dependencies.

### 6.3. Nested Loops and Multi-Level Exits

An algorithm finding the first matching pair across two collections:

```java
outer:
for (String left : lefts) {
    for (String right : rights) {
        if (matches(left, right)) {
            chosen = left + ":" + right;
            break outer;
        }
    }
}
```

This is an **illustrative** snippet requiring `lefts`, `rights`, `chosen`, and `matches` to be declared. The `outer` label exits both loops once a pair is found. Using `flatMap` then `findFirst` can fit if pairs are represented as pure values, but if the loops mutate state per attempt, have different stopping conditions, or need to release resources at the stopping point, a loop is easier to read.

### 6.4. Retries, Backoff, and Cleanup

A network API handler may need to:

- Retry at most N times.
- Stop immediately on success.
- Catch retryable errors.
- Record attempt counts and outcomes.
- Close resources in `finally` or `try-with-resources`.
- Abort completely on unrecoverable errors.

This is **process orchestration**, not a pipeline transforming independent elements. `for` or `while` with `try/catch` making the policy explicit is usually easier to evaluate and debug. Streams do not automatically provide retries, transactions, or resource cleanup.

## 7. Complete Java 17 Program

The following program includes both cases where **a loop can be cleanly replaced by a Stream** and cases where **a loop should be kept**.

Create file **`LoopVsStreamDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

public class LoopVsStreamDemo {
    record Task(String id, int priority, boolean cancelled) {}
    record ParseResult(int total, List<String> errors, boolean stopped) {}

    static int sumBeforeStopLoop(List<Integer> values) {
        int sum = 0;
        for (int value : values) {
            if (value < 0) break;
            if (value == 0) continue;
            sum += value;
        }
        return sum;
    }

    static int sumBeforeStopStream(List<Integer> values) {
        return values.stream()
                .takeWhile(value -> value >= 0)
                .filter(value -> value != 0)
                .mapToInt(Integer::intValue)
                .sum();
    }

    static Optional<String> firstReadyLoop(List<Task> tasks) {
        for (Task task : tasks) {
            if (task.cancelled()) continue;
            if (task.priority() >= 8) return Optional.of(task.id());
        }
        return Optional.empty();
    }

    static Optional<String> firstReadyStream(List<Task> tasks) {
        return tasks.stream()
                .filter(task -> !task.cancelled())
                .filter(task -> task.priority() >= 8)
                .map(Task::id)
                .findFirst();
    }

    static ParseResult parseUntilStop(List<String> raw) {
        int sum = 0;
        boolean stopped = false;
        List<String> errors = new ArrayList<>();
        for (int i = 0; i < raw.size(); i++) {
            String value = raw.get(i).strip();
            if (value.equals("STOP")) {
                stopped = true;
                break;
            }
            if (value.isEmpty()) continue;
            try {
                sum += Integer.parseInt(value);
            } catch (NumberFormatException e) {
                errors.add("Line " + (i + 1) + ": " + value);
            }
        }
        return new ParseResult(sum, List.copyOf(errors), stopped);
    }

    static int applyTransactions(List<String> commands) {
        boolean active = false;
        int pending = 0;
        int committed = 0;

        for (String command : commands) {
            switch (command) {
                case "BEGIN" -> {
                    if (active)
                        throw new IllegalStateException("Already active");
                    active = true;
                    pending = 0;
                }
                case "COMMIT" -> {
                    if (!active)
                        throw new IllegalStateException("No transaction");
                    committed += pending;
                    pending = 0;
                    active = false;
                }
                case "ROLLBACK" -> {
                    if (!active)
                        throw new IllegalStateException("No transaction");
                    pending = 0;
                    active = false;
                }
                default -> {
                    if (!active || !command.startsWith("ADD "))
                        throw new IllegalArgumentException("Invalid command");
                    pending += Integer.parseInt(command.substring(4));
                }
            }
        }
        if (active)
            throw new IllegalStateException("Unclosed transaction");
        return committed;
    }

    public static void main(String[] args) {
        List<Integer> readings = List.of(4, 0, 8, -1, 16, 32);
        System.out.println("Loop sum: "
                + sumBeforeStopLoop(readings));
        System.out.println("Stream sum: "
                + sumBeforeStopStream(readings));

        List<Task> tasks = List.of(
                new Task("A", 7, true),
                new Task("B", 4, false),
                new Task("C", 9, false),
                new Task("D", 10, false)
        );
        System.out.println("First ready loop: "
                + firstReadyLoop(tasks));
        System.out.println("First ready stream: "
                + firstReadyStream(tasks));

        ParseResult parsed = parseUntilStop(
                List.of("10", " ", "oops", "20", "STOP", "30"));
        System.out.println("Parsed total: " + parsed.total());
        System.out.println("Errors: " + parsed.errors());
        System.out.println("Stopped: " + parsed.stopped());

        int committed = applyTransactions(List.of(
                "BEGIN", "ADD 3", "ADD 2", "ROLLBACK",
                "BEGIN", "ADD 7", "COMMIT"));
        System.out.println("Committed: " + committed);
    }
}
```

Compile and run:

```bash
javac LoopVsStreamDemo.java
java LoopVsStreamDemo
```

**Exact stdout** with Java 17:

```text
Loop sum: 12
Stream sum: 12
First ready loop: Optional[C]
First ready stream: Optional[C]
Parsed total: 30
Errors: [Line 3: oops]
Stopped: true
Committed: 7
```

### 7.1. Explaining the Output

**Both Loop sum and Stream sum equal 12.** Source `[4,0,8,-1,16,32]` has marker `-1`. The loop uses `break`; the Stream uses `takeWhile(value >= 0)`. The numbers 16 and 32 **are not added**, unlike the `filter(n >= 0)` approach shown earlier.

**First ready is Optional[C] in both cases.** Task A is cancelled, B has priority 4 below threshold 8, C has priority 9 and is not cancelled. C is the first valid task in encounter order so both approaches pick the same ID. Task D is also eligible but appears after C.

**Parsed total equals 30.** Line 1 is 10; line 2 is blank and skipped; line 3 `oops` is not a number so it goes into `errors`; line 4 is 20; line 5 is `STOP` which stops the loop; line 6 is 30 and is not processed. The result records the exact line `Line 3` and flag `stopped=true`.

**Committed equals 7.** The first transaction adds 3+2 to `pending` but `ROLLBACK` discards it. The next transaction adds 7 and `COMMIT`s, so the final result is 7. This is an example where a loop and `switch` keep state logic clearer than a Stream pipeline containing mutable variables.

The example is deterministic, requires no libraries outside Java 17, and has no network or thread dependencies. Earlier illustrative snippets are not necessarily standalone; **this program is a complete program** compiled and verified.

## 8. When Do Streams Truly Improve Design?

Streams are usually well-suited for transformations with **clear inputs and outputs** and minimal external state dependencies:

```java
List<String> emails = users.stream()
        .filter(User::active)
        .map(User::email)
        .filter(Objects::nonNull)
        .map(String::strip)
        .filter(email -> !email.isEmpty())
        .distinct()
        .toList();
```

This is an illustrative snippet: it requires `users`, the `User` type, and `Objects` imported. The meaning is: select active users, get email, filter missing, normalize, deduplicate, and collect into a list. The steps are **data transformations** and read like a business specification.

Other suitable cases:

- `mapToInt(...).sum()` to sum numeric properties.
- `groupingBy(...)` to group by a stable key.
- `anyMatch(...)` to ask whether any element matches a predicate.
- `allMatch(...)` to check whether all elements match a condition.
- `findFirst()` to pick the first element on an ordered source.
- `flatMap(...)` to expand one element into zero or more elements and flatten, when the result has a clear model.
- `Collectors.toMap(...)` or `groupingBy(...)` to build keyed result structures.

Streams make code better when the pipeline can be explained in one sentence: **“take data → filter → transform → collect result”**. If understanding a pipeline requires tracing 4 external mutable variables and 3 exception branches inside lambdas, a loop may be the more maintainable choice.

### Streams Do Not Force the Entire Application to Be Purely Functional

Java supports multiple styles. You can use a loop at the **orchestration** layer and use Streams inside independent data transformations. This is often a sensible combination:

```java
for (Batch batch : batches) {
    if (batch.cancelled()) break;

    long amount = batch.items().stream()
            .filter(Item::valid)
            .mapToLong(Item::amount)
            .sum();

    persistBatchTotal(batch.id(), amount);
}
```

This snippet is illustrative, requiring `Batch`, `Item`, `batches`, and `persistBatchTotal` declared. The loop expresses the stopping rule and persisting one batch; the Stream describes an independent sum within a batch. Use this only when the contract of `persistBatchTotal` and error handling are properly designed.

## 9. Watch Out for Lazy Evaluation, Short-Circuiting, and Side Effects

Intermediate operations like `map` and `filter` are typically **lazy**: they build a pipeline and do not execute the mapper for elements until a terminal operation demands data.

```java
Stream<Integer> pipeline = Stream.of(1, 2, 3)
        .map(n -> n * 2);
List<Integer> result = pipeline.toList(); // [2, 4, 6]
```

A Stream can only be used for one terminal operation; after `toList`, do not call `count` again on the same Stream object.

### Do Not Assume Callbacks Run Exactly Once for Every Element

`findFirst`, `findAny`, `anyMatch`, and `takeWhile` can **short-circuit**. If you put mandatory business auditing inside `map` or `peek`, elements not needed for the result may not be processed. Some terminal operations can also optimize the pipeline so mappers do not run as you might expect.

Example:

```java
boolean found = Stream.of(1, 2, 3, 4)
        .anyMatch(n -> n == 1); // true
```

There is no need to call the predicate on every element to know the answer. Therefore, if the goal is “validate data and log every row”, a short-circuiting pipeline cannot replace a process required to handle all rows.

### Parallel Execution and Mutable Variables

Do not convert a Stream to `parallelStream()` while callbacks update unsynchronized mutable variables:

```java
int[] total = {0};
values.parallelStream().forEach(n -> total[0] += n);
```

This snippet illustrates a **data race** that can lose updates; do not use it to compute sums. Replace it with `mapToInt(...).sum()` when addition is appropriate or a properly designed Collector. For workflows depending on step-by-step order, arbitrary parallelization can be wrong even without throwing exceptions.

## 10. Exceptions and Resources: Prefer Clear Boundaries

### Checked Exceptions in Lambdas

Common functional interfaces like `Function.apply`, `Predicate.test`, and `Consumer.accept` do not declare checked exceptions. If each element must call an API throwing `IOException`, you cannot simply write a lambda that throws the checked exception outward without handling it.

A loop can clearly express per-element `try/catch` and decide whether to continue or stop. You can also wrap error outcomes in typed result objects and process them with a Stream; the choice depends on complexity, and there is no mandatory rule forcing Streams.

### Resource Management

A `Stream` from `Files.lines(path)` can keep a file open. Terminal operations like `collect` or `forEach` **do not automatically close** the Stream. Use `try-with-resources` at the owning boundary:

```java
// Illustrative: requires Path path and IOException handling in the enclosing method.
try (Stream<String> lines = Files.lines(path)) {
    lines.filter(s -> !s.isBlank())
         .forEach(System.out::println);
}
```

If you need to track line numbers and record parse errors per line, a loop reading from `BufferedReader` with `try-with-resources` can clearly express line-by-line reading, early stopping, line numbering, and resource cleanup. Do not force `Files.lines(...).forEach(...)` into a disguised loop with lots of captured variables.

### Errors and Rollback

A pipeline does not automatically create a transaction. If an action has already sent a request or written to a database and another callback throws an exception, earlier side effects are not automatically undone. An explicit loop makes `try`, `catch`, `finally`, and commit/rollback boundaries easier to see; however, the application itself must still provide real transaction mechanisms and error policies.

## 11. Performance: Measure Instead of Guessing

There is no guarantee that loops are always faster than Streams, or Streams always faster than `for` loops. Performance differences depend on:

- Data size, complexity of mappers, filters, and stopping conditions.
- Source structure, memory contiguity, boxing/unboxing, and primitive Stream types.
- JIT, JVM optimizations, allocation cost, and inlining capability.
- Source splittability and coordination overhead in parallel pipelines.
- I/O, network, or database calls, which can dwarf loop overhead itself.

For example, summing `int`s can use `IntStream` to avoid boxing:

```java
int total = numbers.stream()
        .mapToInt(Integer::intValue)
        .sum();
```

But if processing only a few elements with a state machine, micro-optimizing Stream calls does not make code more readable. When performance matters, measure with a proper benchmark (such as JMH for microbenchmarks), rather than guessing from syntax length or a single un-warmed `System.nanoTime` run.

## 12. Code Review Decision Table

| Question | Stream Usually Fits | Loop Usually Clearer |
| --- | --- | --- |
| Pure filter/transform/collect pipeline? | Yes | Not required |
| Only need count, sum, grouping, matching? | Yes | Possible, but more verbose |
| Need to stop at a prefix with a simple predicate? | `takeWhile` on ordered source | `break` if stopping rule is complex |
| Need to skip some independent records? | `filter` | `continue` when other branches exist |
| Need to return the first matching element? | `findFirst` | `return` when side processing is needed |
| Need retries, rollbacks, multiple error types per step? | Possible, but easily messy | Usually yes |
| Need a state machine depending on command order? | Usually no | Yes |
| Need nested loops with multi-level exit? | `flatMap/findFirst` if pure | Usually yes if control flow is complex |
| Need to mutate shared variables? | Should not use side effects | Use local variables, control scope |
| Need to call external service per element? | Only when error semantics are clear | Usually easier to orchestrate |
| Want parallel execution? | Only when callbacks/state fit | Do not parallelize order-dependent algorithms |
| Want fewer lines of code at all costs? | Not a criterion | Not a criterion |

**Practical rule:** if Stream step names clearly tell the story and callbacks have independent meaning, Streams are usually easy to read. If readers must mentally simulate state and exceptions across multiple lambdas to understand the result, consider a loop or splitting the algorithm into small methods.

## 13. Common Mistakes

1. **Replacing `break` with `filter`:** `filter` does not stop, so data after the stop marker still gets processed.
2. **Assuming `continue` works inside a lambda:** `continue` is invalid without an enclosing loop.
3. **Thinking `return` in a lambda exits the outer method:** it only returns from the lambda.
4. **Using `forEach` to build a list via a shared `ArrayList`:** especially dangerous with parallel streams.
5. **Turning a state machine into a Stream using captured mutable fields:** obscures order dependencies.
6. **Separating stopping logic from error info:** loses the ability to report the exact line and reason.
7. **Using `findAny` instead of `findFirst` when the first element must be chosen:** drops the encounter-order contract.
8. **Putting mandatory side effects in a short-circuiting pipeline:** not every element is guaranteed to be visited.
9. **Reusing a Stream after a terminal operation:** Streams are single-use.
10. **Using `parallelStream` with state depending on previous elements:** prone to races or wrong ordering.
11. **Choosing `takeWhile` on an unordered source to mean “before STOP line”:** lacks clear encounter order.
12. **Hiding checked exceptions in a lambda by catching and returning null unconditionally:** masks errors and corrupts results.
13. **Forgetting to close I/O-backed Streams:** terminal operations do not close resources automatically.
14. **Assuming shorter Stream code is faster:** unfounded without measurement.
15. **Forcing all operations into one pipeline:** can obscure transaction and error-handling boundaries.
16. **Not checking semantic equivalence when refactoring:** the same example showed `filter` differs from `takeWhile`.

## 14. Exercises

**Exercise 1.** For `[4,0,8,-1,16,32]`, compare the sum from a loop with `break` and a Stream using `filter(n>=0)`. Why do they differ?

**Exercise 2.** Write a Stream using `takeWhile` equivalent to a loop stopping at the first negative number. What condition on source ordering is important?

**Exercise 3.** Given a list of names with blank strings, convert a `continue` loop into a `map(String::strip).filter(...)` pipeline. Why is this a reasonable refactoring?

**Exercise 4.** A lambda inside `forEach` contains `return;`. Does it exit the lambda, the terminal operation, or the enclosing method?

**Exercise 5.** Use `findFirst` to pick the first `Task` that is not cancelled and has priority at least 8. State the result from the program.

**Exercise 6.** For string batch `["10"," ","oops","20","STOP","30"]`, state the expected total, errors, and stop flag.

**Exercise 7.** A system reads commands BEGIN, ADD, ROLLBACK, COMMIT. Why can a loop and `switch` be easier to maintain than `map` over mutable state?

**Exercise 8.** Using `anyMatch` to find a matching element, can you expect the predicate to run on all elements?

**Exercise 9.** Replace `parallelStream().forEach(n -> total[0] += n)` with a proper aggregation.

**Exercise 10.** When processing a file line-by-line, does calling `lines.collect(...)` automatically close the file? Where should closing be placed?

**Exercise 11.** Name two situations where Streams improve readability and two situations where loops are clearer.

**Exercise 12.** When optimizing a small pipeline's performance, why is looking at line count or a single test run insufficient?

### Answer Hints

1. The loop with `break` returns 12; `filter(n>=0)` returns 60 because it skips the negative number and continues summing afterward.
2. `values.stream().takeWhile(n -> n>=0).mapToInt(Integer::intValue).sum()`; encounter order is required for “before the marker” to be meaningful.
3. Elements are independent, and the goal is transformation and list creation.
4. It only exits the current lambda invocation; it does not exit the enclosing method.
5. `Optional[C]` on the given `Task` source.
6. Total 30, error `Line 3: oops`, `stopped=true`; the 30 after STOP is not read.
7. State depends on previous commands and rollbacks must follow order; a loop expresses transitions directly.
8. No; `anyMatch` short-circuits.
9. `values.parallelStream().mapToInt(Integer::intValue).sum()` if the `int` range fits.
10. No; use `try-with-resources` on the Stream/reader owning the resource.
11. Stream: filtering/transforming/collecting Lists and grouping/aggregating. Loop: retries with errors, state machines, or complex stopping rules.
12. JIT, warmup, inputs, and overhead make results environment-dependent; use proper benchmarks if needed.

## Conclusion

**Functional design does not mean eliminating all loops.** Streams excel when the problem is transforming data and collecting results with independent, declarative operations. Loops excel when **expressing control flow** matters: breaking, skipping, returning, handling errors, transitioning state, or coordinating resources.

Keep whichever makes **stopping conditions, error policies, state boundaries, and result contracts** easiest for readers to see. You can use a loop to orchestrate the overall workflow and Streams inside pure calculations. When refactoring, verify semantic equivalence using data with stop markers, empty sources, parse errors, and transaction states—do not just compare line counts.
