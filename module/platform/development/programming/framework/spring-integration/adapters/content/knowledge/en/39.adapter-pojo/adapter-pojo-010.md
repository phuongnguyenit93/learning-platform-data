# Script adapter

A script adapter allows embedding a script into a Spring Integration message processing flow. The script can handle payload transformation, condition filtering, routing, or minor business logic. This lets an application adjust certain mapping and processing rules without rewriting entire Java endpoints.

In the Spring Integration Adapters module, a script still sits at the boundary of a message flow: a message enters from a channel, the endpoint supplies input data to the script, and the result becomes the next message or decides whether the message continues. You must clearly design the contract between Java and the script, the script engine lifecycle, and error handling before using this in a multi-instance environment.

## 1. Where does a script adapter sit in an IntegrationFlow?

Spring Integration works with `Message<?>`, comprising payload and headers. A script adapter receives the message or mapped subsets of its data, executes the script, and returns the result to the endpoint using it.

| Endpoint role | Script output | Flow behavior |
|---|---|---|
| Transformer | Normalized payload or a new object | Emits a new message, usually preserving existing headers if the transformer only returns a payload |
| Filter | Boolean value | `true` passes the message onward; `false` removes the message from the output branch |
| Router | Channel name or routing key per configured contract | Forwards the message to the matching channel |
| Service activator | Processing result, or no result | Performs an action; if a result is returned, it can flow onward via the output channel |

Not every script should be used as a service activator. If the script only transforms data structure, place it in a transformer. If it only decides whether to continue, use a filter. If it selects destinations, use a router. Picking the right role keeps flow behavior readable and avoids stuffing multiple responsibilities into one script.

Spring Integration supports JSR-223-based scripting when the application provides the corresponding script engine. JSR-223 is the Java API for discovering and invoking scripting engines; the JDK itself does not guarantee built-in engines for every language. Depending on the Spring Integration version and installed dependencies, you can declare a script directly on an endpoint or wrap the script inside a POJO registered as a transformer/service activator. Verify XML and Java DSL syntax against your project's library version.

## 2. When should you use a script?

Scripts fit short logic with clear inputs/outputs that changes frequently with integration rules, such as:

- Renaming fields between partner payloads and internal models.
- Normalizing date, amount, or status code formats.
- Checking simple conditions before forwarding a message to another channel.
- Mapping an event type code to a target channel name.
- Building an intermediate payload from data received over HTTP, files, or brokers.

Prefer Java/POJOs when processing involves complex branching, explicit transactions, multiple repositories, calling multiple services, performance optimization, or strict type safety. Long scripts are harder to debug, refactor, and check with IDE tooling than statically typed Java code. Critical rules can be implemented in a POJO and called from a script or endpoint; never turn a script into the home for core business logic.

Before choosing a script, define who is allowed to edit it, how it is reviewed and released, whether hot-reloading at runtime is needed, and what happens when the script fails. Without clear answers to those questions, operational overhead can outweigh flexibility benefits.

## 3. Data contract between messages and scripts

Do not let scripts guess message structure or access the entire application context. Specify the exact variables the script receives. A simple contract might include:

| Variable name | Contents | Convention |
|---|---|---|
| `payload` | Message payload | Use an agreed schema; e.g., `Map`, DTO, or parsed JSON structure |
| `headers` | Permitted headers | Supply only headers needed for processing; omit credentials or unrelated internal metadata |
| `message` | Full message, if genuinely required | Use only when the script needs metadata beyond payload; avoid coupling scripts deeply to Spring Messaging |
| `correlationId` | Flow correlation identifier | Can be mapped from the corresponding header for logging or replies |

This contract is defined by the application; variable names do not magically appear in every JSR-223 engine. The adapter must build bindings or a context and populate data under the published names. If you rename variables, change payload types, or alter header semantics, treat it as a contract change and update related scripts and tests.

Pass a curated subset of headers rather than all headers if the script only needs a few values. For instance, an order normalization script might receive only `sourceSystem`, `schemaVersion`, and `correlationId`. Never place authentication tokens, cookies, connection handles, or privileged objects into the script context.

## 4. Example: using Groovy as a transformer

Suppose the system receives order messages as maps. The input payload may contain `id`, `total`, and `currency`; the `sourceSystem` header identifies the sender. The script validates the order total and produces a normalized structure for downstream steps.

Script `order-normalize.groovy`:

```groovy
def total = new BigDecimal(payload.total.toString())

if (total.signum() <= 0) {
    throw new IllegalArgumentException("Order total must be positive")
}

return [
    orderId: payload.id.toString(),
    total: total,
    currency: payload.currency.toString().toUpperCase(),
    source: headers['sourceSystem']
]
```

The script only reads the provided payload and headers, then returns a new map. It does not call repositories, send HTTP requests, or publish messages to brokers itself. Those actions belong to other endpoints in the flow.

The following Java snippet illustrates a POJO transformer using JSR-223. The example intentionally creates fresh bindings per execution and synchronizes calls because not every `ScriptEngine` guarantees thread safety across concurrent calls sharing one instance:

```java
import java.util.Map;
import javax.script.Bindings;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineManager;
import javax.script.ScriptException;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class OrderScriptAdapter {

    private static final String SCRIPT = """
        def total = new BigDecimal(payload.total.toString())
        if (total.signum() <= 0) {
            throw new IllegalArgumentException('Order total must be positive')
        }
        return [
            orderId: payload.id.toString(),
            total: total,
            currency: payload.currency.toString().toUpperCase(),
            source: headers['sourceSystem']
        ]
        """;

    private final ScriptEngine engine;

    public OrderScriptAdapter() {
        this.engine = new ScriptEngineManager().getEngineByName("groovy");
        if (this.engine == null) {
            throw new IllegalStateException(
                "No JSR-223 engine named 'groovy' is available");
        }
    }

    public synchronized Object transform(
            Message<Map<String, Object>> message) throws ScriptException {
        Bindings bindings = engine.createBindings();
        bindings.put("payload", message.getPayload());
        Object sourceSystem = message.getHeaders().get("sourceSystem");
        if (sourceSystem == null) {
            throw new IllegalArgumentException("Missing required header: sourceSystem");
        }
        bindings.put("headers", Map.of("sourceSystem", sourceSystem));
        return engine.eval(SCRIPT, bindings);
    }
}
```

Flow using the POJO as a transformer:

```java
@Bean
IntegrationFlow normalizeOrders(OrderScriptAdapter scriptAdapter) {
    return IntegrationFlow.from("orders.raw")
        .transform(scriptAdapter, "transform")
        .channel("orders.normalized")
        .get();
}
```

In this example, the application must add a dependency providing a Groovy JSR-223 engine compatible with the running Java version. If `getEngineByName("groovy")` returns `null`, the engine is not installed or the engine name does not match the provider. Verify engine names and dependencies in your real build/deploy environment; never assume the JDK alone includes a Groovy engine.

The Java snippet uses text blocks, requiring Java 15 or newer; on older Java versions, convert the script into a regular string or load it from a resource.

`synchronized` is a simple illustration for guarding a shared engine. It serializes executions and can limit throughput. Under heavy load, consider per-worker engines or an engine pool; share a single engine only when that specific engine's documentation confirms its concurrency policy. If the engine supports compiling scripts, compile once and reuse the compiled script according to the provider's thread-safety guarantees.

## 5. Using scripts for filters, routers, and service activators

Using the same script engine setup, you can build POJO methods with explicit return contracts and attach them to the corresponding endpoints.

**Filter:** method returns `boolean`. `true` lets the message proceed; `false` drops the message from the filter's output. If rejected messages must be kept for inspection, configure a discard channel or dedicated branch instead of dropping silently.

**Router:** method returns a routing value constrained to a valid channel list. Never let a script construct arbitrary bean or channel names from external input. If the value is invalid, route the message to an error channel or an intentional failure branch.

**Service activator:** method executes an action or returns a result. Writing data, calling services, and emitting messages should remain explicit in observable, testable components. Scripts should only coordinate small rules, not hold connections or manage transactions themselves.

Standardize how `null` results are handled. For a transformer, producing no output payload usually means emitting no further message; for a service activator, `null` may signal no reply. If `null` represents valid data, wrap the result in an explicit type or return a status-bearing object so the endpoint does not misinterpret it as missing output.

## 6. Execution errors and retries

Scripts can fail due to syntax errors, missing variables, wrong types, input data violating constraints, or engine errors. Categorize errors to choose the right handling:

| Error category | Examples | Handling approach |
|---|---|---|
| Script/configuration error | Missing brace, uncompilable script, engine not found | Catch at startup or deployment checks; never retry messages infinitely |
| Data error | Missing `id`, `total` cannot parse as number | Route message to error/quarantine flow with reason; fix data or contract before replay |
| Transient external error | Script calls a service that temporarily fails | Better to isolate the service call in its own endpoint; apply bounded retries there |
| Programming error | Unexpected null, bad cast, missing branch | Record exception and message ID, fix script or code, and replay under control |

Do not retry every exception under one blanket policy. Syntax errors or deterministic bad data will fail on every attempt. If the script runs in a synchronous flow, exceptions can propagate back to the caller. If the flow is asynchronous, configure an error channel or error handler so failures are not lost in generic logs.

When sending failed messages to a dead-letter channel, record the original message, `messageId`, `correlationId`, script version, timestamp, and exception type. Be careful with payloads containing personal data or secrets; apply data masking and retention policies. Replay only after identifying the root cause and knowing which script version will process the message.

## 7. Script governance and execution safety

A script is executable code running inside the application process. A standard JSR-223 engine does not automatically build a secure sandbox for untrusted code. Scripts can access the classpath, files, network, or Java APIs depending on the engine and host-provided context. Therefore:

- Load scripts only from controlled, reviewed sources released through your software delivery pipeline.
- Never allow end users to submit arbitrary scripts to run inside the application JVM.
- Never expose `ApplicationContext`, bean factories, connections, credentials, or broad-privilege objects in bindings.
- Restrict callable APIs per engine capabilities; do not treat omitting a variable from bindings as a security sandbox.
- Bound execution time, input size, and resource usage as supported by the engine/runtime. If untrusted code must execute, use an isolated process or service with real security boundaries.
- Record the script version or checksum to trace which logic processed an outcome.

For scripts packaged inside the application, classpath resources keep script versions aligned with application releases and easy to roll back. If loading scripts from an external config store for independent updates, define source authentication, pre-activation syntax validation, caching, versioning, rollback, and fallback behavior when the store is unreachable. Never silently reload a script on every message, as that increases latency and risks replicas running different versions simultaneously.

## 8. Performance and multi-replica operation

Script engines incur initialization, parse/compile, and execution costs. To keep load under control:

1. Initialize the engine and load scripts per bean or worker lifecycle, not a fresh engine per message without reason.
2. Reuse compiled scripts when supported by the engine and ensure thread-safe sharing.
3. Create fresh bindings per message so data from one message never leaks into the next run.
4. Bound script-executing threads and upstream queue lengths; do not let slow scripts grow backlogs indefinitely.
5. Measure execution duration, error rates, timeouts, dropped message counts, and the active script version.

Each replica may maintain its own engine and script cache. When rolling out a new version, ensure replicas converge on the released version or use compatible transitions. If scripts update dynamically, avoid uncontrolled splits where some replicas run the new version while others run the old one. Global variables or state stored inside the engine must not be used for business state, as they are not shared consistently across replicas and vanish on pod restarts.

## 9. Testing script adapters

Tests must verify both script logic and the endpoint contract:

- **Standalone script tests:** supply sample payloads and bindings; assert output, types, and exceptions.
- **Adapter tests:** verify the adapter creates exact bindings, passes only permitted headers, and picks the right engine.
- **IntegrationFlow tests:** send messages to the input channel, check the output channel, preserved/transformed headers, and filter/router behavior.
- **Failure tests:** test missing payload fields, wrong types, syntax errors, and missing engines; verify messages reach the expected error path.
- **Concurrency tests:** run multiple messages concurrently to uncover race conditions, shared bindings, or non-thread-safe engines.
- **Deployment tests:** confirm the engine dependency is present in the artifact/runtime container and script resources are packaged at the expected path.

Do not test only one happy path. Add boundary cases such as zero amount, missing fields, empty strings, absent headers, and unsupported schema versions. For scripts with multiple branches, test data should cover every critical branch.

## 10. Checklist for taking scripts to production

1. Identify the endpoint needing scripting and choose transformer, filter, router, or service activator.
2. Document the input/output contract: payload schema, allowed headers, return type, and error representation.
3. Select the engine and verify dependency compatibility with your Java and Spring Integration versions.
4. Keep scripts small and versioned; review them with the same rigor as application source code.
5. Test standalone, adapter, IntegrationFlow, failure modes, and concurrency.
6. Package scripts or deploy a controlled script source; verify scripts load before accepting messages.
7. Monitor execution latency, errors, backlog, and script version per replica; prepare rollback and failed-message replay procedures.

A well-designed script adapter has bounded inputs, predictable outputs, holds no state across messages, and triggers no side effects outside its contract. Once a script begins needing multiple dependencies, transactions, or hard-to-test logic, refactor that work into a strongly typed POJO/service and leave scripting only for small transformations where it still adds practical value.
