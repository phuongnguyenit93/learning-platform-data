# Deciding Between a Single Provider, All Providers, or a Processing Chain

## 1. Core Question: When Multiple Providers Are Discovered, How Should They Be Called?

In a Java runtime extensibility system, a **service contract** (interface or abstract type) may have multiple **providers** (implementations). \`ServiceLoader\`, a dependency injection container, or a plugin registry helps **discover** implementations, but **selecting and coordinating execution** remains the application's design responsibility.

For example, a \`DocumentProcessor\` interface has three providers: format validation, sensitive-information scanning, and content transformation. Sometimes the application needs only one of the three, sometimes it must call all three independently, and sometimes the output of one step is the input to the next. These three situations lead to three different models:

| Model | Meaning | Key question |
|---|---|---|
| **Single provider** | Select a single implementation to handle the request | Who is responsible for handling this request? |
| **All providers / fan-out** | Invoke a set of providers, usually on the same input | What distinct result or side effect must each provider contribute? |
| **Processing chain / pipeline** | Invoke providers in order and pass results between steps | How does data flow through the transformation steps? |

No single model is always best. Misunderstanding the semantics can cause the application to submit a transaction multiple times, corrupt the transformation order, or pick the wrong provider.

## 2. Single Provider: One Request, One Handler

**Single provider** fits when a request has exactly one strategy or one responsible party: choosing an encoder by format, a payment processor by method, a driver by protocol, or one handler per event type.

A registry typically maps a key to an implementation:

\`\`\`text
Request(format="csv")
       |
       v
Registry: "csv" -> CsvExporter
       |
       v
CsvExporter.export(...)
       |
       v
Response
\`\`\`

Design steps:

1. Define the selection key, such as \`format\`, \`protocol\`, \`tenant\`, or \`paymentMethod\`.
2. Check how each provider declares its key or capability. If keys collide, enforce a clear rule; **fail-fast** is usually better than picking arbitrarily.
3. Select the provider once at the request boundary, avoiding mid-request changes if the registry can hot-reload.
4. Define behavior when no provider exists: return a clear error, use a controlled fallback, or reject the request.
5. Record the provider actually selected to aid debugging, version tracking, and auditing.

If the system uses \`ServiceLoader\`, do not assume discovery order is a business priority rule. Load order can be affected by classpath/module path, configuration sources, or class loaders and is unsuitable as a substitute for an explicit selection policy.

**When priority is needed:** you can define scores, priority levels, or specificity. You must define how to break ties when two providers share the same priority—for example, rejecting ambiguous configuration or selecting by a published stable key. If multiple providers expose \`supports(request)\`, consider the cost and side effects of the check: \`supports\` should be fast and must not mutate business state.

## 3. All Providers: Invoking Multiple Independent Parties

The **all providers** model, sometimes called broadcast or fan-out, sends the same event/input to multiple independent providers. For example: delivering an order-completed event to a logger, a metrics collector, and an audit sink; or collecting findings from multiple independent analyzers and aggregating them.

\`\`\`text
         +--> AuditProvider -------+
Event ---+--> MetricsProvider -----+--> Aggregate results
         +--> NotificationProvider-+
\`\`\`

Distinguishing point: providers **do not need the previous provider's output** as input. They can run sequentially or in parallel depending on safety and business requirements.

Decisions to make upfront:

- **Scope**: invoke every registered provider, or only those supporting this request type?
- **Synchronous vs. asynchronous**: if an immediate response is needed, sequential invocation is easy to reason about; if tasks are independent and resource-bounded, an executor can be used.
- **Result**: collect all outputs, compute an aggregate/score, or care only about side effects?
- **Single provider failure**: stop everything (fail-fast), collect errors into a report, or let the remaining providers run (best-effort)?
- **Idempotency and retry**: resending an event can cause notifications or transactions to execute multiple times.
- **Ordering**: if one provider must run after another, that may be a pipeline/dependency graph rather than independent fan-out.

Do not use all-providers to process a **single payment**, because calling two payment processors could create two transactions. For integrations with side effects, distinguish “run every handler concurrently” from “select a single responsible handler”.

Parallel execution does not automatically guarantee faster performance: you must control pools, timeouts, backpressure, concurrency limits, and how in-flight tasks terminate when a request is canceled. Likewise, each provider must be thread-safe for how it is actually used.

## 4. Processing Chain: Each Step Receives the Previous Step's Output

**Chain / pipeline** fits when there are ordered transformation or validation steps. For instance, a document goes through normalization, sensitive-data redaction, and then formatting for output.

\`\`\`text
Input
  |
  v
NormalizeProvider
  |
  v
RedactProvider
  |
  v
FormatProvider
  |
  v
Output
\`\`\`

Key characteristics:

- **Order is semantic**: changing the order can change the outcome.
- **Input/output contract**: steps must agree on data types, or adapters are needed to convert types between stages.
- **Error policy**: failure in one step usually prevents the pipeline from producing a valid output; optional step-skipping can be used, but it must be explicitly designed.
- **State mutation**: prefer immutable data or define clear ownership if mutation occurs.
- **Skip / early-stop capability**: represent this in a typed result (for example accepted/rejected) rather than using an ambiguous \`null\`.
- **Observability**: record duration, safe inputs/outputs, and errors per step; never log sensitive data.

A sequential processing pipeline differs from the GoF **Chain of Responsibility**: in Chain of Responsibility, each handler decides whether to handle the request or forward it to the next handler; a transformation pipeline usually requires every stage to apply (unless a skip policy exists). The two patterns can be combined, but they are not identical.

When a pipeline has branches, joins, conditionals, or cross-dependencies, a **DAG/workflow engine** model may be more suitable than a linear list.

## 5. Java 17+ Example: Demonstrating All Three Strategies

Create the file **\`ProviderSelectionDemo.java\`**. The program uses an in-memory registry and data and requires no external libraries. The examples intentionally omit \`ServiceLoader\` to highlight the **execution policy** once a provider list has been obtained.

\`\`\`java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.UnaryOperator;

public class ProviderSelectionDemo {
    // 1. Single provider: choose one formatter by key.
    interface Formatter {
        String format(String input);
    }

    static final class UppercaseFormatter implements Formatter {
        public String format(String input) {
            return input.toUpperCase(java.util.Locale.ROOT);
        }
    }

    static final class BracketFormatter implements Formatter {
        public String format(String input) {
            return "[" + input + "]";
        }
    }

    static String single(Map<String, Formatter> registry,
                         String key, String input) {
        Formatter formatter = registry.get(key);
        if (formatter == null) {
            throw new IllegalArgumentException("Unknown formatter: " + key);
        }
        return formatter.format(input);
    }

    // 2. All providers: each observer receives the same event.
    interface Observer {
        String name();
        String onEvent(String event);
    }

    static List<String> all(List<Observer> observers, String event) {
        List<String> reports = new ArrayList<>();
        for (Observer observer : observers) {
            reports.add(observer.name() + ": " + observer.onEvent(event));
        }
        return reports;
    }

    // 3. Pipeline: previous step's output becomes next step's input.
    static String pipeline(List<UnaryOperator<String>> stages, String input) {
        String current = input;
        for (UnaryOperator<String> stage : stages) {
            current = stage.apply(current);
        }
        return current;
    }

    public static void main(String[] args) {
        Map<String, Formatter> formatters = Map.of(
            "upper", new UppercaseFormatter(),
            "bracket", new BracketFormatter()
        );
        System.out.println("Single: " +
            single(formatters, "upper", "java"));

        Observer audit = new Observer() {
            public String name() { return "audit"; }
            public String onEvent(String event) {
                return "recorded " + event;
            }
        };
        Observer metric = new Observer() {
            public String name() { return "metric"; }
            public String onEvent(String event) {
                return "counted " + event;
            }
        };
        System.out.println("All: " +
            all(List.of(audit, metric), "order-created"));

        List<UnaryOperator<String>> stages = List.of(
            String::strip,
            s -> s.replace(" ", "-"),
            s -> "[" + s + "]"
        );
        System.out.println("Pipeline: " +
            pipeline(stages, "  hello world  "));
    }
}
\`\`\`

Compile and run:

\`\`\`bash
javac ProviderSelectionDemo.java
java ProviderSelectionDemo
\`\`\`

Exact output:

\`\`\`text
Single: JAVA
All: [audit: recorded order-created, metric: counted order-created]
Pipeline: [hello-world]
\`\`\`

Explanation:

- \`single\` invokes only the formatter identified by the key \`upper\`. \`Map.of\` is suitable for a fixed registry and disallows modification after creation.
- \`all\` invokes both \`audit\` and \`metric\` with the same event \`order-created\`. Here the results are returned in the order of \`List.of(audit, metric)\`, but no equivalent ordering guarantee exists across all discovery sources.
- \`pipeline\` starts with a string containing whitespace; \`strip\` removes leading/trailing whitespace, the second step turns the space between words into a hyphen, and the third step wraps it in square brackets. If the stage order changes, the output can differ.

The example uses **static registration**, not hot plugin loading. When using dedicated class loaders or \`ServiceLoader\`, the discovered provider list still needs to go through the same selection rules, version checks, ordering, and lifecycle management.

## 6. Choosing a Model by Requirement

| Scenario | Recommendation | Why |
|---|---|---|
| Choose a \`pdf\` or \`csv\` exporter | Single | One output belongs to one specific format |
| Choose a payment gateway by card issuer | Single | One party is responsible for the payment |
| Emit an event to logging, metrics, and audit | All providers | Independent subscribers |
| Run multiple analyzers to gather findings | All providers + aggregate | Results from multiple sources are needed |
| Normalize → redact data → serialize | Pipeline | Each step depends on the previous step's output |
| Try providers in turn until one accepts | Chain of Responsibility/fallback | Has a stopping rule; does not run all |
| Multiple parallel steps then merge and validate | DAG/workflow | Non-linear dependencies |

A quick way to choose is to ask three questions:

1. **Is completing via a single provider enough, with the rest acting as alternatives?** Use single or rule-based fallback.
2. **Must all providers see the same event/input while remaining independent of each other's output?** Use fan-out.
3. **Is step A's output step B's input, or does order make a difference?** Use pipeline/chain.

Do not pick all-providers merely because \`ServiceLoader\` returns an \`Iterable\`. The discovery mechanism returns a **set of candidates**; it does not decide the business execution model.

## 7. Ordering and Priority Rules in Plugin Systems

Provider ordering is a common source of bugs as an application grows. If deterministic order is needed, declare metadata such as \`order\`, \`phase\`, or a dependency list. When two providers share the same order, pick a transparent tie-breaking rule or reject the configuration. Never let \`HashMap\` iteration order, classpath, JAR paths, or incidental scanning order make business decisions.

For example, a pipeline with \`VALIDATE\`, \`TRANSFORM\`, and \`PERSIST\` phases may require providers to implement a specific \`Stage\`. Before activation, the host sorts providers based on validated metadata, detects dependency cycles, and verifies each stage fits its position. If the registry hot-reloads, capture an **immutable snapshot** for the entire request to avoid providers disappearing or reordering mid-processing.

For single-provider selection where multiple candidates satisfy \`supports\`, you can use priority, specificity, or a pinned version, but priority must never hide configuration conflicts or the risk of choosing the wrong provider.

## 8. Error Handling: Fail-Fast, Best-Effort, Fallback, and Rollback

The three models have different error semantics:

**Single:** a failure of the selected provider is a failure of the request, unless a predefined fallback exists. Fallback is only safe when you know the first provider has not caused an irreversible side effect. For example, a timeout calling a payment gateway does not prove the transaction was not processed; automatically trying another gateway can create a duplicate charge.

**All providers:** you can choose **fail-fast** if every contribution is mandatory, or **best-effort** when one observer's failure does not block the remaining observers. Return per-provider result reports distinguishing success, failure, timeout, and skipped. For asynchronous event emission, consider an outbox, bounded retries, idempotency keys, and a dead-letter queue for unprocessable messages.

**Pipeline:** a stage failure usually stops subsequent steps from running. If earlier steps already wrote external data, rollback may require a transaction (if within a shared scope) or **compensation** (saga), because exceptions alone cannot undo external writes. Intermediate data should have clear ownership to avoid leaving half-finished state.

You can model outcomes with explicit types such as \`Success<T>\`, \`Failure(code, detail)\`, \`Skipped(reason)\`, or records/enums to avoid returning an ambiguous \`null\`. Logs must record \`pluginId\`, \`pluginVersion\`, \`requestId\`, stage, and duration without leaking sensitive data.

## 9. Concurrency and Lifecycle Management

In a host handling concurrent requests, provider selection is tied to thread-safety and hot-reload rules.

- **Registry:** immutable snapshots or thread-safe structures prevent races when registering/unregistering providers. Registry thread-safety alone is not enough if an implementation holds unsynchronized mutable state.
- **Parallel all-providers:** avoid sharing mutable input; set concurrency limits, timeouts, and cancellation policies. Results may arrive out of call order, so aggregate by ID or deterministic order when needed.
- **Pipeline:** if stages have side effects, define tracing rules and intermediate data ownership. Dependent steps cannot be arbitrarily parallelized.
- **Hot replacement:** a request should retain its selected provider snapshot; the old version stops accepting new requests while finishing in-flight tasks before closing resources.
- **Resources and class loaders:** the host must manage \`close\`, threads, subscriptions, and live references. Calling \`URLClassLoader.close()\` does not immediately release classes or all plugin instances.

A plugin running in the same JVM usually holds significant process privileges. Load order and selection rules do not replace metadata, compatibility, authenticity, and trust checks before executing third-party code. For untrusted plugins, consider out-of-process isolation.

## 10. Applying This with ServiceLoader

\`ServiceLoader\` is Java's built-in **discovery** mechanism. Assuming the \`TaskProvider\` interface exists and JARs declare providers according to the rules, the host can build a candidate list:

\`\`\`java
// Snippet integrated into a system that has TaskProvider, not a standalone file.
List<TaskProvider> discovered = new ArrayList<>();
for (TaskProvider provider : ServiceLoader.load(TaskProvider.class)) {
    discovered.add(provider);
}
\`\`\`

After discovery, the host should:

1. Validate each provider's contract and metadata against the trust policy.
2. Apply configuration to decide between single, all, or pipeline. Do not default to \`forEach(provider::execute)\` in every case.
3. Build a registry/snapshot with an explicit order or selection key.
4. Execute with appropriate error, timeout, and lifecycle policies.

In practice, iterating \`ServiceLoader\` can instantiate providers during traversal; therefore, if JARs must be checked before **any plugin code runs**, perform artifact/manifest validation in an earlier step rather than treating \`ServiceLoader\` iteration as a harmless discovery operation for untrusted plugins. \`ServiceLoader.reload()\` only clears that loader's provider cache; it does not automatically add JARs outside the class loader's scope.

## 11. Common Mistakes and Design Checklist

- Treating \`ServiceLoader\` returning multiple providers as a requirement to call all of them.
- Using \`findFirst()\` to select a provider without a priority/identity rule.
- Letting multiple plugins with side effects receive a request that should only be handled once.
- Assuming parallel fan-out is always faster and needs no backpressure or error control.
- Leaving pipeline order undeclared so results change when discovery order changes.
- Falling back immediately after a timeout on an operation that may have already committed externally.
- Failing to guard against duplicate keys/providers or registry mutations while requests are running.
- Catching a generic exception for all errors and losing the failing provider and stage details.
- Lacking contract tests for providers and failing to simulate missing, duplicate, failing, or slow cases.

Before implementing, verify: whether the **business goal** is single / all / chain; whether the **decision source** is key/config/metadata; whether **ordering** is deterministic; whether **result types and error policies** are clear; whether **side effects and retries** are safe; and whether **thread-safety, timeouts, lifecycle, and security** fit the runtime environment.

**Remember:** a provider is the unit that supplies behavior, while the **selection policy** is the host's rule for using that behavior. Choose **a single provider** for decisions with one accountable handler, **all providers** when independent contributions are all required, and a **processing chain** when order and intermediate data are part of the business contract.