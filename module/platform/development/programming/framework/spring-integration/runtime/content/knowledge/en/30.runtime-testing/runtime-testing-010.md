# Testing Integration Graphs and Observability Hooks in Spring Integration Runtime

## 1. Goal: verifying both topology and operational signals

In **SPRING_INTEGRATION_RUNTIME**, a message flow is not merely one Java function calling another. Spring Integration builds a network of channels, consumer endpoints, handlers, pollers, gateways, routers, error flows, and manageable lifecycle components. When a flow is modified via Java DSL, annotations, or XML configuration, a test that only sends one message and checks the final payload is **not enough** to catch:

- Wrong input channel or output channel;
- Missing subscriber, unstarted endpoint, or wrong lifecycle;
- Broken `errorChannel`, `discardChannel`, or router branch;
- Dynamic endpoints added while the runtime graph has not been refreshed;
- Metrics/tracing/observations not firing even though business logic succeeded;
- Retries, executors, pollers, or brokers causing errors to surface on another thread;
- Observations created yet missing low-cardinality tags, leaking scopes, or never stopping.

The topic **Testing runtime → Testing Integration Graphs and Observability Hooks** requires writing tests that can **prove structure is wired properly** and **prove observability signals fire at runtime**, without depending on a live external monitoring server.

A practical strategy has three layers:

1. **Graph assertions:** `IntegrationGraphServer` has the expected nodes/links, the right message paths exist, and topology refreshes after registering/removing dynamic flows.
2. **Behavior assertions:** real messages flow through channels, verifying outputs, error paths, endpoint states, correlation, and transactions/retries per scenario.
3. **Observability assertions:** `ObservationRegistry` and `ObservationHandler` receive start/stop/error events; metric/tracing hooks are wired properly; no high-cardinality tags appear in metrics.

~~~mermaid
flowchart TD
    T["JUnit / Spring Test"] --> G["IntegrationGraphServer.getGraph()"]
    T --> M["MessageChannel.send(message)"]
    T --> O["TestObservationRegistry / custom ObservationHandler"]
    G --> A["Assert nodes + typed links"]
    M --> B["Assert output / failure / lifecycle"]
    O --> C["Assert observation started/stopped, name/tags"]
    A --> R{"Tests pass?"}
    B --> R
    C --> R
    R -->|Yes| P["Flow wiring + runtime hooks verified"]
    R -->|No| D["Diagnose right layer"]
~~~

**Do not conflate them:** an edge `ordersIn -> ordersHandler` in the graph does not prove the handler received a message; a metric timer does not prove the DB committed. Combine structural checks, actual execution, and durable resource state when business logic requires it.

## 2. What is the integration graph?

Spring Integration provides **`IntegrationGraphServer`**, a bean that collects the runtime object model and returns a **`Graph`** object. The graph is not a static blueprint: it is synthesized from the actual Spring Integration components present in the `ApplicationContext`.

Three basic groups of information:

| Graph part | Spring Integration 6.x Java API | Role |
| --- | --- | --- |
| `contentDescriptor` | `graph.getContentDescriptor()` | Provider info, application name, format/version |
| `nodes` | `graph.getNodes()` | Channels, endpoints, producers, handlers, and metadata |
| `links` | `graph.getLinks()` | Connections between node IDs, with link types |

Nodes extend `IntegrationNode`, providing:

- `getNodeId()`: numeric ID of the node in the current graph;
- `getName()`: component name;
- `getComponentType()`: component type;
- `getProperties()`: observable properties;
- `isObserved()` (Spring Integration 6.0.1+): indicates whether the component is instrumented via `ObservationRegistry` per management status.

Each `LinkNode` in Spring Integration **6.5.x** has `getFrom()`, `getTo()`, and `getType()`. Link types can be `input`, `output`, `route`, `discard`, or `error`.

> **Version note:** in Spring Integration **7.1**, `LinkNode` is represented as a Java record with accessors `from()`, `to()`, `type()`, no longer necessarily `getFrom()/getTo()/getType()` as in 6.x code. The test examples below specifically target the **Spring Integration 6.5.x** API; if your project uses 7.x, adjust accessors per the corresponding Javadoc.

An illustrative graph:

~~~text
nodes:
  #11: ordersIn       [channel]
  #12: normalize       [transforming consumer]
  #13: normalizedOrders[channel]
  #14: auditHandler    [service activator]

links:
  11 --input--> 12
  12 --output--> 13
  13 --input--> 14
~~~

Node IDs `11`, `12` are examples only. **Never hard-code** numeric IDs in tests, as they depend on runtime context/graph rebuilds. Look up node IDs by stable **component names** or appropriate properties.

## 3. Give components stable names so the graph is testable

When Spring Integration auto-generates endpoint IDs, names can include method names, bean names, indices, or suffixes depending on how the framework constructs beans. Refactoring a method can break exact-string tests even when the business flow remains right.

For endpoints that are **architectural contracts** under test, prefer explicit IDs:

~~~java
@Bean
IntegrationFlow orderFlow(OrderService service) {
    return IntegrationFlow.from("ordersIn")
        .transform(String.class, String::trim,
                endpoint -> endpoint.id("trimOrderEndpoint"))
        .handle(service, "process",
                endpoint -> endpoint.id("orderProcessorEndpoint"))
        .get();
}
~~~

The snippet above illustrates the Java DSL idea; `OrderService`, imports, and matching DSL overloads for your exact version are needed. For annotation-generated endpoints, inspect actual endpoint names via the graph or declare explicit beans/endpoints when stable contracts are needed.

**Explicit naming does not mean every piece becomes a separate node.** The graph builder models structure by actual component type and may fold a handler into an endpoint node. Tests should rely on input/output links and the nodes actually published by your current version.

## 4. Registering and retrieving the graph in tests

The graph server is provided as a Spring bean:

~~~java
@Bean
IntegrationGraphServer integrationGraphServer() {
    return new IntegrationGraphServer();
}
~~~

Once the context refreshes, you can fetch the cached graph:

~~~java
Graph graph = integrationGraphServer.getGraph();

Collection<IntegrationNode> nodes = graph.getNodes();
Collection<LinkNode> links = graph.getLinks();
~~~

If components are added or destroyed after the graph was built, call:

~~~java
Graph refreshed = integrationGraphServer.rebuild();
~~~

**`getGraph()` retrieves the cached graph**; node metadata/metrics may update at runtime, yet **newly added/removed topology** must be verified with `rebuild()` after structural changes. `rebuild()` refreshes the model; it does **not** start endpoints, subscribe consumers, or fix broken flows.

An integration test does not need to boot a web server or enable Actuator:

~~~text
JUnit + Spring ApplicationContext
          |
          +-- IntegrationGraphServer (bean)
          +-- channels, endpoints, handlers
          +-- ObservationRegistry / test hook
~~~

Spring Boot Actuator's `integrationgraph` HTTP endpoint is useful for deployment smoke tests, whereas testing directly in-JVM avoids configuring remote access, security, and network ports. Actuator exposure is a **separate concern**, not required to test the `Graph` object.

## 5. Graph assertions: names, IDs, and typed links

A common mistake:

~~~java
assertTrue(graph.getNodes().size() > 0);
~~~

An application can contain many default nodes so this passes even when **the entire flow you meant to test is missing**.

A more useful test verifies:

1. Node `graphInput` actually exists;
2. Node `graphOutput` actually exists;
3. An endpoint takes input from `graphInput`;
4. **That same endpoint** emits output to `graphOutput`.

Helper example for Spring Integration **6.5.x**:

~~~java
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

import org.springframework.integration.graph.Graph;
import org.springframework.integration.graph.IntegrationNode;
import org.springframework.integration.graph.LinkNode;

import static org.junit.jupiter.api.Assertions.*;

static void assertFlowPath(
        Graph graph, String inputName, String outputName) {

    Map<String, IntegrationNode> byName = graph.getNodes()
        .stream()
        .collect(Collectors.toMap(
            IntegrationNode::getName,
            Function.identity(),
            (left, right) -> left));

    IntegrationNode input = byName.get(inputName);
    IntegrationNode output = byName.get(outputName);

    assertNotNull(input, "Input node missing: " + inputName);
    assertNotNull(output, "Output node missing: " + outputName);

    Set<Integer> consumers = graph.getLinks().stream()
        .filter(link -> link.getFrom() == input.getNodeId())
        .filter(link -> link.getType() == LinkNode.Type.input)
        .map(LinkNode::getTo)
        .collect(Collectors.toSet());

    assertFalse(consumers.isEmpty(),
        "No consumer connected to " + inputName);

    boolean pathExists = graph.getLinks().stream()
        .filter(link -> link.getTo() == output.getNodeId())
        .filter(link -> link.getType() == LinkNode.Type.output)
        .anyMatch(link -> consumers.contains(link.getFrom()));

    assertTrue(pathExists,
        inputName + " has no consumer writing to " + outputName);
}
~~~

The helper intentionally avoids hard-coding numeric node IDs. It **does not automatically search multi-hop paths**; it targets one transformer/handler between two channels. If a flow has `router -> queue -> poller -> handler`, write a graph traversal over the corresponding typed edges.

**Distinguish input/output directions:** an `input` link normally connects **channel → endpoint**, while `output` connects **endpoint → channel**. Check `from/to` according to the link direction published by the graph, rather than guessing from variable names.

### When must tests also inspect `route`, `discard`, `error`?

| Link type | Flow example | Key assertion |
| --- | --- | --- |
| `input` | `ordersIn → transformer` | Consumer is wired to the right channel |
| `output` | `transformer → normalizedOrders` | Output channel is configured |
| `route` | `@Router` with multiple branches | Path exists to every required business channel |
| `discard` | Filter or idempotent receiver | Real discard sink exists; messages are not dropped unintentionally |
| `error` | Poller/adapter with error channel | Error path is wired per supporting component |

In some cases, an adapter/endpoint does not represent every dynamic path in the static graph. For instance, a handler manually calling `MessageChannel.send()` resolved at runtime may not expose an output link like an `AbstractReplyProducingMessageHandler` with a configured output channel. **Never infer business correctness from the graph alone** when topology is dynamic or custom-routed.

## 6. Micrometer Observation: a hook distinct from the integration graph

Since Spring Integration **6.0**, the framework supports the **Micrometer Observation API**. Each Observation has a context, name, low/high cardinality key values, and lifecycle callbacks dispatched to matching `ObservationHandler`s.

When Spring Integration needs to instrument `IntegrationManagement` components:

1. Provide an **`ObservationRegistry`** bean in the application context.
2. Enable `@EnableIntegrationManagement`.
3. Configure `observationPatterns` to select which components to instrument.
4. Register an appropriate `ObservationHandler` to actually **collect test observations, metrics, or trace spans**.

**Easy to miss:** declaring only an `ObservationRegistry` bean is **not enough**; in Spring Integration, management components are **not** all instrumented by default unless observation patterns are selected. In tests you can set `"*"` to cover everything, while production should pick an appropriate subset.

~~~java
@Configuration
@EnableIntegration
@EnableIntegrationManagement(observationPatterns = "*")
class ObservationConfig {

    @Bean
    ObservationRegistry observationRegistry() {
        return ObservationRegistry.create();
    }
}
~~~

**However**, `ObservationRegistry.create()` by default **does not emit Prometheus metrics or trace spans** unless an appropriate `ObservationHandler` is registered. For direct testing, use `TestObservationRegistry` from `micrometer-observation-test` or register a custom `ObservationHandler`.

### Distinguishing three easily confused mechanisms

| Mechanism | Purpose | What test evidence does it give? |
| --- | --- | --- |
| `IntegrationGraphServer` | Inspect topology: nodes/links | Node/link assertions |
| `ObservationRegistry` + `ObservationHandler` | Verify observability hook execution | Observation started/stopped/errored, names and tags |
| `MeterRegistry` + meter observation handler | Verify actual metrics like timers/counters | Meter/timer exists in registry, sample count increments |

**Do not** assert a metric in `SimpleMeterRegistry` if only `TestObservationRegistry` is present without a meter `ObservationHandler`; in that setup, there is no reason for timers to appear.

## 7. Instrumented components and observation names

Spring Integration 6.x documentation lists notable component types:

- `AbstractMessageChannel.send()`: producer observation;
- `AbstractMessageHandler`: handler/consumer observation;
- `MessageProducerSupport`: inbound producer observed on receive;
- `MessagingGatewaySupport`: gateway/request-reply observation;
- `SourcePollingChannelAdapter`: since Spring Integration **6.5**, observation support for inbound polling.

Typical observation names:

| Name | Scope | Notes |
| --- | --- | --- |
| `spring.integration.producer` | Channel send/message producer | Commonly used when asserting channel `send()` |
| `spring.integration.handler` | Message handler | May not apply to handler lambdas that are not `AbstractMessageHandler` |
| `spring.integration.gateway` | Messaging gateway | Not always present if the test does not traverse a gateway |

Exact names/tags depend on **conventions and versions**. Metric docs use low-cardinality keys such as `spring.integration.name` and `spring.integration.type`. Do not confuse the observation name with the exported Prometheus metric name that your system may transform.

### Observed vs. managed

`IntegrationNode.isObserved()`, available since Spring Integration 6.0.1, shows whether a component is instrumented with an `ObservationRegistry`. This is a **configuration signal**, not proof that an observation was started/stopped during a test.

A test should have two steps:

~~~text
Graph node isObserved?  -> instrument flag/management configuration
Send message            -> actual ObservationHandler recorded event?
~~~

If `isObserved()` is true yet no sample appears, either the test never sent through that component, there is no subscriber, or the registry handler did not capture data.

## 8. Using TestObservationRegistry to test without a monitoring server

Micrometer provides **`micrometer-observation-test`** for test scope. `TestObservationRegistry` includes a built-in handler that records observations and validators checking valid lifecycles.

Sample Gradle dependencies (for learner reference only—**do not run Gradle in STEP 4**):

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-integration")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("io.micrometer:micrometer-observation-test")
}
~~~

Dependency versions should follow your project's compatible Spring Boot/Spring Integration BOM. Without a BOM, pin versions explicitly; never mix incompatible Micrometer 1.x/2.x and Spring Framework generations arbitrarily.

A standalone observation test without Spring Integration to learn the API:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.tck.TestObservationRegistry;
import io.micrometer.observation.tck.TestObservationRegistryAssert;

TestObservationRegistry registry = TestObservationRegistry.create();

Observation.createNotStarted("order.validate", registry)
    .lowCardinalityKeyValue("operation", "validate")
    .observe(() -> {
        // Instrumented logic
    });

TestObservationRegistryAssert.assertThat(registry)
    .doesNotHaveAnyRemainingCurrentObservation()
    .hasObservationWithNameEqualTo("order.validate")
    .that()
    .hasLowCardinalityKeyValue("operation", "validate")
    .hasBeenStarted()
    .hasBeenStopped();
~~~

This snippet belongs inside a JUnit test method. It proves the test registry works, **not** that Spring Integration instrumentation is enabled. To test real integration hooks, send messages through **Spring Integration-managed channels/handlers**.

## 9. Integrated example: JUnit testing graph and observations in one context

This example targets **Java 17+, Spring Integration 6.5.x, Spring Framework 6.x, JUnit 5, and Micrometer Observation 1.x**. Place everything in `RuntimeGraphObservationTest.java` under package `demo.integration`.

The example creates:

- A `DirectChannel` named `graphInput`;
- A `QueueChannel` named `graphOutput`;
- A transformer turning `"hello"` into `"HELLO"`;
- `IntegrationGraphServer` to inspect nodes/links;
- `TestObservationRegistry` and `@EnableIntegrationManagement(observationPatterns = "*")` to capture observations.

~~~java
package demo.integration;

import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

import io.micrometer.observation.tck.TestObservationRegistry;
import io.micrometer.observation.tck.TestObservationRegistryAssert;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.MessageEndpoint;
import org.springframework.integration.annotation.Transformer;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.config.EnableIntegrationManagement;
import org.springframework.integration.graph.Graph;
import org.springframework.integration.graph.IntegrationGraphServer;
import org.springframework.integration.graph.IntegrationNode;
import org.springframework.integration.graph.LinkNode;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(RuntimeGraphObservationTest.Config.class)
class RuntimeGraphObservationTest {

    @Autowired
    private IntegrationGraphServer graphServer;

    @Autowired
    @Qualifier("graphInput")
    private MessageChannel input;

    @Autowired
    @Qualifier("graphOutput")
    private PollableChannel output;

    @Autowired
    private TestObservationRegistry observations;

    @BeforeEach
    void clearObservations() {
        observations.clear();
    }

    @Test
    void graphContainsWiredInputAndOutput() {
        Graph graph = graphServer.getGraph();

        Map<String, IntegrationNode> nodes = graph.getNodes()
            .stream()
            .collect(Collectors.toMap(
                IntegrationNode::getName,
                Function.identity(),
                (a, b) -> a));

        IntegrationNode in = nodes.get("graphInput");
        IntegrationNode out = nodes.get("graphOutput");

        assertNotNull(in, "graphInput node missing");
        assertNotNull(out, "graphOutput node missing");

        Set<Integer> consumers = graph.getLinks()
            .stream()
            .filter(l -> l.getFrom() == in.getNodeId())
            .filter(l -> l.getType() == LinkNode.Type.input)
            .map(LinkNode::getTo)
            .collect(Collectors.toSet());

        assertFalse(consumers.isEmpty(),
            "No input consumer connected to graphInput");

        boolean outputConnected = graph.getLinks()
            .stream()
            .filter(l -> l.getTo() == out.getNodeId())
            .filter(l -> l.getType() == LinkNode.Type.output)
            .anyMatch(l -> consumers.contains(l.getFrom()));

        assertTrue(outputConnected,
            "Transformer does not send to graphOutput");
    }

    @Test
    void sendsMessageAndPublishesObservation() {
        boolean accepted = input.send(
            MessageBuilder.withPayload("hello").build());

        assertTrue(accepted);

        Message<?> response = output.receive(1_000);
        assertNotNull(response, "No reply on graphOutput");
        assertEquals("HELLO", response.getPayload());

        // Channel send is an SI-instrumented operation.
        TestObservationRegistryAssert.assertThat(observations)
            .doesNotHaveAnyRemainingCurrentObservation()
            .hasObservationWithNameEqualTo(
                "spring.integration.producer")
            .that()
            .hasBeenStarted()
            .hasBeenStopped();
    }

    @Configuration
    @EnableIntegration
    @EnableIntegrationManagement(observationPatterns = "*")
    static class Config {

        @Bean
        IntegrationGraphServer integrationGraphServer() {
            return new IntegrationGraphServer();
        }

        @Bean
        TestObservationRegistry observationRegistry() {
            return TestObservationRegistry.create();
        }

        @Bean("graphInput")
        MessageChannel graphInput() {
            return new DirectChannel();
        }

        @Bean("graphOutput")
        PollableChannel graphOutput() {
            return new QueueChannel();
        }

        @Bean
        UppercaseTransformer uppercaseTransformer() {
            return new UppercaseTransformer();
        }
    }

    @MessageEndpoint
    static class UppercaseTransformer {

        @Transformer(
            inputChannel = "graphInput",
            outputChannel = "graphOutput")
        public String upper(String payload) {
            return payload.toUpperCase(java.util.Locale.ROOT);
        }
    }
}
~~~

### Why are both tests needed?

- `graphContainsWiredInputAndOutput()` checks **topology**: the channel actually connects to an endpoint and the endpoint emits to the output.
- `sendsMessageAndPublishesObservation()` checks **behavior** and **instrumentation**: a `"HELLO"` message actually lands in the queue, and the registry observes a producer observation.
- Tests need no Prometheus, Zipkin, or OpenTelemetry collector.
- `QueueChannel.receive(1_000)` uses a **finite timeout**, never blocking indefinitely.
- `@BeforeEach observations.clear()` prevents observations from earlier tests from causing false positives.

**Important note:** `@EnableIntegrationManagement(observationPatterns = "*")` enables observations on components that Integration Management can instrument. If a component is excluded by another pattern or replaced by a custom test harness, adjust assertions to match actual wiring.

### Notable version details

The example uses `LinkNode` accessors from **6.5.x**. With **Spring Integration 7.1**, switch to:

~~~java
link.getFrom()   // 6.x
link.getTo()     // 6.x
link.getType()   // 6.x

link.from()      // 7.1 record
link.to()        // 7.1 record
link.type()      // 7.1 record
~~~

Do not mix both sets of methods in one code target. Other assertions (`Graph.getNodes()`, `IntegrationNode.getName()`, `getNodeId()`) remain compatible per verified Javadoc.

**Do not treat the lesson as CI-verified code:** in STEP 4, content is authored without running builds/tests or academic Content QA. In a real project, pin BOM versions and run tests to verify wiring against your actual dependencies.

## 10. Standalone hook test: custom ObservationHandler

`TestObservationRegistry` lets you assert names/tags, yet sometimes you need to test **application-installed hooks**—for instance counting observation starts/stops and recording audit telemetry. You can implement `ObservationHandler<Observation.Context>`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;

final class CountingObservationHandler
        implements ObservationHandler<Observation.Context> {

    private final AtomicInteger starts = new AtomicInteger();
    private final AtomicInteger stops = new AtomicInteger();
    private final AtomicInteger errors = new AtomicInteger();

    @Override
    public boolean supportsContext(Observation.Context context) {
        return true;
    }

    @Override
    public void onStart(Observation.Context context) {
        starts.incrementAndGet();
    }

    @Override
    public void onStop(Observation.Context context) {
        stops.incrementAndGet();
    }

    @Override
    public void onError(Observation.Context context) {
        errors.incrementAndGet();
    }

    public int starts() {
        return starts.get();
    }

    public int stops() {
        return stops.get();
    }

    public int errors() {
        return errors.get();
    }

    public void reset() {
        starts.set(0);
        stops.set(0);
        errors.set(0);
    }
}
~~~

Register this handler with `TestObservationRegistry` before sending messages:

~~~java
CountingObservationHandler hook =
        new CountingObservationHandler();

TestObservationRegistry registry =
        TestObservationRegistry.create();

registry.observationConfig().observationHandler(hook);

// Execute instrumented operation.
Observation.createNotStarted("test.operation", registry)
        .observe(() -> { });

assertEquals(1, hook.starts());
assertEquals(1, hook.stops());
assertEquals(0, hook.errors());
~~~

In Spring Integration tests, you can expose the hook as a bean, register it on the registry in test configuration, and reset counters **before** sending messages. When two handlers receive the same observations (your hook and `TestObservationRegistry`'s handler), do not assume callback ordering between handlers is a business contract.

### Testing start/stop/error conditionally

| Hook callback | When it fires | What to assert? |
| --- | --- | --- |
| `onStart` | Observation starts | Invoked when message traverses component |
| `onStop` | Observation finishes | No leaked observations; stop counter matches |
| `onError` | Code calls `Observation.error(ex)` | Error recorded per active convention |
| `onEvent` | Observation event emitted | Event name and context when app emits explicit events |
| `onScopeOpened` / `onScopeClosed` | Scope opened/closed | Proper lifecycle in async/threading scenarios |

**Do not assume every Java exception automatically increments `onError`** unless the instrumentation scope calls `Observation.error(...)`. For custom hook tests, inject an intentional error and check actual observation behavior for your version.

## 11. Graph node `isObserved()` cannot replace runtime hook assertions

In the graph, `IntegrationNode.isObserved()` reports whether the component is instrumented with an observation registry, yet:

~~~text
isObserved == true
    ≠ sample emitted
    ≠ trace exported
    ≠ metric timer incremented
    ≠ message processed successfully
~~~

You can check:

~~~java
Graph graph = graphServer.getGraph();

IntegrationNode channel = graph.getNodes()
        .stream()
        .filter(node -> "graphInput".equals(node.getName()))
        .findFirst()
        .orElseThrow();

assertTrue(channel.isObserved());
~~~

Available in Spring Integration 6.0.1+ when `observationPatterns` covers the component. However, with different metadata versions or `ObservationRegistry.NOOP`, this flag may not behave as expected. If this assertion fails, check the configurer/pattern/registry instead of increasing timeouts indefinitely.

Separate the two questions:

1. **Is it instrumented?** Check `isObserved()` and config.
2. **Was it actually invoked?** Check `TestObservationRegistry` or a custom `ObservationHandler`.

## 12. Testing link graphs: avoiding brittle tests

### 12.1. Do not snapshot the entire graph uncritically

The graph can include many default components like `errorChannel`, `nullChannel`, internal error loggers, and auto-configured beans. A full-JSON snapshot comparison can break whenever the framework changes metadata or bumps package versions, even when business logic is completely intact.

Assert by **architectural contract** instead:

~~~text
MUST: graphInput exists
MUST: graphOutput exists
MUST: a consumer connects graphInput to graphOutput
MUST: error recovery path exists if business contract requires it

MAY: extra default nodes
MAY: additional metrics properties
MAY: different numeric nodeIds
~~~

### 12.2. Do not check only node names

An existing node without links may be a **disconnected** channel. For a flow with a router:

- Assert an input link exists from the source channel to the router.
- Assert route/discard/error links for required branches.
- Send messages to test the **actual selected route** per header/payload.
- For dynamic routes resolved at runtime, the static graph may not show every dynamic target.

### 12.3. Separate behavior checks when topology is complex

A multi-hop path:

~~~mermaid
flowchart LR
    I["ordersIn"] --> R["Router"]
    R -->|priority| Q1["priorityQueue"]
    R -->|normal| Q2["regularQueue"]
    Q1 --> P1["Priority poller"]
    Q2 --> P2["Regular poller"]
    P1 --> H["Handler"]
    P2 --> H
    H --> O["results"]
~~~

From the graph, you can write a BFS/DFS over `nodeId` and typed links. Still, testing message routing **cannot rely on BFS alone**: routers choose branches from data, pollers depend on triggers, and handlers can throw. A graph path means a **connection can exist**, not that every input traverses it.

## 13. Runtime graph and dynamically registered flows

Spring Integration supports `IntegrationFlowContext` for registering/destroying flows at runtime. For the graph, refresh topology after changes:

~~~java
IntegrationFlowContext.IntegrationFlowRegistration registration =
        flowContext.registration(newFlow)
                .id("tenantAFlow")
                .autoStartup(false)
                .register();

Graph newGraph = graphServer.rebuild();

// Assert nodes/links created by tenantAFlow are present.

registration.start();
// Test message flow and observation hooks.

registration.stop();
registration.destroy();

Graph afterRemoval = graphServer.rebuild();

// Assert destroyed components disappeared if not shared.
~~~

This is an **illustrative snippet**; `flowContext` is an `IntegrationFlowContext` bean, `newFlow` is a validly built Java DSL flow, and imports must be added. When destroying a flow, beans/channels shared with other flows are not necessarily removed; tests must not assert all dependencies vanish if still in use.

### What to assert

| Moment | Graph test | Behavior/observation test |
| --- | --- | --- |
| Before registration | New flow nodes do not exist yet | No new consumer |
| After registration + `rebuild()` | Created nodes/links appear | Endpoint may not be running yet due to `autoStartup=false` |
| After `start()` | Nodes still exist | Messages actually process; observations appear |
| After `stop()` | Nodes may remain in the graph | New messages are not processed by the stopped endpoint |
| After `destroy()` + `rebuild()` | Flow-owned nodes vanish | Old flow's subscriptions/side effects are gone |

**Stop is not destroy**, and a node existing in the graph does not prove the endpoint is running. `IntegrationGraphServer` provides a callback to add properties—allowing you to attach `SmartLifecycle.isRunning()` for diagnostics—yet **never assume every node has a `"running"` property** unless configured.

## 14. Adding lifecycle properties to the graph for testing

`IntegrationGraphServer.setAdditionalPropertiesCallback(...)` lets you add metadata from a `NamedComponent` to its node. For example:

~~~java
@Bean
IntegrationGraphServer integrationGraphServer() {
    IntegrationGraphServer server = new IntegrationGraphServer();

    server.setAdditionalPropertiesCallback(component -> {
        if (component instanceof SmartLifecycle lifecycle) {
            return Map.of(
                "running", lifecycle.isRunning(),
                "autoStartup", lifecycle.isAutoStartup());
        }

        return Map.of();
    });

    return server;
}
~~~

Import `org.springframework.context.SmartLifecycle` and `java.util.Map`. This observes state exposed through the graph rather than mutating lifecycle itself. An application may require admin privileges to call `start/stop`, while the graph only displays it.

Test:

~~~java
IntegrationNode endpoint = graphServer.getGraph().getNodes()
        .stream()
        .filter(node -> "orderPollingEndpoint".equals(node.getName()))
        .findFirst()
        .orElseThrow();

assertEquals(Boolean.TRUE,
        endpoint.getProperties().get("running"));
~~~

**Caching note:** the graph may cache nodes/metadata; `getGraph()` keeps a topology cache, though docs note certain stats in the graph can be dynamic. With custom property callbacks, to be sure after structural/lifecycle changes, call `rebuild()` and verify real behavior. Do not assume every custom property refreshes live under the same rules.

## 15. Testing Message History alongside observations

Message History and Micrometer Observation answer two different questions:

| Mechanism | Trail recorded | Limitations |
| --- | --- | --- |
| `MessageHistory` | Tracked components traversed | Header can grow long; does not prove commit |
| `Observation` | An operation's start/stop/error, timers/spans per conventions | Does not automatically store full path as a history header |
| `IntegrationGraphServer` | Configured topology | Does not tell which branch a specific message took |
| Logs/traces | Context and incident progression | Requires proper propagation/retention |

You can enable `@EnableMessageHistory` in tests and inspect:

~~~java
Message<?> message = output.receive(1_000);

MessageHistory history = MessageHistory.read(message);
assertNotNull(history);

boolean passedThroughInput = history.stream()
    .anyMatch(properties ->
        "graphInput".equals(properties.getProperty(
            MessageHistory.NAME_PROPERTY)));

assertTrue(passedThroughInput);
~~~

This applies when `graphInput` is in the tracked component set and the output message retains the history header. Import `org.springframework.integration.history.MessageHistory` and configure `@EnableMessageHistory` with real component names. **Never hard-code entry counts**: hop count depends on the framework, handlers, and tracking patterns.

Note that since Spring Integration 6.3, Message History uses an append-only/clone approach on fan-out. Custom splitter/router tests should verify two branches' histories **do not mix** when each branch continues through different components.

## 16. Testing metrics via SimpleMeterRegistry: don't confuse it with TestObservationRegistry

`TestObservationRegistry` records observation lifecycles. If your goal is asserting **timers/counts**, you need a `MeterRegistry` and an `ObservationHandler` that converts observations into meters.

Basic Micrometer example:

~~~java
SimpleMeterRegistry meterRegistry = new SimpleMeterRegistry();
ObservationRegistry observationRegistry = ObservationRegistry.create();

observationRegistry.observationConfig()
    .observationHandler(
        new DefaultMeterObservationHandler(meterRegistry));

Observation.createNotStarted("demo.operation", observationRegistry)
    .lowCardinalityKeyValue("component", "test")
    .observe(() -> { });

Timer timer = meterRegistry.find("demo.operation").timer();

assertNotNull(timer);
assertEquals(1L, timer.count());
~~~

Import `io.micrometer.core.instrument.simple.SimpleMeterRegistry`, `io.micrometer.core.instrument.Timer`, `io.micrometer.observation.Observation`, `io.micrometer.observation.ObservationRegistry`, `io.micrometer.core.instrument.observation.DefaultMeterObservationHandler`, and JUnit assertions. Requires compatible `micrometer-core`/`micrometer-observation` dependencies.

**Key requirement:** the meter handler must be registered. Merely calling `ObservationRegistry.create()` without a handler does **not** automatically produce timers on observation start/stop.

Spring Integration also had an earlier metrics captor mechanism. When an `ObservationRegistry` is provided, `IntegrationManagement` prioritizes observation and may bypass a separate `MetricsCaptor`. Do not assert the same metric is emitted by both paths without understanding your version and management configuration.

## 17. Error paths: asserting exceptions, ErrorMessages, and hooks at the right boundary

Three common error patterns:

| Where the error happens | How it surfaces | What to test? |
| --- | --- | --- |
| `DirectChannel`/synchronous handler | Exception reaches `send()` if not swallowed | `assertThrows`, resource rollback |
| Poller/`ExecutorChannel` | Worker/poller error handler may publish `ErrorMessage` | Bounded await on error channel, original/failed message |
| Reactive publisher | `onError` terminal signal | `StepVerifier` or subscriber; no `ErrorMessage` by default |

Synchronous exception example:

~~~java
RuntimeException thrown = assertThrows(
        RuntimeException.class,
        () -> input.send(MessageBuilder
                .withPayload("force-error")
                .build()));

assertNotNull(thrown);
~~~

This assertion assumes a handler **configured to throw** when payload `"force-error"` arrives. It does not apply directly to section 9's flow test because the transformer there simply uppercases strings.

### Asserting ErrorMessage on an error channel

~~~java
Message<?> error = errors.receive(2_000);
assertNotNull(error);
assertInstanceOf(ErrorMessage.class, error);

Throwable cause = ((ErrorMessage) error).getPayload();
assertNotNull(cause);
~~~

`errors` must be a **pollable error channel** to which the adapter/poller/worker is actually configured to send errors. Never expect the global `errorChannel` to receive synchronous exceptions from a `DirectChannel` without an error-publishing boundary.

### Observation error hook

Do not assume `TestObservationRegistry` increments a counter named `errors` for every exception. To test errors, check whether the component's instrumentation calls `Observation.error(ex)`, whether recovery handles the exception before the observation closes, and your version's naming/tag conventions. In an integration test, when observing the right event:

~~~java
assertTrue(hook.errors() > 0);
~~~

This assertion is only valid when `hook` is registered on the same `ObservationRegistry` and the component/adapter under test actually reports errors to the observation. If it fails, investigate the **observation boundary** before trying to fix it with longer sleeps.

## 18. Async: testing without fixed sleeps

### Common mistake

~~~java
input.send(message);
Thread.sleep(2_000);
assertEquals(1, counter.get());
~~~

On fast machines it wastes time; on slow CI it can still flake. Moreover, a handler finishing after 2 seconds before transaction/ack commits also invalidates the assertion.

### Using QueueChannel receive timeout

~~~java
Message<?> result = results.receive(2_000);
assertNotNull(result, "Message not processed within bounded wait");
~~~

With `QueueChannel`, this is the simplest way to wait until a **message actually arrives**. Tests should use finite timeouts and clear diagnostics on timeout.

### Using Awaitility or polling conditions

If results are written to an `AtomicInteger`/DB instead of a queue:

~~~java
await()
    .atMost(Duration.ofSeconds(5))
    .untilAsserted(() ->
        assertEquals(3, processedCounter.get()));
~~~

Requires the Awaitility test dependency and importing `org.awaitility.Awaitility.await` and `java.time.Duration`. Check durable business state (DB rows, idempotency markers) rather than merely waiting for a log line.

### When to enable a mock clock?

In Reactor, `StepVerifier.withVirtualTime` can test retries/backoffs on a virtual scheduler. However, Spring Integration pollers use their own triggers/task schedulers; **do not assume** Reactor virtual time controls real pollers. For pollers, consider deterministic triggers, mock sources, or bounded waits in a controlled scheduler/integration test.

## 19. Spring Integration testing support and mock endpoints

The `spring-integration-test` and `spring-integration-test-support` artifacts provide utilities:

- `MockIntegrationContext` to substitute message sources/handlers inside configured endpoints;
- `MockIntegration` to build stub/mock `MessageSource`, `MessageHandler`, and `MessageChannel`;
- Helpers to test message flows without hitting external dependencies.

Structural example (requires a configured test context):

~~~java
mockIntegrationContext.substituteMessageHandlerFor(
    "remoteRequestEndpoint",
    MockIntegration.mockMessageHandler()
        .handleNext(message -> captured.add(message)));
~~~

**This is an illustrative snippet, not a standalone test.** Check overload signatures and Mockito/static imports matching your test module version. Tests should verify the target's **endpoint ID** rather than guessing names.

Do not replace a real handler with a mock and still claim you tested the **real handler's** instrumentation: a mock that is not an `AbstractMessageHandler` may not emit the same observations; when verifying topology/management, test at least one real path.

### Comparing two test styles

| Test type | Advantage | When to use |
| --- | --- | --- |
| Handler/service unit test | Fast, verifies business rules | Many edge cases |
| Spring Integration context test with stub adapter | Verifies channels, advice, graph, observations | Wiring and policies |
| Embedded/real broker, DB (Testcontainers) | Verifies acks, transactions, stores, redelivery | End-to-end reliability |
| Deployment smoke test with Actuator graph | Verifies topology of real running artifact | Post-rollout |
| Load/chaos test | Verifies executors, pollers, retry storms | Non-functional/SLAs |

**A graph-only test cannot replace a business integration test**, and a handler-only unit test does not prove real topology.

## 20. Pollers, executors, and observation hooks

### Poller test

With a `QueueChannel`/message source + `PollingConsumer`, assert:

1. The endpoint reports `isRunning()` accurately.
2. Real messages are polled and reach the handler.
3. After `stop()`, no new messages are polled (once in-flight drains per contract).
4. Metrics/observations appear on components instrumented in your app version.
5. When the handler throws, the error flow runs and the source/store rolls back/redelivers if designed to.

**Version caveat:** Spring Integration 6.5 added observations for `SourcePollingChannelAdapter`; not every poller type has identical observation hooks across all versions. To measure poller duration, measure on the specific instrumented component or via a reliable custom test hook.

### ExecutorChannel test

~~~mermaid
sequenceDiagram
    participant Test as Test thread
    participant Ex as ExecutorChannel
    participant W as Worker thread
    participant Reg as ObservationRegistry
    Test->>Ex: send(Message)
    Ex-->>Test: handoff accepted
    Ex->>W: deliver
    W->>Reg: Observation start
    W->>W: handler process
    W->>Reg: Observation stop/error
    W-->>Test: result through QueueChannel / DB marker
~~~

Do not assert observations immediately after `send()` if the handler runs on another worker: the observation may not have finished yet. Wait for an **end-to-end signal** first (reply, DB state, bounded latch), then check the hook. If the observation handler's `onStop` runs after output is enqueued, a separate bounded wait for sample completion may still be needed.

### Context propagation

`Observation` scopes can rely on ThreadLocals and tracing context. Across an executor, threads do not automatically inherit every caller context; configure an appropriate task decorator/context propagation mechanism. Tests must not check only the observation name and assume parent-child trace linking worked.

Put `traceId` in message headers for correlation and verify trace propagation on the specific adapter. With Reactor, use `Reactor Context` and your stack's tracing integration rather than copying ThreadLocals manually.

## 21. Retries, transactions, message stores, and correlation

**An observability hook firing does not prove the business transaction succeeded.**

Handler example:

~~~text
Message received
  -> Observation start
  -> JDBC INSERT
  -> handler throws
  -> Transaction rollback
  -> Observation error/stop
  -> broker redelivery (if adapter configured)
~~~

Tests should assert at each layer:

| What must be proven | Assertion to use |
| --- | --- |
| Endpoint/flow wired properly | Graph nodes + links |
| Handler was invoked | Output queue or spy counter |
| Retries ran exact attempt count | Retry callback/counter, not inferred from graph |
| DB rollback | Query rows after transaction finishes |
| Broker redelivery | Ack/nack, deliveries in broker test |
| Correlation preserved | `eventId`, `correlationId`, sequence headers |
| ErrorMessage accurate | Error channel receives original/failed message |
| Observability hook works | Registry recorded start/stop/error |
| Message persisted safely | Readback from message store after restart |

Retry advice can call a handler multiple times yet **not** create as many observation samples as attempts if the observation sits outside the retry scope. For instance, an endpoint-level observation may record one sample for the whole retry sequence while the handler ran three times. To measure attempts, instrument inside the retry callback or handler invocation.

### Message store tests

With a durable `QueueChannel` or `MessageGroupStore`, the graph only shows that components **exist and connect**. It does not prove bytes in the store deserialize after a restart, correlation groups release properly, or retries are idempotent. Write dedicated persistence tests and verify serializer/versioning compatibility.

### LockRegistry and performance

An aggregator can slow down due to `LockRegistry` contention on `correlationId`. A valid graph and recorded observation samples still do not tell you where a critical section is blocked. Use lock wait/hold metrics, group size/age, database waits, and message history to diagnose.

## 22. Testing custom observation conventions, tags, and privacy

Spring Integration allows customizing `ObservationConvention` on supported components, such as `AbstractMessageHandler.setObservationConvention(...)` with an appropriate `MessageReceiverObservationConvention`.

Tests should verify:

- **Low cardinality**: endpoint name/operation type, `success/failure` status; never put unique event IDs into tags.
- **High cardinality**: put `eventId`/`traceId` into trace attributes when appropriate, never directly into time-series metrics.
- Never log payloads, tokens, personal information, or secret endpoint URLs into telemetry.
- Error sampling and failure tags must not generate millions of unique label combinations.

Assertion example for a custom observation:

~~~java
TestObservationRegistryAssert.assertThat(registry)
    .hasObservationWithNameEqualTo("order.validate")
    .that()
    .hasLowCardinalityKeyValue("operation", "validate")
    .hasBeenStarted()
    .hasBeenStopped();
~~~

Do not hard-code `order.validate` as a Spring Integration default name; it is an **application-custom observation**. For framework-managed observations, consult the names/conventions published for your exact version.

## 23. Testing dynamic graph refreshes and topology drift

A subtle regression to catch is **drift**: the same flow name with altered bean wiring after a refactor or starter upgrade.

Helpful techniques:

1. Define a set of **invariants**: critical input/output/route/error channels must exist.
2. Snapshot **selectively**: component names/types and relevant links, not every default node.
3. Run tests under a staging profile matching production.
4. Register and destroy dynamic flows, calling `rebuild()` after each change.
5. Verify no orphan handlers/subscribers remain after `destroy()`.
6. When the graph diff changes, review whether it is an intentional change or a regression.
7. In deployment smoke tests, compare the graph **after context refresh** against the expected contract and secure Actuator exposure.

### Example normalizing a graph for comparison

~~~java
Set<String> channelNames = graph.getNodes().stream()
    .filter(node -> node.getComponentType() != null)
    .map(IntegrationNode::getName)
    .collect(Collectors.toSet());

assertTrue(channelNames.containsAll(
        Set.of("graphInput", "graphOutput")));
~~~

This only **asserts node names**, not links; combine it with section 5's helper. Do not hard-code `Graph.getContentDescriptor().get("providerVersion")` as a fixed expected value if tests run across patch versions.

## 24. Common test failures and how to diagnose them

| Symptom | Possible cause | Diagnostic action |
| --- | --- | --- |
| Graph shows only default nodes | Endpoints not registered / context not refreshed | Check `@EnableIntegration`, bean config, graph server |
| Node exists with no input link | Wrong input channel or inactive bean | Inspect `Graph.getLinks()` by ID |
| Link missing after registering new flow | Reading cached graph | Call `rebuild()` |
| Link test breaks upgrading SI 6.x to 7.1 | `LinkNode` changed from class getters to record accessors | Use version-matching API |
| Behavior test passes yet graph test fails | Handler sends to dynamic channel not shown in static graph | Distinguish dynamic routing from declared links |
| `isObserved()` is false | Missing registry/pattern or uninstrumented node | Check `@EnableIntegrationManagement` and registry bean |
| `TestObservationRegistry` is empty | No handler, component never ran, pattern didn't match | Send message through real managed channel |
| Micrometer meter never appears | Only `ObservationRegistry` present, missing meter handler | Register `DefaultMeterObservationHandler` |
| Handler ran, sample still not stopped | Async task incomplete or asserted too early | Wait on end-to-end condition, bounded await |
| `ErrorMessage` never reaches channel | Synchronous exception lacked error publishing boundary | Check worker/poller/adapter error handler |
| `isRunning()` true yet no output | Empty poller, handler failed, full queue, wrong route | Check queue depth, retry/error flow, and metrics |
| Flaky test on CI | Fixed sleep, shared static state, uncleaned thread pools | `receive(timeout)`, per-test context, Awaitility |
| Test counts grow unexpectedly | `TestObservationRegistry` not cleared or multiple operations sampled | Reset before test, filter by name/tags |
| Trace ID present without parent-child link | Broken context propagation across executor/broker | Assert span relationships with tracer test backend |
| Request ID used as metric tag | High cardinality, rising monitoring costs | Move event ID to traces/logs |
| Stopped flow still shows nodes in graph | `stop()` is not `destroy()` | Test lifecycle separately from structural removal |

### Layer-by-layer debugging checklist

1. **Context:** test profile, dependency versions, `@EnableIntegration`, component bean names.
2. **Graph:** `getGraph()` vs. `rebuild()`, node names, node IDs, typed links.
3. **Message:** input send accepted, output/error queue, payload, headers, correlation.
4. **Runtime:** running state, poller/executor, thread, async completion.
5. **Observation:** registry bean, patterns, custom handlers, sample lifecycle.
6. **Metrics/tracing:** handler/exporter, names/tags, sampling/context propagation.
7. **Durable side effects:** transactions, broker ack/requeue, message store/DB.
8. **Cleanup:** no leaked executor tasks, subscriptions, or dynamic registrations.

## 25. Hands-on exercises

1. **Basic graph:** build `graphInput → transformer → graphOutput`, asserting both channel nodes and both typed links exist.
2. **Negative graph test:** intentionally point the transformer `outputChannel` to another channel and watch the test fail at the output link check.
3. **Observation patterns:** replace `observationPatterns = "*"` with a pattern selecting only one channel; compare `IntegrationNode.isObserved()` and `TestObservationRegistry`.
4. **Missing registry:** remove the `TestObservationRegistry` bean; verify whether any observations are actually captured.
5. **Meter handler:** add `SimpleMeterRegistry` and `DefaultMeterObservationHandler`, and assert timer counts after sending a message.
6. **Custom hook:** install `CountingObservationHandler`, create a custom observation, and verify starts=stops=1, errors=0.
7. **Error hook:** make the handler throw; confirm `assertThrows` on `DirectChannel` without assuming global `errorChannel` gets a message.
8. **ErrorMessage:** switch to a poller or executor with a configured error channel, and assert `ErrorMessage` via `receive(timeout)`.
9. **Dynamic flow:** register a flow with `IntegrationFlowContext`, and test `rebuild()` after register and destroy.
10. **Message History:** enable `@EnableMessageHistory` with a selective pattern and compare hops on the output against graph nodes.
11. **Executor:** move the handler behind an `ExecutorChannel`, wait using a queue/latch, and avoid fixed `Thread.sleep`.
12. **Poller:** test start/stop lifecycle and `QueueChannel` backlog; assert observations on components instrumented in your version.
13. **Retry:** configure the handler to fail twice then succeed; verify attempts with a counter rather than using observation counts as a proxy.
14. **Transaction:** fail after a JDBC `INSERT`, verifying row rollback and observation error/stop independently.
15. **Correlation:** splitter/aggregator with `correlationId` and `sequenceNumber`, testing output + group state + graph.
16. **Privacy:** add a unique `eventId` and verify it is not used as a low-cardinality metric tag.
17. **Observability outage:** simulate an unavailable collector and ensure the business flow does not break because of an external telemetry hook.
18. **Version update:** migrate the graph test from SI 6.x to 7.1, updating `LinkNode` accessors while confirming the topology contract stays intact.

### Self-check questions

- Why is checking `graph.getNodes().size() > 0` not enough?
- How do `getGraph()` and `rebuild()` differ when registering dynamic flows?
- Why should numeric node IDs never be hard-coded?
- How do `LinkNode.Type.input`, `output`, `error`, `route`, and `discard` differ?
- What distinct roles do `@EnableIntegrationManagement(observationPatterns = "*")` and `ObservationRegistry` play?
- Why does a `TestObservationRegistry` containing an observation not prove a Prometheus timer was exported?
- Does `isObserved()` prove an observation started/stopped?
- When using `ExecutorChannel`, which condition should you wait for before asserting hooks?
- Why does an `ErrorMessage` not appear automatically when a `DirectChannel` handler throws an exception?
- Does a handler retried three times necessarily produce three observation samples?
- Why does message history not replace distributed tracing or transaction tests?
- Which invariants should be tested when rolling out a dynamic flow?

## 26. Checklist before moving to STEP 6 QA

- Test content separates **graph assertions**, **behavior assertions**, and **observation assertions**.
- Endpoint/channel IDs are explicitly stabilized, avoiding matching auto-generated names unnecessarily.
- Graph tests inspect typed links, not just node counts.
- Graph tests after structural changes call `rebuild()`.
- Target API is locked: main examples use Spring Integration 6.5.x; 7.1 updates `LinkNode` getters.
- `ObservationRegistry` bean, `@EnableIntegrationManagement`, and `observationPatterns` are properly configured.
- `TestObservationRegistry` is reset between tests; assertions verify observations started and stopped.
- Having an `ObservationRegistry` is not mistaken for having a metrics/traces exporter.
- Finite timeouts are used for async/pollers; no fixed sleeps.
- Retry attempts, transaction rollbacks, broker acks, and correlation are verified against real state.
- `eventId`/`orderId` are never placed into low-cardinality metric tags.
- Simulated failures test error-publishing boundaries and recovery flows.
- Dynamic flow tests clean up registrations and executor workers afterward.
- Examples/versions are aligned when integrated into a project; in STEP 4, Gradle/Content QA has not run yet.

## 27. Official references

- [Spring Integration — Integration Graph](https://docs.spring.io/spring-integration/reference/graph.html): graph structure, nodes, typed links, cache/rebuild.
- [Spring Integration API — IntegrationGraphServer 6.5](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/graph/IntegrationGraphServer.html): `getGraph()`, `rebuild()`, properties callback.
- [Spring Integration API — Graph 6.5](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/graph/Graph.html): `getContentDescriptor()`, `getNodes()`, `getLinks()`.
- [Spring Integration API — IntegrationNode 6.5](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/graph/IntegrationNode.html): `getName()`, `getNodeId()`, `isObserved()`.
- [Spring Integration API — LinkNode 6.5](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/graph/LinkNode.html): `getFrom()`, `getTo()`, `getType()`.
- [Spring Integration API — LinkNode 7.1](https://docs.spring.io/spring-integration/api/org/springframework/integration/graph/LinkNode.html): record accessors `from()`, `to()`, `type()`.
- [Spring Integration — Metrics and Management](https://docs.spring.io/spring-integration/reference/metrics.html): `ObservationRegistry`, management patterns, convention names.
- [Spring Integration — Testing Support](https://docs.spring.io/spring-integration/reference/testing.html): `MockIntegrationContext`, `MockIntegration`, endpoint testing.
- [Spring Integration — Java DSL Runtime Flows](https://docs.spring.io/spring-integration/reference/dsl/java-runtime-flows.html): dynamic flow registration and destroy.
- [Micrometer — Observation Testing](https://docs.micrometer.io/micrometer/reference/observation/testing.html): `TestObservationRegistry` and lifecycle assertions.
- [Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html): `ObservationHandler`, conventions, cardinality.
- [Spring Framework — Observability](https://docs.spring.io/spring-framework/reference/integration/observability.html): observations and metrics/tracing.
- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): `ErrorMessage` and error publishing boundaries.
- [Spring Integration — Message History](https://docs.spring.io/spring-integration/reference/message-history.html): history header and tracked components.
