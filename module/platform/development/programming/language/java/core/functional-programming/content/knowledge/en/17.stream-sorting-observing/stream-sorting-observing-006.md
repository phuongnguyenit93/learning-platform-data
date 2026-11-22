# Why is Stream.peek() Unsuitable for Mandatory Business Operations?

## 1. The problem: "having written peek" does not mean "having executed the business logic"

In Java Stream, `peek(Consumer<? super T> action)` is an **intermediate operation** primarily useful for **observing** elements passing through a pipeline, usually for debugging. It is not a command that forces the program to execute a business action on each element.

A plausible-looking but dangerous example:

```java
long count = orders.stream()
        .peek(order -> sendInvoice(order))
        .count();
```

This is a **flawed-by-design illustration snippet**; `orders` and `sendInvoice` are hypothetical application components, not a standalone program. The intention is "count the orders and send an invoice for each order". However, **`count()` can compute the result without traversing the elements** when the source knows its size and the steps in the pipeline do not change the number of elements. In that case, the action in `peek` may **not be called even though `count()` still returns the correct result**.

This is not an accidental bug in a particular Java version; it conforms to the **Stream API contract**. The Javadoc states that side effects in behavioral parameters may not be executed for every element, or may not even run at certain stages, if their execution does not affect the pipeline's result. `peek` is not a mechanism to confirm that an invoice was sent, inventory was updated, data was persisted, or a payment was processed.

**Core message:** if an action is **mandatory for business correctness**, do not hide it inside `peek()`. Place it in an intentional processing step with appropriate error handling and transaction mechanisms.

## 2. What contract does peek() actually have?

The API signature in Java 17:

```java
Stream<T> peek(Consumer<? super T> action);
```

This is a **signature excerpt for reading the API**, not a method to define yourself.

`peek`:

- Accepts a `Consumer` (an action that returns no value).
- Returns a `Stream<T>` to continue chaining the pipeline.
- Logically, allows observing elements as they are processed by the pipeline.
- Is an **intermediate operation**, so calling `peek(...)` alone does not start traversing data.
- Does not modify output elements by `peek`'s own contract; if you want to **transform data**, use `map`.
- Provides no guarantee that every element will trigger `action`, nor does it guarantee the order or thread in which side effects run when the pipeline runs in parallel.

Example of observation during development:

```java
List<String> normalized = names.stream()
        .map(String::trim)
        .peek(s -> System.out.println("normalized=" + s))
        .filter(s -> !s.isEmpty())
        .toList();
```

This is an **illustration snippet inside a method**, assuming `names` is a `List<String>` and `List` is imported. The `peek` part helps developers observe the intermediate state of an element when the action is executed. However, application code **should not depend** on each log line being printed exactly once and in the exact order across all types of pipelines.

It is necessary to distinguish **logging for debugging** from **legally/business-mandated audit logging**. An audit record needs to be executed in a controlled manner, with error checking and durable storage according to the application contract; that is not the role of `peek`.

## 3. First reason: Streams are lazy; merely building a pipeline runs nothing

A Stream pipeline is often described as a chain of intermediate operations. For example:

```java
List<String> traces = new ArrayList<>();
var pipeline = List.of("An", "Binh", "Chi").stream()
        .peek(traces::add)
        .filter(s -> s.length() > 2);
```

This is a snippet placed in a method with `List` and `ArrayList` imported. Immediately after creating `pipeline`, `traces` **is still empty**: `peek` and `filter` are lazy intermediate steps.

When running a terminal operation:

```java
List<String> result = pipeline.toList();
```

In this specific sequential case, the elements pass through `peek` before `filter`, producing `traces = [An, Binh, Chi]` and `result = [Binh, Chi]`. However, seeing the action run in this scenario **does not create a general guarantee** that it runs for every terminal operation, on every source, or after the pipeline is optimized.

Therefore, the statement `orders.stream().peek(this::persist)` **does not make `persist` run immediately**. If the application does not invoke a terminal operation, that action may never happen at all.

## 4. Second reason: count() can skip peek() completely

Here is the decisive example:

```java
List<String> names = List.of("An", "Binh", "Chi");
List<String> observed = new ArrayList<>();

long count = names.stream()
        .peek(observed::add)
        .count();

System.out.println(count);     // 3
System.out.println(observed);  // []
```

These are statements inside a method with `List` and `ArrayList` imported; the result `observed = []` has been verified on Java 17.

Why?

1. `List` provides the element count deterministically.
2. `peek` does not change the number of elements in the stream.
3. `count()` can obtain the element count from the source's size information instead of traversing each element.
4. If there is no traversal, `peek`'s action does not run.

**Important:** not **every** `count()` skips `peek`. When a pipeline has a step that affects the number of elements (for example, `filter` depending on a condition), the implementation may need to traverse to compute the count. However, **any mandatory business action must not depend on this optimization condition**.

Especially dangerous:

```text
long total = invoices.stream()
        .peek(invoice -> chargeCustomer(invoice))
        .count();
```

This is **pseudocode illustrating what to avoid**. If `chargeCustomer` is a mandatory payment operation, a terminal operation can still succeed without charging a single invoice. Moreover, if there is an error or retry, placing payment inside a pipeline does not by itself solve transactional issues.

**Do not fix this by adding a dummy operation "to force peek to run"**. This strategy still relies on unguaranteed side effects and is easily broken when optimizing or changing the pipeline structure.

## 5. Third reason: short-circuiting does not process all elements

Many terminal operations are allowed to terminate once they have enough information:

- `findFirst()`, `findAny()`: once a matching element is found, there is no need to read the rest.
- `anyMatch()`: once one element satisfies the predicate, it can stop.
- `allMatch()`: once an element does not satisfy the predicate, it can stop.
- `noneMatch()`: once an element satisfies the predicate, it can stop.

Intermediate steps `limit()` or `takeWhile()` can also reduce the number of elements to process or stop early based on a condition.

Example:

```java
List<Integer> visited = new ArrayList<>();
int first = List.of(1, 2, 3, 4).stream()
        .peek(visited::add)
        .filter(n -> n > 1)
        .findFirst()
        .orElse(-1);
```

These are statements in a method body with `List` and `ArrayList` imported. In the **sequential ordered** example tested on Java 17, `first = 2` and `visited = [1, 2]`. `3` and `4` do not go through `peek`'s action because `findFirst` already has its answer.

Suppose `peek` sends a notification to every user, while the terminal operation below only needs to check whether there is **at least one** user. The pipeline can succeed **before** all notifications are sent. That is a business bug.

The key point: **a terminal operation succeeding does not mean all elements have passed through peek**. This is even more important when the pipeline has an infinite source or an operation that allows early termination.

## 6. Fourth reason: parallelism, ordering, and side effects

With `parallelStream()`, stages can execute across multiple threads, and the actual order of side effects in `peek` **does not always follow encounter order**. Even when the final result respects ordering where required, printing logs or updating shared state inside `peek` can be observed in a different order.

Example that **should not be used for business logic**:

```text
List<String> audit = new ArrayList<>();
orders.parallelStream()
        .peek(o -> audit.add("AUDIT:" + o.id()))
        .forEach(o -> doWork(o));
```

This is illustrative pseudocode with hypothetical `orders` and `doWork`. `ArrayList` is not protected when multiple threads write concurrently; the program may encounter race conditions or incomplete results. Using `Collections.synchronizedList` or a synchronized structure only solves **part** of the data race problem; it **does not fix** the mistake of putting a mandatory audit action in `peek`.

In parallel operations:

- **The invocation order of side effects is not guaranteed by default**, even with a source that has encounter order.
- `Consumer`s that touch shared state may require synchronization; however, synchronization does not automatically guarantee exactly-once execution in external systems.
- An exception on one thread can cause the terminal operation to fail; one must not infer that all other side effects have completed or been rolled back.
- An element may not have been processed yet when the pipeline short-circuits. `peek` should not be used as the sole place to execute an action that requires proof of completion.

`forEachOrdered` is a terminal operation option when an action must **execute in encounter order**, but if the action is writing to a DB, sending an email, or processing a payment, **you still need to manage retries, idempotency, transactions, and errors** separately.

## 7. Distinguishing peek(), map(), filter(), forEach(), and forEachOrdered()

| API | Operation type | Role | Should it contain mandatory business operations? |
| --- | --- | --- | --- |
| `peek(action)` | Intermediate | Observe elements, mainly for debugging | **No** |
| `map(transform)` | Intermediate | Transform element `T → R` | **Should not** embed mandatory side effects; use for data transformation |
| `filter(predicate)` | Intermediate | Keep elements matching a condition | **Do not** use the predicate to perform side effects |
| `forEach(action)` | Terminal | Perform action on stream elements | Can be used when the action is the processing goal, but does not by itself guarantee transactions/exactly-once |
| `forEachOrdered(action)` | Terminal | Perform action in encounter order if the stream is ordered | Useful when order matters; still requires business-level design |
| `toList()` | Terminal | Collect computed results into a List | Suitable for separating the preparation step from the business execution step |
| `for` loop | Non-Stream | Execute explicitly in programmatic order | Often clearest when each action needs individual error and state handling |

`map` may run zero or more times depending on the terminal operation; even though it is usually executed in `toList()`, you should not turn it into a place for processing payments. `map` is suitable for **creating data** in preparation for the next step. If the code needs to do something mandatory, write a separate step with a clear name and contract.

`forEach`/`forEachOrdered` are terminal operations that express the intent to **perform an action**, not to "turn side effects into a transaction". For operations with external system effects, the caller needs to define how to handle the case where the third action throws an exception after the previous two succeeded.

## 8. Java 17 program: observing behavior and alternatives

Create the file `PeekBusinessSafetyDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

public class PeekBusinessSafetyDemo {
    public static void main(String[] args) {
        List<String> names = List.of("An", "Binh", "Chi");

        List<String> observed = new ArrayList<>();
        long count = names.stream().peek(observed::add).count();
        System.out.println("count=" + count);
        System.out.println("observedByPeek=" + observed);

        List<String> lazyObserved = new ArrayList<>();
        var pipeline = names.stream()
                .peek(lazyObserved::add)
                .filter(s -> s.length() > 2);
        System.out.println("beforeTerminal=" + lazyObserved);
        System.out.println("filtered=" + pipeline.toList());
        System.out.println("afterTerminal=" + lazyObserved);

        List<Integer> visited = new ArrayList<>();
        int first = List.of(1, 2, 3, 4).stream()
                .peek(visited::add)
                .filter(n -> n > 1)
                .findFirst()
                .orElse(-1);
        System.out.println("findFirst=" + first);
        System.out.println("visited=" + visited);

        List<String> events = names.stream()
                .map(String::toUpperCase)
                .toList();
        System.out.println("events=" + events);

        List<String> saved = new ArrayList<>();
        for (String event : events) {
            saved.add("saved:" + event);
        }
        System.out.println("saved=" + saved);

        AtomicInteger total = new AtomicInteger();
        names.parallelStream()
                .forEachOrdered(name -> total.incrementAndGet());
        System.out.println("forEachOrderedCount=" + total.get());
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 PeekBusinessSafetyDemo.java
java PeekBusinessSafetyDemo
```

**Verified** output:

```text
count=3
observedByPeek=[]
beforeTerminal=[]
filtered=[Binh, Chi]
afterTerminal=[An, Binh, Chi]
findFirst=2
visited=[1, 2]
events=[AN, BINH, CHI]
saved=[saved:AN, saved:BINH, saved:CHI]
forEachOrderedCount=3
```

Analysis:

1. **`count=3`, `observedByPeek=[]`:** this is the clearest example that `peek` is not an action guaranteed to execute.
2. **`beforeTerminal=[]`:** merely creating the `peek(...).filter(...)` pipeline performs no action yet.
3. **`filtered=[Binh, Chi]` and `afterTerminal=[An, Binh, Chi]`:** in this sequential run, `toList()` triggered traversal and `peek` observed each element before `filter`.
4. **`findFirst=2`, `visited=[1, 2]`:** the terminal operation finding the first element allowed early termination.
5. **`events` → `saved`:** creates **transformed data** using `map(...).toList()`, then executes an **explicit** loop. If this were a real save operation, the loop is where `try/catch`, transactions, logging, and error-handling policies belong.
6. **`forEachOrderedCount=3`:** the terminal `forEachOrdered` is called on a parallel stream from an ordered List; `AtomicInteger` is used to demonstrate a thread-safe counter. This does not turn the entire business operation into exactly-once across multiple program runs.

In the example, the `ArrayList` used to observe `peek` is only inside **sequential and controlled** pipelines. You should not take `observed::add` and switch to `parallelStream()` as a way to collect results.

## 9. Business problem: filter/transform first, then execute explicitly

Suppose a program has a list of orders. The goal is to prepare processing receipts for orders with a valid quantity, then execute the necessary commands. We should separate the **computation step** and the **step with side effects**.

File `ExplicitBusinessActionsDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class ExplicitBusinessActionsDemo {
    record Order(int id, int amount) { }
    record Receipt(int id, String status) { }

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order(101, 20),
                new Order(102, 0),
                new Order(103, 35));

        List<Receipt> planned = orders.stream()
                .filter(order -> order.amount() > 0)
                .map(order -> new Receipt(order.id(), "READY"))
                .toList();
        System.out.println("planned=" + planned);

        List<String> effects = new ArrayList<>();
        for (Receipt receipt : planned) {
            effects.add("persist:" + receipt.id());
        }
        System.out.println("effects=" + effects);

        List<String> ordered = new ArrayList<>();
        planned.parallelStream()
                .forEachOrdered(receipt -> ordered.add("send:" + receipt.id()));
        System.out.println("ordered=" + ordered);
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 ExplicitBusinessActionsDemo.java
java ExplicitBusinessActionsDemo
```

Output:

```text
planned=[Receipt[id=101, status=READY], Receipt[id=103, status=READY]]
effects=[persist:101, persist:103]
ordered=[send:101, send:103]
```

Explanation:

- Use `filter` to select orders with `amount > 0`; use `map` to create `Receipt` **values**. Do not send invoices or write to the database inside `peek`.
- `toList()` creates the `planned` list that can be inspected, verified, and passed to the next stage. Because the input data is finite and small in the example, materialization is appropriate.
- The `for (Receipt receipt : planned)` loop is where the `persist` action is modeled; in the example it only adds strings to a List, so no external service is needed.
- `forEachOrdered` illustrates a terminal operation in encounter order, even with `parallelStream()`. The code only writes strings into a List for illustration; **there is no real DB or email connection**.

In production, replace `effects.add(...)` with a business service and design **explicitly for when an operation fails**. Avoid assuming this example guarantees atomicity, durability, or exactly-once; it mainly shows **where to place actions** appropriately.

## 10. Why should peek() not be used for auditing, DB writes, sending emails, or payments?

Consider a hypothetical system that must record an audit for each processed order. If you use:

```text
orders.stream()
      .peek(auditService::record)
      .filter(Order::isValid)
      .count();
```

This is **illustrative pseudocode**, which does not compile standalone because of hypothetical types/services. Besides the possibility of `peek` being skipped during optimization, there are several unresolved business questions:

1. **Timing:** `peek` runs before `filter`, which may record audits even for rejected orders. If placed after `filter`, counting logic and optimizations still leave side effects unguaranteed.
2. **Scope:** the pipeline can short-circuit, causing the action to run on only a subset of the data.
3. **Ordering:** a parallel stream may execute out of the desired order.
4. **Midway errors:** if some audits have already been recorded and a later step fails, there is no automatic rollback.
5. **Retries:** if the caller retries the entire process, external operations may be executed again; `peek` does not provide an idempotency key.
6. **Monitoring:** a successful terminal `count()` is not proof that audit records were durably saved.

Even when switching to `forEach`, you still need answers to the questions about transactions and retries. However, `forEach` at least **accurately expresses the intent of a terminal action**, instead of hiding business logic in an intermediate observation step.

For monetary transactions, emails, and edit history, the system needs additional appropriate mechanisms such as **idempotency keys**, database transactions, the **outbox pattern**, processed-state tracking, and controlled retries; these are separate architectural decisions, **not capabilities of the Stream API**.

## 11. Sorting and observing: peek() does not turn Stream into a reliable logging tool

In the sorting and observing group of operations, `peek` often appears alongside `sorted`:

```java
List<Integer> values = List.of(3, 1, 2);
var sortedValues = values.stream()
        .sorted()
        .peek(n -> System.out.println("after sort: " + n))
        .toList();
```

These are illustrative statements in a method with `List` imported. In this sequential pipeline, the `after sort` message can help learners **observe elements after the sorting step**. However, logging here is only **diagnostic**, not an action that must execute for every value under every kind of terminal operation.

Do not rely on `peek` to "force-verify that sorting ran" or "count every processed element". `sorted` itself can also be optimized away by the pipeline in contexts where observing the contents is unnecessary; `peek`'s side effects do not become part of a contractually guaranteed result.

If you need to check the sorting result in tests, **collect the data and then assert the contents**:

```java
List<Integer> sorted = values.stream().sorted().toList();
// Verify sorted.equals(List.of(1, 2, 3)) in the test.
```

This approach checks the **output values** instead of relying on the invocation count or order of intermediate side effects.

## 12. Exceptions, retries, and consistency

If `peek` calls an external API that can throw a `RuntimeException`, that exception **can propagate when the action is actually executed**. However, you cannot rely on it definitely being thrown: if the stage is skipped due to optimization or short-circuiting, the action does not run and the exception is not thrown either.

Risky design example:

```text
stream.peek(item -> {
    charge(item);
    audit(item);
}).count();
```

This is pseudocode that does not run standalone; it illustrates **two external side effects** attached to `peek`. No `charge` calls may run at all; or some may run and then an exception occurs; there is no rollback contract.

A better approach:

- Separate a pure pipeline for **filtering/transforming/determining the list of work**.
- Create explicit **commands/tasks** with stable IDs, ensuring validity before triggering actions.
- Execute actions via a **service** or transparent loop, with per-item error handling and status data.
- For external effects, consider **transactions and idempotent retries** based on the characteristics of the data store/service.
- Persist success/failure audit signals from **the execution step itself** and an appropriate storage system, rather than inferring them from a pipeline's terminal result.

In particular, **do not promise exactly-once** just because you use `forEachOrdered` or a loop. They help make execution order clear within a single successful processing pass, whereas exactly-once in distributed systems requires a different design.

## 13. Alternatives by goal

**Want to inspect elements passing through a pipeline while debugging:** use `peek(System.out::println)` intentionally, knowing that side effects may be elided and order may differ in parallel. You can remove `peek` after debugging.

**Want to transform elements:** use `map`, preferably with a pure expression:

```java
List<String> normalized = names.stream()
        .map(String::trim)
        .map(String::toUpperCase)
        .toList();
```

Illustrative statements in a method with `names: List<String>` and `List` imported. The resulting list is the returned data, independent of debug logging.

**Want to select elements:** use `filter` and inspect the result; do not use side effects to perform an "implicit filter".

**Want to execute an action for each element:** when appropriate, use terminal `forEach` or `forEachOrdered` with a clear error policy, or a `for` loop:

```java
for (String item : names) {
    System.out.println("process:" + item);
}
```

Illustrative snippet in a method with an appropriate `names`. In production, replace printing with an appropriate service and design error handling/transactions.

**Want to produce metrics:** use terminal `count`, `sum`, `collect`, `reduce`, or an appropriate collector; do not count with `peek(x -> counter.incrementAndGet())`. Metrics must be based on **terminal operation results**, not on an observation stage that might be skipped.

**Want durable auditing:** use a dedicated audit step within a transaction or controlled workflow; do not confuse `peek` with an event log that has a delivery contract.

## 14. Common mistakes/misconceptions

| Misconception | Why it is wrong | Better practice |
| --- | --- | --- |
| `peek` will always run for every element | Pipelines are lazy, have optimizations, and support short-circuiting | Do not put mandatory business logic in `peek` |
| Having a terminal operation guarantees all `peek` calls run | `count()` can read the source size; `findFirst()` can stop early | Choose the processing approach based on the terminal operation's actual contract |
| `peek` is suitable for sending emails or saving to a DB | No execution guarantee, rollback, or idempotency | Separate an explicit business stage |
| Add `filter(x -> true)` to force `peek` to run | Relies on optimizer behavior and alters the pipeline for non-business reasons | Use a loop, service, or purpose-built terminal action |
| Returning `count=100` proves 100 operations completed | Count only reports the number of elements counted, not side effects | Track action results directly |
| `peek` will run on the same thread that called the terminal operation | Parallel pipelines can run across multiple threads | Avoid stateful side effects; synchronize when truly needed |
| `peek` always preserves log order | Actions may be invoked out of encounter order | Use appropriate observation methods; do not treat logs as business ordering |
| `map` can replace `peek` to force DB writes | `map` is still an intermediate operation | Let `map` produce data, and let an outer step handle DB writes |
| `forEachOrdered` means durable exactly-once | It only enforces encounter order for actions during a single traversal | Design retries/idempotency and persist state |
| `ArrayList.add` inside `parallelStream().peek` is safe | Prone to race conditions and incomplete results | Avoid side effects; use a collector or an appropriate thread-safe structure |

## 15. Exercises and answers

**Exercise 1 — Result and side effect.** Can the following snippet produce `count=4` while `counter=0`?

```java
AtomicInteger counter = new AtomicInteger();
long count = List.of("A", "B", "C", "D").stream()
        .peek(s -> counter.incrementAndGet())
        .count();
```

Answer: **Yes**. On a List source with a known size, `count()` can compute directly and skip the `peek` stage. The snippet consists of illustrative statements in a method with `AtomicInteger` and `List` imported. Even thread-safe `AtomicInteger` does not give `peek` a mandatory execution contract.

**Exercise 2 — Laziness.** `List<String> logs = new ArrayList<>(); var p = data.stream().peek(logs::add);` has just been assigned. Can we assert that `logs` already contains every element?

Answer: **No**. There is no terminal operation yet, so describing the pipeline does not traverse the source by itself; `logs` has not been populated by `peek`.

**Exercise 3 — Early termination.** Does `stream.peek(this::sendEmail).findFirst()` satisfy the requirement to send an email to **every** element?

Answer: **No**. `findFirst()` only needs the first element of a stream with encounter order. Sending emails to all objects must not be placed in `peek` of that pipeline.

**Exercise 4 — Proposed fix.** Given `List<Order> orders` and a requirement to filter valid orders, create receipts, and save each receipt, where should the save step be placed?

Answer: use `orders.stream().filter(...).map(...).toList()` to create the list of receipts; then use a loop or service to process each receipt, managing errors and transactions. If the data is too large, you can design an explicit terminal action to avoid materializing everything; still do not use `peek` for mandatory saving.

**Exercise 5 — Ordering.** Can you use `parallelStream().peek(x -> audit(x))` and trust that audits are recorded in the exact List order?

Answer: **No**. Side effects in a parallel pipeline can occur out of encounter order and are not guaranteed to execute for every element. When order is needed, use a solution with an ordering contract and appropriate durable storage.

**Exercise 6 — map instead of peek?** If you change `peek(x -> charge(x))` to `map(x -> {charge(x); return x;})`, is there now a mandatory payment guarantee?

Answer: **Not yet**. `map` is also an intermediate operation; operations may not be executed if the terminal operation does not need the values. You should separate `charge` into an independent business step, with transactions/idempotency.

**Exercise 7 — Proper purpose.** When is `peek` still useful?

Answer: when you need to **observe and debug** values passing through a pipeline (especially between `map`/`filter`/`sorted`), with the awareness that logs are only diagnostic aids, not mandatory proof that all data was processed.

## 16. Conclusion

- **`peek()` is an intermediate operation for observation**, commonly used for debugging, not a tool for executing mandatory business logic.
- **Lazy evaluation** means `peek` does not run without a traversal; **optimizations** can skip the action, typically `count()` on a sized source.
- **Short-circuiting** such as `findFirst()` causes only part of the data to be processed; **parallelism** complicates ordering and shared state.
- A terminal operation's result **does not prove** that intermediate side effects were executed.
- Use **`map`/`filter` for data transformation**, `toList`/collectors to obtain results, and **terminal actions or loops/services** to execute actions in a controlled way.
- **`forEach`/`forEachOrdered` do not by themselves provide transactions or exactly-once**: critical business logic needs its own error-handling, idempotency, and durability mechanisms.
- When you see `.peek(sendEmail)`, `.peek(saveToDatabase)`, or `.peek(chargeCustomer)` in a code review, treat it as a sign to inspect and redesign.

References: [Java 17 Stream.peek](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#peek(java.util.function.Consumer)), [Java 17 Stream.count](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#count()), [Java 17 Stream — Side-effects](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html#SideEffects).
