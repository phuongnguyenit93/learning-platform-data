# peek() for Observing During Debugging in Java Stream

## 1. What Is peek() and What Is It Used For?

In Java, **Stream.peek(Consumer<? super T> action)** creates an **intermediate operation** that returns another Stream with elements of the same type T. When an element actually passes through this step, the action can receive that element to **observe** it: printing logs, inspecting state before/after a transformation step, checking filter conditions, or helping place breakpoints in an IDE.

A typical pipeline snippet:

~~~java
List<String> result = words.stream()
        .peek(word -> System.out.println("Before: " + word))
        .map(String::strip)
        .peek(word -> System.out.println("After: " + word))
        .filter(word -> !word.isBlank())
        .toList();
~~~

This is an **illustrative snippet**, assuming words is a List<String> containing no nulls and List is imported. Logging shows values flowing through two positions: before and after strip. **peek does not transform elements according to the Stream contract**; the map step is what creates new values from elements.

The Java documentation emphasizes that **peek is primarily intended to support debugging**. It is not a reliable place to write business data, send mandatory notifications, compute sums, update caches, or count records that must all be processed. The reason is not just a clean-code convention: **Streams are allowed to optimize, short-circuit, and parallelize**, making the execution of side effects in peek not guaranteed in the way an explicit loop normally provides.

**Key sentence to remember:** peek is suitable for **looking at** data when the pipeline actually passes through that step; peek should not be used to **define the result** of the pipeline or mandatory work that must occur.

## 2. Signature and Position of peek in a Stream Chain

General signature in Stream<T>:

~~~java
Stream<T> peek(Consumer<? super T> action);
~~~

This is an **abbreviated API signature** for explanation, not a standalone program. Its parts:

- **Stream<T>**: the element type remains T before and after peek. For example, a Stream<Order> remains a Stream<Order>.
- **Consumer<? super T>**: the action receives an element and has the SAM **void accept(T)**; it does not return a value to replace the element.
- **Intermediate operation**: like map or filter, peek returns a new Stream; merely declaring the pipeline does not start processing all the data.
- **Lazy**: work is triggered by a terminal operation such as toList, collect, forEach, reduce, findFirst, or count, yet **steps are not guaranteed to be called for every element**.
- **Pipeline**: if there are multiple peeks, each peek only observes the values at its corresponding position relative to the preceding/following operations.

Conceptual example of a pipeline:

~~~text
Stream<String> source
    |
    v
peek("raw")               -> observe initial value
    |
    v
map(String::strip)        -> produce normalized String
    |
    v
peek("normalized")        -> observe value after map
    |
    v
filter(notBlank)          -> discard elements that do not match
    |
    v
peek("accepted")          -> observe remaining elements
    |
    v
toList()                  -> request final result
~~~

This is a **conceptual diagram**, not Java syntax. Place peek **before filter** to see discarded elements as well; place peek **after filter** to see only the elements that continue past that step.

**Position determines log semantics.** Do not see an "accepted" log and infer that the element has completed all subsequent processing steps: if the terminal operation or later steps fail, the log in peek only proves that the element reached that position in a specific execution.

## 3. Java 17 Example: Observing Before/After map and filter

Create the file **PeekTraceDemo.java**:

~~~java
import java.util.List;
import java.util.Locale;

public class PeekTraceDemo {
    public static void main(String[] args) {
        List<String> words = List.of(
                "  Java  ", "Go", "  Kotlin ", "", " Java ");

        List<String> result = words.stream()
                .peek(s -> System.out.println("source=[" + s + "]"))
                .map(String::strip)
                .peek(s -> System.out.println("strip=[" + s + "]"))
                .filter(s -> s.length() >= 4)
                .peek(s -> System.out.println("accepted=[" + s + "]"))
                .map(s -> s.toUpperCase(Locale.ROOT))
                .toList();

        System.out.println("Result: " + result);
    }
}
~~~

Run with **JDK 17 or later**:

~~~bash
javac -encoding UTF-8 PeekTraceDemo.java
java PeekTraceDemo
~~~

Stdout in a sequential pipeline with a filter operation that needs to inspect each element:

~~~text
source=[  Java  ]
strip=[Java]
accepted=[Java]
source=[Go]
strip=[Go]
source=[  Kotlin ]
strip=[Kotlin]
accepted=[Kotlin]
source=[]
strip=[]
source=[ Java ]
strip=[Java]
accepted=[Java]
Result: [JAVA, KOTLIN, JAVA]
~~~

**Reading the output element by element:**

1. **"  Java  "** appears verbatim at source, is stripped to "Java", satisfies length >= 4 so it reaches accepted, and is then converted to "JAVA".
2. **"Go"** is stripped to "Go", which does not have at least four characters; therefore there is no accepted log for Go.
3. **"  Kotlin "** becomes "Kotlin", passes the filter, and is then converted to uppercase.
4. The empty string passes through the first two logs but is discarded by the filter.
5. **" Java "** produces a second "JAVA" after normalization.

In a **sequential pipeline** of this form, the logs reflect the processing of consumed elements and the correlation before/after each operation. However, **do not generalize from this example** that every terminal operation, data source, or parallel stream guarantees the same number of peek invocations. Java Stream has optimizations and short-circuiting rules analyzed below.

**Why not use peek to normalize?** An action such as **s -> s = s.strip()** only reassigns the local lambda parameter variable and does not change the stream element. To replace an element, use **map(String::strip)**.

## 4. Lazy Evaluation: Creating a Pipeline Does Not Run peek Yet

An intermediate operation **does not proactively traverse the source** when you declare it. Data is generally requested only when a terminal operation starts consuming the stream.

Create the file **PeekLazyDemo.java**:

~~~java
import java.util.List;
import java.util.stream.Stream;

public class PeekLazyDemo {
    public static void main(String[] args) {
        System.out.println("create pipeline");

        Stream<String> pipeline = List.of("a", "bb", "ccc")
                .stream()
                .peek(s -> System.out.println("visited: " + s))
                .filter(s -> s.length() > 1);

        System.out.println("before terminal");
        long count = pipeline.count();
        System.out.println("count: " + count);
    }
}
~~~

Run:

~~~bash
javac PeekLazyDemo.java
java PeekLazyDemo
~~~

Stdout:

~~~text
create pipeline
before terminal
visited: a
visited: bb
visited: ccc
count: 2
~~~

Explanation:

- At the **pipeline** declaration step, Java has constructed the chain of operations, but peek has not printed any "visited" line yet.
- **count()** is a terminal operation. In this example with **filter(s -> s.length() > 1)**, Java must inspect each element to know how many remain; the elements pass through peek before filter.
- Because all three source elements are inspected, there are three visited lines. Among them, only two elements ("bb" and "ccc") satisfy the condition, so count equals 2.
- A Stream pipeline can only be consumed once; after count, you must not invoke another terminal operation on the same already-used pipeline object.

**Note:** Having a terminal operation does not mean every peek will run. The example above was chosen so that inspecting the data is necessary; calling count on a source with a known size can be optimized without traversing through peek at all.

## 5. Big Trap: count() May Not Execute peek

Since modern Java versions, a Stream can **compute the count() result without traversing each element** if the source already knows its exact size and the pipeline does not change the element count. Because peek by contract does not alter the elements or size, Java can skip the entire peek action.

Example:

~~~java
long size = List.of("a", "bb", "ccc")
        .stream()
        .peek(s -> System.out.println("debug: " + s))
        .count();

System.out.println(size);
~~~

This is an **illustrative snippet** inside a method with List imported. In Java 17, the Stream implementation on a sized list can compute **3** directly without calling the Consumer in peek. Therefore, **you cannot assert that three debug lines will always be printed**. Relying on a count-style terminal operation to "force" peek logging to run is wrong.

From the Stream contract perspective:

~~~text
Source with known size, no operation changing element count:
  count() can retrieve the size directly
  -> no need to traverse each element
  -> peek might not run

With filter changing whether elements are kept:
  to know the exact count, the predicate must be evaluated
  -> typically the pipeline must traverse the relevant elements
~~~

**Important point:** peek is an **intermediate operation**, and Java does not promise to produce side effects in peek for every element if the terminal result can be determined without executing that action. A pipeline's functionality is defined by its output data, not by incidental log lines.

In many cases, Stream optimizations can elide not only peek but also other steps if the terminal operation's result does not depend on them and optimization conditions are met. Never write code whose business correctness depends on side effects of intermediate steps.

## 6. Short-Circuit: Some Elements Do Not Need to Be Seen

Terminal operations such as **findFirst**, **findAny**, **anyMatch**, **allMatch**, **noneMatch**, or intermediate operations such as **limit** can cause a pipeline to **stop early**.

If only the first matching element is needed, Java does not necessarily have to walk through the entire source.

Create the file **PeekShortCircuitDemo.java**:

~~~java
import java.util.stream.IntStream;

public class PeekShortCircuitDemo {
    public static void main(String[] args) {
        int firstEven = IntStream.rangeClosed(1, 5)
                .peek(n -> System.out.println("visit=" + n))
                .filter(n -> n % 2 == 0)
                .findFirst()
                .orElse(-1);

        System.out.println("firstEven=" + firstEven);

        boolean found = IntStream.rangeClosed(1, 5)
                .peek(n -> System.out.println("check=" + n))
                .anyMatch(n -> n == 3);

        System.out.println("found=" + found);
    }
}
~~~

Run:

~~~bash
javac PeekShortCircuitDemo.java
java PeekShortCircuitDemo
~~~

Stdout with a sequential pipeline having encounter order:

~~~text
visit=1
visit=2
firstEven=2
check=1
check=2
check=3
found=true
~~~

**Explanation:**

- **findFirst()** needs the first even element, so it only needs to inspect 1 and then 2. Numbers 3, 4, and 5 do not need to reach peek in that pipeline.
- **anyMatch(n -> n == 3)** finishes as soon as it finds 3, so it does not need to continue checking 4 and 5.
- Each terminal operation in this example operates on **a separate Stream** because a consumed Stream cannot be reused.

**Note on parallel streams:** when running in parallel, the system may have already processed multiple elements before the stop signal propagates. Do not rely on the log count or exact observation order in a parallel pipeline matching the sequential example's output.

### 6.1. skip and limit Change the Set of Observed Elements

If you place peek after a skip or limit step, it only sees the elements that actually reach that position. If you place peek **before** skip/limit, you may see more elements. However, optimizations can alter action execution; do not use log counts as the source of truth for processed data.

Illustrative example:

~~~java
List<Integer> result = IntStream.rangeClosed(1, 6)
        .boxed()
        .skip(2)
        .limit(3)
        .peek(n -> System.out.println("selected=" + n))
        .toList();
~~~

This is an illustrative snippet requiring IntStream and List to be imported. The resulting data is **[3, 4, 5]**. peek is placed after skip/limit to help observe the elements reaching the final selection step; it does not necessarily observe the entire source [1, 2, 3, 4, 5, 6].

## 7. Streams Usually Process Element-by-Element, Not Line-by-Line

Beginners might imagine Java executes like this:

~~~text
Step 1: first peek for all elements
Step 2: map for all elements
Step 3: filter for all elements
Step 4: final peek for all elements
~~~

In many simple sequential pipelines (stateless operations), Stream **fuses processing steps** per element: one element goes through the required steps before moving to the next element. That is why the stdout of **PeekTraceDemo** looks like:

~~~text
source=[  Java  ]
strip=[Java]
accepted=[Java]
source=[Go]
strip=[Go]
...
~~~

rather than printing all source lines first and then all strip lines.

However, this is **not the only execution model**. Some **stateful** intermediate operations such as sorted or distinct may require buffering, seeing many elements before emitting data downstream. Parallel pipelines can also split work across multiple tasks.

**Conclusion:** Use peek logs to understand values flowing through stages, but do not write business logic that assumes a per-step/per-element execution model is invariant across all Stream types.

## 8. Placing peek Before and After sorted to Understand Stateful Operations

For example, sorted can buffer values and then emit them in a new order. Create the file **PeekSortedDemo.java**:

~~~java
import java.util.List;

public class PeekSortedDemo {
    public static void main(String[] args) {
        List<String> result = List.of("c", "a", "b")
                .stream()
                .peek(s -> System.out.println("before=" + s))
                .sorted()
                .peek(s -> System.out.println("after=" + s))
                .toList();

        System.out.println("result=" + result);
    }
}
~~~

Run:

~~~bash
javac PeekSortedDemo.java
java PeekSortedDemo
~~~

Stdout in the sequential example:

~~~text
before=c
before=a
before=b
after=a
after=b
after=c
result=[a, b, c]
~~~

Here:

1. The source supplies elements in the order **c, a, b**.
2. sorted needs the data to determine the ordering, so the three **before** logs appear before the **after** logs in this sequential implementation.
3. After sorted, elements are emitted in natural order **a, b, c**, observed by the second peek.
4. Terminal **toList()** returns a list in the stream's current encounter order.

Placing peek on both sides of sorted is very useful for observing where order changes, but **do not use it to guarantee the order of side effects on a parallel stream**.

**A common misconception:** sorted changes **order**, not necessarily content or count; filter can drop elements; distinct can drop duplicates; map changes values. Logs must be read in the context of the operations before/after them.

## 9. peek Does Not Replace map, filter, or forEach

Many bugs happen when APIs are used for the wrong purpose:

| API | Role | Result |
| --- | --- | --- |
| **map(Function<T,R>)** | Transform element from T to R | Stream<R> |
| **filter(Predicate<T>)** | Keep elements matching condition | Stream<T> |
| **peek(Consumer<T>)** | Observe elements while pipeline executes | Stream<T> |
| **forEach(Consumer<T>)** | Terminal operation for each output element to process | void |
| **forEachOrdered(Consumer<T>)** | Terminal action in encounter order of an ordered stream | void |
| **collect(...)** | Gather into a data structure/result | Depends on collector |
| **toList()** | Collect Stream results into a List | List<T> |

Example of **wrong transformation intent**:

~~~java
// DO NOT USE peek to replace map.
Stream<String> pipeline = words.stream()
        .peek(s -> s.toUpperCase());
~~~

This is an illustrative snippet, assuming a Stream<String>. **String.toUpperCase()** returns a new String; peek's action ignores that return value, so the original element is **not replaced**. The program still compiles, but it does not perform the transformation the author intended.

The right way:

~~~java
Stream<String> pipeline = words.stream()
        .map(s -> s.toUpperCase(Locale.ROOT));
~~~

This illustrative snippet needs Locale imported and assumes words has an appropriate type. With immutable Strings, map is what puts the uppercased strings into the output Stream.

### 9.1. Mutating Mutable Objects in peek Is Another Trap

Suppose an Order object has a setter:

~~~java
orders.stream()
        .peek(order -> order.setStatus("PAID"))
        .toList();
~~~

This is an **illustrative anti-pattern**, assuming the types/methods exist. It attempts to use peek to update business state. There are risks:

- The action in peek may **not run** in optimized or short-circuited pipelines.
- Mutating object state causes **side effects**, making the stream hard to reason about and prone to data races in parallel streams.
- toList() returns a list of references to the elements; it does not guarantee that a transaction or external state update succeeded.
- The code hides update intent inside a method named peek, making code reviews harder.

If data transformation is needed, consider **map** to create new values (preferring immutability). If updating objects or calling services is required, use an explicit workflow with error handling, transactions, synchronization, and testing; do not put mandatory work inside peek.

### 9.2. forEach and forEachOrdered Also Need Proper Context

**forEach** is a terminal operation that applies an action to the resulting stream elements, though in parallel streams it does not guarantee preserving encounter order. **forEachOrdered** guarantees encounter order if the Stream has an encounter order; however, it still does not turn a pipeline into a transaction and does not automatically make the action thread-safe.

If the goal is to log the final output, a clearer approach may be to compute the result first, then iterate over the result in order and log it. If you want to observe *between* stages, peek is the appropriate debugging tool.

## 10. Using peek to Identify Elements Filtered Out

A useful pattern when debugging business rules:

~~~java
List<Order> eligible = orders.stream()
        .peek(o -> debug("input", o))
        .filter(isPaid)
        .peek(o -> debug("after paid", o))
        .filter(isDomestic)
        .peek(o -> debug("after domestic", o))
        .toList();
~~~

This is an **illustrative snippet**, assuming Order, the Predicates, and the debug method are already defined. In practice, an Order might fail the first condition and never appear in the "after paid" log. An Order that passes paid but fails domestic will appear in "after paid" but not in "after domestic".

**Do not infer why an element was excluded solely from its absence in the final log**. To know the full reason, you may need to log/trace directly in the rule or build a structured check result (**Decision**, **ValidationResult**, list of rejection reasons). Using peek between filters only tells you **which steps** the element passed through when the action ran.

### 10.1. When Null Elements Exist

The following snippet can throw a NullPointerException:

~~~java
employees.stream()
        .peek(e -> System.out.println(e.name()))
        .filter(Objects::nonNull)
        .toList();
~~~

This is an **intentionally dangerous illustrative snippet**: peek reads a property before filtering out null elements. If the source contains nulls, you must place a guard before dereferencing:

~~~java
employees.stream()
        .filter(Objects::nonNull)
        .peek(e -> System.out.println(e.name()))
        .toList();
~~~

Objects must be imported and Employee.name() must exist accordingly. **Safe peek placement** must also obey the same null, exception, and input data rules as map and filter.

If logging to see null inputs as well, print the object itself instead of calling a property when it is unsafe:

~~~java
employees.stream()
        .peek(e -> System.out.println("input=" + e))
        .filter(Objects::nonNull)
        .toList();
~~~

This is an illustrative snippet. Here **String.valueOf(Object)** is used during string concatenation; for null, it produces the text "null" instead of dereferencing Employee. However, calling **toString()** on a non-null object can still have side effects or throw an exception if the class defines an unsafe method.

## 11. Parallel Streams: Do Not Infer Data Order from Log Order

With **parallelStream()** or **stream().parallel()**, elements can be processed by multiple different tasks/workers:

~~~java
List<Integer> values = List.of(1, 2, 3, 4, 5);

List<Integer> result = values.parallelStream()
        .peek(n -> System.out.println(
                Thread.currentThread().getName() + ": " + n))
        .map(n -> n * 2)
        .toList();

System.out.println(result);
~~~

This is an illustrative snippet requiring List to be imported. The resulting List still preserves the source's encounter order when ordered: **[2, 4, 6, 8, 10]**. However, **the order of peek lines, thread names, and element partitioning are not fixed**, so you should not write an exact expected stdout for parallel logs.

Distinguish between:

- **Result order** of the terminal operation, which can be defined by the API contract and encounter order.
- **Execution timing order** of peek's action, which does not necessarily match that order.
- **Executing thread** of the action, which can vary across elements.
- **Visibility and state safety** of objects read/written by the action, which still must be considered separately.

For example, counting with `int[] counter = {0};` and `peek(x -> counter[0]++)` in a parallel stream is an anti-pattern: non-atomic updates can lose increments; more importantly, peek can even be optimized away. Even using AtomicInteger **does not turn peek into a reliable business counting mechanism** when the API does not guarantee invoking the action for every element.

If the goal is **counting elements**, use **count()**. If the goal is summing, use **mapToInt(...).sum()**, **reduce**, or an appropriate collector; if mandatory telemetry is needed, integrate it at an execution point with a clear contract.

## 12. Other Limitations of Side Effects in Streams

### 12.1. Stateless and Non-Interfering Are Key Principles

Stream behavioral parameters should be **non-interfering** (not modifying the data source while the pipeline is traversing it) and mostly **stateless** (not depending on mutable state that changes between invocations). Injecting side effects in peek easily violates these principles.

Example of what not to do:

~~~java
List<Integer> values = new ArrayList<>(List.of(1, 2, 3));

values.stream()
        .peek(n -> values.add(n + 10))
        .toList();
~~~

This is an **illustrative anti-pattern**, assuming List and ArrayList are imported. It modifies the ArrayList source during traversal, which can lead to a ConcurrentModificationException or undefined behavior under the Stream contract. Do not use peek to "add data back into the same source while traversing it".

**Do not interpret a single run's output as a guarantee**: a specific test run might appear to finish, yet the behavior still violates the non-interference rule.

### 12.2. Do Not Rely on Action Invocation Counts

Side effects of behavioral parameters in a pipeline may be elided if the implementation can compute the result in an equivalent way. Short-circuiting also prevents some elements from reaching the action step. Therefore:

- Do not verify processing correctness by **counting peek lines**.
- Do not use peek to write mandatory audit records per transaction.
- Do not expect the action to run "exactly once per source element".
- Do not store auxiliary state inside map/filter/peek and use it to determine the final result.

To establish **successful processing** in a real system, define clear transaction/task boundaries and log at a point with an explicit contract, rather than relying solely on an intermediate Stream step.

### 12.3. Do Not Handle Errors by Swallowing Exceptions in peek

Example:

~~~java
stream.peek(item -> {
    try {
        sendToRemoteService(item);
    } catch (Exception ignored) {
        // Ignore error.
    }
}).toList();
~~~

This is an **anti-pattern** snippet, not standalone, assuming stream and sendToRemoteService are available. If sending data is the main job, putting it in peek and swallowing errors causes inconsistent data states that are very hard to spot in code reviews.

If a debugging action can throw an error, it can fail the pipeline; if resilient logging is needed, use a logging framework and appropriate operational policies, avoiding accidentally masking business errors. A peek statement is not an isolation boundary for exceptions or transactions.

## 13. peek with sorted, distinct, limit, and Stateful Steps

What peek outputs often depends on position:

| Pipeline | What does peek intend to see? | Notes |
| --- | --- | --- |
| **peek → map** | Value before transformation | Map may return a different type |
| **map → peek** | Value after transformation | If mapper produces null, logging must tolerate null |
| **peek → filter** | Elements reaching the step before filtering | Some will be discarded |
| **filter → peek** | Elements that passed the filter | Does not mean the entire pipeline has completed |
| **peek → sorted** | Source order in a sequential pipeline | sorted may buffer before emitting |
| **sorted → peek** | Order after sorting | Parallel logging may not follow encounter order |
| **peek → distinct** | Elements before duplicate removal | May contain duplicates |
| **distinct → peek** | Elements after distinct | No guarantee of counting via logs |
| **limit → peek** | Elements reaching the step after limit | Short-circuiting may reduce element count |
| **peek → count** | May see no logs at all | If count optimizes using source size |

The table helps decide **where to place breakpoints**. It is not a set of guarantees that peek's Consumer will definitely be called in all cases.

### 13.1. Use Breakpoints Instead of Mutating Logic

When debugging with an IDE:

1. Place a breakpoint inside the lambda passed to peek to inspect the element, thread, and state at a specific step.
2. Use the debugger to inspect variables/stack frames; be aware that in parallel pipelines multiple threads can interleave.
3. When investigating a hard-to-reproduce bug, consider temporarily switching to **stream.sequential()** or an explicit loop to check ordering. That is for diagnosis and does not mean production code should change parallelization without evaluation.
4. After fixing the bug, remove temporary logs or lower the log level to avoid runtime overhead and data exposure risks.

**Do not debug by mutating data inside peek**. If you need to inspect after a transformation, placing peek before/after map, filter, or sorted is enough to observe.

## 14. Attaching Contextual Logging to a Pipeline

A good log should answer: "which element is being seen, at which stage, in which run?" Example:

~~~java
Function<String, String> normalize = String::strip;

List<String> cleaned = inputs.stream()
        .filter(Objects::nonNull)
        .peek(x -> logger.debug("stage=raw value={}", x))
        .map(normalize)
        .peek(x -> logger.debug("stage=normalized value={}", x))
        .filter(x -> !x.isBlank())
        .toList();
~~~

This is an **illustrative snippet**, assuming logger supports message placeholder syntax, with Function, List, Objects imported and an appropriate inputs source. **No logger is declared**, so do not copy it verbatim as a standalone file.

To control overhead:

- Use **debug/trace level** for temporary information, avoiding excessive printing in production.
- Do not log **sensitive data** (tokens, passwords, personal information), even while debugging.
- When the action builds large Strings or calls an expensive **toString()**, consider checking the log level first or using a logging API that handles arguments efficiently.
- Do not assume a thread-safe logger means all objects referenced by peek are thread-safe.
- Do not treat peek logs as official audit records because the JVM may skip the action in some pipelines.

If you need to describe why elements were discarded, logging inside a **business Predicate** or creating a **structured validation result** can be clearer; peek between filters only observes the elements passing through each stage.

## 15. Comparing peek with an Explicit Loop

Sometimes you **must** perform an action for every item and handle errors item by item. A loop states that intent more clearly:

~~~java
for (Order order : orders) {
    auditService.recordAttempt(order);
    if (policy.accepts(order)) {
        accepted.add(order);
    }
}
~~~

This is an illustrative snippet, assuming Order, auditService, policy, and accepted are already defined. If audit must run for every order in this loop, the action is placed directly in the flow; the caller must still handle exceptions/transactions as required. An explicit loop does not automatically provide retries or synchronization either, but at least it does not hide mandatory work inside an intermediate operation.

If you only want to view data **for debugging**, a Stream with peek is often concise and easy to insert into an existing pipeline:

~~~java
List<Order> result = orders.stream()
        .filter(policy::accepts)
        .peek(o -> logger.debug("accepted candidate {}", o.id()))
        .toList();
~~~

This illustrative snippet requires the types/methods/variables to be defined. This is an **observation log**, not a promise that every valid order has been successfully audited.

**Practical balance:** Keep pipelines declarative for pure data transformation logic; use toggleable observation tools to track down bugs; use explicit workflows for mandatory, ordered side effects with retry and transactional requirements.

## 16. Common Mistakes When Using peek

| Misconception/mistake | What can happen | Right approach |
| --- | --- | --- |
| Calling stream().peek(...) and expecting logs to appear | No terminal operation yet, so no data is consumed | Run an appropriate terminal operation; remember optimizations may apply |
| Using peek(...).count() to force the action to run | count can read the size without traversing | Do not use peek for mandatory side effects |
| Thinking peek modifies elements | Consumer does not produce replacement values in a Stream | Use map for transformations |
| Writing to database/cache/audit inside peek | May be skipped, run unexpectedly, or duplicate side effects | Move business work to a workflow with a clear contract |
| Assuming peek runs for every source element | filter/limit/findFirst/anyMatch can stop or drop elements | Check position and terminal operation |
| Relying on System.out.println order in parallel streams | Logs can interleave across threads | Rely on result data and APIs with encounter-order guarantees |
| Placing peek that reads properties before a null guard | May throw NullPointerException | Place filter(Objects::nonNull) before it or check inside the action |
| Modifying the source ArrayList from peek | Violates non-interference, may throw ConcurrentModificationException | Do not modify the source while traversing |
| Counting elements with counter++ in peek | Race condition, action is not guaranteed to run | Use count() or an appropriate collector |
| Leaving verbose logs in production | Increases overhead, risks exposing data | Lower log level, remove temporary instrumentation |
| Recording "processed" right before the next step | Later steps may fail; logs become misleading | Record business state at actual completion boundaries |

## 17. Debugging Checklist with peek

Before adding peek to a pipeline, ask:

1. **Is the goal observation or state update?** If a state update is mandatory, do not use peek.
2. **Can the source contain null?** Avoid unchecked dereferencing in logs.
3. **Do you want to see data before or after map/filter/sorted?** Place peek in the right spot.
4. **What is the terminal operation?** Does it run the pipeline? Does it allow shortcuts like count?
5. **Are there findFirst, anyMatch, or limit?** If so, only part of the source may pass through.
6. **Is the Stream running in parallel?** Do not infer order from log timestamps.
7. **Does the logger have side effects or significant cost?** Limit volume and sensitive data.
8. **Do you need data to reproduce a bug?** You can extract transformation steps or use fixtures/breakpoints instead of just watching the console.
9. **Are you relying on peek call counts to assert correctness?** Write tests that check output data, not just log line counts.
10. **Can peek be removed after debugging is done?** Keep the pipeline pure and maintainable.

## 18. Exercises

### Exercise 1: Predict Output with filter

Given the list **["a", "bb", "ccc"]**, write the pipeline **peek → filter(length >= 2) → peek → toList**. Predict which elements appear at the two peeks in a sequential stream and the final result list.

Hint: before filter there are a, bb, ccc; after filter there are bb, ccc. Note that this is a prediction for a specific pipeline that must traverse to build the result, not a guarantee for all Stream optimizations.

### Exercise 2: Why Doesn't peek with count Run?

Try:

~~~java
List.of(1, 2, 3).stream()
        .peek(System.out::println)
        .count();
~~~

This is an illustrative snippet. Why might you not see three lines of numbers? Distinguish between the value **count = 3** and whether **peek's action executes**. Then add a filter with a condition that makes the output size unknown in advance and observe the difference.

### Exercise 3: Observing Before/After sorted

Given **["z", "a", "m"]**. Write **peek → sorted → peek → toList** and explain why the logs before/after sorted can form two differently ordered groups in a sequential pipeline.

### Exercise 4: Short-Circuit

Using IntStream.rangeClosed(1, 100), add peek, filter numbers divisible by 7, then **findFirst()**. Predict the first number selected. Why do elements greater than 7 not need to pass through the entire sequential pipeline?

### Exercise 5: Wrong Transformation with peek

Given immutable Strings, why does **peek(s -> s.toUpperCase())** not convert the result to uppercase? Rewrite it using **map(s -> s.toUpperCase(Locale.ROOT))** and verify the output list.

### Exercise 6: Audit Design

A system requires writing an audit record for every transaction, regardless of whether the transaction passes the filter. Why should you not write **orders.stream().peek(audit::record).filter(...).count()**? Propose a workflow with a clear audit boundary and error reporting capability.

### Exercise 7: Observing in a Parallel Pipeline

Write a parallel stream and peek to print the number along with the thread name. Compare the log order with the result order of **toList()** on a source with encounter order. Explain why log order must not be used to reconstruct the exact result order.

## 19. Takeaways

- **peek(Consumer)** is an intermediate operation primarily used to **observe** elements during debugging, not a replacement for **map**, **filter**, or mandatory business work.
- **Lazy streams:** declaring a pipeline does not execute peek. A terminal operation is required, yet even that **does not guarantee** peek runs on every element.
- **count can optimize away traversal** when the size is known; **findFirst/anyMatch/limit** can stop early.
- **The order of peek logs** is not a general contract, especially with **sorted**, **parallel streams**, and optimizations.
- **Do not use side effects in peek as a source of truth** to write audits, update state, count elements, or drive business logic.
- Use **map** to transform, **filter** to select, **collect/toList** to produce results, and **explicit workflows** when side effects must be guaranteed to occur.

One question is enough to choose the right tool: **"If the JVM does not call peek's action during a valid execution, is the application still correct?"** If the answer is **no**, that action should not be placed inside peek.