# Managing the start, scope, error, and stop Lifecycle

## 1. Two Things to Manage: Measured Work and Active Scope

When observing an operation such as order processing, we need to mark start and end times and record any errors. At the same time, code running inside the operation needs to know which observation it belongs to, so nested calls can attach to the right context.

Micrometer separates these two needs:

- **Observation lifecycle:** defines when the unit of work starts and stops.
- **Scope lifecycle:** defines which observation is currently active during an execution block.

You can think of an observation as starting and stopping a stopwatch for the work, and scope as placing that work's name into the thread's "currently processing" slot. Stopping the stopwatch and clearing the current slot are two separate actions.

```text
Observation:   create → start ------------------------------→ stop
Scope:                        open → execute → close
Error if any:                           error(ex)
```

The diagram shows the roles, without enforcing that `error(ex)` always precedes `close`. Where the error is reported depends on how try/catch and the wrapping API are written.

Getting either lifecycle wrong can cause two classes of problems:

1. Forgetting `stop()`: observation handlers do not receive the completion signal on time.
2. Forgetting to close the scope: the old observation may remain active when the thread moves on to another task.

This lesson uses synchronous execution to explain both lifecycles in full, then points out what must change when work runs asynchronously. The signal model is described in [Micrometer Observation — Introduction](https://docs.micrometer.io/micrometer/reference/1.13/observation/introduction.html).

## 2. Four Operations That Do Not Substitute for One Another

| Operation | Responsibility | What must not be assumed |
| --- | --- | --- |
| `start()` | Starts the observation and notifies matching handlers of the start milestone | Does not automatically make the observation current on the thread |
| `openScope()` | Places the observation into the current scope and returns a closeable scope resource | Does not replace `start()` or `stop()` |
| `error(ex)` | Records/signals an error on the observation | Does not rethrow the exception, roll back, or stop the observation |
| `stop()` | Ends the observation and notifies the completion milestone | Does not replace closing the scope |

When a handler supports the context in use, these signals map to `onStart`, `onScopeOpened`, `onError`, and `onStop`. Closing the scope triggers the `onScopeClosed` callback. Actual output still depends on the handlers: the same lifecycle can drive timing, tracing, or custom observation behavior.

### 2.1. Creating Unstarted to Prepare Metadata

```java
Observation observation = Observation.createNotStarted(
        "orders.process", registry)
        .lowCardinalityKeyValue("channel", "web");
```

This is an excerpt, assuming `ObservationRegistry registry` already exists. After that call, the observation has not started yet. You can prepare the name/tags and required input data before handlers receive the start milestone.

If the method returns right after that snippet without calling `start()` or a lifecycle-managing API such as `observe(...)`, no complete unit of observed work has occurred.

There is also a way to create and start immediately:

```java
Observation observation = Observation.start("orders.process", registry);
```

This is useful when you want to start right at that exact spot. Do not call `start()` again out of forgetting that the helper already started the observation.

### 2.2. Starting Does Not Mean Scope Is Open

With a registry configured to observe and no outer observation present, right after `start()`, `registry.getCurrentObservation()` can still be `null`.

That does not prove the observation failed to start. It only indicates there is no current observation in the active scope.

For inner code to see that observation as current:

```java
try (Observation.Scope scope = observation.openScope()) {
    // Synchronous calls inside this scope can find the current observation.
}
```

This is only the scope-management snippet. The enclosing observation still must be started and stopped by whatever owns its lifecycle.

### 2.3. Reporting the Error and Propagating It to the Caller Are Two Responsibilities

```java
observation.error(ex);
throw ex;
```

The first line serves observability. The second maintains the exception flow to the caller.

If you only report the error and return a fake success value, the caller can misread the business outcome. If you only throw the error in a manually managed structure without reporting it to the observation, handlers may not receive the corresponding error signal.

A business operation returning a "rejected" value without throwing an exception also does not cause `onError` to fire automatically. You must define the convention: is that a normal outcome for grouping, or a failure to record via the error mechanism? Do not turn every conditional branch into an exception just to generate more telemetry.

### 2.4. Stopping Does Not Mean Data Has Been Exported to a Backend

`stop()` is the end signal within the observation mechanism. Handlers may finalize timers or spans at this point, but sending/storing data in external systems still depends on the registry, exporter, and network transport.

Therefore, "called stop" and "saw metrics on the dashboard" are two different milestones. Do not add another `stop()` call just because a dashboard has not updated yet.

## 3. Manual Management Pattern for Synchronous Work

Suppose `processOrder()` is an application business method. The following snippet shows explicit lifecycle ownership:

```java
Observation observation = Observation.createNotStarted(
        "orders.process", registry)
        .lowCardinalityKeyValue("channel", "web");

observation.start();
try (Observation.Scope scope = observation.openScope()) {
    processOrder();
}
catch (RuntimeException | Error ex) {
    observation.error(ex);
    throw ex;
}
finally {
    observation.stop();
}
```

`processOrder()` is not a Micrometer API; the snippet illustrates where business logic goes, not a standalone program. A complete runnable program appears in the hands-on section.

### 3.1. Why Is the Scope Inside Try-With-Resources?

`Observation.Scope` is a resource that must be closed. Try-with-resources closes it when the block finishes normally, throws an exception, or exits via `return`.

What must be restored is **the previous scope**. In a task with no enclosing observation, current may return to `null`. In a task with an active parent observation, current must return to the parent observation, not always to `null`.

Do not replace closing the scope with manually clearing current to null. Doing so can break the observation enclosing the child work.

### 3.2. Why Is stop Inside finally?

Business logic has multiple exit paths: running to completion, returning early, or throwing an error. Placing `stop()` only after the business line misses paths that never reach that line.

```java
observation.start();
processOrder();
observation.stop();
```

The snippet above is an example **missing error-path management**: if `processOrder()` throws an exception, the `stop()` line never runs. It also fails to open a scope if inner calls need the current observation.

In the proper pattern, `finally` is responsible for stopping the observation that this method itself created/started. Do not use `finally` to stop a framework or caller observation.

### 3.3. Why Does catch Come After the Resource Block?

In the pattern above, if business logic throws an error:

```text
business logic throws error
    → try-with-resources closes scope
    → catch calls error(ex)
    → catch rethrows error
    → finally calls stop()
    → error continues to caller
```

Because of that, `onError` on this path can be invoked after the observation is no longer current. Callbacks must read the context passed in, rather than guessing the observation from the registry's current observation.

If you need errors reported while the scope is still open, you can put a business try/catch inside the scope. Moving the catch changes the order of `error` and `close`. You do not need to change the structure just to force a specific callback order unless specifically required; prioritize a single clear lifecycle owner.

### 3.4. Checked Exceptions Must Be Handled According to the Actual Contract

Catching `RuntimeException | Error` does not cover a checked exception declared by the business method.

For example, a synchronous helper taking `Callable<T>` can manage both the return value and checked exceptions as follows. This is a method inside a utility class, requiring imports for `java.util.concurrent.Callable`, `Observation`, and `ObservationRegistry`:

```java
static <T> T observeCall(ObservationRegistry registry,
                         Callable<T> action) throws Exception {
    Observation observation =
            Observation.start("orders.process", registry);
    try (Observation.Scope scope = observation.openScope()) {
        return action.call();
    }
    catch (Exception | Error ex) {
        observation.error(ex);
        throw ex;
    }
    finally {
        observation.stop();
    }
}
```

`return action.call()` does not bypass cleanup: Java still closes the resource and executes `finally` before returning the result. This helper observes the synchronous duration of `call()`; if `call()` only creates a future and returns it, it does not enclose the work running inside the future.

These patterns assume custom handlers behave normally. Observation callbacks contain user code so they can also throw errors; do not treat `finally` as a guarantee that the framework neutralizes every handler error. Inside custom handlers, avoid operations prone to long blocking or disrupting the business thread.

## 4. Using observe to Manage Entire Synchronous Work

When the entire task fits in a synchronous lambda, you can usually write concisely:

```java
Observation.createNotStarted("orders.process", registry)
        .lowCardinalityKeyValue("channel", "web")
        .observe(() -> processOrder());
```

The wrapping API manages starting, scope, reporting exceptions escaping the lambda, and stopping. Do not wrap the same observation with the manual pattern and also call `observe`.

For a lambda that returns a value, you can use the supplier overload. An independent example illustrating returning a value:

```java
int accepted = Observation.createNotStarted("orders.count", registry)
        .observe(() -> 3);
```

The value `3` comes from the task, not the number of times the observation ran. If the lambda throws an exception, `observe` does not turn it into a default success value.

For Micrometer 1.13.0's `observe(Runnable)` in the verification program below, the observed error path is:

```text
start → open scope → execute
                        |
                    throws exception
                        v
close scope → error → stop → exception exits observe
```

Do not turn the ordering of a single overload/version into a mandatory rule for every instrumentation. What must hold is that the scope is restored, the observation is stopped, and business errors are not accidentally swallowed.

Both explicit calls and `observe` wrapping are illustrated in [Micrometer Observation — Components](https://docs.micrometer.io/micrometer/reference/1.13/observation/components.html).

## 5. Java Program Verifying the Lifecycle

The program runs four scenarios:

1. Manual management and success.
2. Manual management and throwing an error.
3. Using `observe(Runnable)` and throwing an error.
4. Parent/child observations with nested scopes.

The handler only prints lifecycle milestones so learners can see the order, without creating a monitoring system or HTTP endpoint.

### 5.1. Preparing Libraries

JDK 17 or newer is required. For this standalone example, place the two JARs at the same version into the `lib/` directory:

```text
io.micrometer:micrometer-observation:1.13.0
io.micrometer:micrometer-commons:1.13.0
```

You can obtain the libraries from Maven Central or your build tool's cache. Pinning versions keeps the lesson's stdout reproducible; in a Spring Boot application, use the versions managed by Boot's dependency management.

Structure:

```text
lifecycle-demo/
├── ObservationLifecycleDemo.java
└── lib/
    ├── micrometer-observation-1.13.0.jar
    └── micrometer-commons-1.13.0.jar
```

### 5.2. Complete Source Code

Save as `ObservationLifecycleDemo.java`:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;

public class ObservationLifecycleDemo {
    static final class LifecyclePrinter
            implements ObservationHandler<Observation.Context> {
        @Override
        public boolean supportsContext(Observation.Context context) {
            return true;
        }

        @Override
        public void onStart(Observation.Context context) {
            System.out.println("START " + context.getName());
        }

        @Override
        public void onScopeOpened(Observation.Context context) {
            System.out.println("OPEN " + context.getName());
        }

        @Override
        public void onScopeClosed(Observation.Context context) {
            System.out.println("CLOSE " + context.getName());
        }

        @Override
        public void onError(Observation.Context context) {
            System.out.println("ERROR " + context.getName()
                    + " type=" + context.getError().getClass().getSimpleName());
        }

        @Override
        public void onStop(Observation.Context context) {
            String error = context.getError() == null
                    ? "none" : context.getError().getClass().getSimpleName();
            System.out.println("STOP " + context.getName() + " error=" + error);
        }
    }

    static String currentName(ObservationRegistry registry) {
        Observation current = registry.getCurrentObservation();
        return current == null ? "none" : current.getContext().getName();
    }

    static void manual(ObservationRegistry registry, boolean fail) {
        String name = fail ? "manual.failure" : "manual.success";
        Observation observation = Observation.createNotStarted(name, registry);
        System.out.println("CREATED current=" + currentName(registry));
        observation.start();
        System.out.println("AFTER_START current=" + currentName(registry));
        try (Observation.Scope scope = observation.openScope()) {
            System.out.println("BODY current=" + currentName(registry));
            if (fail) {
                throw new IllegalStateException("manual failed");
            }
        }
        catch (RuntimeException | Error ex) {
            observation.error(ex);
            System.out.println("AFTER_ERROR current=" + currentName(registry));
            throw ex;
        }
        finally {
            observation.stop();
        }
    }

    static void automatic(ObservationRegistry registry) {
        Observation observation =
                Observation.createNotStarted("automatic.failure", registry);
        Runnable work = () -> {
            System.out.println("BODY current=" + currentName(registry));
            throw new IllegalArgumentException("automatic failed");
        };
        observation.observe(work);
    }

    static void nested(ObservationRegistry registry) {
        Observation parent = Observation.start("parent", registry);
        try (Observation.Scope parentScope = parent.openScope()) {
            System.out.println("PARENT current=" + currentName(registry));
            Observation child = Observation.start("child", registry);
            try (Observation.Scope childScope = child.openScope()) {
                boolean parentMatches =
                        child.getContext().getParentObservation() == parent;
                System.out.println("CHILD current=" + currentName(registry)
                        + " parentMatches=" + parentMatches);
            }
            finally {
                child.stop();
            }
            System.out.println("RESTORED current=" + currentName(registry));
        }
        finally {
            parent.stop();
        }
    }

    public static void main(String[] args) {
        ObservationRegistry registry = ObservationRegistry.create();
        registry.observationConfig()
                .observationHandler(new LifecyclePrinter());

        System.out.println("CASE manual.success");
        manual(registry, false);
        System.out.println("AFTER current=" + currentName(registry));

        System.out.println("CASE manual.failure");
        try {
            manual(registry, true);
        }
        catch (IllegalStateException ex) {
            System.out.println("CAUGHT " + ex.getMessage());
        }
        System.out.println("AFTER current=" + currentName(registry));

        System.out.println("CASE automatic.failure");
        try {
            automatic(registry);
        }
        catch (IllegalArgumentException ex) {
            System.out.println("CAUGHT " + ex.getMessage());
        }
        System.out.println("AFTER current=" + currentName(registry));

        System.out.println("CASE nested");
        nested(registry);
        System.out.println("AFTER current=" + currentName(registry));
    }
}
```

In the example, the handler supports the general `Observation.Context` and accepts every context in the practice registry. A specialized handler in a real application may need a narrower support condition.

### 5.3. Run Commands

In PowerShell inside the directory containing the file:

```powershell
javac --release 17 -cp "lib/*" ObservationLifecycleDemo.java
java -cp ".;lib/*" ObservationLifecycleDemo
```

On Linux/macOS, replace the classpath entry separator when running with `:`:

```bash
javac --release 17 -cp "lib/*" ObservationLifecycleDemo.java
java -cp ".:lib/*" ObservationLifecycleDemo
```

The program was compiled with `--release 17` and run on OpenJDK 24.0.2 with Micrometer 1.13.0. Captured stdout:

```text
CASE manual.success
CREATED current=none
START manual.success
AFTER_START current=none
OPEN manual.success
BODY current=manual.success
CLOSE manual.success
STOP manual.success error=none
AFTER current=none
CASE manual.failure
CREATED current=none
START manual.failure
AFTER_START current=none
OPEN manual.failure
BODY current=manual.failure
CLOSE manual.failure
ERROR manual.failure type=IllegalStateException
AFTER_ERROR current=none
STOP manual.failure error=IllegalStateException
CAUGHT manual failed
AFTER current=none
CASE automatic.failure
START automatic.failure
OPEN automatic.failure
BODY current=automatic.failure
CLOSE automatic.failure
ERROR automatic.failure type=IllegalArgumentException
STOP automatic.failure error=IllegalArgumentException
CAUGHT automatic failed
AFTER current=none
CASE nested
START parent
OPEN parent
PARENT current=parent
START child
OPEN child
CHILD current=child parentMatches=true
CLOSE child
STOP child error=none
RESTORED current=parent
CLOSE parent
STOP parent error=none
AFTER current=none
```

### 5.4. Analyzing the Success Path

`CREATED current=none` appears before the `START` callback: creating unstarted and starting are two distinct steps.

`AFTER_START current=none` confirms the observation has started but is not yet in scope. The `BODY current=manual.success` line only appears after `OPEN`.

When business logic finishes, the scope is closed before `finally` stops the observation. The scenario's final line is `AFTER current=none`, showing the scope is no longer held.

There is no `ERROR` callback on the success branch.

### 5.5. Analyzing the Manual Error Path

The error occurs inside the resource block. Because the catch sits outside that block, the sequence is:

```text
CLOSE manual.failure
ERROR manual.failure type=IllegalStateException
AFTER_ERROR current=none
STOP manual.failure error=IllegalStateException
CAUGHT manual failed
```

The `AFTER_ERROR` line is printed right after `observation.error(ex)`. It is evidence that reporting an error does not rethrow the exception or end the observation; control flow continues until `throw ex` and `finally`.

The `STOP` line proves the error path still passes through stopping the observation. The `CAUGHT` line comes from the caller, after cleanup, showing the business failure still propagates outward.

### 5.6. Analyzing observe and Nested Scopes

In the `automatic.failure` scenario, application code only calls `observe(work)`; the wrapping API generates the callback sequence and passes the error back to the caller. In the verified version, `CLOSE` also appears before `ERROR`.

In the nested scenario:

- When parent opens its scope, current is `parent`.
- Child is created/started inside that scope; `parentMatches=true` confirms the child's parent relationship in the example.
- When child opens its scope, current is `child`.
- After the child scope closes, `RESTORED current=parent`.
- When the parent scope closes and the parent observation stops, current returns to `none`.

The two observations still have two separate `START/STOP` pairs. The child finishing must not cause the parent to end prematurely.

## 6. Managing Scopes at the Right Execution Boundaries

### 6.1. A Scope Is a Resource That Must Have an Owner

When obtaining an `Observation.Scope` from `openScope()`, the code that opens it must ensure it closes at the end of the corresponding block. For synchronous execution, try-with-resources is the easiest choice to verify.

The snippet below is an example **wrong because it drops the resource**:

```java
observation.openScope();
processOrder();
observation.stop();
```

Without holding the scope resource, the code has nowhere to close it. `stop()` does not fix this omission. In a separate verification with Micrometer 1.13.0, after calling `stop()` while a scope remained open, the registry still returned that observation as current; only closing the scope restored the previous current observation.

Consequence: do not deduce that once an observation has stopped, it can no longer pollute the thread's scope.

### 6.2. Close in Reverse Order of Opening

With parent and child scopes, the semantically safe structure is:

```text
open parent
    open child
        execute child
    close child
    continue parent
close parent
```

Closing the parent scope while the child scope is still active breaks the nesting structure. Do not rely on whether a particular version warns, auto-recovers, or keeps running to treat such usage as valid.

Nested try-with-resources directly expresses the order to follow.

### 6.3. One Observation Can Enter Multiple Separate Execution Scopes

A unit of work can outlive a single code block running on one thread. In that case, placing the observation into scope during each execution slice and stopping the entire observation do not necessarily happen at the same time.

This does not permit arbitrarily sharing one scope object across threads. Each scope must bind to the actual execution slice it manages, opened and closed in the right place; the observation is only stopped when the work per its defined boundary actually finishes.

In this synchronous lab, each observation only needs one scope. With executors/reactive code, use instrumentation and context propagation designed for that model rather than extending a calling-thread scope yourself.

## 7. Rules for Recording Errors

### 7.1. Errors Escaping a Lambda Differ from Errors Handled Inside

If an exception escapes the `observe` lambda, the wrapping API has the chance to record it and rethrow it.

However, if the lambda catches the exception itself and returns normally, the outer API cannot know whether the application treated that event as a failure or recovered successfully.

Example snippet:

```java
Observation observation =
        Observation.createNotStarted("orders.process", registry);

observation.observe(() -> {
    try {
        processOrder();
    }
    catch (IllegalStateException ex) {
        observation.error(ex);
        useBusinessFallback();
    }
});
```

`processOrder()` and `useBusinessFallback()` are application methods. This is an example of **explicitly marking an error even though the method can complete via a fallback**, not a mandatory policy for every system.

If the fallback is an expected outcome and should not count as a failure of the overall operation, you may need a child observation for the failed attempt or appropriate outcome metadata. That decision must follow the question being measured, avoiding making error rates meaningless.

### 7.2. Report Errors in One Responsible Place

Do not report the same exception multiple times to the same observation just because it passes through multiple catch blocks. Each call to `error(ex)` can make handlers react another time.

If you already let `observe` handle escaping errors, there is no need for an inner catch just to call `error` and rethrow the exact same exception, unless a specific verified contract requires it. Having a single owner for error reporting avoids duplicate callbacks.

One error may be recorded on both a child observation and a parent observation when it causes both units of work to fail. Those are two different measurement scopes, distinct from reporting twice on the same object.

### 7.3. Do Not Alter Business Logic to Serve Telemetry

`observation.error(ex)` does not substitute for a rollback. `stop()` does not commit a transaction. Closing a scope does not catch exceptions for the caller.

These belong to different mechanisms. Instrumentation should reflect the true business path, preserving return values and exceptions per the original contract.

Likewise, do not place essential business actions inside handlers or context suppliers assuming they always execute: an observation can be disabled or become a no-op. Work that must be invoked belongs on the business execution path, independent of whether telemetry handlers exist.

## 8. One Owner of start/stop for Each Observation

| Source creating observation | Who owns the lifecycle? | What should inner code do? |
| --- | --- | --- |
| Framework already wraps HTTP request | Framework instrumentation | Use the current scope or create meaningful child observations |
| Method creates observation and manages manually | The method/utility that started it | Report errors, close its own scope, stop that exact observation |
| Call to `createNotStarted(...).observe(...)` | Wrapping API | Run the work; avoid extra start/stop on the same object |
| Custom async task | Component aware of true completion | Clearly define where it starts, stops, and opens/closes scopes while running |

Do not stop the observation obtained from `registry.getCurrentObservation()` just because a child method finished. Current may be the HTTP request or an outer task that is still running.

Likewise, do not reuse a stopped observation for the next order. Each execution has its own lifecycle and context; the registry can be shared, whereas the observation must reflect that exact run.

Do not rely on assuming "calling stop twice is probably harmless" as a way for multiple layers to coordinate. A given version may guard against duplicate handling on some paths, yet a testable design still has one place responsible for stopping once at the work boundary.

## 9. When Moving to Async, Redefine What Completion Means

Here is an example of **measuring the wrong boundary if the goal is the entire work in the future**:

```java
CompletableFuture<Order> future =
        Observation.createNotStarted("orders.async", registry)
                .observe(() -> submitOrderAsync());
```

The snippet assumes the application has an `Order` type and `submitOrderAsync()` returning `CompletableFuture<Order>`. It is not a standalone runnable program.

The lambda may only submit work to an executor and return the future immediately. Synchronous `observe` stops when the lambda returns, without waiting for the future to complete. Thus:

- The measured interval may only be task submission time.
- Errors occurring later inside the future do not automatically become exceptions escaping the already-finished lambda.
- The submitting thread's scope does not automatically exist validly on the task execution thread.

If the goal is solely measuring task submission time, that boundary may fit, provided it is named and interpreted accordingly. If the goal is order processing until completion, you must use an observation mechanism that understands that completion point.

When designing it yourself, answer all of these:

1. Does the observation start at submission or when the task actually begins?
2. If the executor rejects the task immediately, who reports the error and stops it?
3. When the task completes with success or failure, who stops it exactly once?
4. When a task is canceled, has the business boundary ended, or is background work still continuing?
5. Where are scopes opened and closed on each running thread?
6. By what mechanism is the relationship with the parent observation propagated?

Creating observations and propagating context are two related but separate problems. See [Micrometer Observation — Instrumentation](https://docs.micrometer.io/micrometer/reference/1.13/observation/instrumenting.html).

With reactive publishers, bind the lifecycle to subscription and termination signals using appropriate instrumentation. Opening a scope around building a publisher does not mean that scope covers execution later on. Do not call `block()` or `join()` just to force a synchronous model while ignoring the application's threading requirements.

## 10. Applying in Spring Boot Actuator

In a Spring Boot 3.3 application with appropriate observation auto-configuration, inject the Spring-managed registry instead of creating a separate registry in every method.

Constructor snippet example:

```java
public OrderService(ObservationRegistry observationRegistry) {
    this.observationRegistry = observationRegistry;
}
```

This is an excerpt inside a service that already has the corresponding field. The registry is shared; observations are created per execution.

Spring Boot registers matching `ObservationHandler` beans onto the managed registry. However, registering a handler does not transfer lifecycle ownership of an observation from the framework to every service using the registry. Start/stop boundaries must still follow whoever creates and manages the observation.

If an HTTP request is already instrumented, you can create child observations for distinct business work such as order processing. Avoid wrapping the same boundary multiple times just to generate extra metrics.

Boot's integration and propagation of the current observation across threads/reactive pipelines depend on configuration and related libraries; see [Spring Boot 3.3 — Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

This lesson's console program does not need to expose Actuator endpoints. It verifies the lifecycle at the API level; viewing metrics/traces on a backend is a separate output verification step once the corresponding integration is in place.

## 11. Common Mistakes

| Symptom | Common oversight | Structural fix |
| --- | --- | --- |
| Business error drops the stop callback | Placed stop after the work without `finally` | Put stopping in an always-run block or use the wrapping API |
| Started, yet current is not the expected observation | Scope was not opened | Open scope for the right execution range |
| Stopped, yet thread still holds old current | Scope was not closed | Manage the scope resource; do not use stop in place of close |
| Parent observation disappears when child method finishes | Cleared current manually or closed out of order | Restore previous scope with proper nesting |
| Exception occurred, yet error callback did not run | Caught error or managed manually without reporting | Define who is responsible for `error` per contract |
| Error callback runs multiple times | Reported manually and also let wrapper report the same error | Choose one place to report errors for a given observation |
| Observation ends too early | Lambda only returned a future/publisher | Choose a mechanism tied to actual completion |
| Duplicate measurements appear | Start/stop or instrumentation wrapped twice | Audit lifecycle owners and work boundaries |
| Child service stops the HTTP observation | Stopped the framework's current observation | Stop only observations you own |
| Requests mix contexts | Retained previous scope/context | Create per-run observation/context and close scope on time |

## 12. Scenario-Based Self-Check

**Scenario 1:** A method calls `start()`, business logic finishes, yet a child method does not see the current observation. Can you conclude `start` failed to run?

No. Start and scope are two different axes. Check whether a scope was opened on the thread actually executing the child method.

**Scenario 2:** Code only calls `observation.error(ex)` and then `return`. Does the observation stop on its own?

Do not assume so. Reporting an error does not replace stopping. There must be a place stopping the lifecycle, usually `finally` in manual management or an appropriate wrapper.

**Scenario 3:** The child scope closed and the registry returned the parent observation. Is this a scope leak?

Not necessarily a leak. If the parent is still in scope, that is proper restoration. Check against the scope prior to opening the child, rather than requiring every close to make current `null`.

**Scenario 4:** `observe` finished when the future was only halfway done. Is the API broken?

Not necessarily. The synchronous lambda may have finished submitting the task. To observe the entire background work, you must choose a different boundary and completion mechanism.

**Further practice with the sample program:**

- Replace the manual error with an early return and verify `CLOSE` and `STOP` still appear.
- Move the error-reporting catch inside the scope, predict, and verify where `ERROR` appears relative to `CLOSE`.
- Keep the parent observation open, run two child observations sequentially, and check that current returns to parent after each child.
- In automated tests, verify success paths, exception paths, and no unexpected lingering scopes, rather than checking only for a single `START` line.

A properly managed lifecycle tells you who starts it, which block puts the observation in scope, who reports errors, and who stops it. Verifying all exit paths keeps metrics accurate to the work and ensures context is restored for the next execution.
