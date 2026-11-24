# allOf() Waits for Multiple Tasks and How to Collect Typed Results

## 1. Why Is allOf() Needed?

In a Spring application, an aggregation API may need to fetch price, inventory, and shipping status from three independent sources. If each source is called via `@Async` or `CompletableFuture.supplyAsync`, you have three `CompletableFuture<T>` instances that can finish at different times. The business requirement is to **wait until all required sources finish and then combine the results**, not to take "whichever result finishes first."

Java provides:

~~~java
public static CompletableFuture<Void> allOf(CompletableFuture<?>... cfs)
~~~

When you use `CompletableFuture.allOf(a, b, c)`, you get a **barrier Future**: it completes when **all** input Futures have completed (either successfully or with an error). If all succeed, the combined Future completes normally with the value `null` because the return type is `Void`; **it does not hold a list of results**. If at least one Future fails, the combined Future completes exceptionally.

Therefore, the design usually has two steps:

1. **Merge the completion signal:** `CompletableFuture.allOf(...)`.
2. **Collect typed values:** after the barrier **succeeds**, read each input Future with `join()` and transform them into a `List<T>` or a specific record/DTO.

Conceptual example:

~~~java
CompletableFuture<User> userFuture = loadUser();
CompletableFuture<Balance> balanceFuture = loadBalance();

CompletableFuture<AccountView> combined =
        CompletableFuture.allOf(userFuture, balanceFuture)
                .thenApply(ignored ->
                        new AccountView(
                                userFuture.join(),
                                balanceFuture.join()));
~~~

This is an illustrative snippet inside a service, **not a standalone program**: `User`, `Balance`, `AccountView`, `loadUser`, and `loadBalance` are types/methods defined by the project. The essence of the example: the result has type `CompletableFuture<AccountView>`, without turning into `Object[]` or losing generic types.

**Quick reminder:** `allOf` **waits for all**; `thenApply` **collects results**; `join` **reads each completed value**. None of these three steps creates worker threads by itself.

## 2. Exact Contract of CompletableFuture.allOf

### 2.1. API and Outcomes

| Scenario | `CompletableFuture.allOf(...)` | Key takeaway |
| --- | --- | --- |
| Two Futures not done yet | Combined Future not done | Must not be treated as a complete result |
| One Future done, one not done yet | Still not done | `allOf` is a barrier waiting for **all** |
| All succeed | Completes normally with value `Void/null` | Read the inputs to obtain concrete values |
| At least one Future completes exceptionally | Combined Future completes exceptionally after inputs finish | Handle the exception; does not run the success-only `thenApply` branch |
| Empty input array | Combined Future already completed with `null` | A `sequence` helper can return an empty list |
| A `null` element in the input array | Throws `NullPointerException` on invocation | Validate the input list |
| One Future never completes | Barrier can wait indefinitely | Explicit deadlines, rejections, and job status tracking |

`allOf` imposes no wait timeout, does not cancel running tasks, does not create a thread pool, does not prevent tasks from overloading, and **does not guarantee partial results** are returned if one element fails.

With multiple errors, do not rely on the barrier's `join()` reporting whichever failed first chronologically. When you need to report each failing source, handle each Future with `handle` before gathering.

### 2.2. allOf vs. anyOf and thenCombine

| Tool | When can the combined stage finish? | Combined result |
| --- | --- | --- |
| `allOf(a,b,c)` | After all three have completed | `CompletableFuture<Void>`; does not extract values by itself |
| `anyOf(a,b,c)` | When **any one** Future finishes | `CompletableFuture<Object>`; can be hard to preserve types |
| `a.thenCombine(b, fn)` | When both succeed | Value type returned by `fn`, suitable for two sources |
| `a.thenCompose(fn)` | When `a` succeeds and the next Future is needed | Used for **sequentially dependent** work, not a barrier |
| `allOf(...).thenApply(fn)` | When all input Futures succeed | Value type produced by `fn`, used for `n` sources |

`anyOf` with empty input returns an incomplete Future, whereas `allOf` with empty input returns an already completed Future. That is an important difference when handling dynamic lists.

### 2.3. allOf Does Not Launch Tasks on Its Own

Suppose:

~~~java
CompletableFuture<String> a =
        CompletableFuture.supplyAsync(() -> "A", executor);
CompletableFuture<String> b =
        CompletableFuture.supplyAsync(() -> "B", executor);
CompletableFuture<Void> barrier = CompletableFuture.allOf(a, b);
~~~

`supplyAsync` is what **submits work** to `executor`; `allOf` only tracks completion. If the executor is `SyncTaskExecutor`, each supplier may run on the caller thread; if it is an async pool, the work executes on pool workers. The `Executor` argument and pool configuration determine the execution model, not the name `allOf`.

If no `Executor` is passed to `supplyAsync`, Java typically uses `ForkJoinPool.commonPool()`. In a Spring project where reporting, JDBC, and short tasks need separate pools, pass an explicit executor or invoke `@Async("beanName")` methods via a Spring proxy; do not assume every CompletableFuture runs in Boot's pool.

## 3. Standard Pattern: Collecting List<T> in Input Order

A `List<CompletableFuture<T>>` can be converted into **a single** `CompletableFuture<List<T>>` without casting from `Object`.

~~~java
import java.util.List;
import java.util.concurrent.CompletableFuture;

public final class FutureCollections {
    private FutureCollections() { }

    public static <T> CompletableFuture<List<T>> sequence(
            List<CompletableFuture<T>> input) {
        List<CompletableFuture<T>> futures = List.copyOf(input);

        CompletableFuture<?>[] array =
                futures.toArray(new CompletableFuture<?>[0]);

        return CompletableFuture.allOf(array)
                .thenApply(ignored ->
                        futures.stream()
                                .map(CompletableFuture::join)
                                .toList());
    }
}
~~~

This is a valid Java 17 class that can be placed in `FutureCollections.java`. In a Java 8–15 project, `Stream.toList()` is unavailable; substitute an appropriate collector. `List.copyOf(input)` takes a snapshot of the **Future references** at call time, preventing the caller from mutating the list structure after building the barrier. It does not copy or freeze mutable `T` results. `List.copyOf` rejects `null` elements, and `allOf` itself also rejects null elements.

**Key properties:**

- When `input` contains `CompletableFuture<Report>`, the return type is `CompletableFuture<List<Report>>`. The compiler enforces type safety; no casting from `List<Object>`.
- `thenApply` **only runs when the barrier completes normally**. If one task fails, the returned stage is also exceptional; it does not loop over elements and accidentally turn errors into success.
- When the `thenApply` callback runs after the barrier succeeds, each child Future is already complete; `join()` at that moment **does not wait further** provided the Futures remain in their terminal state.
- The resulting list preserves **`input` order**, not task completion order. `Stream.toList()` returns a list that cannot be modified via the list API.
- An empty `input` produces a `CompletableFuture<List<T>>` already completed with an empty list.

If you need ordering by deadline, priority, or completion order, write separate sorting logic. `allOf` does not provide "results in completion order."

### Mistake: Returning List<Object> or Casting Everything

~~~java
// Illustrative anti-pattern, not an API encouraged for use.
CompletableFuture<?>[] array = ...;
CompletableFuture<Void> barrier = CompletableFuture.allOf(array);
// There is no barrier.getResults() method.
// barrier.join() returns null (Void), and cannot be cast to List<Report>.
~~~

Code that uses `CompletableFuture<?>[]` at the barrier-creation step **does not erase the type** of the original `List<CompletableFuture<Report>>`. Keep the generically typed list to collect results in the next step. Avoid raw `CompletableFuture[]` and unchecked casts when unnecessary.

## 4. Standalone Java 17 Example with Deterministic Output

The following example demonstrates three cases independent of CPU speed or thread scheduling:

1. `allOf` **has not completed** while one of two tasks is still pending, even though the other has finished.
2. Collecting same-type data into `List<String>`; collecting **heterogeneous** data into a `Summary` record.
3. A single failing Future fails the barrier; when partial success must be preserved, transform each Future into `Outcome<T>` before gathering.

Save as **`FanInDemo.java`**:

~~~java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public final class FanInDemo {
    record Summary(String sku, int stock) { }

    record Outcome<T>(String source, T value, String error) { }

    static <T> CompletableFuture<List<T>> sequence(
            List<CompletableFuture<T>> input) {
        List<CompletableFuture<T>> snapshot = List.copyOf(input);
        CompletableFuture<?>[] array =
                snapshot.toArray(new CompletableFuture<?>[0]);

        return CompletableFuture.allOf(array)
                .thenApply(ignored ->
                        snapshot.stream()
                                .map(CompletableFuture::join)
                                .toList());
    }

    public static void main(String[] args) {
        CompletableFuture<String> first = new CompletableFuture<>();
        CompletableFuture<String> second = new CompletableFuture<>();
        CompletableFuture<List<String>> together =
                sequence(List.of(first, second));

        second.complete("B");
        System.out.println("WAIT_AFTER_B=" + together.isDone());

        first.complete("A");
        System.out.println("TYPED_VALUES=" + together.join());

        CompletableFuture<String> sku =
                CompletableFuture.completedFuture("P-7");
        CompletableFuture<Integer> stock =
                CompletableFuture.completedFuture(4);

        CompletableFuture<Summary> summary =
                CompletableFuture.allOf(sku, stock)
                        .thenApply(ignored ->
                                new Summary(sku.join(), stock.join()));
        System.out.println("SUMMARY=" + summary.join());

        CompletableFuture<String> ok =
                CompletableFuture.completedFuture("OK");
        CompletableFuture<String> failed =
                CompletableFuture.failedFuture(
                        new IllegalStateException("unavailable"));

        CompletableFuture<Void> all =
                CompletableFuture.allOf(ok, failed);

        try {
            all.join();
        } catch (CompletionException ex) {
            System.out.println("ALL_ERROR="
                    + ex.getCause().getClass().getSimpleName());
        }

        CompletableFuture<Outcome<String>> safeOk =
                ok.handle((value, error) ->
                        new Outcome<>("first", value,
                                error == null ? null
                                        : error.getClass().getSimpleName()));

        CompletableFuture<Outcome<String>> safeFailed =
                failed.handle((value, error) ->
                        new Outcome<>("second", value,
                                error == null ? null
                                        : error.getClass().getSimpleName()));

        System.out.println("PARTIAL="
                + sequence(List.of(safeOk, safeFailed)).join());

        System.out.println("EMPTY="
                + sequence(List.<CompletableFuture<String>>of()).join());
    }
}
~~~

Run with JDK 17+:

~~~bash
javac --release 17 FanInDemo.java
java FanInDemo
~~~

Program stdout:

~~~text
WAIT_AFTER_B=false
TYPED_VALUES=[A, B]
SUMMARY=Summary[sku=P-7, stock=4]
ALL_ERROR=IllegalStateException
PARTIAL=[Outcome[source=first, value=OK, error=null], Outcome[source=second, value=null, error=IllegalStateException]]
EMPTY=[]
~~~

**Why is it deterministic?** There are no randomly scheduled workers in the example; both Futures are `complete`d manually in a fixed order. Right after `second.complete("B")`, `first` is not done yet, so `together.isDone()` must be `false`. After `first.complete("A")`, the barrier succeeds and the result still follows `List.of(first, second)`, yielding `[A, B]` even though B finished first.

The `Summary` section shows how to collect two distinct types `String` and `Integer` into a **typed record**, rather than `List<Object>`. The `ALL_ERROR` section shows that by default `allOf` does not return partial successes. Finally, `handle` turns each Future into an `Outcome<String>` that **always completes normally**, allowing `sequence` to collect both success and error states. This approach is intentional: if the entire operation must succeed, **do not** swallow errors; if the report tolerates a missing source, model the error explicitly.

## 5. Heterogeneous Types: Build a DTO Instead of Forcing List<T>

`allOf` accepts `CompletableFuture<?>...`, so it can wait on Futures of different types. However, there is no single `T` that accurately represents `User`, `Money`, and `Inventory` together in `List<T>`. When each source has a distinct meaning, build a DTO:

~~~java
// Illustrative code in a service; records are defined by the project.
CompletableFuture<User> user = findUser(userId);
CompletableFuture<Money> balance = findBalance(userId);
CompletableFuture<Inventory> inventory = findInventory(userId);

CompletableFuture<Dashboard> dashboard =
        CompletableFuture.allOf(user, balance, inventory)
                .thenApply(ignored ->
                        new Dashboard(
                                user.join(),
                                balance.join(),
                                inventory.join()));
~~~

Each `join()` returns its original type; `Dashboard`'s constructor checks compatibility at compile time. This is far more readable than:

~~~java
// Anti-pattern: loses type-safety and relies on integer positions.
List<Object> result = List.of(
        user.join(), balance.join(), inventory.join());
User u = (User) result.get(0);
~~~

In the proper example, the result is `CompletableFuture<Dashboard>` so the caller can `thenApply`/`thenCompose`/`handle`, rather than forcing the caller to invoke synchronous `get()` immediately. If an input Future fails, the DTO-building `thenApply` **does not run**; handle the error via a completion stage or `handle` at the appropriate layer.

With exactly **two** Futures, `thenCombine` can express this more concisely:

~~~java
CompletableFuture<DashboardPart> part =
        user.thenCombine(balance, DashboardPart::new);
~~~

`thenCombine` fits when combining only two sources and both must succeed; with three or more sources, `allOf` plus a DTO keeps the code symmetrical, or you can chain `thenCombine` if the structure is complex.

## 6. Spring Boot @Async Integration: Runnable Example

A plain Java program can use `CompletableFuture.supplyAsync`; in Spring, you typically have a service calling APIs or DBs on a dedicated executor and an aggregator responsible for combining results. The example below uses **Java 17 + Maven + Spring Boot 3.3.5**; no web server or DB is required.

The example contains two independent async methods returning **two different record types**. `CatalogAggregator.fetch` combines both via `allOf(...).thenApply(...)`; `ApplicationRunner` prints the final DTO for verification.

### 6.1. Directory Structure

~~~text
spring-allof-demo/
├── pom.xml
└── src/main/java/com/example/fanin/
    ├── FanInApplication.java
    ├── CatalogClient.java
    └── CatalogAggregator.java
~~~

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>spring-allof-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.3. FanInApplication.java

~~~java
package com.example.fanin;

import java.util.concurrent.TimeUnit;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@SpringBootApplication
@EnableAsync
public class FanInApplication {
    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(FanInApplication.class, args)) {
            // Context closes automatically after ApplicationRunner completes.
        }
    }

    @Bean("catalogExecutor")
    ThreadPoolTaskExecutor catalogExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(2);
        pool.setQueueCapacity(10);
        pool.setThreadNamePrefix("catalog-");
        pool.setWaitForTasksToCompleteOnShutdown(true);
        return pool;
    }

    @Bean
    ApplicationRunner demonstration(CatalogAggregator aggregator) {
        return args -> {
            CatalogAggregator.Snapshot result =
                    aggregator.fetch("P-7").get(5, TimeUnit.SECONDS);
            System.out.println("SNAPSHOT=" + result);
        };
    }
}
~~~

`ApplicationRunner` intentionally calls `get(5, SECONDS)` to produce deterministic stdout and then closes the context. This approach **blocks the startup thread** in the demo; it is not required for a web controller that wants true asynchrony. Two core workers in the bean is just a sample configuration, not a default for every Spring app.

### 6.4. CatalogClient.java

~~~java
package com.example.fanin;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class CatalogClient {
    public record Price(String sku, int amount) { }
    public record Stock(String sku, int available) { }

    @Async("catalogExecutor")
    public CompletableFuture<Price> price(String sku) {
        // Simulated price lookup result; replace with real HTTP/DB in production.
        return CompletableFuture.completedFuture(new Price(sku, 120));
    }

    @Async("catalogExecutor")
    public CompletableFuture<Stock> stock(String sku) {
        return CompletableFuture.completedFuture(new Stock(sku, 7));
    }
}
~~~

`CatalogClient` is a Spring-managed bean called by `CatalogAggregator` **through a proxy**, so both methods are submitted to `catalogExecutor` by the `@Async` interceptor. The implementation method returns a `CompletableFuture.completedFuture` containing the computed result: that is a valid return type for the target method and **does not** break the outer proxy's async mechanism. Note that tiny methods like this demo are not necessarily worth dispatching to a worker in production; the goal is simply to illustrate fan-out and fan-in.

### 6.5. CatalogAggregator.java

~~~java
package com.example.fanin;

import java.util.concurrent.CompletableFuture;
import org.springframework.stereotype.Service;

@Service
public class CatalogAggregator {
    public record Snapshot(
            String sku, int amount, int available) { }

    private final CatalogClient client;

    public CatalogAggregator(CatalogClient client) {
        this.client = client;
    }

    public CompletableFuture<Snapshot> fetch(String sku) {
        CompletableFuture<CatalogClient.Price> price =
                client.price(sku);
        CompletableFuture<CatalogClient.Stock> stock =
                client.stock(sku);

        return CompletableFuture.allOf(price, stock)
                .thenApply(ignored -> new Snapshot(
                        sku,
                        price.join().amount(),
                        stock.join().available()));
    }
}
~~~

Key points:

- Obtain **both Future handles first**, without calling `join()` immediately after each dispatch.
- Combine with `allOf(price, stock)` to observe when **both** have finished.
- Inside `thenApply`, read the strongly typed `Price` and `Stock` results to construct `Snapshot`; that is a non-blocking synchronous callback over already-available data.
- `fetch` returns `CompletableFuture<Snapshot>` so the caller chooses how to wait/compose, instead of blocking the thread inside the aggregator.
- `@Async` sits on methods of a **different bean** from the aggregator; there is no self-invocation.

### 6.6. Run and Output

From the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Ignoring Spring/Maven logs, the line printed by the program is:

~~~text
SNAPSHOT=Snapshot[sku=P-7, amount=120, available=7]
~~~

The output DTO does not depend on the order in which workers finish, because `allOf` waits for all and the record is built using the exact field names in code. Even though the pool has two core workers, **there is no guarantee** the two methods will definitely execute simultaneously on CPU; queues, thread scheduling, and task duration determine actual overlap. This example verifies result-gathering correctness, not concurrency benchmarking.

## 7. Collect All-Success or Accept Partial Success?

### 7.1. All-or-Nothing: Preserve Exceptions

For a report requiring **all** sources to be accurate, keep the default policy:

~~~java
// Snippet in a service: price and stock are typed CompletableFutures.
CompletableFuture<Snapshot> allRequired =
        CompletableFuture.allOf(price, stock)
                .thenApply(ignored -> new Snapshot(
                        price.join(), stock.join()));
~~~

`Snapshot` here is an illustrative record with two fields matching the input types, not the `Snapshot` record from the Spring example in section 6. If `price` fails, `thenApply` does not build the snapshot. Attach `whenComplete((value, error) -> ...)` for logging/metrics, or `handle` at the API layer to map errors to status codes. In Spring `@Async`, business errors inside a worker can be turned into exceptional completions; **submission rejection** when the executor is full can happen synchronously at the proxy call site (e.g., `TaskRejectedException`), so the fan-out phase also needs `try/catch` if you need a 503 response instead of an accidental 500.

### 7.2. Partial Success: Normalize Each Result Before allOf

If business rules still allow aggregation when one provider fails, **convert each Future into a result with explicit status** before passing it to `allOf`.

~~~java
// Illustrative excerpt; record Outcome<T> is defined by the project.
record Outcome<T>(String source, T value, Throwable error) { }

CompletableFuture<Outcome<Price>> safePrice =
        price.handle((value, error) ->
                new Outcome<>("price", value, error));

CompletableFuture<Outcome<Stock>> safeStock =
        stock.handle((value, error) ->
                new Outcome<>("stock", value, error));

CompletableFuture<PartialView> partial =
        CompletableFuture.allOf(safePrice, safeStock)
                .thenApply(ignored ->
                        new PartialView(
                                safePrice.join(),
                                safeStock.join()));
~~~

`Price`, `Stock`, and `PartialView` in the snippet are project-specific models; the record name `Outcome` applies only to the snippet. Because `handle` runs for both success/failure and returns an `Outcome` normally, the barrier can succeed and the callback sees **each individual error**. If the handler throws an exception, `safePrice` can still be exceptional, so keep handlers short and free of unintended exceptions.

In real systems, map `Throwable` to categorized error codes instead of exposing raw stack traces or exceptions containing sensitive data in HTTP responses. Keep original logs on the server, while clients receive appropriate `source`, `status`, and `message`.

### 7.3. Fail-Fast vs. Waiting for All Before Reporting Errors

If one source fails early while another hangs, `allOf` may not complete yet because it is a barrier that **waits for all Futures to reach a terminal state**. Therefore, do not rely on `allOf` as a "fail-fast" mechanism to return errors immediately. To terminate early upon error, add explicit design: an overall deadline, a separate failure signal, or a coordination library/logic with cancellation and explicit state-acceptance rules.

If multiple sources fail, `allOf` does not surface a list of exceptions. In the partial-success model, per-source `handle` as above provides full visibility. In the all-or-nothing model, you can log errors per Future before creating the barrier, while avoiding logging the exact same error repeatedly.

## 8. Timeouts, Cancellation, and Preventing Infinite Waits

### 8.1. allOf Has No Default Timeout

If a Future is dropped because `DiscardPolicy`/`DiscardOldestPolicy` silently discards tasks, gets stuck on I/O, or nobody calls `complete`, the barrier can stay pending forever. `allOf` does not accept a wait timeout in its parameters.

Synchronous callers can use:

~~~java
// Snippet: combined is a CompletableFuture<Snapshot>.
try {
    Snapshot view = combined.get(3, TimeUnit.SECONDS);
    send(view);
} catch (TimeoutException ex) {
    recordDeadlineExceeded();
} catch (ExecutionException ex) {
    recordFailure(ex.getCause());
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Interrupted while waiting", ex);
}
~~~

`send`, `recordDeadlineExceeded`, and `recordFailure` here are assumed business methods, not a standalone example. `get(timeout)` bounds the **caller's wait time**; it does not complete `combined` itself and does not stop child tasks.

With `CompletableFuture`, you can make the aggregated stage complete exceptionally on timeout:

~~~java
// Snippet: aggregated future created and managed by the application.
CompletableFuture<Snapshot> bounded =
        combined.orTimeout(3, TimeUnit.SECONDS);
~~~

`orTimeout` returns the **exact same** `CompletableFuture` instance it is called on, without creating an independent copy. After timeout, `join()` can throw `CompletionException` wrapping `TimeoutException`. However, child Futures and real I/O work may keep running; timeout does not replace HTTP/DB socket timeouts, cancellation, idempotency, or worker lifecycle management.

### 8.2. Cancelling the Aggregate Does Not Cancel Every Child

~~~java
CompletableFuture<Void> all = CompletableFuture.allOf(a, b, c);
all.cancel(true);
~~~

`cancel(true)` on `CompletableFuture` completes `all` itself as a cancellation (if not already terminal). It **does not interrupt** upstream tasks and does not promise that `a`, `b`, and `c` are all cancelled. In `CompletableFuture`'s implementation, the `mayInterruptIfRunning` parameter does not directly control interrupting tasks. To manage cancellation, retain handles to child Futures separately and cancel requests according to the executor's contract, while also handling tasks that may still finish late.

When tasks produce DB/HTTP side effects, after a timeout or cancellation the caller may retry while the old task still writes data. Use idempotency keys, conditional updates, and job state to prevent duplicates. For long-running work that must survive restarts, in-memory `CompletableFuture` does not replace a durable DB or message queue.

### 8.3. Do Not Create Unbounded Fan-Out

With thousands of Futures submitted to a pool with a huge queue, per-task wait time can exceed deadlines even while workers are busy. `allOf` does not throttle the number of in-flight tasks. Apply:

- Bounded pools and queues; handle `TaskRejectedException` right at submission time.
- Semaphores/bulkheads or splitting lists into bounded chunks; note that sequential batching reduces parallelism but stabilizes load.
- An overall timeout and individual timeouts for external calls; propagate deadlines across services if needed.
- Metrics for submitted, active, queued, failed, timed-out, rejected tasks, and pending `allOf` barriers.
- No blocking `join()/get()` inside the same small pool that needs to run the remaining tasks; this can cause starvation/deadlock if all workers wait on work still sitting in the queue.

For CPU-bound workloads, increasing pool size endlessly does not arbitrarily increase throughput; for I/O-bound workloads, account for connection counts, quotas, and external latency, not just thread count.

## 9. Understanding thenApply, thenApplyAsync, and Execution Threads

~~~java
CompletableFuture<Result> aggregate =
        CompletableFuture.allOf(a, b)
                .thenApply(ignored -> combine(a.join(), b.join()));
~~~

`thenApply` does not schedule itself on a separate executor. Under `CompletableFuture`'s policy, the callback **may run on the thread that just completed the final stage**, or another thread participating in completion; if the barrier is already complete upon registration, the callback may run immediately on the caller thread. Therefore keep the callback **lightweight**, only constructing records/maps or doing cheap calculations.

If the aggregation step is CPU-intensive or writes large files, you can choose:

~~~java
CompletableFuture<Result> aggregate =
        CompletableFuture.allOf(a, b)
                .thenApplyAsync(
                        ignored -> combine(a.join(), b.join()),
                        aggregationExecutor);
~~~

`aggregationExecutor` here is an `Executor` initialized and managed by the application; the snippet is not a standalone program. `thenApplyAsync` dispatches the callback to the supplied executor. Also handle rejection: if the aggregation executor refuses the task, the stage can become exceptional. Do not use `thenApplyAsync` just to read two values and build a record when scheduling overhead exceeds the work itself.

Another risk is incorrect composition:

~~~java
// Anti-pattern: joining immediately upon submission serializes the entire call path.
Result aResult = loadA().join();
Result bResult = loadB().join();
return CompletableFuture.completedFuture(combine(aResult, bResult));
~~~

This forces the caller to wait for A to finish **before** dispatching B (when `loadA` dispatches upon call), losing parallel execution. **Initialize all futures first**, then use a barrier to collect results. For sequentially dependent work, `thenCompose` is the right choice—do not try to fan out steps that lack input data yet.

## 10. Common Pitfalls

| Symptom / Misconception | Cause | Fix |
| --- | --- | --- |
| `allOf(...).join()` returns `null` | The barrier's result type is `Void` | Keep references to input Futures and call each `join()` after the barrier |
| Collecting results into `Object[]` and casting everywhere | Loses generic types in application code | `sequence(List<CompletableFuture<T>>)` or a record/DTO |
| One source fails, remaining results are not received | `allOf` is exceptional, `thenApply` does not run | Choose all-or-nothing or `handle` each Future before gathering |
| Results are not in completion order | The `sequence` pattern collects in input-list order | Sort by ID/priority/timestamp if needed |
| One task hangs and `allOf` hangs too | No deadline or task was silently discarded | Timeouts, explicit rejection signaling, job state, and monitoring |
| Overall timeout fires, yet worker still writes to DB | Timeout does not cancel upstream tasks | Cancellation contract, I/O timeouts, idempotency |
| `@Async` still runs inline | Missing `@EnableAsync`, self-invocation, or using `SyncTaskExecutor` | Call via Spring proxy; verify executor |
| Aggregation callback slows down workers | `thenApply` runs on completion thread | Keep callback small or use `thenApplyAsync` with a separate pool |
| HTTP API remains slow | Controller calls `join()` right after fan-out | Return an async type or job ID/202 per contract |
| Overload from thousands of tasks | Unbounded fan-out and queues | Bound concurrency, pools/queues, and backpressure |
| Flaky tests | Relying on `Thread.sleep` to time completion | Use `CountDownLatch`, manual Futures, and state assertions |
| Swallowing errors with `exceptionally` and returning fake data | Error handling hides missing data | Partial results must include source status, never fake success |

### Checklist When Reviewing Code Using allOf

1. Is the Future list concretely typed and free of `null` elements?
2. Are **all tasks dispatched** before waiting, without accidentally calling `join()` sequentially?
3. Is `allOf` used as a barrier, without mistaking it for containing `List<T>`?
4. Is result-collection code inside `thenApply`/`thenCompose` after the barrier succeeds, instead of blocking on a request thread unnecessarily?
5. If one Future fails, does the API contract require failing everything or returning a partial result?
6. Are there timeouts, rejection handling, cancellation, and alerts for tasks pending too long?
7. Are concurrency/queues bounded, without unbounded fan-out or blocking workers on Futures from the same pool?
8. In Spring, are `@Async` calls made through a proxy from another bean, with the right executor name and managed lifecycle?
9. Does the output DTO preserve exact fields/types without relying on arbitrary completion order?
10. Are there tests for empty input, multiple results, single error, multiple errors, timeout, a pending Future, and overload?

## 11. Self-Check Exercises

1. Why does `CompletableFuture.allOf(a, b)` return `CompletableFuture<Void>` instead of `CompletableFuture<List<T>>`? Where is the data?
2. Two `CompletableFuture<String>` instances complete in the order B then A. What order does `sequence(List.of(A,B))` return? Why?
3. If three Futures have types `User`, `Balance`, and `Stock`, how do you return `CompletableFuture<Dashboard>` without using `Object[]`?
4. Why does `allOf(...).thenApply(...)` not run the success callback when one child Future fails? What must you do if you want to report both successful data and errors?
5. If one Future reports an error while the other never completes, can the barrier return the error immediately or keep waiting? Which mechanism enforces deadlines?
6. How do `get(2, SECONDS)`, `orTimeout(2, SECONDS)`, and `cancel(true)` differ? Do they stop DB writes?
7. When using Spring `@Async`, why should a controller avoid calling `join()` immediately if the API wants to respond non-blockingly?
8. Does `thenApply` guarantee running on a separate pool? When should you choose `thenApplyAsync`?
9. If 5,000 requests each fan out 10 tasks simultaneously, does `allOf` automatically limit concurrency? What safeguards are needed?

**Takeaway:** `allOf` solves the problem of **waiting for all**, not **collecting typed data** or throttling concurrency. Keep the original `CompletableFuture<T>` handles, merge signals with `allOf`, read each result after all succeed, and construct a clear `List<T>`/DTO. For partial failures, use `handle` before gathering; for production, add deadlines, backpressure, and task monitoring.

## Official Documentation

- [Java SE 17 — CompletableFuture (allOf, anyOf, thenApply, handle, orTimeout)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 17 — CompletionStage](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html)
- [Spring Framework 6.2 — Task Execution, @Async and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
