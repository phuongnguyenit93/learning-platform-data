# CompletableFuture: Normal Completion and Exceptional Completion in Java

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain the two fundamental outcomes of a <code>CompletableFuture&lt;T&gt;</code>: **normal completion** and **exceptional completion**.
- Identify whether a future is incomplete, completed normally, or completed exceptionally; distinguish these from the concept of a running or stopped thread.
- Use <code>complete(value)</code>, <code>completeExceptionally(error)</code>, <code>completedFuture(value)</code>, <code>failedFuture(error)</code>, <code>supplyAsync(...)</code>, and <code>runAsync(...)</code> for their intended purposes.
- Observe results with <code>get()</code>, <code>join()</code>, <code>getNow(...)</code>, <code>isDone()</code>, <code>isCompletedExceptionally()</code>, and <code>isCancelled()</code>.
- Predict how dependent stages such as <code>thenApply</code>, <code>thenCompose</code>, <code>exceptionally</code>, <code>handle</code>, and <code>whenComplete</code> behave when the source succeeds or fails.
- Understand the relationship between completion, cancellation, timeout, and task execution on threads.

This lesson uses Java 17+ APIs in <code>java.util.concurrent</code>, prioritizing standalone examples with deterministic results.

## 2. What Does CompletableFuture Represent?

<code>CompletableFuture&lt;T&gt;</code> represents a result of type <code>T</code> that may become available later. It implements both <code>Future&lt;T&gt;</code> and <code>CompletionStage&lt;T&gt;</code>: it allows both waiting for/reading the result and declaring subsequent processing steps.

At any given time, a future can be:

1. **Incomplete:** no final result has been recorded in the future yet.
2. **Normally completed:** holds a result value of type <code>T</code> (including <code>null</code> if allowed by the API).
3. **Exceptionally completed:** holds a failure state associated with a <code>Throwable</code>, so that observers know the operation did not produce a successful value.

~~~text
                     Incomplete CompletableFuture<T>
                                   |
                     +-------------+-------------+
                     |                           |
             normal completion          exceptional completion
                     |                           |
               value T/null                Throwable/cause
                     |                           |
               join()/get()                 join()/get()
              returns value               throws per API
                     |                           |
          success stage runs          success-only stage may be
                                      skipped; exception-handling
                                      branch may be triggered
~~~

**Both types of completion count as "done".** Therefore, <code>isDone()</code> returns <code>true</code> for normal results, failures, and cancellations alike. Never use <code>isDone()</code> alone to conclude success.

It is necessary to distinguish between **future completion** and **execution task lifecycle**. A future can be completed manually without any background thread running; conversely, marking a future as cancelled does not necessarily force running code to stop immediately. A future only stores the result state according to its contract.

## 3. Normal Completion

A <code>CompletableFuture&lt;String&gt;</code> completes normally when it has a final successful result, for example <code>"OK"</code>.

### 3.1. Creating an Already-Completed Future

~~~java
CompletableFuture<String> done =
        CompletableFuture.completedFuture("OK");
~~~

The snippet above is **illustrative code**, with <code>java.util.concurrent.CompletableFuture</code> imported in an appropriate Java context. <code>done</code> is already completed at creation time, so <code>done.join()</code> returns <code>"OK"</code> without waiting for any computation.

<code>CompletableFuture.completedFuture(null)</code> is also a **normally completed** future with a value of <code>null</code>. Therefore, **a null value does not mean the future is incomplete or has failed**.

### 3.2. Manual Completion

~~~java
CompletableFuture<String> result = new CompletableFuture<>();
boolean first = result.complete("Đã xử lý");
boolean second = result.complete("Giá trị khác");
~~~

This is an **illustrative code snippet**, not a standalone program. In a non-contended sequence like the above:

- <code>new CompletableFuture&lt;&gt;()</code> creates an incomplete future.
- The first <code>complete("Đã xử lý")</code> call completes it successfully and returns <code>true</code>.
- The <code>complete("Giá trị khác")</code> call returns <code>false</code>, because the future already has a result; the initial successful value is preserved.

The <code>complete(T value)</code> method returns <code>true</code> when that call itself completes the future, and <code>false</code> if the future was already completed beforehand. In a multithreaded program, multiple parties may try to complete the same future; only one normal completion call wins the race.

### 3.3. Completion from an Asynchronous Task

~~~java
CompletableFuture<Integer> answer =
        CompletableFuture.supplyAsync(() -> 40 + 2);
~~~

<code>supplyAsync</code> accepts a <code>Supplier&lt;T&gt;</code>: if the supplier finishes by returning a value, the future is completed normally with that value. There is no guarantee that the future is already completed at the exact moment <code>supplyAsync</code> returns. You must use a result observation mechanism if you need to know for sure.

<code>runAsync</code> accepts a <code>Runnable</code> and returns a <code>CompletableFuture&lt;Void&gt;</code>. When the runnable finishes normally, its future completes normally with the value <code>null</code>; this is a success state, not a missing result due to an error.

If no custom <code>Executor</code> is provided, the common async forms of <code>CompletableFuture</code> use the JDK's default executor mechanism, typically <code>ForkJoinPool.commonPool()</code> under the conditions described in the API documentation. Do not rely on specific thread names to determine success or failure.

## 4. Exceptional Completion

A future completes exceptionally when its final outcome is an error state instead of a value of type <code>T</code>. The exception may come from the executing code or be attached to the future by a manual completion call.

### 4.1. Manual Completion with completeExceptionally

~~~java
CompletableFuture<String> result = new CompletableFuture<>();
IOException original = new IOException("Không thể đọc dữ liệu");

boolean first = result.completeExceptionally(original);
boolean second = result.complete("Kết quả đến muộn");
~~~

This is **illustrative code** in a context with <code>CompletableFuture</code> and <code>IOException</code> imported. With the sequence above, <code>first</code> is <code>true</code>, while <code>second</code> is <code>false</code>.

<code>result</code> completes exceptionally with <code>original</code>; the subsequent <code>complete</code> call does not change the error state into a success state.

**Important:** <code>completeExceptionally(error)</code> is an operation that **completes the future with an error state**, not one that directly throws <code>error</code> at the call site. Observers of the result later will receive the exception according to the contract of <code>get()</code> or <code>join()</code>.

The <code>Throwable</code> parameter of <code>completeExceptionally</code> must not be <code>null</code>; passing <code>null</code> causes a <code>NullPointerException</code> at this call and does not represent a successful completion.

### 4.2. Creating a Failed Future Upfront

~~~java
CompletableFuture<String> failed =
        CompletableFuture.failedFuture(
                new IllegalStateException("Dịch vụ không khả dụng"));
~~~

This snippet uses <code>failedFuture(Throwable)</code>, available since Java 9 and on Java 17+. The returned future is already completed exceptionally. This is a convenient tool for expressing an immediately failed step, such as when checking preconditions or returning a stub/test fixture.

### 4.3. Supplier or Runnable Throwing an Exception

~~~java
CompletableFuture<Integer> future =
        CompletableFuture.supplyAsync(() -> {
            throw new IllegalArgumentException("Dữ liệu không hợp lệ");
        });
~~~

The future will complete exceptionally when the supplier throws an error and the execution mechanism records the failure. The type of exception seen by external code depends on the result-observation API: for example, <code>join()</code> typically throws a <code>CompletionException</code> whose cause is the supplier's error.

However, a successful call to <code>supplyAsync</code> **does not mean the supplier ran successfully**. The scheduling method may return a future before the supplier even starts, and the subsequent completion indicates the processing outcome.

## 5. The Rule That Only One Normal Completion Takes Effect

<code>CompletableFuture</code> allows multiple threads to compete to complete it via <code>complete</code>, <code>completeExceptionally</code>, or <code>cancel</code>. Only the first recorded normal-completion outcome takes effect; subsequent completion calls do not overwrite the existing result.

| State Before Call | Call | Outcome |
| --- | --- | --- |
| Incomplete | <code>complete("A")</code> | Completes normally; returns <code>true</code> |
| Incomplete | <code>completeExceptionally(e)</code> | Completes exceptionally; returns <code>true</code> |
| Already succeeded | <code>complete("B")</code> | Value unchanged; returns <code>false</code> |
| Already succeeded | <code>completeExceptionally(e)</code> | Not changed to error; returns <code>false</code> |
| Already failed | <code>complete("B")</code> | Not changed to success; returns <code>false</code> |
| Already failed | <code>completeExceptionally(other)</code> | Old error unchanged; returns <code>false</code> |

With concurrent completion calls, you cannot predict which side wins based solely on the order written in two different threads. If the application needs a policy like "pick the best result", "prefer newer data", or "prefer errors", you must define and synchronize that policy; <code>complete</code> does not compare priorities on its own.

The exception to the *no-overwrite* rule is the low-level APIs <code>obtrudeValue</code> and <code>obtrudeException</code>, which intentionally force a result onto an already-completed future. They are positioned in the API documentation primarily for special error-recovery purposes and can cause inconsistencies with dependent stages that have already observed the previous result. Do not use them as a regular mechanism for changing business results.

## 6. Standalone Java 17 Example: Two States and Return Values of complete

Create the file **CompletionOutcomeDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class CompletionOutcomeDemo {
    public static void main(String[] args) {
        CompletableFuture<String> success = new CompletableFuture<>();
        CompletableFuture<String> failed = new CompletableFuture<>();

        System.out.println("Ban đầu: " + success.isDone()
                + ", " + failed.isDone());

        boolean successFirst = success.complete("DONE");
        boolean successAgain = success.completeExceptionally(
                new IllegalStateException("Quá muộn"));

        IllegalArgumentException original =
                new IllegalArgumentException("ID không hợp lệ");
        boolean failedFirst = failed.completeExceptionally(original);
        boolean failedAgain = failed.complete("LATE");

        System.out.println("Complete success: "
                + successFirst + ", " + successAgain);
        System.out.println("Complete failure: "
                + failedFirst + ", " + failedAgain);

        System.out.println("Success status: "
                + success.isDone() + ", "
                + success.isCompletedExceptionally());
        System.out.println("Failure status: "
                + failed.isDone() + ", "
                + failed.isCompletedExceptionally());

        System.out.println("Success value: " + success.join());

        try {
            failed.join();
        } catch (CompletionException ex) {
            System.out.println("Failure cause: "
                    + ex.getCause().getClass().getSimpleName());
            System.out.println("Original instance: "
                    + (ex.getCause() == original));
        }

        CompletableFuture<String> emptySuccess =
                CompletableFuture.completedFuture(null);
        System.out.println("Null is normal: "
                + emptySuccess.isDone() + ", "
                + emptySuccess.isCompletedExceptionally() + ", "
                + (emptySuccess.join() == null));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 CompletionOutcomeDemo.java
java CompletionOutcomeDemo
~~~

**Exact stdout:**

~~~text
Ban đầu: false, false
Complete success: true, false
Complete failure: true, false
Success status: true, false
Failure status: true, true
Success value: DONE
Failure cause: IllegalArgumentException
Original instance: true
Null is normal: true, false, true
~~~

### Output Explanation

1. Both futures are initially incomplete, so <code>isDone()</code> is <code>false</code>.
2. <code>success.complete("DONE")</code> wins and puts the future into the normal state. The subsequent <code>completeExceptionally</code> call cannot reverse the outcome.
3. <code>failed.completeExceptionally(original)</code> wins and puts the future into the error state. The subsequent <code>complete("LATE")</code> call cannot fix the stored error.
4. <code>isDone()</code> returns <code>true</code> for both after completion; only the failed future has <code>isCompletedExceptionally()</code> returning <code>true</code>.
5. <code>success.join()</code> returns <code>DONE</code>. <code>failed.join()</code> throws <code>CompletionException</code> in the example's <code>IllegalArgumentException</code> failure case.
6. <code>ex.getCause() == original</code> confirms the cause is the **exact same error instance** used to complete the future, not merely the same type or message.
7. A future with a <code>null</code> result is still a normally completed future: <code>isDone()</code> is <code>true</code>, <code>isCompletedExceptionally()</code> is <code>false</code>, and <code>join()</code> returns <code>null</code>.

The example uses no background threads, so the order of completions and output lines does not depend on executor scheduling.

## 7. Observing State: isDone, isCompletedExceptionally, and isCancelled

These methods answer different questions:

| Method | Question | What Cannot Be Inferred |
| --- | --- | --- |
| <code>isDone()</code> | Has the future completed in any form? | Does not prove success |
| <code>isCompletedExceptionally()</code> | Did the future finish due to an exception/cancellation state? | Does not provide the full cause without observing the exception |
| <code>isCancelled()</code> | Was the future cancelled according to CompletableFuture's cancellation state? | Does not prove underlying work has completely stopped |
| <code>getNumberOfDependents()</code> | Estimates the number of dependent stages waiting for completion | Not an instantaneously consistent coordination metric |

Example:

~~~java
CompletableFuture<String> f =
        CompletableFuture.failedFuture(new IllegalStateException("x"));

System.out.println(f.isDone());                   // true
System.out.println(f.isCompletedExceptionally()); // true
System.out.println(f.isCancelled());              // false
~~~

This is an **illustrative snippet**, not a standalone program. <code>isCompletedExceptionally()</code> identifies the error state, while <code>isCancelled()</code> helps distinguish cancellation cases. Do not treat every exception as cancellation.

An error-prone pattern:

~~~java
if (future.isDone()) {
    String value = future.join(); // Can still throw an error!
}
~~~

This is an **illustrative snippet**. <code>isDone()</code> being <code>true</code> only guarantees you no longer have to wait for a final state; it does not guarantee <code>join()</code> has a value to return.

Another error-prone pattern is checking <code>!future.isCompletedExceptionally()</code> while the future is still pending and concluding it will definitely succeed. At that moment, <code>isCompletedExceptionally()</code> may be <code>false</code> simply because **there is no result yet**.

## 8. Retrieving Results: How Do get() and join() Differ?

Both <code>Future.get()</code> and <code>CompletableFuture.join()</code> can wait for the result, but their exception contracts differ.

| Scenario | <code>get()</code> | <code>join()</code> |
| --- | --- | --- |
| Future completes normally | Returns value <code>T</code> | Returns value <code>T</code> |
| Future is still pending | Waits for completion (no-timeout overload) | Waits for completion |
| Future completes with a regular error | Throws checked <code>ExecutionException</code> with cause | Typically throws unchecked <code>CompletionException</code> with cause |
| Waiting thread is interrupted | May throw checked <code>InterruptedException</code> | Does not declare <code>InterruptedException</code>; waits per join's uninterruptible policy |
| Future was cancelled | May throw <code>CancellationException</code> | May throw <code>CancellationException</code> |
| Timed wait | <code>get(timeout, unit)</code> may throw <code>TimeoutException</code> | No direct timeout overload on <code>join()</code> |

**Distinguishing the two "causes":** the original error used to complete the future may be wrapped in a <code>CompletionException</code> when calling <code>join()</code>, or in an <code>ExecutionException</code> when calling <code>get()</code>. Handlers need to inspect <code>getCause()</code> to reach the original technical or business error.

An illustrative example:

~~~java
CompletableFuture<Integer> bad =
        CompletableFuture.failedFuture(
                new IllegalArgumentException("bad input"));

try {
    bad.get();
} catch (java.util.concurrent.ExecutionException e) {
    System.out.println(e.getCause().getClass().getSimpleName());
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
}
~~~

This is an **illustrative snippet inside a Java method** with <code>CompletableFuture</code> imported. In this example, the root cause is <code>IllegalArgumentException</code>. The <code>InterruptedException</code> branch restores the interrupt flag to avoid swallowing the interruption request if the waiting call is interrupted.

### getNow(valueIfAbsent)

<code>future.getNow(fallback)</code> does not wait for completion:

- If the future has completed normally, returns the result (including <code>null</code>).
- If incomplete, returns <code>fallback</code>.
- If completed exceptionally, it can still throw the corresponding exception instead of silently returning the fallback.

Therefore, <code>getNow("default")</code> is **not** a recovery mechanism for a failed future. The fallback value only represents the case where the result is not yet ready; it does not replace an existing exception. If <code>fallback</code> happens to match a valid value, looking at the return value alone cannot reliably distinguish between "pending" and "succeeded with that exact value".

## 9. Normal Processing Chains: thenApply, thenAccept, and thenRun

A <code>CompletionStage</code> can create stages that depend on the previous result.

~~~text
source: CompletableFuture<String>
          |
          | completes normally with "java"
          v
thenApply(String::toUpperCase)
          |
          v
dependent: CompletableFuture<String> = "JAVA"
~~~

With <code>thenApply(fn)</code>:

- When the source completes normally, the function receives the source value and returns a new value to complete the next stage.
- When the source completes exceptionally, the normal transformation function **is not run**; the dependent stage also completes along the exceptional path.
- When the transformation function itself throws an error, the dependent stage completes exceptionally with that function's error, even though the preceding source succeeded.

Two similar forms:

- <code>thenAccept(consumer)</code>: runs only on the success branch to consume the value; the dependent stage has type <code>Void</code>.
- <code>thenRun(runnable)</code>: runs only after the source succeeds, without receiving the source value; the dependent stage also has type <code>Void</code>.

Do not assume that because "the source future is done", the <code>thenApply</code> callback has definitely run. If the source completed with an error, the normal stage is skipped. Whether a dependent stage uses an <code>Async</code> variant can affect the thread and scheduling, but **does not change the success/failure branching condition**.

## 10. Recovering from Failure: exceptionally, handle, and whenComplete

This is the most important distinction when designing pipelines with two outcomes.

| API | When Source Succeeds | When Source Fails | Returned Stage Outcome |
| --- | --- | --- | --- |
| <code>thenApply(fn)</code> | Runs <code>fn</code> | Skips <code>fn</code> | Stage transforming data if successful |
| <code>exceptionally(fn)</code> | Does not call <code>fn</code>, keeps result | Calls <code>fn</code> with the error to provide a replacement value | Stage that can recover with a value |
| <code>handle((value, error) -&gt; ...)</code> | Called with result and <code>error == null</code> | Called with <code>error != null</code> | Stage whose result is decided by the handler function |
| <code>whenComplete((value, error) -&gt; ...)</code> | Called to observe, keeps normal result if callback does not throw | Called to observe, keeps original failure if callback does not throw | Observation stage; **does not replace an error with a recovery value** |

### 10.1. exceptionally: Producing a Replacement Value on Error

~~~java
CompletableFuture<String> recovered = original
        .exceptionally(error -> "Tài liệu dự phòng");
~~~

This is **illustrative code** with <code>original</code> as an existing <code>CompletableFuture&lt;String&gt;</code>. If the source succeeds, the new stage keeps the success value; if the source fails, the function supplies a replacement value so the new stage completes normally.

**Do not confuse:** <code>exceptionally</code> creates a next stage capable of recovery; it does not mutate the state of the failed source future. If other branches still hold a reference to the source future and call <code>join()</code>, those branches may continue to see the original exception.

If the <code>exceptionally</code> function itself throws an error, the recovery stage also completes exceptionally with the new exception. Simply "attaching exceptionally" does not guarantee the entire pipeline will succeed.

### 10.2. handle: Handling Both Paths

~~~java
CompletableFuture<Integer> normalized = original.handle(
        (value, error) -> error == null ? value.length() : -1);
~~~

This is **illustrative code**, assuming <code>original</code> has type <code>CompletableFuture&lt;String&gt;</code>. The <code>handle</code> function is invoked when the source completes in any form:

- Success: <code>error == null</code>; <code>value</code> can be a string or <code>null</code> if a null value is a valid success. This example assumes the successful source does not return null.
- Failure: <code>error != null</code>; the code takes the fallback branch to return <code>-1</code>.

Do not simply check <code>value == null</code> to infer an error, because a future that completes normally with <code>null</code> also passes <code>null</code> into the callback.

### 10.3. whenComplete: Observing Without Turning Failure into Success

~~~java
CompletableFuture<String> observed = original.whenComplete(
        (value, error) -> {
            if (error != null) {
                recordFailure(error);
            }
        });
~~~

This is **illustrative code** with <code>recordFailure</code> as an application-defined function. When <code>original</code> fails and the callback runs normally, <code>observed</code> still completes exceptionally. It does not "swallow" the error to return a valid string.

If the <code>whenComplete</code> callback throws an exception when the preceding source succeeded, the dependent stage can complete with the callback's exception. If the source already failed and the callback also throws, by <code>whenComplete</code>'s contract, the error from the source takes precedence in determining the dependent stage's completion. Therefore, error-observation callbacks should be designed reliably and avoid accidentally introducing additional errors.

### 10.4. thenCompose and Exceptional Completion

<code>thenCompose</code> is used when the transformation function returns another <code>CompletionStage</code>. When the source fails, the normal compose function is skipped, and the dependent stage follows the error path. When the source succeeds and the function returns a failed stage, the resulting future also fails accordingly.

If error recovery must run **asynchronously** and return an alternative <code>CompletionStage</code>, Java 17 supports <code>exceptionallyCompose</code> and its Async variants. This method differs from <code>exceptionally</code> in that the recovery function returns a stage, avoiding accidentally creating nested futures.

## 11. Standalone Java 17 Example: Pipeline Routing Through Both Completion Branches

Create the file **CompletionStageRoutingDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class CompletionStageRoutingDemo {
    public static void main(String[] args) {
        CompletableFuture<String> ok =
                CompletableFuture.completedFuture("java");

        CompletableFuture<String> bad =
                CompletableFuture.failedFuture(
                        new IllegalStateException("service down"));

        AtomicInteger skippedCalls = new AtomicInteger();
        AtomicBoolean observedFailure = new AtomicBoolean();

        CompletableFuture<Integer> transformed =
                ok.thenApply(String::length);

        CompletableFuture<Integer> skipped =
                bad.thenApply(value -> {
                    skippedCalls.incrementAndGet();
                    return value.length();
                });

        CompletableFuture<Integer> recovered =
                skipped.exceptionally(error -> -1);

        CompletableFuture<Integer> handled =
                bad.handle((value, error) ->
                        error == null ? value.length() : -2);

        CompletableFuture<String> observed =
                bad.whenComplete((value, error) ->
                        observedFailure.set(error != null));

        System.out.println("Thành công thenApply: "
                + transformed.join());
        System.out.println("Lần chạy callback bị bỏ qua: "
                + skippedCalls.get());
        System.out.println("Phục hồi exceptionally: "
                + recovered.join());
        System.out.println("Xử lý handle: "
                + handled.join());
        System.out.println("whenComplete thấy lỗi: "
                + observedFailure.get());
        System.out.println("Stage nguồn vẫn lỗi: "
                + bad.isCompletedExceptionally());

        try {
            observed.join();
        } catch (CompletionException ex) {
            System.out.println("Quan sát không phục hồi: "
                    + ex.getCause().getClass().getSimpleName());
        }
    }
}
~~~

Run with Java 17+:

~~~bash
javac -encoding UTF-8 CompletionStageRoutingDemo.java
java CompletionStageRoutingDemo
~~~

**Exact stdout:**

~~~text
Thành công thenApply: 4
Lần chạy callback bị bỏ qua: 0
Phục hồi exceptionally: -1
Xử lý handle: -2
whenComplete thấy lỗi: true
Stage nguồn vẫn lỗi: true
Quan sát không phục hồi: IllegalStateException
~~~

Analysis:

1. <code>ok</code> completes normally with <code>"java"</code>, so <code>thenApply(String::length)</code> returns <code>4</code>.
2. <code>bad</code> is already completed exceptionally. The callback in <code>thenApply</code> on the error branch does not run, so <code>skippedCalls</code> remains <code>0</code>.
3. <code>skipped</code> fails following the source. <code>exceptionally</code> on <code>skipped</code> converts the failure to the value <code>-1</code>, so the **recovered future** completes normally.
4. <code>handle</code> is invoked on the failed source, receives <code>error != null</code>, and returns <code>-2</code>. The <code>handled</code> stage completes normally.
5. <code>whenComplete</code> is invoked to record that an error occurred, but <code>observed</code> still completes exceptionally with <code>IllegalStateException</code>.
6. <code>bad.isCompletedExceptionally()</code> remains <code>true</code>: other recovery stages do not alter the source's state.

The example uses already-completed futures and callbacks without asynchronous delays, so it does not depend on the order in which tasks run on a thread pool. Results printed **after** the corresponding <code>join()</code> calls ensure the stages have completed.

## 12. Completion of a Task Executed by an Executor

A future from <code>supplyAsync</code> has its outcome determined by the work inside the supplier. If the supplier throws a <code>RuntimeException</code>, code collecting the result from the future must handle the exceptional completion path.

Create the file **AsyncCompletionDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class AsyncCompletionDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newFixedThreadPool(2);

        try {
            CompletableFuture<Integer> good =
                    CompletableFuture.supplyAsync(() -> 20 + 22, executor);

            CompletableFuture<Integer> bad =
                    CompletableFuture.supplyAsync(() -> {
                        throw new IllegalArgumentException("bad input");
                    }, executor);

            System.out.println("Kết quả tốt: " + good.join());

            try {
                bad.join();
            } catch (CompletionException ex) {
                System.out.println("Kết quả lỗi: "
                        + ex.getCause().getClass().getSimpleName()
                        + " -> " + ex.getCause().getMessage());
            }

            System.out.println("Good exceptional: "
                    + good.isCompletedExceptionally());
            System.out.println("Bad exceptional: "
                    + bad.isCompletedExceptionally());
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
                executor.shutdownNow();
                throw new IllegalStateException("Executor không kết thúc");
            }
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 AsyncCompletionDemo.java
java AsyncCompletionDemo
~~~

**Stdout under normal executor execution:**

~~~text
Kết quả tốt: 42
Kết quả lỗi: IllegalArgumentException -> bad input
Good exceptional: false
Bad exceptional: true
~~~

The two suppliers can run in parallel and finish in any order. The program still prints in the chosen order because <code>main</code> observes <code>good.join()</code> first, and only then observes <code>bad.join()</code> and their states.

<code>shutdown()</code> asks the executor to stop accepting new tasks, while <code>awaitTermination(...)</code> waits for tasks to finish and helps clean up resources. If an unusual timeout occurs in an overloaded environment, the example throws an executor-specific error and does not claim the stdout above will be complete; that is an operational condition, not the outcome path this lesson illustrates.

Note: <code>join()</code> on a failed future reports the future's state; **it does not propagate the exception along a synchronous call stack from worker to main**. The <code>CompletionException</code> wrapper provides the asynchronous result-observation contract.

## 13. Cancellation Is a Form of Exceptional Completion

<code>CompletableFuture.cancel(boolean mayInterruptIfRunning)</code> marks the future as cancelled if possible. In Java's <code>CompletableFuture</code> implementation, cancellation is a form of exceptional completion carrying a <code>CancellationException</code>.

Illustrative example:

~~~java
CompletableFuture<String> future = new CompletableFuture<>();
boolean cancelled = future.cancel(true);

System.out.println(cancelled);                        // true
System.out.println(future.isDone());                  // true
System.out.println(future.isCancelled());             // true
System.out.println(future.isCompletedExceptionally()); // true
~~~

This is an **illustrative snippet** with no prior completion calls before <code>cancel(true)</code>. Note:

- <code>future.join()</code> or <code>future.get()</code> on the cancelled future itself may throw <code>CancellationException</code> directly. Do not catch only <code>CompletionException</code> and assume you have covered all failure types.
- For <code>CompletableFuture</code>, the <code>mayInterruptIfRunning</code> parameter **is not used to interrupt underlying execution** under this implementation's contract. Thus, <code>cancel(true)</code> does not guarantee the async work has stopped.
- Dependent stages waiting for normal completion may become exceptionally completed due to source cancellation. The exception observed on a dependent stage may be wrapped in a <code>CompletionException</code>.
- Reading <code>isCancelled()</code> only provides the future's state, not a confirmation that resources, transactions, or workers have finished cleaning up.

For a producer that genuinely needs to stop work, you must design an explicit cooperative mechanism such as a cancellation flag, interrupting the appropriate thread, or an executor shutdown procedure; do not treat changing the future's state as forcibly stopping code.

## 14. Timeouts Can Also Decide Completion

Java 17 has two convenience methods introduced in Java 9:

- <code>orTimeout(timeout, unit)</code>: if the future has not completed within the deadline, attempts to complete **that same future** exceptionally with a <code>TimeoutException</code>.
- <code>completeOnTimeout(value, timeout, unit)</code>: if not completed within the deadline, attempts to complete **that same future** normally with the fallback <code>value</code>.

Both methods return **the same CompletableFuture receiving the call**, not a copy with an independent timeout rule. They race against any result that the task or manual completion code may supply first.

Illustrative example:

~~~java
CompletableFuture<String> slow = new CompletableFuture<>();
slow.completeOnTimeout("Giá trị dự phòng", 200,
        java.util.concurrent.TimeUnit.MILLISECONDS);
~~~

If no party completes <code>slow</code> sooner within the deadline, the future will complete **normally** with <code>"Giá trị dự phòng"</code>.

~~~java
CompletableFuture<String> another = new CompletableFuture<>();
another.orTimeout(200, java.util.concurrent.TimeUnit.MILLISECONDS);
~~~

If no party completes <code>another</code> before the deadline, the future will complete **exceptionally** with a <code>TimeoutException</code>. At the <code>join()</code> call site, you may see a <code>CompletionException</code> with the corresponding timeout as its cause.

**Do not infer** that the timeout terminated the underlying I/O or running task. Timeout only affects the future's completion according to its documented rules. If the underlying task continues running and eventually calls <code>complete(...)</code>, that late completion call cannot replace the timeout outcome that already won.

Also distinguish <code>get(timeout, unit)</code>: if the wait time of **the get call itself** expires, it throws <code>TimeoutException</code> to the caller, without completing the future itself with an error. This is a major difference between "timing out while waiting to retrieve a result" and "setting a timeout on completion state".

## 15. Combining Multiple Futures: allOf and anyOf

### allOf

<code>CompletableFuture.allOf(f1, f2, ...)</code> creates a future of type <code>Void</code> that completes when all input futures have completed. If any input future completes exceptionally, the combined future also completes exceptionally per its contract, rather than returning a list of successful results.

~~~java
CompletableFuture<String> first =
        CompletableFuture.completedFuture("A");
CompletableFuture<Integer> second =
        CompletableFuture.completedFuture(10);

CompletableFuture<Void> combined =
        CompletableFuture.allOf(first, second);
combined.join();

String a = first.join();
Integer b = second.join();
~~~

This is **illustrative code**. <code>allOf</code> does not automatically collect each future's value into a list; after the combination succeeds, read each source to retrieve its value.

If one of the sources fails, <code>combined.join()</code> may throw <code>CompletionException</code>. Do not rely on it to "fail fast" at the moment the first source fails; by contract, <code>allOf</code> completes when **all input futures complete**, and then expresses exceptional completion if there was an error.

### anyOf

<code>CompletableFuture.anyOf(f1, f2, ...)</code> completes when **any single input future completes**, using that future's result or error. It does not mean "take the first successful future".

If one future fails earlier than a succeeding future, <code>anyOf</code> can complete exceptionally with the failed source's exception. To implement a "prefer successful result" policy, you need a different selection design rather than simply switching <code>allOf</code> to <code>anyOf</code>.

In real multithreaded code, race outcomes depend on completion order. Do not publish stdout assuming a particular future wins unless the example has synchronization enforcing that order.

## 16. Error Model in Stage Chains: Failures Are Not Swallowed Automatically

Consider the pipeline:

~~~text
supplyAsync(fetchData)
    |
    +-- success --> thenApply(parse) --> thenApply(validate) --> result
    |
    +-- failure --> normal thenApply stages are skipped
                     |
                     +--> exceptionally(fallback) --> can recover
                     |
                     +--> whenComplete(log) --> still reports failure
~~~

Note the following characteristics:

1. **Each step returns a new stage.** If you keep a reference to the failed source, calling <code>source.join()</code> still reports the error even if a child branch has recovered.
2. **Errors in a callback are recorded in the stage created by that callback.** A <code>thenApply</code> that receives a successful value but throws <code>NumberFormatException</code> causes the new stage to fail; the preceding source may still have succeeded.
3. **Exception propagation may be wrapped in <code>CompletionException</code>.** When handling errors deep in a chain, inspect the cause in a controlled manner and avoid assuming every throwable is the same root class.
4. **Recovery only happens when code actively provides a valid result.** A default value such as <code>0</code>, an empty string, or <code>null</code> is not always a valid representation of failure for the API contract.
5. **Async stages can still fail.** Running a callback on a different executor does not change its success or failure semantics; it only changes when and where the callback executes.

A contract-selection pattern is to recover from expected errors while continuing to propagate unrecoverable ones:

~~~java
CompletableFuture<String> recovered = source.exceptionally(error -> {
    if (isRecoverable(error)) {
        return cachedValue();
    }
    throw new IllegalStateException("Không thể phục hồi", error);
});
~~~

This is an **illustrative code snippet**, assuming <code>source</code>, <code>isRecoverable</code>, and <code>cachedValue</code> already exist and the data types match. On the recoverable branch, the dependent stage completes normally. On the other branch, it completes exceptionally with an <code>IllegalStateException</code> carrying the cause for diagnostics.

Before writing <code>isRecoverable</code>, keep in mind that the received exception may be a <code>CompletionException</code> wrapper. Do not classify errors by comparing fragile <code>getMessage()</code> strings; rely on exception types and specific contracts instead.

## 17. Callback Execution Threads and Completion Timing

A common question: "Does the <code>thenApply</code> callback always run on the worker thread that completed the source?"

No. According to <code>CompletableFuture</code>'s execution policy, dependent actions **without the <code>Async</code> suffix** may be executed by the thread completing the future or another caller participating in the completion process. Actions **with the <code>Async</code> suffix** are submitted to the corresponding executor, either the default one or one you provide.

This has two consequences:

- Do not rely on thread names, log timestamps, or the order of independent callbacks to determine the future's state. Use the completion API or appropriate synchronization mechanisms.
- Do not place heavy blocking tasks or operations with uncontrolled side effects inside a callback that you assume will definitely run on a background executor. Consider using an Async variant with an explicitly managed executor.

However, regardless of which thread runs the callback, **the logical relationship remains the same**: <code>thenApply</code> only executes when the source completes normally; <code>handle</code> executes for both success and error; <code>exceptionally</code> recovers the error branch.

For workflows that need to report a single result to a client, choose a clear output stage and observe the completion of that exact stage, avoiding multiple threads writing to an unsynchronized "status" variable.

## 18. Common Misconceptions and Mistakes

### 18.1. isDone() Being true Means Success

False. Failed and cancelled futures are also done. Use <code>join()</code>/<code>get()</code> to retrieve the result per contract, or additionally check state/design error-handling callbacks.

### 18.2. completeExceptionally() Throws the Exception Immediately to the Caller

False. It completes the future with an error state; for a caller to see the exception, the caller must observe the future via an appropriate API or stage. The <code>completeExceptionally(error)</code> call itself normally returns a boolean.

### 18.3. complete() Always Overwrites the Old Result

False. Normal completion only has one winner. Subsequent <code>complete</code> calls return <code>false</code>. Do not use <code>obtrudeValue</code> to patch an unclear, competing producer design.

### 18.4. getNow(fallback) Turns Every Error into the Fallback

False. It only returns the fallback when the future is **incomplete**. An already-failed future can still throw an exception when called.

### 18.5. exceptionally Makes the Source Future Succeed Again

False. It creates a dependent stage that can complete successfully with a replacement value. The source future retains its failed state, and other branches can still observe that error.

### 18.6. whenComplete Swallows the Error Because It Ran a Callback

False. <code>whenComplete</code> observes, while the source's exceptional completion normally continues to the dependent stage. If you need to turn a failure into a value, use <code>exceptionally</code> or <code>handle</code> per contract.

### 18.7. null Means Error or Incomplete

False. <code>CompletableFuture.completedFuture(null)</code> is a normal completion. If you want to detect an error in <code>handle</code>, check the <code>error</code> parameter, not just the <code>value</code>.

### 18.8. join() and get() Throw the Exact Same Exceptions

False. <code>get()</code> has checked exceptions like <code>InterruptedException</code> and <code>ExecutionException</code>; <code>join()</code> represents regular completion errors via unchecked <code>CompletionException</code>. Both can directly report <code>CancellationException</code> when the future is cancelled.

### 18.9. cancel(true) Always Interrupts and Stops the Task

False for <code>CompletableFuture</code>. A cancelled future state does not guarantee a running supplier stops; this method's interrupt parameter does not control the worker the way some <code>FutureTask</code> implementations do.

### 18.10. allOf Returns a List of Results

False. It returns <code>CompletableFuture&lt;Void&gt;</code>. You need to read the results from each source future after the group completes normally.

### 18.11. anyOf Always Picks a Success

False. The first future to complete may finish with an exception; <code>anyOf</code> may fail immediately with that result.

### 18.12. Timeout Always Stops the Background Task

False. <code>orTimeout</code> or <code>completeOnTimeout</code> decides the **future's state** upon expiration; it does not automatically ensure the task or I/O has been cancelled.

## 19. What Should Tests Verify?

When writing unit or integration tests for completion, separate **future state**, **observed value/error**, and **dependent stage behavior**.

| Case | Verification |
| --- | --- |
| Newly created future | <code>isDone() == false</code> |
| First <code>complete(value)</code> | Returns <code>true</code>; <code>join()</code> returns the exact value |
| Second <code>complete</code> | Returns <code>false</code>; previous value unchanged |
| <code>completeExceptionally(original)</code> | Returns <code>true</code> if pending; future completes exceptionally |
| <code>complete</code> after exceptional completion | Returns <code>false</code>; previous error intact |
| <code>join()</code> on regular failure | Throws <code>CompletionException</code> with appropriate cause |
| <code>get()</code> on regular failure | Throws <code>ExecutionException</code> with appropriate cause |
| Future completed normally with <code>null</code> | <code>isDone() == true</code>, <code>isCompletedExceptionally() == false</code> |
| <code>thenApply</code> on failed source | Normal callback does not run; dependent stage fails |
| <code>exceptionally</code> returns fallback | Dependent stage succeeds, source remains failed |
| <code>whenComplete</code> observes error | Callback is invoked; error is not automatically cleared |
| <code>cancel</code> before completion | Future transitions to cancelled state; reading result reports cancellation |

Example of verifying the cause in JUnit 5 (**illustrative snippet in a test class that already has the JUnit 5 dependency and appropriate imports**):

~~~java
IllegalArgumentException original =
        new IllegalArgumentException("bad id");

CompletableFuture<String> failed = new CompletableFuture<>();
boolean updated = failed.completeExceptionally(original);

assertTrue(updated);
assertTrue(failed.isDone());
assertTrue(failed.isCompletedExceptionally());

CompletionException thrown =
        assertThrows(CompletionException.class, failed::join);
assertSame(original, thrown.getCause());
~~~

This snippet checks the **exact cause instance**, not just the class or message. With Java 17 and JUnit 5, the corresponding assertions belong to <code>org.junit.jupiter.api.Assertions</code>. Do not present the snippet above as a standalone Java program because it requires a test class and JUnit dependency.

In concurrency tests, use <code>CountDownLatch</code>, futures for coordination, or timed APIs; avoid relying on "lucky" thread execution order. In a race between normal and exceptional completion, assert that **only one completion wins**, rather than always demanding a specific branch win if ordering has not been established.

## 20. Checklist When Designing an API Returning CompletableFuture

Before releasing a method that returns <code>CompletableFuture&lt;T&gt;</code>, ask yourself:

1. **What is the success value?** Is <code>null</code> valid, or should you use a data type that clearly expresses "no result"?
2. **What exceptions are meaningful to the caller?** Does a technical error need to be translated into an API-layer exception while preserving the cause?
3. **Who is responsible for completion?** Which producer calls <code>complete</code>/<code>completeExceptionally</code>; is there a risk of multiple producers racing?
4. **Who is responsible for observation?** Does the caller use <code>get()</code>, <code>join()</code>, or register a dependent stage?
5. **Is there a genuine recovery branch?** If using <code>exceptionally</code>/<code>handle</code>, does the fallback value still satisfy the business contract?
6. **Is there a logging-only stage?** Use <code>whenComplete</code> and understand that it does not automatically turn an error into success.
7. **What do timeout and cancellation mean?** Is the future's state sufficient to confirm the task has stopped or resources have been released?
8. **Is executor control needed?** Are blocking callbacks offloaded to an appropriate executor?
9. **When combining multiple futures**, do you need to wait for all, wait for the first completion, or select the first successful result under a custom policy?
10. **Do tests cover both completion types** and dependent stages, including <code>null</code>, cancellation, timeout, and errors inside callbacks?

**Remember:** a completed <code>CompletableFuture</code> can carry either a **success value** or an **error state**. Both states make <code>isDone()</code> return <code>true</code>, yet they lead to completely different callback branches and observation behaviors. Good design clearly defines who completes the future, who handles exceptions, when to recover with a value, and when to preserve the error for the caller to decide.