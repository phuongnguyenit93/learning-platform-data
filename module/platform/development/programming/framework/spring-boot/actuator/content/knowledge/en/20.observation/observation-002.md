# Roles of ObservationRegistry, Observation.Context, and ObservationHandler

## 1. Why Are Three Separate Components Needed?

Suppose we want to observe an order confirmation operation. We need to know when the operation starts, stops, fails, and what attributes it has. Then, the same operation can serve multiple needs: measuring duration, creating spans to trace calls, or selective logging.

If the order-processing code performed all three tasks itself, it would become tightly coupled to each observability tool. Whenever we switched tools or added an output, we would have to modify business code.

Micrometer Observation splits the problem into roles:

| Component | Question it answers |
| --- | --- |
| `Observation` | When does this execution start, stop, or emit an error or event? |
| `ObservationRegistry` | Which configuration and handlers does the observation use? What is the current observation in the execution scope? |
| `Observation.Context` | Which data and state belong to this specific observation run? |
| `ObservationHandler` | When receiving a lifecycle milestone, what observation action should be performed? |

The three types in the title do not replace `Observation`. They work together so `Observation` operates: the registry supplies configuration, the context carries data, and handlers react to the lifecycle.

```text
Business code instrumented with Observation
              |
              v
        ObservationRegistry
        selects config/handlers
              |
              v
         Observation  ------ uses ------> Context of this execution
              |
        start / error / event / stop
              |
              v
       Handler supporting context
              |
       timing / tracing / logging
```

This separation of responsibilities is used in [Micrometer Observation — Introduction](https://docs.micrometer.io/micrometer/reference/1.13/observation/introduction.html). The hands-on section below uses Micrometer 1.13.0 to verify callbacks directly; when using Spring Boot 3.3, let Boot's dependency management manage library versions.

## 2. ObservationRegistry: Where Shared Observation Configuration Lives

### 2.1. The Registry Manages Configuration, Not a Single Request's Result

In a standalone Java program, you can create a registry and register a handler:

```java
ObservationRegistry registry = ObservationRegistry.create();
registry.observationConfig().observationHandler(new CheckoutHandler());
```

This is an excerpt; `CheckoutHandler` is defined in full in the runnable example below.

The registry specifies which handlers participate, along with related customizations such as observation predicates, naming/tag conventions, and context filters. For this lesson, the most important point is that **the handler must be registered on the exact registry that the observation uses**.

If you register a handler on registry A but create an observation using registry B, that observation will not automatically find A's handler. Having the same observation name also does not connect two configurations together.

A registry is typically shared across the application. It is not an object that holds an order ID or the individual result of one invocation. Those values belong in the corresponding context.

### 2.2. A New Registry Does Not Come with All Integrations

`ObservationRegistry.create()` only creates a standalone program's registry. It does not automatically:

- Create a Prometheus backend or a tracing system.
- Attach every handler available in Spring.
- Send data over the network.
- Store a history of all completed observations for querying.

In Micrometer 1.13.0 in the hands-on example, a fresh registry with no handlers causes the observation to perform no observation work; the code passed into `observe(...)` still runs.

Therefore, if running business logic produces the right result but no timer/span appears, check the registry and handler configuration before concluding that the lambda was not called.

### 2.3. The Current Observation Is a Scope Concept

The registry can return the current observation:

```java
Observation current = registry.getCurrentObservation();
```

`start()` and "becoming the current observation" are two different things. Opening an `Observation.Scope` is what puts the observation into the thread's current scope in normal synchronous execution.

This allows code deep inside a call chain to find the enclosing observation without passing parameters through every method. However, it does not mean the registry is a global variable holding the "most recent request" across all users.

When there is no active scope, the result can be `null`. Always account for this case when reading the current observation from shared code.

## 3. Observation.Context: Data and State of One Observation Run

### 3.1. Context Accompanies a Specific Observation

Suppose two orders are processed concurrently:

```text
Shared Registry
   |
   +-- Observation A -- Context A: channel=web, result=success
   |
   +-- Observation B -- Context B: channel=store, result=failed
```

Two executions can share the same handler, but they should not share a mutable context.

The context holds standard fields such as name, contextual name, error, and key–value pairs. You can also place auxiliary data into its map-like store or create a subclass with well-typed fields.

Example from the hands-on program:

```java
static final class CheckoutContext extends Observation.Context {
    final String channel;
    String result = "pending";

    CheckoutContext(String channel) {
        this.channel = channel;
    }
}
```

`channel` and `result` serve to observe the checkout operation in the example. Each invocation creates a new `CheckoutContext`. The handler reads that context to know the outcome of that exact call, without holding the result in a shared instance field.

### 3.2. Auxiliary Data Connects Callbacks

A handler may need information from `onStart` to complete its work in `onStop`. A classic example is the state of a timing measurement.

In the example, to make stdout easy to verify, we store a marker:

```java
context.put(START_MARKER, "ready");
```

Then read it back in `onStop`:

```java
String marker = context.get(START_MARKER);
```

`START_MARKER` is a shared key object; its **value** lives inside each context. Using a private key prevents accidentally overwriting another handler's data.

If you put data into the context under a key with inconsistent value types, retrieving it can cause a cast failure. For important or complex data, a dedicated context subclass expresses the contract more clearly.

### 3.3. Putting Data into Context Does Not Mean It Is Exported as Tags

Three forms of data must be distinguished:

| Data form | Example | What must not be assumed |
| --- | --- | --- |
| Context class field | `context.result = "success"` | Does not automatically become a tag on every timer |
| Internal map entry | `context.put(START_MARKER, "ready")` | Does not automatically export the whole map to backends |
| Declared metadata | `lowCardinalityKeyValue("channel", "web")` | Output still depends on the handlers and integrations in use |

In the example, the handler explicitly reads `result` and `marker` to print them. If you remove that logic, those two values do not appear in stdout on their own.

Metadata with a bounded set of values, such as `web/store` channels, is usually suitable for grouping metrics. Order IDs with a very large number of values should be considered for detailed data like traces, avoiding metric tags. Regardless of category, only include data genuinely needed for observation; "high cardinality" does not automatically make sensitive data appropriate to export.

### 3.4. Context Is Mutable, So Timing of Reads Matters

At the start of the operation, `result` may be `pending`; after business logic runs, it changes to `success` or `failed`. `onStart` cannot assume it knows the final outcome.

If a handler needs data right when starting, you must populate that data before `start()` or before calling `observe(...)`. Do not add important information too late and expect earlier callbacks to have seen it.

The context is also not a thread-safe synchronized memory space for arbitrary threads. Do not share a context that is being mutated across concurrent tasks without proper access and lifecycle management.

## 4. ObservationHandler: Where Lifecycle Reactions Happen

### 4.1. A Handler Receives Only the Context Types It Supports

A handler typed as:

```java
ObservationHandler<CheckoutContext>
```

must implement the check:

```java
@Override
public boolean supportsContext(Observation.Context context) {
    return context instanceof CheckoutContext;
}
```

The generic declaration indicates the type the callbacks expect to receive; `supportsContext` is the runtime selection check. Do not return `true` for every context and blindly cast to an arbitrary subclass.

If a handler only supports `CheckoutContext`, an observation created with the default `Observation.Context` is not automatically turned into `CheckoutContext`. Having the same name `checkout` also does not change the result of the `instanceof` check.

### 4.2. Callbacks Have Distinct Responsibilities

| Callback | Corresponding signal | What the handler can do |
| --- | --- | --- |
| `onStart(context)` | Observation is started | Prepare measurement state, start observation work |
| `onScopeOpened(context)` | Observation enters scope | Set up state tied to the execution scope |
| `onEvent(event, context)` | An event is explicitly signaled | Record a detailed milestone of the operation |
| `onError(context)` | An error is reported to the observation | Read the error recorded on the context |
| `onScopeClosed(context)` | Scope is closed | Clean up state tied to the scope |
| `onStop(context)` | Observation ends | Finalize the measurement or corresponding output |

The table focuses on callbacks used in this lesson; the API has additional capabilities. The context and handler model is presented in [Micrometer Observation — Components](https://docs.micrometer.io/micrometer/reference/1.13/observation/components.html).

A handler is not a business method. `onError` does not retry payment or roll back a transaction on its own. `onStop` should also not be where business success or failure is decided.

A handler can be invoked by multiple observations concurrently. Per-execution state should live in the context, not in fields such as `this.currentOrder` or `this.startedAt` on a singleton handler.

### 4.3. One Observation Can Serve Multiple Outputs

You can register multiple matching handlers, such as one handler for metrics and another handler for tracing. Business code still describes the same single execution through Observation.

This does not mean you must always write every handler yourself. When using a framework, many handlers are already integrated. Only add a custom handler when you need additional observation behavior.

When a composite handler selects the first matching element, selection rules inside the composite differ from a list of independent handlers. Do not rely on assuming every declared handler is guaranteed to run in every configuration; verify how they are registered and their support predicates.

## 5. Distinguishing Observation Lifecycle from Scope Lifecycle

### 5.1. Start/Stop Measures a Unit of Work; Open/Close Scope Defines the Current Scope

You can picture two axes:

```text
Work lifecycle:       create → start --------------------→ stop
Synchronous scope:             open → run code → close
```

Opening a scope does not replace starting an observation. Closing a scope does not replace stopping an observation.

For example, if you only close the scope and forget `stop()`, handlers may not finalize measurements. If you only call `start()` without opening a scope, inner code should not expect `getCurrentObservation()` to return that observation.

For straightforward synchronous work, `observe(...)` is a convenient way to manage these operations together with exception reporting.

### 5.2. Nested Scopes Must Restore the Outer Scope

When a parent observation is already in scope, and a child observation opens its scope:

```text
parent scope open  → current = parent
child scope open   → current = child
child scope close  → current restored to parent
parent scope close → returns to scope before parent
```

The diagram shows proper scope ordering on the same thread. You must close in the reverse order of opening and not let a scope outlive the unit of work it surrounds.

The parent–child relationship is not a consequence of reusing the same context. Parent and child contexts hold separate data; retrieving the current observation and establishing relationships depend on how instrumentation creates observations.

### 5.3. Switching Threads Does Not Automatically Carry All State

`Observation.Context`, Spring `ApplicationContext`, Reactor `Context`, and thread context propagation mechanisms are different concepts.

Submitting a lambda to an executor does not guarantee the current observation on the submitting thread becomes current on the worker thread. Likewise, do not open a scope around building a reactive publisher and assume that scope still exists when the publisher actually executes.

For async/reactive tasks, use the framework's context propagation and instrumentation mechanisms. The hands-on section in this lesson intentionally uses a single synchronous thread so the roles of the three components are clearly visible.

## 6. Runnable Java Example: Seeing All Three Roles

The example below runs two checkout attempts: one succeeds and one throws an exception. The handler only prints callbacks for learning purposes; the program requires no Spring server, HTTP endpoints, metrics system, or tracing backend.

### 6.1. Preparation

JDK 17 or newer and two libraries at the same version are required:

```text
io.micrometer:micrometer-observation:1.13.0
io.micrometer:micrometer-commons:1.13.0
```

Place the two corresponding JARs in a `lib/` folder next to the Java file. You can obtain them from Maven Central or your build tool's cache. These are pinned versions for the standalone example, not a requirement to override Spring Boot-managed versions in a real application.

Directory structure:

```text
observation-demo/
├── ObservationRolesDemo.java
└── lib/
    ├── micrometer-observation-1.13.0.jar
    └── micrometer-commons-1.13.0.jar
```

### 6.2. Complete Source Code

Save with the exact filename `ObservationRolesDemo.java`:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;

public class ObservationRolesDemo {
    private static final Object START_MARKER = new Object();

    static final class CheckoutContext extends Observation.Context {
        final String channel;
        String result = "pending";

        CheckoutContext(String channel) {
            this.channel = channel;
        }
    }

    static final class CheckoutHandler
            implements ObservationHandler<CheckoutContext> {
        @Override
        public boolean supportsContext(Observation.Context context) {
            return context instanceof CheckoutContext;
        }

        @Override
        public void onStart(CheckoutContext context) {
            context.put(START_MARKER, "ready");
            System.out.println("START " + context.getName()
                    + " channel=" + context.channel);
        }

        @Override
        public void onScopeOpened(CheckoutContext context) {
            System.out.println("SCOPE_OPEN " + context.getName());
        }

        @Override
        public void onEvent(Observation.Event event, CheckoutContext context) {
            System.out.println("EVENT " + event.getName());
        }

        @Override
        public void onError(CheckoutContext context) {
            System.out.println("ERROR "
                    + context.getError().getClass().getSimpleName());
        }

        @Override
        public void onScopeClosed(CheckoutContext context) {
            System.out.println("SCOPE_CLOSE " + context.getName());
        }

        @Override
        public void onStop(CheckoutContext context) {
            String error = context.getError() == null
                    ? "none" : context.getError().getClass().getSimpleName();
            String marker = context.get(START_MARKER);
            System.out.println("STOP " + context.getName()
                    + " result=" + context.result
                    + " error=" + error + " marker=" + marker);
        }
    }

    static void checkout(ObservationRegistry registry,
                         String channel, boolean fail) {
        CheckoutContext context = new CheckoutContext(channel);
        Observation observation = Observation.createNotStarted(
                "checkout", () -> context, registry)
                .lowCardinalityKeyValue("channel", channel);
        try {
            observation.observe(() -> {
                Observation current = registry.getCurrentObservation();
                System.out.println("BODY current="
                        + (current == observation ? "checkout" : "unexpected"));
                observation.event(Observation.Event.of("inventory.checked"));
                if (fail) {
                    context.result = "failed";
                    throw new IllegalStateException("payment unavailable");
                }
                context.result = "success";
            });
        }
        catch (IllegalStateException ex) {
            System.out.println("CAUGHT " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        ObservationRegistry registry = ObservationRegistry.create();
        registry.observationConfig()
                .observationHandler(new CheckoutHandler());

        checkout(registry, "web", false);
        System.out.println("---");
        checkout(registry, "store", true);
        System.out.println("AFTER current="
                + (registry.getCurrentObservation() == null ? "none" : "leaked"));

        Observation.createNotStarted(
                "without.handler", ObservationRegistry.create())
                .observe(() -> System.out.println("NO_HANDLER business=executed"));
    }
}
```

### 6.3. Compiling and Running

In PowerShell inside the directory containing the file:

```powershell
javac --release 17 -cp "lib/*" ObservationRolesDemo.java
java -cp ".;lib/*" ObservationRolesDemo
```

On Linux/macOS, the classpath entry separator when running is `:`:

```bash
javac --release 17 -cp "lib/*" ObservationRolesDemo.java
java -cp ".:lib/*" ObservationRolesDemo
```

The example was compiled with `--release 17` and verified on OpenJDK 24.0.2, using the two Micrometer 1.13.0 JARs. Captured stdout:

```text
START checkout channel=web
SCOPE_OPEN checkout
BODY current=checkout
EVENT inventory.checked
SCOPE_CLOSE checkout
STOP checkout result=success error=none marker=ready
---
START checkout channel=store
SCOPE_OPEN checkout
BODY current=checkout
EVENT inventory.checked
SCOPE_CLOSE checkout
ERROR IllegalStateException
STOP checkout result=failed error=IllegalStateException marker=ready
CAUGHT payment unavailable
AFTER current=none
NO_HANDLER business=executed
```

### 6.4. Reading the Output by Responsibility

**Registry:** the same registry is passed into both `checkout` calls. The handler is registered once before running, rather than being added per order.

**Context:** each `checkout` call creates a new `CheckoutContext`. The first carries `channel=web`, the next carries `channel=store`. The `result` field changes per call; the `marker=ready` mark is written by the handler in `onStart` and read back in `onStop`.

**Handler:** the `START`, `SCOPE_OPEN`, `EVENT`, `SCOPE_CLOSE`, `ERROR`, and `STOP` lines are printed by callbacks. The `BODY` line is printed by code inside `observe`, distinguishing the observed work from the observation handler.

**Scope:** `BODY current=checkout` confirms this observation is active while the lambda executes. `AFTER current=none` confirms neither execution's scope remains held at the end of the program.

**Error:** `CAUGHT payment unavailable` only appears after the exception exits `observe(...)` and is caught by the demo code. Observation does not turn a payment failure into a successful outcome.

**Registry without handler:** the last line shows that the code inside `observe` still executes when using a new registry without handlers. There are no callback lines for `without.handler`.

### 6.5. Callback Order Depends on the Execution Path Used

On the error path of `observe(Runnable)` in this Micrometer 1.13.0 run:

```text
lambda throws error
    → close scope
    → report error to observation
    → stop observation
    → exception exits observe
```

That is why the output shows `SCOPE_CLOSE` before `ERROR`. Do not memorize a diagram claiming that errors are always reported before the scope closes.

If you manage the lifecycle manually and call `observation.error(ex)` directly inside the scope, you can produce a different order. A handler should rely on the milestone at which it is notified and the context data available at that milestone, not on assuming every callback always runs while the observation is still current.

An easily overlooked consequence: in `onStop`, use the `context` parameter received by the callback to read data for the ending observation. Do not call `registry.getCurrentObservation()` and assume it is still that observation; its scope may already be closed or current may have returned to an outer observation.

## 7. When Manual Lifecycle Control Is Needed

`observe(...)` suits synchronous work enclosed in a single lambda. If managing explicitly, you are responsible for error reporting, closing the scope, and stopping the observation.

The following snippet illustrates the usage structure inside a method that already has a registry. `performCheckout()` is an application business call, not a built-in Micrometer function; this is an excerpt, not a standalone program:

```java
Observation observation = Observation.createNotStarted(
        "checkout", registry)
        .lowCardinalityKeyValue("channel", "web");

observation.start();
try (Observation.Scope scope = observation.openScope()) {
    performCheckout();
}
catch (RuntimeException | Error ex) {
    observation.error(ex);
    throw ex;
}
finally {
    observation.stop();
}
```

Key points to understand:

- Try-with-resources closes the scope for this execution path.
- `finally` stops the observation even when business logic throws an exception.
- `observation.error(ex)` reports the error to the observation mechanism; `throw ex` propagates the exception to the caller.
- If the business logic has checked exceptions, you must handle/declare and report errors according to the method's contract; do not merely copy the catch block and omit application exception types.

In the snippet, the catch sits outside the try-with-resources, so the scope is closed before the catch reports the error. Closing the scope and reporting the error remain two separate operations.

Conversely, if a lambda catches an exception itself and returns normally, `observe` cannot know on its own that an error was handled inside. If that is a failure needing observation, the handling code must explicitly report it via `observation.error(ex)` according to the chosen business semantics. Do not attach an error to a normal branch just to generate an extra signal.

Avoid calling `start/stop` manually and also using `observe` on the same observation. Choose one clear way to own the lifecycle rather than letting multiple layers try to end it.

## 8. Placing the Three Components in Spring Boot Actuator

### 8.1. Use the Spring-Managed Registry

In an application with Actuator and appropriate auto-configuration, inject `ObservationRegistry` rather than creating a separate registry inside a service.

Constructor structure example:

```java
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    private final ObservationRegistry observationRegistry;

    public CheckoutService(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }
}
```

This class only illustrates receiving the registry and does not implement business logic. When adding methods, create a new observation and context for each execution using the injected registry.

A `final ObservationRegistry` field in a singleton service is appropriate. A `CheckoutContext currentContext` field used to hold data across all requests is a design prone to mixing data between calls.

### 8.2. Let Spring Register Handler Beans

Spring Boot can automatically register `ObservationHandler` beans onto the managed registry. For example, keeping the demo class in the same package and wanting to register its handler, add the following method inside a `@Configuration` class:

```java
@Bean
ObservationRolesDemo.CheckoutHandler checkoutObservationHandler() {
    return new ObservationRolesDemo.CheckoutHandler();
}
```

This is a bean declaration snippet; you must import `org.springframework.context.annotation.Bean` in the configuration class. Do not also register that same handler manually on the registry a second time.

The handler in the demo only supports `CheckoutContext`. If Spring code creates an observation using an overload that does not provide a custom context, the default context will not match that condition. There are two clear design options:

1. Continue creating `CheckoutContext` when observing checkout and use the specialized handler.
2. Write a handler for the general `Observation.Context`, with an appropriate support condition such as checking the context type or operation name per contract.

Do not remove the type check just to force the handler to run on every HTTP, database, or messaging observation from the framework.

Spring Boot's rules for injecting the registry, registering beans, and classifying tags are described in [Spring Boot 3.3 — Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

### 8.3. ObservationRegistry and MeterRegistry Are Not the Same Place

`ObservationRegistry` coordinates observation lifecycles. `MeterRegistry` manages Micrometer Metrics meters and measurements.

A metrics handler connects the two mechanisms: it listens to observations and writes figures into the meter registry. A tracing handler performs a different role, such as creating/managing spans through the tracing integration.

Therefore:

- Seeing an observation run does not prove a span was sent to a backend.
- Having a console-printing handler does not create timers on its own.
- Having local metrics does not prove network metric export is working.
- To query `/actuator/metrics`, you also need an HTTP application, an exposed endpoint, and actual recorded measurements; the standalone Java program above does not create this endpoint.

In Boot's standard integration, low-cardinality tags are used for metrics and traces, while high-cardinality tags are reserved for traces. A custom handler must still follow its own data design. Do not treat this classification mechanism as a promise that every internal map attribute on a context will be exported automatically.

### 8.4. Place Meaningful Observation Boundaries

If the framework already observes an HTTP request, a business observation such as `checkout` can be a unit of work inside that request. This makes sense when you need to separate business duration/outcome from the overall HTTP request.

Conversely, creating another observation with the same meaning just to "make sure data appears" can cause duplicate measurement. Before adding a handler or instrumentation, determine which unit of work is being measured and who owns its lifecycle.

## 9. Common Issues and How to Find the Cause

| Symptom | Cause to consider | How to check |
| --- | --- | --- |
| Lambda runs but handler prints nothing | Wrong registry used or handler not registered | Match where the observation is created against the configured registry |
| Handler is registered but does not receive expected observations | `supportsContext` does not match | Check the actual context class, not just the operation name |
| Cast error when callback runs | Specialized handler received an incompatible context | Fix the support predicate instead of blindly casting |
| `onStart` sees missing data | Data was added after starting | Set input info before start; read results at the appropriate milestone |
| Concurrent requests overwrite each other's state | Per-call state stored in a singleton handler or shared context | Move per-call state into individual contexts |
| Inner code does not see current observation | Only started without opening scope, or switched threads | Check execution scope and propagation mechanism |
| After completion an observation is still current | Scope was not closed properly | Use explicit scope management and verify restoration |
| Business error occurred but handler did not see error | Exception caught inside lambda without reporting | Check error handling and calls to `observation.error(ex)` |
| Attribute exists in context but backend does not show it | Internal attribute was not mapped to output data | Check handlers/conventions and declared metadata |
| Callbacks appear but no timer/span exists | Current handler only performs another action, like console printing | Check specific metrics/tracing integration |
| Duplicate output appears | Handler registered twice or same boundary instrumented twice | Audit registration sites and observation creation sites |

Callbacks are Java code executed on the thread invoking the observation lifecycle, not an asynchronous queue by default. A custom handler doing slow I/O or throwing errors can impact the observed call. The console-printing example in this lesson is for learning; in real applications, keep handlers lightweight, handle errors carefully, and avoid putting business logic back into callbacks.

Do not treat handlers as a reliable persistence mechanism for financial auditing or transaction processing. Enabling/disabling observations or changing observation handlers should not decide whether an order gets created.

## 10. Exercises to Test Understanding

Apply each change individually on a copy of the example program, then compare with the original output.

### Exercise 1: Remove CheckoutHandler Registration

Delete the `observationHandler(new CheckoutHandler())` call while keeping the business logic.

Expected: lines printed by the handler disappear. Business code still runs; do not conclude "checkout did not run" from not seeing `START/STOP`. The `BODY current` line may change because the observation no longer participates in observation as originally configured; do not use it as proof that business logic was skipped.

### Exercise 2: Allow Only a Different Context Type

Replace the `supportsContext` condition with an always-false condition to observe the effect, without modifying business logic.

Expected: this handler receives no callbacks for checkout. This is the difference between "a handler exists in configuration" and "a handler supports the context of the observation in question."

Do not keep that artificial condition in a real design; the exercise's purpose is to verify the selection point.

### Exercise 3: Move Per-Call Data to a Handler Field

Imagine a singleton handler with a `String lastResult` field updated by every `onStop`. When two requests run concurrently, why can this not replace `context.result`?

Answer: that field belongs to a shared handler, so it cannot stably represent a single observation run. Separate contexts tie data to each observation; if adding concurrency to the example, you must also manage objects and scopes properly per execution thread.

### Exercise 4: Catch Errors Inside the Lambda

Replace the exception-throwing branch with code that catches and handles the error inside the lambda, without calling `observation.error(ex)`.

Expected: outside `observe`, the exception from the handled branch is no longer received; the error callback does not appear automatically just because an exception object was created. If that failure needs recording, it must be reported explicitly per the observation contract.

### Exercise 5: Add a Second Handler

Register another lightweight handler that only counts stop occurrences and supports the same `CheckoutContext`.

Expected with suitable independent handlers: the same two checkout calls can serve both the callback-printing handler and the counting handler. You do not need to duplicate business logic once per observability tool.

When automated testing of real instrumentation is needed, Micrometer provides `micrometer-observation-test` and `TestObservationRegistry` to verify names, tags, start/stop calls, and leaked scopes. See [Micrometer Observation — Testing](https://docs.micrometer.io/micrometer/reference/1.13/observation/testing.html). This lesson's lab uses deterministic stdout to directly see the roles without guessing processing times.

After this lesson, learners should be able to explain which registry a checkout run goes through, which context it carries, which handlers support it, and who is responsible for closing the scope/stopping the observation. Those four answers help diagnose most cases of "code ran but no observation data appeared."
