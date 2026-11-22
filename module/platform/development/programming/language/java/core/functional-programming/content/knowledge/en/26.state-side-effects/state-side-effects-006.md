# Do Not Use AtomicInteger Just to Bypass the Effectively Final Rule

When starting to use **lambdas** in Java, many people encounter a compilation error because a local variable referenced inside a lambda **is not final or effectively final**. A common “quick fix” is to replace an int variable with **AtomicInteger**, and then call incrementAndGet() or addAndGet() inside the lambda. The code may compile, but switching to a mutable container **does not solve the design problem**: it can introduce side effects, make the operation unpredictable, and fail to take advantage of standard Stream aggregations.

Let’s distinguish between two needs:

- **Needing to compute a result** such as element count, total amount, valid line count, or grouped results: typically use **count, sum, reduce, collect**, or an explicit loop and return the value.
- **Needing a genuinely shared atomic state across multiple threads** such as the number of completed tasks or a progress counter: **AtomicInteger** may be appropriate, but that is a real concurrency requirement, not a way to avoid the variable capture error message.

This lesson explains the exact **effectively final** rule, why a mutable holder can be referenced by a lambda, the risks of misusing AtomicInteger, how to replace it with pure aggregations or collectors, and the cases where AtomicInteger is the right tool. All standalone examples use **Java 17+**.

## 1. What does effectively final mean?

A lambda can reference **local variables** and **method parameters** from the enclosing scope if those variables are **final or effectively final**.

~~~java
int minimum = 10;

List<Integer> values = List.of(3, 10, 15, 20);

long count = values.stream()
    .filter(number -> number >= minimum)
    .count();
~~~

The variable minimum is not declared with the final keyword, yet it is still **effectively final** because after being assigned 10, it is never reassigned. The lambda is allowed to read this value.

If we add a reassignment to minimum:

~~~java
int minimum = 10;
minimum = 15;

long count = values.stream()
    .filter(number -> number >= minimum)
    .count();
~~~

The snippet above **does not compile**: minimum is no longer effectively final. The compiler error message usually takes the form **local variables referenced from a lambda expression must be final or effectively final**.

The condition here is about **reassigning the captured local variable**, not whether a lambda statement can or cannot read mutable data types. Java allows referencing a mutable object through an effectively final local variable; it is precisely that allowance that leads some people to use AtomicInteger as a trick to bypass the constraint.

### 1.1. final and effectively final

| Case | Effectively final? | Can lambda capture? |
| --- | --- | --- |
| int limit = 10; then read-only | Yes | Yes |
| final int limit = 10; | Yes and declared final | Yes |
| int limit = 10; then limit++ | No | No |
| int limit = 10; then limit = 20 | No | No |
| AtomicInteger counter = new AtomicInteger(); only calling incrementAndGet() | The counter reference variable can be effectively final | Yes |
| List<String> items = new ArrayList<>(); only calling items.add(...) | The items reference variable can be effectively final | Yes |

**Important:** The effectively final nature of a **reference** does not make **the object that the reference points to** immutable. AtomicInteger can increment its internal value, and ArrayList can add elements, even though the local variable holding the reference is not reassigned.

### 1.2. Uninitialized local variable assigned exactly once

A variable does not necessarily need an initializer at declaration time to be considered effectively final:

~~~java
int minimum;
minimum = 10;

long count = values.stream()
    .filter(x -> x >= minimum)
    .count();
~~~

If minimum is assigned exactly once according to the **definite assignment** rules and there is no assignment that breaks its effectively final status, this usage can be valid. The core point is not having the final keyword, but rather **the variable being assigned in a way compatible with Java's capture constraint**.

### 1.3. Mutable objects vs. mutable variables

~~~java
List<String> result = new ArrayList<>();

Runnable action = () -> result.add("Java");
action.run();
~~~

This snippet **compiles**: the result variable itself is not reassigned. However, **the ArrayList is modified**, so the lambda has a side effect. Successful compilation does not prove that action is pure, easy to use in parallel, or safe to share.

## 2. Why does Java impose the effectively final constraint?

Regular local variables belong to the execution context of a method. A lambda can be stored and executed **after the method that created it has finished**, or executed at a different time or on a different thread.

For example:

~~~java
static Runnable makeAction() {
    int threshold = 10;

    return () -> System.out.println(threshold);
}
~~~

The returned Runnable can still use the value of threshold after makeAction has returned. Java captures **the value of the effectively final local variable** according to the appropriate semantics of lambdas, rather than sharing a “local int variable slot” that continues to be updated by the original scope.

The effectively final rule avoids ambiguity where a local variable might be reassigned in one scope while the lambda holds an old value. It also prevents certain confusions about visibility of changes across threads.

**You should not infer that effectively final is a thread synchronization mechanism.** It only constrains reassigning the captured local/parameter. If the reference points to shared mutable state, issues of visibility, races, and atomicity still need to be addressed separately.

### 2.1. Local capture vs. field access

Lambdas can access instance fields or static fields. Fields do not follow the same effectively final local capture rule:

~~~java
class CounterHolder {
    int count;

    Runnable action() {
        return () -> count++;
    }
}
~~~

This code can compile. However, count++ on a field is still a read-modify-write operation with no concurrency safety guarantees. Moving a counter variable to a field **is not a good solution** just to evade the capture rule; it can make state scattered and harder to control.

## 3. Anti-pattern: using AtomicInteger as a mutable int box

A common example:

~~~java
AtomicInteger count = new AtomicInteger();

items.forEach(item -> {
    if (isValid(item)) {
        count.incrementAndGet();
    }
});

System.out.println(count.get());
~~~

This is **illustrative code** assuming items and isValid are already declared. It is valid with respect to capture syntax because the reference variable count is not reassigned. However, if the goal is simply to **count valid elements in a Collection**, using AtomicInteger causes the result to be communicated via a **side effect** instead of a value-returning expression.

A more direct approach:

~~~java
long count = items.stream()
    .filter(this::isValid)
    .count();
~~~

The second snippet is also illustrative code placed inside an instance method with an appropriate isValid method.

The differences:

- **The AtomicInteger approach:** the callback mutates an object outside the pipeline; you have to look at the counter variable both before and after forEach to understand the result.
- **The count() approach:** the pipeline describes the filtering condition and the terminal operation **returns the count result**; no intermediate container is needed.
- **Regarding types:** count() returns **long**, which can be more appropriate than int if the count is large.
- **Regarding optimization:** Stream is allowed to evaluate the pipeline according to its contract; no side effects are needed in callbacks.
- **Regarding testing:** directly compare the count value against the expected result, without needing to initialize or reset a shared holder.

**This does not mean AtomicInteger in the first example is always functionally wrong.** If every callback runs once and increments the variable successfully, it can produce the right number. However, it is a redundant pattern and prone to misuse when the pipeline changes.

## 4. Why AtomicInteger does not “fix” lambda design

AtomicInteger is a class in **java.util.concurrent.atomic**, supporting atomic operations on an integer: get(), set(), incrementAndGet(), getAndIncrement(), addAndGet(), compareAndSet(), updateAndGet(), etc.

~~~java
AtomicInteger counter = new AtomicInteger(0);

counter.incrementAndGet();
System.out.println(counter.get()); // 1
~~~

When a lambda captures the counter variable:

~~~java
AtomicInteger counter = new AtomicInteger();

Consumer<String> action = text -> {
    counter.incrementAndGet();
};
~~~

The local variable counter is **effectively final**, but the AtomicInteger object is mutated. This is **wrapping state in an object** to bypass the local reassignment constraint; it does not turn the computation into an immutable value.

We need to distinguish:

1. **Compilable:** the local reference is not reassigned.
2. **Atomic on increment:** incrementAndGet performs an atomic update.
3. **Business-correct:** the callback must run the exact allowed number of times and the counted value must accurately represent the intended target.
4. **Pure / side-effect-free:** whether the lambda changes state observable from the outside.
5. **Safe for the larger workflow:** whether related operations beyond the increment are properly coordinated.

A piece of code can satisfy (1) and (2) yet **fail (3), (4), or (5)**. The atomicity of an increment does not replace proper algorithm design.

### 4.1. AtomicInteger does not turn a callback into a pure function

A pure function should produce a deterministic result from its input and have no observable side effects. A callback calling counter.incrementAndGet has a **side effect**; with the same input, the counter state changes across invocations.

~~~java
AtomicInteger calls = new AtomicInteger();

Function<String, String> normalize = text -> {
    calls.incrementAndGet();
    return text.trim();
};
~~~

On the surface, normalize returns a new string, yet it simultaneously mutates calls. When bringing normalize into a stream, the program no longer just cares about the resulting list: it inadvertently depends on how many times the callback is executed.

## 5. Streams can optimize and skip unnecessary callbacks

This is a deeper reason not to place side-effect counting inside map or peek.

~~~java
AtomicInteger observed = new AtomicInteger();

long count = List.of(1, 2, 3, 4).stream()
    .map(value -> {
        observed.incrementAndGet();
        return value * 2;
    })
    .count();
~~~

For a source with a known size and a map pipeline that **does not change the number of elements**, Stream can compute count from the source size **without invoking the mapper**. According to the Java Stream contract, implementations are permitted to elide callbacks if executing them does not affect the terminal result.

Therefore:

- count correctly produces 4.
- **You must not use observed.get() to assert that the mapper processed all four elements.**
- Some runtime environments may skip map completely for this pipeline.
- Replacing map with peek to “force” incrementing the counter does not change the contract either.

This is not a bug in AtomicInteger. The mistake lies in assuming that **every intermediate callback must always execute** when a terminal operation is called.

### 5.1. filter, findFirst, and short-circuiting

~~~java
AtomicInteger visited = new AtomicInteger();

Optional<Integer> first = Stream.of(2, 4, 7, 9)
    .filter(value -> {
        visited.incrementAndGet();
        return value % 2 != 0;
    })
    .findFirst();
~~~

findFirst can stop as soon as it finds the first element matching the condition, without inspecting the entire source. In a sequential ordered stream like this example, the three elements 2, 4, and 7 are enough to find the result 7.

However, if you switch to parallel, change the source, add stateful operations, or use a different terminal operation, the number and order of callback invocations should not be part of your program's contract.

**If you need the “first element matching the condition,”** return the Optional from findFirst. **If you need the number of elements matching the condition,** use filter(...).count(). **If you need to count callbacks for runtime observation purposes**, a counter can serve as temporary instrumentation, but it should not be relied upon as a guaranteed business result.

### 5.2. Issues when using parallelStream

~~~java
AtomicInteger counter = new AtomicInteger();

values.parallelStream()
    .filter(this::accept)
    .forEach(value -> counter.incrementAndGet());
~~~

This example can count elements that reach the terminal forEach, provided all operations succeed; incrementing via AtomicInteger avoids lost updates that would occur with a shared int.

However, if the task is simply to count elements matching a predicate, then:

~~~java
long count = values.parallelStream()
    .filter(this::accept)
    .count();
~~~

expresses the intent better, avoids mutating state inside callbacks, and lets Stream perform the appropriate reduction. Calling parallel does not automatically make the AtomicInteger version faster: updates to the same atomic counter can suffer from **contention**, causing multiple workers to wait on each other.

## 6. Replace manual counters with terminal operations

### 6.1. Counting elements

~~~java
long positiveCount = numbers.stream()
    .filter(x -> x > 0)
    .count();
~~~

Instead of incrementing an AtomicInteger inside forEach.

### 6.2. Computing a sum

~~~java
int sum = numbers.stream()
    .mapToInt(Integer::intValue)
    .sum();
~~~

Instead of:

~~~java
AtomicInteger sum = new AtomicInteger();
numbers.forEach(x -> sum.addAndGet(x));
~~~

If the sum can exceed the int range, use mapToLong(...).sum() when appropriate. Both int and long have limits; depending on the domain, you should check for overflow or use a numeric type with a larger range.

### 6.3. Counting by group

~~~java
Map<String, Long> counts = employees.stream()
    .collect(Collectors.groupingBy(
        Employee::department,
        Collectors.counting()
    ));
~~~

This illustrative snippet requires an Employee type with a department() method and imports for Map/Collectors. There is no need for a Map<String, AtomicInteger> mutated outside the callback.

If you want to aggregate into a Map with deterministic key ordering for testing output, you can choose TreeMap:

~~~java
Map<String, Long> ordered = employees.stream().collect(
    Collectors.groupingBy(
        Employee::department,
        TreeMap::new,
        Collectors.counting()
    )
);
~~~

### 6.4. Collecting multiple metrics with a single collector

If you need both a count and a sum, you can use **Collectors.teeing** (Java 12+) to combine two downstream collectors:

~~~java
record Summary(long count, int total) {}

Summary summary = sales.stream().collect(Collectors.teeing(
    Collectors.counting(),
    Collectors.summingInt(Sale::amount),
    Summary::new
));
~~~

This is an illustrative snippet with an appropriate Sale record, with a standalone program shown in Section 11. The result is an explicit **Summary value**, rather than two side-effect AtomicIntegers updated alongside each other.

## 7. Reduce instead of an external accumulator variable

The reduce operation combines multiple elements into a single result according to a deterministic rule.

~~~java
int total = numbers.stream()
    .reduce(0, Integer::sum);
~~~

For a sequential stream, you can think of the addition starting at 0 and combining each element one by one. For a parallel stream, the reduction can be split into local partial results and then merged.

Therefore, the accumulator/combiner must satisfy the requirements for **identity**, **associativity**, and, for the three-argument reduce, **compatibility**.

### 7.1. Do not replace one bug with another mutable identity

You should not use:

~~~java
AtomicInteger identity = new AtomicInteger();

AtomicInteger total = numbers.parallelStream().reduce(
    identity,
    (counter, value) -> {
        counter.addAndGet(value);
        return counter;
    },
    (left, right) -> {
        left.addAndGet(right.get());
        return left;
    }
);
~~~

Even though the addAndGet operations are atomic, the code uses a **shared mutable identity**, violating the reduction model. A group may be combined with the already-mutated identity itself, leading to double-counting or races; this cannot be fixed merely by calling atomic methods.

**Better:** use an immutable value such as Integer/Long with a compatible addition operation, or use **collect** when mutable accumulation is needed:

~~~java
long total = numbers.parallelStream()
    .mapToLong(Integer::longValue)
    .sum();
~~~

When you need to build an ArrayList/StringBuilder with internal mutation, use a contract-compliant Collector with a **supplier that creates appropriate containers** instead of forcing a mutable object into reduce.

### 7.2. Stream accumulators vs. shared mutable variables

Stream.reduce and proper collectors can manage local results according to their contracts. The author does not need to update a single global counter variable from multiple threads.

This separates the **computation logic** from the details of **worker scheduling**, and reduces reliance on atomic contention. Results are only correct if your reducer/collector obeys the corresponding laws; the compiler does not automatically prove these algebraic laws.

## 8. Use a regular loop when it is clearer

Functional programming is not a rule forbidding all mutation.

If you genuinely have a sequential algorithm with multiple branches, a local variable updated inside a loop can be simpler and more accurate than an AtomicInteger holder:

~~~java
int validCount = 0;

for (Order order : orders) {
    if (isValid(order)) {
        validCount++;
    }
}
~~~

This is an illustrative snippet with an appropriate Order type and isValid method.

**There is no local lambda capture here**, so there is no reason to turn validCount into an AtomicInteger. In a sequential function, a non-shared local variable usually has easily understood scope and cost.

A for loop can be used when:

- You need break/continue or complex multi-branch control flow.
- You need to update a small piece of state within a controlled local scope.
- You need to interact with an imperative API.
- A loop is clearer than a Stream pipeline with multiple long lambdas.

The goal is not “a one-line Stream at all costs,” but rather **clear contracts and easily verifiable code**.

## 9. When is AtomicInteger appropriate?

AtomicInteger is designed for cases where you need to **atomically update an integer** from threads that may run concurrently, or for a state structure that requires compare-and-set.

Reasonable examples:

- Counting completed tasks across multiple worker threads.
- Updating a shared status counter of a concurrent service.
- Generating simple internal sequences/tickets when requirements and overflow boundaries allow.
- Certain lock-free algorithms using compareAndSet in accordance with its contract.

In these cases, **shared state is the requirement itself**, not a side effect bolted onto a computation that could otherwise return a value.

### 9.1. Example: counting completed tasks

~~~java
AtomicInteger completed = new AtomicInteger();
ExecutorService pool = Executors.newFixedThreadPool(4);

try {
    List<Future<?>> futures = new ArrayList<>();

    for (int task = 0; task < 1000; task++) {
        futures.add(pool.submit(() -> {
            completed.incrementAndGet();
        }));
    }

    for (Future<?> future : futures) {
        future.get();
    }
} finally {
    pool.shutdown();
}

System.out.println(completed.get()); // 1000
~~~

This illustrative snippet is placed inside a method that declares or handles the checked exceptions from Future.get(), with full imports in the standalone program.

**Why does AtomicInteger make sense here?** Multiple tasks genuinely run on a pool with multiple worker threads; the same completed variable represents a shared state counter. incrementAndGet is an atomic update, avoiding lost updates from count++ on a shared int.

Calling Future.get() waits for each submitted task to finish or report an error; after all futures succeed, the value 1000 is deterministic in the example.

If the count is merely **the number of Futures in a List** or **the number of elements in a known Stream**, you do not need AtomicInteger; the number of tasks **completed over time** is what justifies a concurrent counter.

### 9.2. AtomicInteger does not guarantee multi-step transactions

~~~java
if (counter.get() < limit) {
    counter.incrementAndGet();
}
~~~

The snippet above has a **race** when multiple threads execute it concurrently: the individual get and incrementAndGet operations are atomic, but **the condition check + update is not a single composite atomic operation**. Multiple threads can simultaneously observe a value below limit and then increment past the limit.

You need a synchronization design for the entire invariant, such as a compareAndSet loop, a semaphore, or a lock depending on the situation. Do not assume that every piece of code containing AtomicInteger is automatically thread-safe.

### 9.3. LongAdder for high-frequency statistical updates

In systems with high counter update frequency and heavy contention, **LongAdder** can improve throughput compared to a single AtomicLong in certain workloads. However, **sum() is not a consistent atomic snapshot** while concurrent updates are occurring.

Therefore, LongAdder is typically suited for metrics/statistics, not as a default replacement when compare-and-set or a unique sequence value with instantaneous consistency is needed.

## 10. updateAndGet and accumulateAndGet: lambdas may be retried

An advanced aspect of AtomicInteger is its function-based update methods:

~~~java
AtomicInteger value = new AtomicInteger(5);

int updated = value.updateAndGet(current -> current + 2);
System.out.println(updated); // 7
~~~

Update methods like **updateAndGet**, **getAndUpdate**, **accumulateAndGet**, and **getAndAccumulate** may have to **re-invoke the update function multiple times when CAS fails due to contention**.

Therefore, **the update function must be side-effect-free**, because one successful update does not mean the lambda is called only once:

~~~java
AtomicInteger counter = new AtomicInteger();

counter.updateAndGet(current -> {
    sendEmail(); // Wrong intent: may be called again.
    return current + 1;
});
~~~

This is an intentionally flawed illustrative snippet, where sendEmail is a hypothetical function, not a built-in Java API.

**An interesting contrast:** AtomicInteger can be a useful concurrency building block, yet **even within its own API**, certain update lambdas still require a **pure/stateless** style to avoid repeated side effects. Do not treat using an atomic as a license to put arbitrary business operations inside callbacks.

### 10.1. incrementAndGet and getAndIncrement

~~~java
AtomicInteger next = new AtomicInteger(10);

int oldValue = next.getAndIncrement(); // 10
int newValue = next.incrementAndGet(); // 12
~~~

After the first call, next internally becomes 11; the second call increments to 12 and returns 12. The difference is **whether the old or new value is returned**. Choose the right one if implementing a sequence or serial number, and consider int overflow.

## 11. Complete Java 17+ program

The following program intentionally separates **two kinds of tasks**.

Group A: computing the count of qualifying transactions, total amount, totals by region, and overall summary statistics. These are all **Stream result values**; no AtomicInteger is needed to bypass effectively final.

Group B: creating a worker pool to run **1000 concurrent tasks**. The tasks use AtomicInteger to update the completion count **because there is genuine shared state**.

Create the file **AtomicCaptureDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class AtomicCaptureDemo {
    record Sale(String region, int amount) {}
    record Summary(long count, int total) {}

    public static void main(String[] args) throws Exception {
        List<Sale> sales = List.of(
            new Sale("North", 10),
            new Sale("South", 25),
            new Sale("North", 15),
            new Sale("South", 5)
        );

        int minimum = 10;
        long qualified = sales.stream()
            .filter(sale -> sale.amount() >= minimum)
            .count();
        int total = sales.stream()
            .mapToInt(Sale::amount)
            .sum();

        Map<String, Integer> byRegion = sales.stream().collect(
            Collectors.groupingBy(
                Sale::region,
                TreeMap::new,
                Collectors.summingInt(Sale::amount)
            )
        );
        Summary summary = sales.stream().collect(Collectors.teeing(
            Collectors.counting(),
            Collectors.summingInt(Sale::amount),
            Summary::new
        ));

        System.out.println("qualified=" + qualified);
        System.out.println("total=" + total);
        System.out.println("byRegion=" + byRegion);
        System.out.println("summary=" + summary);
        System.out.println("intSum=" + IntStream.rangeClosed(1, 5).sum());

        AtomicInteger completed = new AtomicInteger();
        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            List<Future<?>> futures = new ArrayList<>();
            for (int task = 0; task < 1000; task++) {
                futures.add(pool.submit(() -> {
                    completed.incrementAndGet();
                }));
            }
            for (Future<?> future : futures) {
                future.get();
            }
        } finally {
            pool.shutdown();
        }

        System.out.println("completedTasks=" + completed.get());
        System.out.println("originalSize=" + sales.size());
    }
}
~~~

Compile/run on **JDK 17 or later**:

~~~bash
javac AtomicCaptureDemo.java
java AtomicCaptureDemo
~~~

**Verified exact stdout:**

~~~text
qualified=3
total=55
byRegion={North=25, South=30}
summary=Summary[count=4, total=55]
intSum=15
completedTasks=1000
originalSize=4
~~~

### 11.1. Output analysis

**qualified=3:** There are three Sales with amount >= 10 (10, 25, and 15); the terminal count() returns the number of matching elements without using a mutable counter.

**total=55:** The amounts add up to 10+25+15+5=55. mapToInt().sum() returns the result directly.

**byRegion:** groupingBy with TreeMap::new and summingInt returns Map<String,Integer>. North has 10+15=25; South has 25+5=30. TreeMap makes the displayed key order predictable.

**summary:** teeing combines counting() and summingInt() into the record Summary(count=4,total=55), replacing two external mutable holders outside the pipeline.

**intSum=15:** The sum of numbers 1..5 is computed with IntStream.sum; no AtomicInteger is needed.

**completedTasks=1000:** 1000 Runnables are submitted to an ExecutorService with four workers. Each task completes one increment. Future.get waits for the corresponding task to finish, so after all futures return successfully, completed has the value 1000. It is precisely the shared state across worker threads that makes AtomicInteger appropriate.

**originalSize=4:** Stream terminal operations do not modify the source List in the example. AtomicInteger is used for task coordination rather than affecting the Sale data.

### 11.2. This is not a full production orchestration system

The example chooses a fixed pool so results are easy to verify. In a real application, you need to design policies for **task cancellation, retries, interrupts, shutdown/awaitTermination, exception handling, task limits, memory pressure**, and ensure no duplicate increments if an operation is retried. A single atomic counter does not provide distributed-system-level exactly-once guarantees.

If the compiler or runner only has JDK 17, the example uses records and Collectors.teeing, which are already supported.

## 12. Distinguishing AtomicInteger, int[], fields, and local variables

There are other “capture bypass” techniques that should also be avoided:

### 12.1. Single-element array as a holder

~~~java
int[] counter = {0};

values.forEach(value -> counter[0]++);
~~~

The code can compile because the counter reference is not reassigned. However, **counter[0]++ is not atomic** and can suffer lost updates in concurrent processing. Changing int to int[] does not guarantee thread-safety or make the lambda pure.

### 12.2. Field mutated from a lambda

~~~java
class Processor {
    int count;

    void process(List<Integer> values) {
        values.forEach(value -> count++);
    }
}
~~~

A field is not subject to the local capture constraint like a local variable, but **the state outlives the method and can be shared across calls/threads**, causing results to depend on execution history. If you are only counting elements, return a long from the method.

### 12.3. AtomicInteger as a mutable holder with atomic synchronization

~~~java
AtomicInteger counter = new AtomicInteger();
values.forEach(value -> counter.incrementAndGet());
~~~

Updating counter is atomic, but the code still performs a side effect. Only use it when **shared state itself** is the requirement; do not choose it as the default option for a pure aggregation.

### 12.4. Local int in a for loop

~~~java
int count = 0;
for (int value : values) {
    count++;
}
~~~

No capture, no holder object, and a clear result. In a sequential context, this can be a good choice if the loop is simpler than a Stream.

## 13. Error handling and pipeline termination issues

When a callback throws an exception, the terminal operation may not complete. A side-effect counter may then reflect only **a partial run**, making it hard to distinguish from a valid business result.

For example:

~~~java
AtomicInteger counter = new AtomicInteger();

try {
    Stream.of("10", "bad", "20")
        .map(Integer::parseInt)
        .forEach(value -> counter.incrementAndGet());
} catch (NumberFormatException error) {
    System.out.println("invalid input");
}
~~~

If a NumberFormatException occurs at the element "bad", the terminal operation fails; counter does not represent the total number of elements processed successfully in a complete transaction. Execution order can also depend on the source and stream mode.

If you need **per-record error handling**, design a result value representing success/failure, or apply validation before aggregating. Do not rely on AtomicInteger as the source of truth for the processing state of the entire pipeline.

### 13.1. When you need to count received events

In a long-running consumer/event handler, actual progress state may need to be updated when **each event is processed/committed by the system**. AtomicInteger can be appropriate to reflect the event count, provided the completion point and retry/duplicate policies are clearly defined. That is a concurrency and reliability problem, not a lambda capture problem.

## 14. Performance and maintainability

Using a shared AtomicInteger in parallelStream can lead to **contention**: multiple threads repeatedly updating the same memory address. For splittable reductions, a count/sum/collect operation usually delegates local result management and merging to the Stream library.

However, one should not claim that Stream is always faster than a for loop or AtomicInteger across every workload. Performance depends on data size, boxing, callbacks, parallelism, memory footprint, splitting strategy, and hardware.

**Evaluate according to three criteria:**

1. **Correctness:** does the result depend on side effects, callback order, errors, or shared state?
2. **Readability:** can a reader directly see “count”, “sum”, or “group” from the terminal/collector?
3. **Performance:** once the logic is correct, do benchmarks/profiling confirm the implementation is suitable?

Do not trade correctness for writing a shorter lambda or compiling past the effectively final constraint.

## 15. Checklist when reviewing lambdas with AtomicInteger

| Question | How to evaluate |
| --- | --- |
| Why is AtomicInteger here? | Is there genuine shared state that needs atomic updates? |
| Are you just trying to count elements? | Prefer filter(...).count() |
| Are you trying to compute a sum? | Prefer mapToInt/Long(...).sum() or an appropriate reduce |
| Are you trying to group/collect multiple values? | Prefer collect and downstream collectors |
| Is it used in map/peek/filter? | Beware of callbacks being elided or short-circuited |
| Is parallelStream used? | Check for side effects, contention, and ordering |
| Does the local variable really need reassignment? | Look at how to structure the result instead of a mutable holder |
| Could a simple loop be used? | No lambda or AtomicInteger needed if there is no concurrency |
| Does the update involve multiple steps? | AtomicInteger does not automatically guarantee multi-operation invariants |
| Is updateAndGet used? | The update function must be side-effect-free because it may retry |
| Is overflow handled? | Check int limits; choose long or another structure if needed |
| Do tests depend on callback counts? | Use business results, not assumptions about execution scheduling |

## 16. Common mistakes

**Mistake 1 — replacing int with AtomicInteger just to compile:** solves the compiler symptom while adding mutation and side effects.

**Mistake 2 — thinking effectively final means the object is immutable:** it only restricts reassigning the captured variable; the object's contents can be mutable.

**Mistake 3 — thinking AtomicInteger makes a callback a pure function:** incrementAndGet mutates externally observable state.

**Mistake 4 — using map/peek to increment a counter then calling count:** Stream can skip callbacks that do not change the element count.

**Mistake 5 — thinking parallel forEach gives deterministic order:** parallel forEach does not guarantee encounter order; do not assign source-order sequences solely with incrementAndGet.

**Mistake 6 — using an AtomicInteger as the identity in reduce:** a shared mutable identity can break the reduction contract even though individual additions are atomic.

**Mistake 7 — using a single-element int[] instead of AtomicInteger:** ++ on an array element is not atomic and is still a side effect.

**Mistake 8 — promoting a local variable to a field:** extends state lifetime, increasing the risk of history-dependent results or contention across calls.

**Mistake 9 — assuming increment atomicity suffices for all invariants:** two-step check-then-act still has races.

**Mistake 10 — side effects inside updateAndGet:** the function may be re-invoked on CAS retries, causing duplicate emails or log entries.

**Mistake 11 — taking a counter after a failed pipeline as a successful result:** processing may have stopped partway through.

**Mistake 12 — counting elements with forEach instead of count:** does extra work, creates an unnecessary holder, and reduces declarativeness.

**Mistake 13 — thinking a lambda always runs once per element:** there are also short-circuiting, optimizations, and stateful intermediate operations.

**Mistake 14 — assuming AtomicInteger is always faster:** multiple threads can contend on the same atomic variable; LongAdder has different trade-offs.

**Mistake 15 — treating all mutation as a bug:** local mutation in a for loop or a Collector's container can be reasonable; the issue is **implicit mutation of shared state** when you just need a value-returning computation.

## 17. Self-check questions

1. What is effectively final, and how does it differ from the final keyword?
2. Why does a lambda reading an un-reassigned local int compile, while a lambda incrementing a local int++ does not?
3. Why is AtomicInteger legally captured even though its internal value is incremented?
4. What is the difference between a final reference and an immutable object?
5. Why might using AtomicInteger in Stream.map followed by Stream.count fail to count the callbacks?
6. When you need the number of elements matching a predicate, what approach is more natural than an external AtomicInteger?
7. When you need a total amount, how do you use mapToLong or reduce to return the result?
8. Why can using AtomicInteger as the identity of a three-argument reduce be wrong even when addAndGet is atomic?
9. When is a local int variable in a for loop clearer than a Stream?
10. Give a scenario where multiple worker threads update shared state and AtomicInteger is an appropriate choice.
11. Why do get() followed by incrementAndGet() not form a single composite atomic check-and-write?
12. Why should a lambda in updateAndGet not send emails or write external data?
13. How does LongAdder differ from AtomicInteger in terms of throughput goals and read consistency?
14. Why does AtomicInteger not by itself prevent a pipeline from having side effects or data races on other data?
15. If a callback throws an error mid-pipeline, why is an external counter not necessarily a complete business result?
16. In the Java program in Section 11, which aggregations merely return values, and what is the genuine shared state?
17. How do you test and measure performance without depending on how many times map/peek callbacks are called by the optimizer?

**Conclusion:** **Effectively final** is Java's rule for capturing local variables, not an invitation to use AtomicInteger as a mutable int box. When you need to compute counts, sums, groups, or statistics in a Stream, **return the result using count/sum/reduce/collect** and keep callbacks from interfering with external state. Only use AtomicInteger when **the problem itself requires integer state updated atomically across concurrent operations**, with invariants, errors, retries, and bounds clearly designed.