# Control Bus and Message-Driven Lifecycle Control in Spring Integration Runtime

## Lesson Objectives

In **SPRING_INTEGRATION_RUNTIME**, a system can have dozens of IntegrationFlows, inbound adapters, gateways, pollers, consumers, channels, and executors. During data source maintenance or when downstream is overloaded, operators may need to **pause message intake**, inspect endpoint status, and **perform a controlled restart** without restarting the entire JVM.

**Control Bus** is an Enterprise Integration Pattern (EIP) in Spring Integration that allows sending **control messages** through a message channel. The message payload is processed as a **management expression**; the expression can invoke methods on Spring beans, such as **start()**, **stop()**, or **isRunning()** methods of endpoints that support lifecycle management.

After this lesson, you will be able to:

- Explain how the Control Bus differs from channels that carry business data.
- Send **start/stop** commands and query **isRunning** for endpoints using explicit bean names.
- Distinguish **Lifecycle**, **SmartLifecycle**, **endpoint**, **IntegrationFlow**, and dynamic flow registration.
- Configure the Control Bus using Spring Integration XML and Java DSL, and deliberately verify replies/errors.
- Understand the impact of lifecycle control on **pollers, message-driven adapters, executors, transactions, retries, MessageStores, and in-flight messages**.
- Design a secure management path: **prevent untrusted callers from submitting arbitrary SpEL expressions**.
- Test pausing/resuming a flow, verify the actual state, and prepare an operational runbook.

> **Operational Principle:** The Control Bus helps dispatch **control commands** to beans/endpoints. It does not automatically provide distributed transactions, automatically drain queues, guarantee revocation of side effects that have already occurred, or guarantee the business outcome of in-flight messages.

## 1. Control Plane vs. Data Plane in Message Flows

Let's distinguish two types of messages:

| Characteristic | Business message (data plane) | Control message (control plane) |
| --- | --- | --- |
| Example payload | OrderCreated, PaymentCommand, InventoryResult | start/stop/isRunning expressions |
| Goal | Execute business functionality | Change or observe runtime state |
| Typical channel | ordersInput, paymentRequests | controlBus |
| Sender | Services, adapters, brokers, business gateways | Authorized administrative components |
| Effect | Write to DB, emit events, call APIs | Enable/disable endpoints, inspect lifecycle |
| Risk | Duplicates, lost messages, transactions, correlation | Stopping the wrong flow, executing dangerous expressions, losing lifecycle control |

~~~mermaid
flowchart LR
    SRC["File / Broker / HTTP source"] --> IN["ordersInput"]
    IN --> POLL["Order processor"]
    POLL --> OUT["Downstream service"]

    ADMIN["Admin service (authenticated)"] --> CB["controlBus channel"]
    CB --> HANDLER["Control Bus endpoint"]
    HANDLER -. "start / stop / inspect" .-> SRC
~~~

The Control Bus is **not** a channel that automatically blocks all business messages. It is an **endpoint that processes commands**: commands only affect the beans/methods targeted by the expression and components that are actually capable of changing lifecycle state.

**Typical use case:** The operations team notices that an inbound file adapter is generating backlog faster than downstream can process it. They stop the **source generating new messages**, process the existing backlog, and then start it again once the system stabilizes.

## 2. EIP Mechanism of the Spring Integration Control Bus

A Control Bus receives a message, evaluates **the payload as a Spring Expression Language (SpEL) expression** within the appropriate application context, and then invokes the corresponding method.

~~~text
Admin command
  payload = "@orderInboundEndpoint.stop()"
       |
       v
MessageChannel: controlBus
       |
       v
Control Bus handler
       |
       v
SpEL: look up bean "orderInboundEndpoint", invoke stop()
       |
       v
Lifecycle state of the bean changes (if supported by the bean)
~~~

Three common expressions:

~~~text
@orderInboundEndpoint.stop()
@orderInboundEndpoint.start()
@orderInboundEndpoint.isRunning()
~~~

The **@** symbol in SpEL is used to reference a Spring bean by name. If a bean name contains dots, hyphens, or characters not convenient to write as an identifier, you can use quoted bean name syntax:

~~~text
@'orders.inbound.endpoint'.stop()
@'orders.inbound.endpoint'.isRunning()
~~~

These are **example expressions**. The bean must **exist in the same ApplicationContext/BeanFactory accessible to the Control Bus**, and it must have the invoked method; otherwise, expression evaluation will raise an error.

### The Control Bus Can Do More Than start/stop

Technically, SpEL can invoke matching public methods on beans that the evaluation context permits access to. Therefore:

- **isRunning()** is commonly used to observe state.
- **start()/stop()** are commonly used for beans implementing Lifecycle/SmartLifecycle.
- Other administrative setters/methods can be invoked if exposed.

**This is also a significant attack surface.** You should not treat the Control Bus as a general text API for arbitrary clients. Never forward raw payloads from HTTP requests or public brokers directly to the Control Bus channel.

### Return Values and Execution Outcomes

A query expression such as **isRunning()** can return a Boolean. A command such as **start()/stop()** typically has a void return type, so it may not produce a reply with a useful payload. When you want to confirm state after a command, **query isRunning() again** or read the bean directly through a management service, combined with checking other runtime criteria.

A `true` return value from **MessageChannel.send(...)** means the message was sent/accepted by the channel according to the channel's contract; **it does not by default prove** that the entire flow has stopped/drained successfully. This is especially important if the control channel uses an executor or the lifecycle implementation executes commands asynchronously.

## 3. Lifecycle in Spring: Lifecycle, SmartLifecycle, and Endpoints

Controlled beans typically support one of the following contracts:

~~~java
public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}
~~~

**SmartLifecycle** extends Lifecycle to add support for auto-startup semantics and lifecycle ordering via phases, along with callback-based stopping:

~~~java
public interface SmartLifecycle extends Lifecycle, Phased {
    boolean isAutoStartup();
    void stop(Runnable callback);
    // Additional provided/inherited methods depend on the version.
}
~~~

In Spring Integration, many **endpoints** (e.g., polling consumers, message-driven consumers, inbound adapters) support lifecycle management. However, **you must not assume that every IntegrationFlow bean, transformer, message channel, or arbitrary service has start()/stop()**.

| Target | What the Control Bus can affect | What to verify |
| --- | --- | --- |
| **Polling endpoint** | Stop/start polling tasks or the appropriate consumer | Endpoint bean ID, poll schedule, in-flight message count |
| **Message-driven inbound adapter** | Stop/start receiving from the source per the adapter's lifecycle | Broker/adapter ack/redelivery, in-flight messages |
| **Event-driven consumer endpoint** | Change lifecycle if the endpoint implementation supports it | Whether subscribers are detached from the channel, whether producers get send errors |
| **IntegrationFlow** | Depends on implementation/registration; do not assume every flow bean is a Lifecycle | May need to control constituent endpoints or flow registration |
| **MessageChannel** | Primarily routes/transports messages | Does not have start/stop lifecycle by default |
| **Executor/TaskScheduler** | Has its own shutdown/management lifecycle | Stopping the source does not automatically cancel queued tasks |
| **Spring Boot application** | Has application-wide lifecycle | Stopping an endpoint does not shut down the entire ApplicationContext |

**Do not use the wrong bean name:** The flow ID, endpoint ID, channel ID, and handler ID can all differ. The SpEL command must reference **the bean that actually provides start()/stop()**. In Java DSL, set an **explicit endpoint ID** for easier control and troubleshooting. In XML, use consistent IDs for adapters/endpoints that need management.

### What Is a SmartLifecycle Phase?

When the application context starts/stops in a coordinated manner, **phase** can be used to determine the startup/shutdown order among SmartLifecycle beans. This is a Spring context lifecycle processor mechanism, **not a transaction across all endpoints**.

A series of individual Control Bus commands **does not automatically follow a global phase runbook** like a full context shutdown. If multiple endpoints must be stopped in a specific sequence, a management service must execute and observe each step.

## 4. Configuring with XML

An XML example declaring a dedicated command channel and a Control Bus endpoint:

~~~xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:int="http://www.springframework.org/schema/integration"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
         http://www.springframework.org/schema/beans
         https://www.springframework.org/schema/beans/spring-beans.xsd
         http://www.springframework.org/schema/integration
         https://www.springframework.org/schema/integration/spring-integration.xsd">

    <int:channel id="controlBus"/>

    <int:control-bus input-channel="controlBus"/>
</beans>
~~~

When the **controlBus** channel is an appropriate synchronous point-to-point channel, commands are processed on the message-sending path. For a Control Bus endpoint, avoid having multiple different subscribers receiving commands with side effects without a clear routing strategy.

**This is only the control plane configuration.** The flows to be controlled and their bean IDs are declared separately. A real system must also configure the **admin command producer**, authentication/authorization, and observability.

## 5. Java DSL: Creating a Dedicated Control Bus for Management

With Spring Integration Java DSL, you can declare:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
class ControlBusConfiguration {

    @Bean
    MessageChannel controlBus() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow controlBusFlow() {
        return IntegrationFlow.from("controlBus")
                .controlBus()
                .get();
    }
}
~~~

What this means:

1. **DirectChannel** allows commands to run synchronously and makes errors easy to observe on the sending thread; stop/start execution on the target bean still follows the bean's lifecycle implementation.
2. **controlBusFlow** creates a Control Bus consumer that receives messages from the named channel.
3. **Channel name** and **target endpoint name** are two separate things. `controlBus` receives commands, while `orderInboundEndpoint` is a bean with a lifecycle accessed by SpEL.
4. This is an illustrative configuration; a real application must include **Spring Integration core/DSL dependencies**, component scanning, business flows, and measures to restrict permission to send control messages.

### Setting an Explicit Endpoint ID

Suppose a polling endpoint is created via Java DSL. The key point is that the ID belongs to the **endpoint**, not just the channel:

~~~java
// Java DSL pseudocode illustrating the meaning of endpoint ID:
IntegrationFlow.from(
        myMessageSource,
        sourceSpec -> sourceSpec
                .id("ordersPollingEndpoint")
                .poller(pollerSpec))
        .channel("ordersInput")
        .get();
~~~

In an actual implementation, how **MessageSource**, poller, and method overloads are constructed depends on the component and version. The purpose of this example is to show that **ordersPollingEndpoint** must be the ID of the created endpoint that holds the lifecycle. Verify the actual bean ID in the context before sending commands:

~~~text
@ordersPollingEndpoint.stop()
@ordersPollingEndpoint.start()
@ordersPollingEndpoint.isRunning()
~~~

Do not guess the ID from the **@Bean IntegrationFlow** method name or configuration package name. Setting explicit IDs, verifying them in integration tests, and documenting them in the runbook reduces the risk of stopping the wrong target.

## 6. Sending Control Messages in Java

Management code can send commands to the `controlBus` channel using Spring Messaging:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
class InternalControlBusSender {
    private final MessageChannel controlBus;

    InternalControlBusSender(
            @Qualifier("controlBus") MessageChannel controlBus) {
        this.controlBus = controlBus;
    }

    void stopOrdersPolling() {
        boolean sent = controlBus.send(
                MessageBuilder.withPayload(
                        "@ordersPollingEndpoint.stop()")
                        .build());
        if (!sent) {
            throw new IllegalStateException(
                    "Control Bus rejected stop command");
        }
    }

    void startOrdersPolling() {
        boolean sent = controlBus.send(
                MessageBuilder.withPayload(
                        "@ordersPollingEndpoint.start()")
                        .build());
        if (!sent) {
            throw new IllegalStateException(
                    "Control Bus rejected start command");
        }
    }
}
~~~

**Warning about this example:** The commands here are **fixed strings in trusted code**, not assembled from arbitrary user input. You must verify that the endpoint bean exists, received the command, and reached the expected state; the `send` result alone is not sufficient to conclude the operation succeeded in every topology.

### Querying State and Replies

An **isRunning()** expression returns a Boolean, unlike stop()/start() commands which typically return void. In an appropriate request-reply flow, the response can be returned via **replyChannel**:

~~~java
import org.springframework.integration.core.MessagingTemplate;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

MessagingTemplate template = new MessagingTemplate();
Message<?> reply = template.sendAndReceive(
        controlBus,
        MessageBuilder.withPayload(
                "@ordersPollingEndpoint.isRunning()").build());

if (reply != null) {
    Boolean running = (Boolean) reply.getPayload();
    // Use running to display administrative status.
}
~~~

In this example, **controlBus** is a synchronous channel with a Control Bus consumer and the target bean has `isRunning()`. If `reply` is null or times out, check **timeouts, replyChannel, expression evaluation errors, and consumer status**; do not interpret null as false.

For internal administrative code running in the same ApplicationContext, an alternative is to inject the bean supporting **Lifecycle** or look it up directly via BeanFactory and call **isRunning()**. The Control Bus is especially useful when you want to keep the **management interface as a message flow**, rather than being mandatory for every in-process lifecycle operation.

## 7. When stop() Is Sent: What Does the System Actually Stop?

Consider an inbound file adapter with a polling endpoint:

~~~mermaid
flowchart LR
    FS["File directory"] --> P["ordersPollingEndpoint"]
    P --> Q["ordersInput / QueueChannel"]
    Q --> H["Order handler"]
    H --> DB[("Business DB")]
    CB["Control Bus"] -. "stop()" .-> P
~~~

A **stop()** command targeting the polling endpoint typically stops **new poll cycles** initiated by that endpoint. It **does not automatically**:

- Delete messages already in a QueueChannel or MessageStore.
- Roll back committed DB transactions.
- Revoke HTTP requests already sent to partners.
- Cancel tasks already sitting in an executor queue.
- Guarantee that in-flight messages have completed.
- Stop all other endpoints sending to that same channel.

**If you want to pause intake of new messages**, inspect **all inbound endpoints** feeding the processing pipeline, not just one adapter. If a broker consumer has its own ack mechanism, stopping may affect how in-flight messages are released/redelivered depending on the implementation.

### Stop and Drain Are Two Separate Operations

**Stop ingress** = stop accepting new messages at a source via lifecycle control.

**Drain backlog** = wait for or process in a controlled manner the messages already received/queued in a queue or executor.

**Stop consumers** = stop the endpoints reading from the backlog.

If you stop consumers before draining, the backlog may **never shrink**. If you only stop ingress while another producer is still sending to the channel, the backlog may continue to grow. Your runbook must decide the order based on the actual topology.

## 8. Runbook for Pausing and Resuming a Message Flow

Suppose an order-intake application has this topology:

~~~text
ordersPollingEndpoint
  → ordersInput
  → QueueChannel (MessageStore)
  → orderProcessingPoller
  → orderHandler
  → JDBC / outbound broker
~~~

The goal is to pause intake for a downstream upgrade without losing already-received orders.

### Phase A — Pause Ingress

1. Identify the **exact endpoint ID** representing the source to pause. Also record the **application instance** hosting the endpoint.
2. Ensure the source can be stopped without losing messages: review transactions, adapter acknowledgements, remote sources, and in-flight messages.
3. Send **@ordersPollingEndpoint.stop()** via `controlBus` on that instance.
4. Query **@ordersPollingEndpoint.isRunning()**; verify state according to the lifecycle contract.
5. Observe poll count/new messages: confirm the source is no longer generating unexpected backlog.

### Phase B — Drain Backlog

1. Keep **orderProcessingPoller** running to continue processing messages already in the queue.
2. Monitor **queue depth**, in-flight task count, active transactions, pending retries, and error counts.
3. Wait until predefined criteria are met, e.g., backlog reaches 0 **and** in-flight reaches 0, or a specific batch/checkpoint finishes.
4. If a message cannot complete, route it to a defined **recovery/DLQ/quarantine** mechanism rather than waiting indefinitely.
5. Only once those conditions are met should you stop downstream consumers if maintenance requires it.

### Phase C — Resume

1. Verify that DB, broker, message store, and downstream services are ready.
2. Start necessary consumers and processing endpoints **before reopening high-volume intake**, if appropriate for the topology.
3. Send **@ordersPollingEndpoint.start()** on the target instance.
4. Query status and verify that polls and messages are actually being processed.
5. Monitor backlog, retry rate, error channel, and latency until the flow stabilizes.

~~~mermaid
flowchart TD
    A["Verify permissions and target"] --> S["Stop ingress"]
    S --> V{"isRunning=false?<br/>Inbound rate drops?"}
    V -- "No" --> ERR["Investigate / do not proceed with maintenance"]
    V -- "Yes" --> D["Drain queued + in-flight work"]
    D --> Q{"Backlog/in-flight criteria met?"}
    Q -- "No" --> R["Monitor retries, errors, DLQ"]
    R --> D
    Q -- "Yes" --> M["Maintenance / deployment"]
    M --> C["Start consumer if needed"]
    C --> U["Start ingress"]
    U --> H["Verify health + traffic + errors"]
~~~

**Do not use a fixed sleep duration and assume the backlog has drained.** With pollers, executors, brokers, and HTTP calls, some in-progress work may no longer appear in queue depth. Measure **in-flight** work via metrics/application state or a purpose-built quiescence mechanism.

### Special Cases

| Case | What to check |
| --- | --- |
| **File inbound adapter** | Files currently being processed, filter/MetadataStore, and whether files will be re-polled after restart |
| **Broker inbound adapter** | Consumer closing behavior, ack/nack/offset handling, redelivery, and rebalancing |
| **Persistent QueueChannel** | Messages remaining in the store on stop, polling consumer transactions, resume capability |
| **ExecutorChannel** | Tasks already submitted to the executor but not yet run; whether the source has already acked |
| **Aggregator/resequencer** | Unreleased groups, group timeouts, cleanup, and late arrivals |
| **HTTP inbound gateway** | How stopping the endpoint affects new requests; load balancers and open requests |
| **Outbound adapter** | Work currently being sent with uncertain responses; idempotency on replay |

**There is no universal Control Bus command called "drain everything safely".** Message-based pause/resume actions are just one tool within an overall graceful operation and recovery strategy.

## 9. Impact on Transactions, Retries, and In-Flight Messages

A start/stop command changes **the endpoint's lifecycle**; it does not automatically alter the semantics of an active transaction.

### Poller Running a Transaction

~~~text
Poller thread:
  begin transaction
    receive message A
    handler update DB
    ...

Admin thread:
  @ordersPollingEndpoint.stop()
~~~

If a stop command arrives while the poller is processing A, the exact outcome depends on the implementation and timing. Do not assume stop **rolled back transaction A** or **waited for A to commit**. The transaction follows the transaction manager/advice configuration and actual execution progress.

**Safe operational criterion:** Track in-flight work and transaction outcomes separately; only declare "drained" when actual criteria are met, not solely by checking `isRunning=false`.

### RetryAdvice and errorChannel

Suppose a handler is retrying an HTTP call with backoff. Stopping an **inbound endpoint** does not necessarily cancel retries **already underway in the handler**. If an endpoint is stopped while a retry/executor queue is busy:

- The handler may complete, fail, or continue retrying according to the advice.
- An ErrorMessage may still be sent to **errorChannel** per endpoint behavior, even after the source has stopped.
- The recovery callback may decide to ACK/rollback per the source contract; the Control Bus does not redefine that policy.
- After resume, the source may **redeliver** unacked messages; business handlers must be idempotent.

**Avoid confusion:** A successfully sent stop command does not mean retries have stopped or all errors have been resolved. A subsequent start must not be treated as "retrying all failed messages"; retry/replay requires its own logic.

### Thread Boundaries

| Boundary | Notable behavior |
| --- | --- |
| **DirectChannel** | Handler runs synchronously on the sending thread; errors propagate back to the sender unless caught |
| **ExecutorChannel** | Workers run on different threads; sender transactions/lifecycle do not cover handed-off tasks by default |
| **QueueChannel + poller** | Controlled consumers can stop pulling new messages while data remains in the queue |
| **Broker** | Stopping a container/consumer may cause the broker to redeliver messages depending on ack/transaction settings |
| **Control Bus DirectChannel** | Control commands run on the sending thread; admin code should not be blocked by long business handlers |

The control channel should be isolated from queues/thread pools saturated by business traffic. If `controlBus` itself depends on an exhausted executor, the stop command meant to relieve load **may also fail to execute in time**.

## 10. Controlling Multiple Endpoints and Multiple Instances

**An internal Control Bus only sees beans managed by its own ApplicationContext**. If a service has three replicas A, B, and C, sending a stop command to instance A **does not automatically stop** B and C.

~~~mermaid
flowchart TD
    ADM["Admin orchestration"] --> A["Replica A: controlBus"]
    ADM --> B["Replica B: controlBus"]
    ADM --> C["Replica C: controlBus"]
    A --> EA["ordersPollingEndpoint A"]
    B --> EB["ordersPollingEndpoint B"]
    C --> EC["ordersPollingEndpoint C"]
~~~

If you need to **pause the entire order-intake system**, you must have cluster-level coordination:

1. List active instances and identify the target on each instance.
2. Send authenticated commands to each target instance, or use an architecturally appropriate management mechanism.
3. Collect status for **each replica**; do not infer "cluster stopped" from a single successful response.
4. Check whether newly scaled-up instances during maintenance have **autoStartup** enabled and might start receiving messages again.
5. Use a **persistent desired state** if the pause state must survive deployments/restarts.

### Desired State vs. Actual State

~~~text
Desired state (stored by admin orchestrator):
    order-import = PAUSED

Actual state:
    replica A: STOPPED
    replica B: STOPPED
    replica C: RUNNING  <-- has not reached desired state
~~~

A **stop()** command via the Control Bus only changes the current state within the targeted process. When a JVM restarts, SmartLifecycle beans with **isAutoStartup()** may be restarted by Spring. If "pause must persist across deploys" is required, use a **control/desired-state store** and controlled startup/reconciliation logic instead of relying solely on in-memory endpoint state.

### Avoiding Unintended Duplicate Control Commands

Start/stop typically has idempotent semantics at the lifecycle level of many implementations, but **do not generalize that every method with side effects is idempotent**. If an admin operation performs multiple actions (e.g., rotating credentials, triggering manual replay), require **commandId**, deduplication, and auditing to prevent repeated execution from client retries.

## 11. Security: The Control Bus Is a High-Privilege Surface

Because the payload is evaluated as **SpEL**, the Control Bus **must never be exposed directly to untrusted messages or HTTP requests**. A client submitting an arbitrary expression could invoke methods on any bean permitted by the evaluation context, far beyond toggling an endpoint.

### Access Control Design Should Follow Default-Deny

- **Do not** wire an inbound HTTP gateway, public Kafka/JMS consumer, or business data channel directly to **controlBus**.
- Create an **admin façade** with **fixed operations**: `PAUSE_ORDERS`, `RESUME_ORDERS`, `CHECK_ORDERS`; never accept raw SpEL strings.
- Authenticate and authorize **before** constructing the control message; protect internal call paths as well.
- Enforce an **allowlist of endpoint/bean names**; never let callers choose arbitrary bean names.
- Separate **read-only** and **mutating commands**. Reading `isRunning` is lower risk than calling `stop`, though not always harmless.
- Record **audit logs** containing the authenticated actor, `commandId`, target, timestamp, and outcome; apply rate limiting and replay protection where needed.
- Never allow secrets, SpEL expressions, or confidential data to appear in uncontrolled payloads/logs.
- Secure network paths, management ports, and message broker transports if commands cross process boundaries.

**Headers like `requestedBy` or `role` do not prove the sender is authenticated.** They are merely metadata unless attached and verified by a trusted security layer.

### Example Façade with a Fixed Allowlist

~~~java
import java.util.Set;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

enum AdminAction {
    PAUSE_ORDERS,
    RESUME_ORDERS
}

final class RestrictedAdminCommands {
    private final MessageChannel controlBus;

    RestrictedAdminCommands(
            @Qualifier("controlBus") MessageChannel controlBus) {
        this.controlBus = controlBus;
    }

    void execute(AdminAction action, Set<String> trustedAuthorities) {
        // These authorities must come from a trusted security context,
        // NOT directly from the caller's request body or headers.
        if (!trustedAuthorities.contains("OPERATE_ORDER_FLOW")) {
            throw new SecurityException("Not authorized");
        }

        String expression = switch (action) {
            case PAUSE_ORDERS -> "@ordersPollingEndpoint.stop()";
            case RESUME_ORDERS -> "@ordersPollingEndpoint.start()";
        };

        if (!controlBus.send(
                MessageBuilder.withPayload(expression).build())) {
            throw new IllegalStateException("Command not delivered");
        }
    }
}
~~~

This snippet illustrates an **application-layer allowlist** and does not include a complete security filter chain or authentication mechanism. If multiple components in the same JVM can directly inject the `controlBus` channel, access must be governed at the application design/configuration level; a single façade alone does not block other call paths.

**Never build expressions by string concatenation from input**, such as taking a user-supplied bean name to construct a command. Doing so lets parser/input tricks bypass an allowlist.

## 12. Control Command Failures and Recovery Paths

The Control Bus is itself a message handler and can fail:

| Failure | Symptom | Remediation |
| --- | --- | --- |
| **Bean does not exist** | SpEL cannot resolve endpoint name | Check the actual ID and context |
| **Bean does not support lifecycle** | Missing expected start()/stop()/isRunning() methods | Target the right endpoint or wrap in a typed manager |
| **Invalid expression** | Parsing/evaluation error | Only allow expressions constructed by trusted code |
| **Control channel has no subscriber** | Send fails or is rejected per channel type | Verify the bean/`controlBusFlow` has started |
| **Target endpoint mid stop/start** | Transient state changes or unexpected state | Serialize commands per target, reconcile actual state |
| **Control channel thread pool busy** | Commands arrive late or miss deadlines | Use an isolated control plane, monitor latency |
| **Target stopped but backlog remains** | `isRunning=false`, queue still full | Execute drain/in-flight runbook |
| **Service restart** | Endpoint may auto-start again | Reconcile against persistent desired state |

**Error path depends on the channel:** With a **DirectChannel**, Control Bus handler errors normally propagate back to the `send` caller unless caught by an interceptor or another handler. With an **ExecutorChannel**, errors occur on the worker thread; you need an error flow and dedicated verification. Never treat a successful `send` call as the final outcome of an asynchronous operation.

### Status Reporting Rules for Operators

Distinguish these states:

~~~text
REQUESTED   = command dispatch requested
DISPATCHED  = message accepted by the channel
APPLIED     = bean processed the command per contract
VERIFIED    = desired runtime state + conditions confirmed
FAILED      = command failed, with reason
TIMED_OUT   = outcome undetermined within deadline
~~~

This is an **application-defined state model**, not a built-in Control Bus enum. If a client times out after a stop command may have already executed, it should not blindly resend any non-idempotent command; it should **read the actual state first**.

## 13. Dynamic IntegrationFlows and the Control Bus

Spring Integration provides **IntegrationFlowContext** to dynamically register/manage IntegrationFlows at runtime. This differs from sending SpEL start/stop commands to an existing endpoint:

| Need | Appropriate tool |
| --- | --- |
| Stop/restart an already-registered lifecycle endpoint | Control Bus or direct Lifecycle call via a management service |
| Query whether an endpoint bean is running | `isRunning()` or equivalent lifecycle API |
| Register a new flow at runtime | **IntegrationFlowContext.registration(...).register()** per API/version |
| Stop or remove a dynamically registered flow | Appropriate **IntegrationFlowContext** lifecycle/registration API |
| Rewire a flow with new configuration | Requires a register/unregister/replace plan, not just `start()` |

**The Control Bus does not create new flows**, and **stop() does not remove bean definitions from the ApplicationContext**. When you need to change topology rather than just running/stopped state, use the appropriate dynamic flow registration mechanism with clear ownership and cleanup controls.

A "replace flow A with flow B" operation is not an atomic transaction: it requires a sequence of **stopping ingress, draining, registering/checking the new flow, switching sources, and removing the old flow**, along with a rollback plan if it cannot complete.

## 14. Observing Control Bus and Lifecycle in Production

Observe **both control commands and the data plane**:

| Metric / log | Question to answer |
| --- | --- |
| **command_requested / verified / failed** | Which commands were executed and verified? |
| **control command latency** | How long from sending a command until the endpoint reaches the desired state? |
| **actual vs desired state** | Which replicas are out of sync? |
| **isRunning** per endpoint/instance | Which endpoints are still running or stopped? |
| **poll count / inbound rate** | Did stopping the source actually halt new messages? |
| **QueueChannel depth / store backlog** | Is the backlog draining or still growing? |
| **in-flight count** | Are handlers, transactions, or external requests still pending? |
| **retry, errorChannel, DLQ** | Did errors or redeliveries spike after pausing? |
| **executor active/queue/rejection** | Are tasks still running or being rejected despite a stopped source? |
| **last restart / auto startup state** | Did a service restart automatically re-enable the endpoint? |

A structured administrative log:

~~~text
commandId=ops-20261122-17
operation=PAUSE_ORDERS
targetBean=ordersPollingEndpoint
instance=orders-service-pod-b
actor=operations-team
requestedAt=2026-11-22T02:10:00Z
commandOutcome=APPLIED
actualRunning=false
queueDepth=184
inFlight=7
drained=false
~~~

This log illustrates that **the endpoint has stopped, yet backlog/in-flight work still remains**. Never report "flow safely shut down" solely because **actualRunning=false**.

**Spring Integration management/Actuator/JMX/metrics** can assist with observability depending on enabled modules and configuration. The Control Bus specializes in command execution; it **does not automatically build a full dashboard**, and a single `isRunning` query does not replace tracing, error monitoring, or metrics.

## 15. Unit and Integration Testing for Control Bus Lifecycle

Before using commands in production, test that the **Control Bus actually receives expressions**, invokes the right bean, and returns results per the lifecycle contract. Simple tests can use a stub Lifecycle bean instead of spinning up a broker/DB.

### Testing with a Spring Context and a Lifecycle Bean

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.Lifecycle;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = {
        ControlBusConfiguration.class,
        ControlBusLifecycleTest.EndpointFixture.class
})
class ControlBusLifecycleTest {

    @Autowired
    @Qualifier("controlBus")
    MessageChannel controlBus;

    @Autowired
    @Qualifier("ordersPollingEndpoint")
    Lifecycle endpoint;

    @Test
    void commandsChangeLifecycleOfNamedBean() {
        assertTrue(controlBus.send(
                MessageBuilder.withPayload(
                        "@ordersPollingEndpoint.start()")
                        .build()));
        assertTrue(endpoint.isRunning());

        assertTrue(controlBus.send(
                MessageBuilder.withPayload(
                        "@ordersPollingEndpoint.stop()")
                        .build()));
        assertFalse(endpoint.isRunning());
    }

    @Configuration
    static class EndpointFixture {
        @Bean("ordersPollingEndpoint")
        Lifecycle endpoint() {
            return new Lifecycle() {
                private volatile boolean running;

                @Override
                public void start() {
                    running = true;
                }

                @Override
                public void stop() {
                    running = false;
                }

                @Override
                public boolean isRunning() {
                    return running;
                }
            };
        }
    }
}
~~~

**What this test proves:** SpEL resolves the bean with an explicit ID; the Control Bus on a DirectChannel invokes start/stop; bean state changes. It **does not prove** the behavior of a file/JMS/Kafka adapter, transaction safety, or executor queue draining.

**Note when running in a project:** `ControlBusConfiguration` from earlier must be compiled, Spring Integration libraries must be present, and JUnit 5/Spring Test dependencies configured. Adjust class/package names and context setup to match your project.

### Testing Status Queries

Using **MessagingTemplate** with an expression that returns a value:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.springframework.integration.core.MessagingTemplate;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

MessagingTemplate template = new MessagingTemplate();

Message<?> reply = template.sendAndReceive(
        controlBus,
        MessageBuilder.withPayload(
                "@ordersPollingEndpoint.isRunning()").build());

assertNotNull(reply);
assertEquals(Boolean.FALSE, reply.getPayload());
~~~

This is a **fragment running in the same fixture after the endpoint has stopped**. With a synchronous Control Bus handler returning Boolean and a properly wired reply channel, the expected result is false. For void `stop()` commands, **do not write tests expecting a Boolean reply**: instead query `isRunning()` or bean state separately.

### Testing Missing Bean Errors

~~~java
assertThrows(RuntimeException.class, () ->
        controlBus.send(
                MessageBuilder.withPayload(
                        "@endpointDoesNotExist.stop()").build()));
~~~

This example applies to the **synchronous path**: some failures may be wrapped in `MessagingException`/`MessageHandlingException` or another SpEL exception. Avoid coupling tests to an exact internal exception class when the goal is to prove **failures are not silently ignored**.

## 16. Integration Testing with Real Endpoints: Pause, Drain, Resume

After stub Lifecycle tests, test **real inbound adapters or polling endpoints**:

1. Create a test source that counts **receive()/poll()** calls.
2. Create an endpoint with a **fixed ID**, test output channel, and counting consumer.
3. Start the context; wait for evidence the poller is running using **CountDownLatch, Awaitility, or a deadline-based condition**, avoiding arbitrary sleeps.
4. Send a stop command via `controlBus` and verify **isRunning=false**.
5. Feed additional input data; verify the source is no longer polled **once stopping completes** according to the endpoint's semantics.
6. If using a **QueueChannel**, verify messages already queued before stopping **do not disappear**.
7. Send a start command; verify polling resumes and pending messages are processed.
8. Shut down the context cleanly; verify there are no thread/task/resource leaks.

If a poll began before the stop command arrived, an in-flight execution may still finish. Tests should not forbid any output **immediately after sending stop** without distinguishing an in-progress poll from a new poll.

### Essential Runtime Test Matrix

| Test case | Test condition | Key assertion |
| --- | --- | --- |
| **Valid command** | Send start/stop to a lifecycle endpoint | Correct state, correct target |
| **Query** | Send `isRunning()` | Appropriate Boolean reply when request-reply flow is configured |
| **Wrong bean ID** | Send command to a nonexistent bean | Error raised, never turned into success state |
| **Non-Lifecycle bean** | Send stop to a channel bean | Error observed, nothing miscontrolled |
| **Pause when idle** | No in-flight messages | Source stops new polls/receives |
| **Pause mid-handler** | Hold one message in-flight with a latch | In-flight message is not cancelled/rolled back by default |
| **QueueChannel backlog** | Queue has messages before stopping ingress | Messages follow store policy; drain is verified |
| **Resume** | Restart endpoint after pause | Source resumes polling without duplicating business processing |
| **Async worker failure** | ExecutorChannel has a failing task after pause | ErrorMessage/transaction/retry are traceable |
| **JVM restart** | Stop endpoint then restart process | Verify `autoStartup`, desired state, and new input |
| **Multiple replicas** | Stop only instance A | B and C are not assumed stopped |
| **Unauthorized request** | Caller without permission requests PAUSE | Façade rejects, `controlBus` never receives expression |
| **Command timeout** | Command dispatched but unverified | No false success returned; actual state is re-read |

### Failure and Recovery Tests

Lifecycle control affects message intake cadence, so combine it with:

- **Transaction test:** Stop mid-DB processing; prove commit/rollback follows actual boundaries rather than assumptions.
- **Retry test:** Source stops while handler is retrying; verify retry budget and that error flow drops no messages.
- **Redelivery test:** After restart, unacked messages may be redelivered; idempotency keys prevent duplicate side effects.
- **MessageStore test:** Persistent queues/groups retain state across stop/start or restart per the store contract.
- **Cluster coordination test:** Send pause to all replicas, observe each node's actual state, and test a new node joining.

Do not conclude **a flow is comprehensively paused** from a unit test invoking a Lifecycle stub. That only verifies the command dispatch mechanism; operational verification must observe the **end-to-end data plane**.

## 17. Anti-Patterns to Avoid

### Anti-pattern 1: Using the Control Bus as an HTTP Endpoint Running Arbitrary SpEL

~~~text
POST /admin/execute
body = "<client-supplied expression>"
  → controlBus
~~~

This design risks **arbitrary expression execution on application beans**. Alternative: typed operations, explicit allowlists, authn/authz, auditing, and network controls.

### Anti-pattern 2: Stopping Consumers First and Expecting the Queue to Drain

~~~text
stop(orderProcessingPoller)
wait(queue.size == 0)
~~~

If the poller is the sole consumer, nothing remains to shrink the queue. Stop **ingress first**, let consumers drain, and only then stop consumers when criteria are met.

### Anti-pattern 3: Treating `isRunning=false` as Zero In-Flight Work

A task already submitted to an executor or a DB transaction in progress may still be running. Measure queue depth, in-flight tasks, and transactions instead of relying solely on the lifecycle flag.

### Anti-pattern 4: Sending Stop to One Replica and Reporting the Whole Cluster Paused

Each replica has its own ApplicationContext. Stopping only A leaves B and C processing messages. Use per-instance management orchestration and desired-state reconciliation.

### Anti-pattern 5: Stopping and Letting `autoStartup` Re-enable on Restart

Control Bus commands are not durable desired state. If pause must survive deployments, store administrative state outside the process and reapply it when instances join.

### Anti-pattern 6: Sending Control Commands Down the Same Congested Path

If `controlBus` shares a saturated queue/executor, load-shedding stop commands can get stuck too. Isolate the control plane or reserve a bounded, secured management path.

### Anti-pattern 7: Auto-Retrying Every Admin Command Without Checking State

When a client times out, the first command may **have already run**. For start/stop, you can usually read state to reconcile; for other operations with side effects, use `commandId`/idempotency or durable result tracking.

## 18. Practice Exercise: Zero-Message-Loss Maintenance for an Order-Intake Flow

**Scenario:** A Spring Integration service has:

~~~text
FTP/File inbound poller (ordersPollingEndpoint)
   → QueueChannel backed by persistent MessageStore
   → orderProcessingPoller
   → service activator
   → DB transaction
   → outbound event
~~~

The application has **two replicas** and is building up a backlog due to a temporarily slow DB. You need to pause the source during a DB upgrade without losing received messages, then resume safely.

### Requirements

- Admins may only issue **PAUSE_ORDERS, RESUME_ORDERS, QUERY_STATUS**; no raw SpEL accepted.
- Must verify **both replicas** have stopped ingress, even if one replica restarts during maintenance.
- Messages already in the persistent MessageStore continue processing or remain stored for resumption after maintenance.
- Do not ACK/mark success for a failed DB transaction merely because the endpoint was stopped.
- Outbound events must not be emitted twice in business terms if messages are redelivered on restart.
- Must distinguish a pause command **that has executed from one that has finished draining**.

### Solution Approach

1. **Endpoint identification:** Declare `ordersPollingEndpoint` and `orderProcessingPoller` with explicit IDs; verify beans support Lifecycle.
2. **Control channel:** Create a dedicated DirectChannel and internal Control Bus consumer; only the admin façade may send valid commands.
3. **Cluster control:** Persist desired state `PAUSED`; dispatch commands to each replica and verify actual state.
4. **Stop new intake:** Stop `ordersPollingEndpoint` on both replicas; monitor inbound counts and new messages entering the queue.
5. **Drain:** Keep `orderProcessingPoller` running; monitor queue depth + in-flight + transactions; set deadlines and recovery for failed messages.
6. **Maintenance:** Proceed only once criteria are met; if not fully drained, explicitly record pending messages in the persistent store.
7. **Recovery:** Start consumers first and verify DB/broker health; start ingress per desired state `RUNNING`; observe throughput.
8. **Deduplication:** Handlers use `eventId`/idempotency keys and appropriate transactions/outbox since redelivery can occur after crashes.
9. **Testing:** Pause while a transaction is active, stop one replica, restart a replica while desired state is `PAUSED`, then resume on both.

### Self-Check Questions

**Question 1:** Sending **@ordersPollingEndpoint.stop()** to `controlBus` returns `send == true`. Does that guarantee all business messages have finished processing?

**No.** Control message delivery and running state do not replace measuring queue depth, in-flight work, and transactions. Stopping ingress does not automatically drain existing backlogs.

**Question 2:** In an application with two replicas, does a stop command sent to replica A's `controlBus` also stop replica B?

**No.** A's Control Bus manages beans inside A's context. Cluster-wide coordination or a well-designed shared source management mechanism is required.

**Question 3:** Should an admin HTTP endpoint accept raw SpEL strings for more "flexibility"?

**No.** That creates a high-privilege method invocation path on Spring beans. Use a typed operation allowlist, authentication/authorization, auditing, and least privilege.

**Question 4:** After stopping an endpoint, the application restarts and the poller starts running again. Is the Control Bus broken?

**No.** A stop command normally changes runtime state; `autoStartup` lifecycle behavior when creating a new ApplicationContext is separate. Persisting pause across restarts requires durable desired-state management.

**Question 5:** Why shouldn't an emergency stop command use an asynchronous Control Bus channel sharing the same busy executor as the data plane?

**Because** the command can queue behind stuck business tasks, missing the load-shedding window. Isolate the control plane and implement a result-verification strategy.

## 19. Production Readiness Checklist

- Is the Control Bus channel **isolated from business inputs** with restricted senders?
- Do all operations pass through an **allowlist + authentication + authorization + audit**?
- Do target beans/endpoints have **explicit IDs in the right ApplicationContext**?
- Do targets actually implement **Lifecycle/SmartLifecycle** with the expected start/stop semantics?
- Do you distinguish send accepted, command applied, and **actual state verified**?
- Is a reply path configured for `isRunning()`, with null/timeout handling?
- Have you avoided assuming `stop()` **drains queues, cancels tasks, rolls back DB work, or revokes external side effects**?
- Do you have a runbook to stop **ingress first**, drain backlog, and then stop consumers per topology?
- Have you accounted for **QueueChannel/MessageStore, executor in-flight work, poller backlog, retries, and errorChannel**?
- Have you tested adapter-specific broker acknowledgement/redelivery behavior across stop/start and restarts?
- Have you avoided nested retries and kept stable idempotency keys when messages are reprocessed?
- With multiple replicas, do you have **per-instance control + desired-state reconciliation**?
- Is there a mechanism to preserve `PAUSED` across application restarts without `autoStartup` unintentionally reopening intake?
- Do admin commands have deadlines, `commandId`, audit outcomes, and actual-state re-read logic?
- Is the control plane's execution path isolated from executors prone to saturation?
- Do you have unit lifecycle tests, real polling tests, async in-flight tests, restart tests, multi-instance tests, and access-control tests?

## Conclusion

The **Control Bus** is a pattern for using **messages** to send management expressions to Spring beans in an application context, especially useful for **starting/stopping** endpoints and observing **isRunning**. It gives Spring Integration systems a control plane unified with the message-driven model.

However, **lifecycle is not business outcome**: a stopped source may still leave messages in queues, tasks in executors, active transactions, and pending retries. Production operation requires combining a **pause-drain-resume procedure**, actual-state verification, error handling, persistence, idempotency, and multi-instance coordination.

Because the Control Bus can evaluate **SpEL** against Spring beans, treat it as a **high-privilege interface**. A production-grade design requires an **operation allowlist**, protected command paths, auditing, and failure-mode testing—not merely sending `start()`/`stop()` strings.

## References

- [Spring Integration Reference — Control Bus](https://docs.spring.io/spring-integration/reference/control-bus.html)
- [Spring Integration Reference — Polling Consumer](https://docs.spring.io/spring-integration/reference/endpoint/polling-consumer.html)
- [Spring Integration Reference — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html)
- [Spring Framework API — Lifecycle](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/Lifecycle.html)
- [Spring Framework API — SmartLifecycle](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/SmartLifecycle.html)
