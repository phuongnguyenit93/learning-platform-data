# allOf, anyOf, and Limitations When Collecting All Failures — CompletableFuture (Java 17+)

## 1. Objectives and Scope

This lesson helps you:

- Accurately distinguish when <code>CompletableFuture.allOf(...)</code> and <code>CompletableFuture.anyOf(...)</code> complete.
- Understand the difference between "all futures have finished" and "all futures have succeeded".
- Recognize that <code>allOf</code> **does not return a list of values** and **does not collect all Throwables** from failed futures.
- Understand that <code>anyOf</code> selects the **completion that occurs first**, whether that completion succeeds, fails, or is cancelled.
- Build a collector using <code>handle</code> to receive every result or every error, preserving the Throwable object and source order.
- Design policies for late errors, timeouts, cancellation, non-completing sources, and empty inputs.
- Test these scenarios using Java 17 examples whose output does not depend on thread scheduling.

In Java, <code>CompletableFuture&lt;T&gt;</code> both represents a future result and supports subsequent processing stages. It can be **incomplete**, **completed normally** with a value of type <code>T</code> (including <code>null</code>), or **completed exceptionally**. A cancelled future is also considered abnormally completed under the <code>CompletableFuture</code> mechanism.

## 2. Two Combinators Answering Two Different Questions

~~~java
CompletableFuture<Void> all =
        CompletableFuture.allOf(first, second, third);

CompletableFuture<Object> any =
        CompletableFuture.anyOf(first, second, third);
~~~

This is an **illustrative** snippet assuming three source variables of type <code>CompletableFuture&lt;?&gt;</code> and importing <code>java.util.concurrent.CompletableFuture</code>.

| Method | Question answered | Result type | On error |
| --- | --- | --- | --- |
| <code>allOf(f1, f2, ...)</code> | Have **all** source futures completed? | <code>CompletableFuture&lt;Void&gt;</code> | Completes exceptionally if at least one source future fails |
| <code>anyOf(f1, f2, ...)</code> | Has **one** source future completed? | <code>CompletableFuture&lt;Object&gt;</code> | If the winning source completes exceptionally, the combined future also fails |
| Application-defined outcome collector | **How** did each source complete? | E.g., <code>CompletableFuture&lt;List&lt;Outcome&lt;T&gt;&gt;&gt;</code> | Stores each error as data so all can be inspected |

<code>allOf</code> is commonly used as a **completion barrier**. <code>anyOf</code> is commonly used as a **completion race**. Neither concept is synonymous with aggregating values, collecting errors, or automatically selecting the best successful result.

~~~text
Source 1: SUCCESS("A") ----------+
                                 |
Source 2: FAILURE(error) --------+---- allOf: wait for all, result is error
                                 |
Source 3: SUCCESS("C") ----------+

Source 1: ------- SUCCESS("A")
Source 2: -- FAILURE(error)            <- completes first
Source 3: ----- SUCCESS("C")
anyOf:    -- FAILURE(error)            <- does not wait for success
~~~

## 3. allOf: All Completed, Not Necessarily All Succeeded

By contract, <code>CompletableFuture.allOf</code> returns a new future that completes when **all** input futures complete. Each input is considered completed whether it succeeds, fails, or is cancelled.

If all sources succeed, the combined future completes normally with the value <code>null</code> of type <code>Void</code>. If **any** source completes exceptionally, the combined future completes exceptionally.

### 3.1. Normal Result Does Not Contain Component Values

~~~java
CompletableFuture<String> name =
        CompletableFuture.completedFuture("An");
CompletableFuture<Integer> count =
        CompletableFuture.completedFuture(3);

CompletableFuture<Void> barrier =
        CompletableFuture.allOf(name, count);

barrier.join();
System.out.println(name.join() + ": " + count.join());
~~~

This is illustrative code placed inside a method with appropriate imports. The printed output is <code>An: 3</code>. <code>barrier.join()</code> returns <code>null</code> because it only confirms that the sources completed normally. To retrieve the component values, you must read the source futures themselves.

If a source succeeds with <code>null</code>, that still counts as a **normal completion**. You must not use a <code>value == null</code> check to conclude that a failure occurred.

### 3.2. One Failed Source Does Not Immediately Terminate allOf

Suppose source A has failed while source B is still pending:

~~~text
A: FAILURE ------------ done=true
B: incomplete --------- done=false
allOf(A,B): waiting --- done=false
~~~

<code>allOf</code> does **not** guarantee "fail fast" the moment one source reports an error. It waits for every input future to complete before completing itself. If one source never completes, calling <code>allOf(...).join()</code> may wait indefinitely even though another source has already failed.

This point matters when collecting errors: waiting for all sources gives time to record every failure, but a timeout or source cancellation policy is needed if you cannot wait forever.

### 3.3. Multiple Failed Sources Do Not Automatically Produce a List of Errors

Suppose all three sources fail:

- Source A throws <code>IllegalArgumentException</code>.
- Source B throws <code>IllegalStateException</code>.
- Source C throws an application-specific data access exception.

<code>allOf(A,B,C).join()</code> reports an error via the <code>CompletionException</code> mechanism. However, the API does not provide a method like <code>allOf.getAllErrors()</code> to retrieve all three exceptions. The combined future has **a single exceptional completion**; you should not assume the exception reported as its cause is the earliest chronologically, the latest, the most important, or all of them.

If you need every failure, **keep references to the source futures** and retrieve the result from each source after they are done, or transform each source into an outcome containing a value/error and apply <code>allOf</code> over those outcome futures.

Nor should you assume that <code>CompletionException.getSuppressed()</code> on the <code>allOf</code> result automatically collects the omitted exceptions. <code>allOf</code> has no contract promising a set of suppressed exceptions corresponding to all sources.

### 3.4. Collecting Values Only When All Succeed

~~~java
CompletableFuture<Void> barrier = CompletableFuture.allOf(a, b, c);

CompletableFuture<List<String>> values = barrier.thenApply(ignored ->
        List.of(a.join(), b.join(), c.join()));
~~~

This is **illustrative code** with three futures of type <code>CompletableFuture&lt;String&gt;</code> and importing <code>java.util.List</code>. When the barrier succeeds, all three sources have succeeded and the callback can retrieve the results. However, if the barrier fails, <code>thenApply</code> will be **skipped** and <code>values</code> will also fail.

Furthermore, <code>List.of</code> does not accept null. If a future succeeds with null, the callback will throw <code>NullPointerException</code> even though all sources completed normally. Therefore, this snippet only illustrates collecting data when values are known to be non-null; it is **not** a general collector for all outcomes.

## 4. anyOf: The First Completion May Be an Error

<code>CompletableFuture.anyOf</code> completes when **any single** source future completes. The combined future receives the successful result or error state from the winning source.

Example:

~~~java
CompletableFuture<String> fastError = new CompletableFuture<>();
CompletableFuture<String> slowSuccess = new CompletableFuture<>();

CompletableFuture<Object> first =
        CompletableFuture.anyOf(fastError, slowSuccess);

fastError.completeExceptionally(
        new IllegalStateException("Lỗi sớm"));
slowSuccess.complete("Thành công muộn");
~~~

This is **illustrative code** in which completions are invoked sequentially in exact order. The future <code>first</code> has completed with the exception from <code>fastError</code>. The later success of <code>slowSuccess</code> does not change the result of <code>first</code>.

**anyOf does not mean "first successful source".** If you want to ignore early errors and only use a successful result, you must write custom orchestration logic.

### anyOf Does Not Stop Losing Sources

<code>anyOf</code> returning a result early does not mean the other source futures are cancelled or that the tasks attached to them automatically stop. They may continue to complete, produce side effects, or fail later.

If an application uses <code>anyOf</code> for two service calls, you must decide:

- Do late errors from the remaining sources still need to be tracked and logged?
- Can the in-flight calls be safely cancelled?
- If the winning source fails, should you fall back to waiting for another source to succeed or fail immediately?
- Which resources must be closed once the result is no longer needed?
- Could side effects have already occurred even if a source future is cancelled?

Do not treat <code>anyOf</code> as a lifecycle management mechanism for all background work.

## 5. Standalone Java 17 Example: Direct Comparison of allOf and anyOf

Save the file **AllAnyDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class AllAnyDemo {
    public static void main(String[] args) {
        CompletableFuture<String> a = new CompletableFuture<>();
        CompletableFuture<String> b = new CompletableFuture<>();
        CompletableFuture<String> c = new CompletableFuture<>();

        CompletableFuture<Void> all =
                CompletableFuture.allOf(a, b, c);
        CompletableFuture<Object> any =
                CompletableFuture.anyOf(a, b, c);

        b.completeExceptionally(
                new IllegalStateException("B failed"));

        System.out.println("any.isDone: " + any.isDone());
        System.out.println("all.isDone khi A/C pending: " + all.isDone());

        try {
            any.join();
        } catch (CompletionException e) {
            System.out.println("any lỗi: "
                    + e.getCause().getClass().getSimpleName());
        }

        a.complete("A");
        c.completeExceptionally(
                new IllegalArgumentException("C failed"));

        System.out.println("all.isDone sau A/C: " + all.isDone());
        System.out.println("all.isCompletedExceptionally: "
                + all.isCompletedExceptionally());

        try {
            all.join();
        } catch (CompletionException e) {
            System.out.println("all có cause: "
                    + (e.getCause() != null));
        }

        System.out.println("A lỗi: " + a.isCompletedExceptionally());
        System.out.println("B lỗi: " + b.isCompletedExceptionally());
        System.out.println("C lỗi: " + c.isCompletedExceptionally());
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac -encoding UTF-8 AllAnyDemo.java
java AllAnyDemo
~~~

**Exact stdout:**

~~~text
any.isDone: true
all.isDone khi A/C pending: false
any lỗi: IllegalStateException
all.isDone sau A/C: true
all.isCompletedExceptionally: true
all có cause: true
A lỗi: false
B lỗi: true
C lỗi: true
~~~

Explanation:

1. As soon as B completes exceptionally, <code>anyOf</code> fails, while <code>allOf</code> remains pending because A and C have not finished.
2. <code>any.join()</code> throws a <code>CompletionException</code> containing B's error.
3. After A succeeds and C fails, all three sources are done. At that point <code>all</code> completes exceptionally.
4. The example only checks whether <code>all</code> has a cause; it **does not assume** <code>allOf</code> must choose either B or C as the representative error.
5. Reading each source's status shows that two errors exist simultaneously. If the program only inspects the error on <code>all</code>, details about both B and C will not be automatically aggregated.

The program creates no background threads: the order of <code>complete</code> calls is determined directly in <code>main</code>, so the output is unaffected by random scheduling.

## 6. Why You Cannot "Collect All Failures" with Only allOf.join()

When dozens of tasks run concurrently, the requirement to "collect all errors" differs from "fail if any error occurs".

~~~text
Required behavior                    Pure allOf
----------------------------------   -----------------------------
Wait for all sources                 Yes
Know if at least one error occurred  Yes, via exceptional completion
Return a List of results             No
Return a List of all Throwables      No
Preserve each source's ID            Not automatically
Distinguish error from null success  Not automatically
Auto-cancel hung tasks               No
~~~

One manual approach is to wait until the sources are done and then inspect each future individually using <code>join()</code> inside a <code>try/catch</code>. However, if the code wraps **the entire loop** in a single <code>try/catch</code>, it may stop at the first failed source and never inspect subsequent ones.

A more maintainable approach is to transform each source future into a future that **completes normally with outcome data**, then use <code>allOf</code> as the barrier. The collector will not depend on <code>allOf</code>'s mechanism for choosing a representative error.

## 7. Designing Outcome: Turning Failures into Data to Collect

A simple definition:

~~~java
record Outcome<T>(boolean success, T value, Throwable error) {}
~~~

An outcome represents the result of **one source**:

- <code>success=true, value="OK", error=null</code>: succeeded with a value.
- <code>success=true, value=null, error=null</code>: succeeded with null; still a **success**.
- <code>success=false, value=null, error=someThrowable</code>: failed, retaining the Throwable object.

When a future fails, the <code>handle</code> callback still executes:

~~~java
CompletableFuture<Outcome<String>> outcome = source.handle(
        (value, error) -> new Outcome<>(error == null, value, error));
~~~

This is an **illustrative snippet** assuming <code>source</code> has type <code>CompletableFuture&lt;String&gt;</code> and <code>Outcome</code> is defined. If the callback creates an Outcome and returns normally, the <code>outcome</code> future **succeeds** with the Outcome object, even if the source failed. As a result, the outcome futures can be combined with <code>allOf</code> without losing any source errors.

### Keep the Capture Callback Simple

The capture callback should only read <code>value</code>/<code>error</code> and construct data. If the callback itself throws an error (for example, by calling a broken data converter), the outcome future can also fail. In that case, <code>allOf</code> over the outcomes may fail because of the **collector**, defeating the goal of collecting all sources.

For high reliability, separate:

1. Capturing the source completion.
2. Waiting for all outcomes.
3. Presenting/logging/mapping outcomes according to the business contract.

Do not perform network calls or complex formatting in the capture step.

### The Throwable May Already Be Wrapped

In <code>handle((value, error) -&gt; ...)</code>, <code>error</code> is the <code>Throwable</code> visible at that source stage. If the error has passed through dependent stages, the received object may be a <code>CompletionException</code> whose cause is the underlying error.

The collector should **preserve the original error object** so that the cause chain, stack trace, and suppressed exceptions remain intact. Deciding which type to display or finding the root cause should be handled by a dedicated diagnostic layer. Do not convert an exception into a <code>getMessage()</code> string and lose information.

## 8. Standalone Java 17 Example: Collecting Both Values and All Errors

Create the file **CollectOutcomesDemo.java**:

~~~java
import java.util.List;
import java.util.concurrent.CompletableFuture;

public class CollectOutcomesDemo {
    record Outcome<T>(boolean success, T value, Throwable error) {}

    static <T> CompletableFuture<Outcome<T>> capture(
            CompletableFuture<T> source) {
        return source.handle((value, error) ->
                new Outcome<>(error == null, value, error));
    }

    static <T> CompletableFuture<List<Outcome<T>>> collect(
            List<CompletableFuture<T>> sources) {
        List<CompletableFuture<Outcome<T>>> observed =
                sources.stream()
                       .map(CollectOutcomesDemo::capture)
                       .toList();

        CompletableFuture<Void> barrier = CompletableFuture.allOf(
                observed.toArray(CompletableFuture[]::new));

        return barrier.thenApply(ignored ->
                observed.stream()
                        .map(CompletableFuture::join)
                        .toList());
    }

    public static void main(String[] args) {
        List<CompletableFuture<String>> sources = List.of(
                CompletableFuture.completedFuture("OK"),
                CompletableFuture.failedFuture(
                        new IllegalArgumentException("bad ID")),
                CompletableFuture.failedFuture(
                        new IllegalStateException("service unavailable")),
                CompletableFuture.completedFuture(null));

        List<Outcome<String>> outcomes = collect(sources).join();

        for (int i = 0; i < outcomes.size(); i++) {
            Outcome<String> result = outcomes.get(i);
            if (result.success()) {
                System.out.println(i + ": SUCCESS "
                        + String.valueOf(result.value()));
            } else {
                Throwable error = result.error();
                System.out.println(i + ": FAIL "
                        + error.getClass().getSimpleName()
                        + " -> " + error.getMessage());
            }
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 CollectOutcomesDemo.java
java CollectOutcomesDemo
~~~

**Exact stdout:**

~~~text
0: SUCCESS OK
1: FAIL IllegalArgumentException -> bad ID
2: FAIL IllegalStateException -> service unavailable
3: SUCCESS null
~~~

### Step-by-Step Execution

1. The list contains four already-completed sources. Two succeeded and two failed.
2. <code>capture</code> registers one <code>handle</code> callback per source, producing exactly one Outcome.
3. Those callbacks only construct a record, so the four corresponding outcome futures complete normally.
4. <code>allOf</code> over the four outcome futures completes normally when all four outcomes are ready.
5. <code>thenApply</code> runs after the barrier and reads each outcome in order; no extra blocking is needed because the barrier has already completed.
6. <code>stream().toList()</code> on an ordered source preserves encounter order. Data is printed in **input order**, with no need to guess which source ran first.
7. Each failed outcome retains that source's own <code>Throwable</code>. Thus neither of the two errors is lost just because <code>allOf</code> has a single representative exceptional completion.
8. The <code>SUCCESS null</code> result clearly demonstrates that null does not automatically mean failure.

This is a foundational pattern for collecting errors, though in real applications you often need to attach a <code>sourceId</code> or operation metadata to each outcome. When inputs come from multiple distinct services, reporting errors by index 0..N can become hard to read if the list changes.

## 9. Post-Collection Policies: Partial Success, All-or-Nothing, and Best Effort

After receiving <code>List&lt;Outcome&lt;T&gt;&gt;</code>, an API may need to choose one of these contracts:

| Contract | Meaning | How outcomes are handled |
| --- | --- | --- |
| **Partial success** | Each source is independent; successful results are still useful | Return successful data alongside per-source errors |
| **All-or-nothing** | The aggregated result is only valid if all sources succeed | Collect all errors, then report a composite failure containing details of the component errors |
| **Best effort** | Use every available result and record failed sources | Return available data and observe errors appropriately |

The collector is only responsible for **preserving completion data**, not deciding which errors are acceptable. The business layer decides whether one missing source causes the overall request to fail.

If you choose all-or-nothing, you can create an application-owned composite exception containing the list of errors with source IDs. Alternatively, you can deliberately use <code>addSuppressed</code> to retain secondary failures, but you must understand that a <code>Throwable</code> has only one direct cause and suppressed exceptions are not an automatic feature of <code>allOf</code>. The composite exception should be designed for the caller's needs, rather than forcing every client to parse message strings.

If only one representative exception is selected, define the selection rule explicitly (such as business priority or source order) instead of relying on whichever error <code>allOf</code> happens to report.

## 10. Avoiding Confusion Between Failed, Cancelled, and Timed-Out Futures

### Cancellation

~~~java
CompletableFuture<String> f = new CompletableFuture<>();
f.cancel(true);

System.out.println(f.isDone());                   // true
System.out.println(f.isCancelled());              // true
System.out.println(f.isCompletedExceptionally()); // true
~~~

The snippet above is **illustrative code**. Cancellation is a form of abnormal completion. A cancelled source can cause <code>allOf</code> to eventually complete exceptionally, or cause <code>anyOf</code> to complete exceptionally if it wins the race.

When reading a cancelled future directly with <code>join()</code>, you may observe <code>CancellationException</code>. Dependent stages may receive/report a wrapped exceptional completion. If the collector needs to distinguish cancellation from business failures, store a separate status instead of lumping every <code>Throwable</code> into the same message.

For <code>CompletableFuture</code>, <code>cancel(true)</code> **does not use the true flag to forcibly interrupt** running work the way some other Future implementations might. Do not treat <code>isCancelled()</code> as proof that the background thread has stopped or cleanup has finished.

### Timeout

- <code>orTimeout(timeout, unit)</code> completes **the future it is called on** with <code>TimeoutException</code> if it is still pending after the deadline.
- <code>completeOnTimeout(value, timeout, unit)</code> completes that future normally with a fallback value if it is still pending after the deadline.
- <code>get(timeout, unit)</code> only bounds **the caller's wait**; on timeout, the <code>get</code> call throws <code>TimeoutException</code> but does not turn the pending future into a failed future.

These cases are not the same. If you need to collect all outcomes within a time limit, explicitly define whether an expiration records a timeout error, a "no result yet" status, or a fallback value. Do not assume a timeout has stopped the computation, HTTP request, or background I/O.

### Sources Pending Forever

If a source never completes, <code>allOf</code> and any outcome collector built on it can also wait indefinitely. To guarantee a final result within a bounded time, you must enforce a deadline or timeout policy on the sources; you cannot expect <code>allOf</code> to automatically break the wait.

## 11. allOf and anyOf with Empty or Null Inputs

~~~java
CompletableFuture<Void> emptyAll = CompletableFuture.allOf();
CompletableFuture<Object> emptyAny = CompletableFuture.anyOf();
~~~

The two cases behave differently:

- <code>allOf()</code> has no sources, so it completes **normally right away** with <code>null</code>.
- <code>anyOf()</code> has no sources to supply a completion, so the returned future remains **incomplete**. Calling <code>emptyAny.join()</code> may wait indefinitely unless something explicitly completes that future.

When a source list can be empty, the application must define its own result. For example, the collector in the earlier example can return an empty outcome list via an empty <code>allOf</code>, whereas logic using <code>anyOf</code> must handle empty input early to avoid waiting forever.

A future **completing normally with null** is valid. Therefore <code>anyOf</code> may receive <code>null</code> from the winning source; the null value alone does not indicate which source won or whether an error occurred. If you need to know the winning source, map source values to a labeled record before racing.

A null future argument inside the array passed to <code>allOf/anyOf</code> is not a valid source future; do not use null as a placeholder for a "missing" task in the array.

## 12. "First Success" Is a Different Problem from anyOf

Suppose the requirement is:

> Call three sources concurrently; ignore early errors and return the first successful result; if all three fail, report all errors.

This involves two additional rules: **first-success** and **aggregate-failure**. Calling <code>anyOf</code> alone is insufficient because an early failure can win the race.

One algorithmic design approach:

1. Create a <code>CompletableFuture&lt;T&gt; result</code> representing the overall result.
2. Attach <code>whenComplete</code> or an appropriate callback to each source.
3. If a source succeeds, attempt <code>result.complete(value)</code>; only one successful completion takes effect.
4. If a source fails, record the error along with the source ID in a synchronized structure.
5. If **all sources have failed** and <code>result</code> is still pending, build a composite error from all failures and attempt <code>completeExceptionally</code>.
6. Account for races among multiple callbacks and choose thread-safe structures to store errors and count completions, avoiding premature error reporting.
7. Define the fate of still-running sources once a success is found, including stopping, timeouts, cleanup, and late errors.

A simpler variant uses the collector from section 8, waits for all sources to complete, and then picks a successful outcome. That variant **collects all errors**, but does not return a result early in time; do not call it first-success in terms of latency.

If sources have side effects, do not assume "losing sources" can be safely cancelled. The Future's result and the underlying system's execution/commit state must be managed separately.

## 13. Errors from the Collector Callback Differ from Source Errors

A failing source and a failing collection callback are two distinct causes.

Example:

~~~java
CompletableFuture<String> source =
        CompletableFuture.failedFuture(
                new IllegalArgumentException("source failure"));

CompletableFuture<Integer> badCollector = source.handle(
        (value, error) -> {
            throw new IllegalStateException("collector failure");
        });
~~~

This is **illustrative code**. <code>badCollector</code> carries the exceptional completion of the **callback**. If you subsequently use <code>allOf(badCollector, ...)</code>, the combined future can still fail, but that is an outcome-processing error rather than necessarily an additional failure in the source system.

Therefore, the core collector should stay simple and avoid calling uncontrolled code. If you need to report or transform errors into complex formats, do so in a later layer after all outcome data has been gathered; treat errors in the reporting layer as a separate category of failure.

Do not indiscriminately use <code>exceptionally(error -&gt; null)</code> just to make every future succeed, because doing so discards the cause and confuses failures with a null success result. An Outcome with a status field is a much clearer mechanism.

## 14. Testing: Driving Completions Deterministically by Hand

To test allOf/anyOf, prefer creating <code>new CompletableFuture&lt;&gt;()</code> instances and explicitly calling <code>complete</code>/<code>completeExceptionally</code> in the desired order. This proves the semantics without relying on luck from the scheduler.

| Scenario | Expectation |
| --- | --- |
| Both sources succeed | <code>allOf</code> succeeds after both are done |
| One source fails, another is pending | <code>allOf</code> is not done yet; <code>anyOf</code> may fail if that source is the winner |
| Both sources fail | <code>allOf</code> reports an error but does not automatically return both exceptions |
| Two failed sources wrapped with <code>handle</code> | Collector contains exactly two failed outcomes |
| One source succeeds with null | Success outcome distinct from failure |
| One source is cancelled | Abnormal completion status is recorded |
| One source hangs forever | <code>allOf</code> may remain pending until completion/timeout |
| Empty source array | <code>allOf</code> succeeds immediately, <code>anyOf</code> remains pending |
| Source completes early with an error | <code>anyOf</code> picks the error, does not wait for success |
| Capture callback throws an exception | Verify the collector's own error instead of misattributing it to a source |

The following **illustrative** JUnit 5 snippet assumes the <code>CollectOutcomesDemo</code> class and appropriate JUnit imports/libraries:

~~~java
CompletableFuture<String> first = new CompletableFuture<>();
CompletableFuture<String> second = new CompletableFuture<>();

CompletableFuture<List<CollectOutcomesDemo.Outcome<String>>> collected =
        CollectOutcomesDemo.collect(List.of(first, second));

IllegalArgumentException e1 = new IllegalArgumentException("one");
IllegalStateException e2 = new IllegalStateException("two");

first.completeExceptionally(e1);
assertFalse(collected.isDone());

second.completeExceptionally(e2);
List<CollectOutcomesDemo.Outcome<String>> data = collected.join();

assertEquals(2, data.size());
assertFalse(data.get(0).success());
assertFalse(data.get(1).success());
assertSame(e1, data.get(0).error());
assertSame(e2, data.get(1).error());
~~~

Assertions are from <code>org.junit.jupiter.api.Assertions</code>; you need to import <code>List</code>, <code>CompletableFuture</code>, and JUnit. The goal of the example is to prove that the collector **waits for both sources** and preserves the **exact Throwable instances**, not merely the same class or message.

When testing with real async tasks, enforce time limits and resource cleanup to prevent hanging the entire suite due to a future that never finishes. A test timeout does not replace asserting the exact number of collected errors.

## 15. Common Design Mistakes

1. **Assuming allOf fails fast:** it waits for every source to complete, even when one source has already failed.
2. **Only printing the exception from allOf.join():** other failures may be silently dropped.
3. **Assuming allOf picks the first or most important error:** no public rule guarantees such an ordering.
4. **Thinking allOf returns a List:** the return type is <code>CompletableFuture&lt;Void&gt;</code>.
5. **Collecting with thenApply after allOf and expecting to handle failures:** thenApply is skipped when a source fails.
6. **Using anyOf as first-success:** an early exception can still win the race.
7. **Forgetting still-running tasks after anyOf:** late errors and side effects may go unmanaged.
8. **Collapsing errors into message strings:** loses type, cause, stack trace, and source identity.
9. **Using null as a failure sentinel:** a normal completion can also hold null.
10. **Using List.of to collect potentially null values:** can throw a new NullPointerException inside the callback.
11. **Not handling an empty source list:** <code>anyOf()</code> has no source to complete it.
12. **Confusing cancellation with a stopped thread:** <code>cancel(true)</code> does not by itself guarantee the background task has terminated.
13. **Applying a timeout to a shared future without checking the impact:** <code>orTimeout</code> can mutate that future's state.
14. **Overcomplicating the capture callback:** the collector may throw a new error, obscuring source failures.
15. **Treating all errors as the same kind:** you may need to distinguish business, infrastructure, timeout, and cancellation errors.
16. **Relying on thread ordering in tests:** race outcomes are non-deterministic without explicit coordination.
17. **Omitting source IDs:** makes it hard to explain to users why each service failed.
18. **Ignoring error information security:** stack traces/causes may contain internal details that should not be exposed in API responses.

## 16. Practical Checklist

When designing an API that uses multiple <code>CompletableFuture</code> instances, verify:

- Do you need to **wait for all** or only for the **first completion**?
- Should an early exceptional completion be allowed to terminate the overall request?
- Does the caller need **one representative error** or a list of **all errors**?
- If all are needed, is an individual outcome preserved for each source, including null successes?
- Are stable ordering and clear source IDs required?
- Is the capture callback kept simple so it does not introduce unintended errors of its own?
- Is there a policy for forever-pending sources, deadlines, timeouts, and cancellation?
- Once <code>anyOf</code> completes, who manages still-running sources and late errors/side effects?
- Is future state distinguished from the actual termination of the background task?
- Do tests cover multiple concurrent errors, early errors, null values, empty lists, and pending cases?

**Remember:** <code>allOf</code> determines **when all sources have completed**, whereas <code>anyOf</code> determines **when one source completes first**. Neither automatically aggregates component exceptions. When you need to report all failures completely, use <code>handle</code> to turn each completion into an outcome holding a value and a Throwable, combine all outcomes, and then apply the result policy defined by your application's contract.
