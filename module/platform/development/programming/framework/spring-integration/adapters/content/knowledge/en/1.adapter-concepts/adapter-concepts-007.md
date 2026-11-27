# Endpoint Lifecycle and Operational State

## Learning Objectives

After this lesson, you will be able to:

- Describe the **creation, startup, running, stopping, and restart** stages of an endpoint in Spring Integration.
- Distinguish **endpoint running state** from **connection readiness**, **channel subscriber availability**, and **successful message processing**.
- Use the concepts **Lifecycle**, **SmartLifecycle**, **autoStartup**, **phase**, **start()**, **stop()**, and **isRunning()** accurately.
- Explain operational differences among inbound polling adapters, message-driven adapters, outbound adapters, and gateways.
- Configure Java DSL so a file inbound endpoint does not auto-start, then toggle it via management code.
- Design safe startup/shutdown sequences, monitor backlogs, handle in-flight messages, and recover after failures.

## 1. Why Does Endpoint Lifecycle Matter?

An IntegrationFlow can connect external systems via files, SFTP, HTTP, JMS, AMQP, Kafka, or databases. Creating beans and declaring a MessageChannel is not enough for a flow to operate: endpoints may need to **start a poller schedule**, **register listeners**, **initialize consumers**, or **open/lease connections** before messages can be exchanged.

For example, suppose an application ingests partner CSVs via SFTP, normalizes them into Order objects, and publishes Kafka events. If downstream Kafka producers or consumers are not ready when the SFTP inbound poller starts scanning and pushing data, the system may suffer send errors or backlogs. During redeployment, if the inbound source stops too late, new messages may keep arriving after downstream processing or outbound delivery has stopped.

Spring Integration provides **endpoint lifecycle** management so the application can proactively:

- **Start** an inbound source or consumer once operational preconditions are met.
- **Pause ingestion** from one source without necessarily shutting down the entire application.
- **Shut down in order** to reduce the risk of interrupting in-flight messages.
- **Restart** an endpoint after a failure or when a maintenance window ends.
- **Observe state** to distinguish a stopped endpoint from a running endpoint with no incoming data.

This is part of managing connection flows and messaging reliability, not merely toggling a Java bean on and off.

## 2. Endpoints, Channels, and External Resources Have Different Lifecycles

Multiple components coexist within a flow:

~~~mermaid
flowchart LR
    SRC["External source<br/>File / SFTP / JMS / Kafka"]
    EP["Inbound endpoint<br/>poller or listener"]
    CH["MessageChannel"]
    H["Transformer / Service activator"]
    OUT["Outbound endpoint"]
    DST["Target system"]
    SRC --> EP --> CH --> H --> OUT --> DST
    SCH["TaskScheduler / Listener container"] -. "Coordinates" .-> EP
    CON["Connection factory / Session / Client"] -. "Provides connectivity" .-> EP
    CON -. "May be used separately" .-> OUT
~~~

An **endpoint** connects a message producer/consumer to a channel. A **MessageChannel** is the message delivery pathway. A **connection factory, session, scheduler, or client** is a resource used by endpoints. Each layer has distinct operational responsibilities.

| Component | When Active | When Stopped or Unavailable |
| --- | --- | --- |
| File inbound polling endpoint | Poller can scan source on schedule | No new polls originate from the stopped endpoint |
| JMS/AMQP/Kafka inbound message-driven endpoint | Listener/consumer triggers via protocol mechanism | Stopped listener stops pulling new deliveries; in-flight progress depends on container |
| Outbound adapter event-driven consumer | Subscribed to channel and invokes handler | May unsubscribe from channel even though adapter bean still exists |
| Outbound adapter polling consumer | Pulls messages from PollableChannel on schedule | Unprocessed messages may remain queued in the channel |
| MessageChannel | Transfers or stores messages per channel type | A channel is not necessarily an endpoint with matching start/stop state |
| Connection/session/client | Provides communication capability with external systems | Can drop or expire even while the endpoint reports running |

Specifically, a **DirectChannel** does not open network sockets or run a scheduler on its own. Conversely, a **QueueChannel** can hold messages in memory even when its polling consumer is paused. By default, QueueChannel does not guarantee durable storage if the application terminates.

## 3. Lifecycle at the Spring Level: Lifecycle and SmartLifecycle

Spring provides two foundational interfaces:

**Lifecycle** defines basic operations and state:

~~~java
void start();
void stop();
boolean isRunning();
~~~

**SmartLifecycle** extends lifecycle management with **auto-startup** and **phase** so Spring's ApplicationContext can coordinate startup and shutdown. Many Spring Integration endpoints participate in this lifecycle mechanism, usually via their corresponding endpoint/consumer implementations.

| Concept | Meaning | Notes |
| --- | --- | --- |
| **start()** | Requests the component to begin operating | May start a scheduler, register a subscriber, or start a listener |
| **stop()** | Requests the component to stop operating | Does not guarantee all running tasks finish immediately or roll back |
| **isRunning()** | Reports the component's lifecycle status | Does not prove the remote server is healthy or messages succeeded |
| **autoStartup** | Whether to start automatically when ApplicationContext starts | Can be set to false to wait for manual activation |
| **phase** | Controls SmartLifecycle startup/shutdown ordering | Lower phase values typically start first; on shutdown, higher phases stop first |

During ApplicationContext startup, Spring's lifecycle processor starts eligible SmartLifecycle beans according to phase and auto-startup settings. When closing the context, Spring coordinates shutdown in reverse order. **Exact ordering depends on the specific beans, endpoints, and configuration**; do not assume every adapter shares the same default phase.

### 3.1. A Mental-Model State Machine, Not an Official Enum

You can visualize an endpoint moving through these states:

~~~mermaid
stateDiagram-v2
    [*] --> Created
    Created --> Initialized: Spring creates and configures bean
    Initialized --> Running: autoStartup or start()
    Running --> Stopping: stop() or context close
    Stopping --> Stopped: Stop completes
    Stopped --> Running: start() while context is alive
    Initialized --> Stopped: Auto-startup disabled
    Stopped --> [*]: Context / resource destruction
~~~

Labels like **Created**, **Initialized**, and **Stopping** in this diagram are conceptual aids for design and operations; **they are not a unified status enum** exposed by every Spring Integration endpoint. The standard **isRunning()** method returns only a boolean, which is insufficient to distinguish "starting up", "connected but idle", or "draining remaining messages".

### 3.2. What Does autoStartup = false Mean?

When **autoStartup(false)** is set on an endpoint, Spring still creates the beans and registers the flow, yet that endpoint **does not start automatically when the context boots**. An administrative task or another service can call start() once readiness conditions are satisfied.

Suitable examples: waiting for partner configuration to be enabled, pausing ingestion during data migration, or avoiding picking up new files during maintenance. Disabling autoStartup alone **does not clear source data** and **does not automatically guarantee once-only processing** when re-enabled.

## 4. Running State Differs from Readiness State

A common operational mistake is seeing **isRunning() == true** and concluding the integration pipeline is healthy. In reality, lifecycle state may not reflect network connectivity or processing capacity.

| Observation | What Can Be Concluded | What Cannot Be Concluded |
| --- | --- | --- |
| Endpoint reports isRunning = true | Endpoint is in the running state of its lifecycle | SFTP/JMS/Kafka/HTTP/DB connections are succeeding |
| Poller keeps triggering | Scheduled polling task is executing | Source has new data or received data is valid |
| JMS/Kafka listener is running | Container/consumer is allowed to receive per config | All partitions/queues have data or consumer lag is zero |
| Message entered DirectChannel | Send was executed per channel semantics | Side effects at target system are complete |
| Message entered QueueChannel | Message was accepted to await retrieval | Message is persisted across restarts or processed by consumer |
| Broker acknowledged event | Producer/broker confirmation threshold reached | Downstream consumer completed business logic |

Distinguish at least four dimensions: **lifecycle state**, **connection health**, **message throughput/backlog**, and **business outcome**. An endpoint that is "running with empty polls" can be completely normal, whereas an endpoint that is "running while every poll fails authentication" demands alerting.

## 5. How Do Polling Inbound Adapters Start and Stop?

With polling file, SFTP, or JDBC inbound adapters, a **MessageSource** works with a **SourcePollingChannelAdapter** and a **poller**. While active, the scheduler triggers source polling on schedule; received messages are sent to the channel for processing.

~~~mermaid
sequenceDiagram
    participant C as ApplicationContext
    participant E as Polling inbound endpoint
    participant S as TaskScheduler / Poller
    participant F as File/SFTP/DB source
    participant M as MessageChannel
    C->>E: start()
    E->>S: Register poll schedule
    loop Each poll while endpoint is active
      S->>F: receive() from source
      F-->>S: Message or no data
      opt Message present
        S->>M: send(message)
      end
    end
    C->>E: stop()
    E->>S: Stop scheduling new polls
~~~

When **stop()** is called:

- The endpoint's polling schedule is stopped/cancelled according to endpoint lifecycle management.
- Do not assume work **already in progress** is aborted instantly; task completion depends on execution threads, schedulers, and configuration.
- Unpicked files may remain at the source. Whether files picked up before a processing error are reselected depends on filters, state, retry policies, and recovery logic.
- Stopping one endpoint sharing a **TaskScheduler** does not mean the application shuts down the scheduler for all other endpoints.

### 5.1. When the Poller Finds No Data

Having no new files or an empty SQL result set **does not mean the endpoint stopped**. The poller continues running on schedule without emitting messages. For monitoring, separate counts of successful polls, empty polls, and failed polls.

### 5.2. Restarts and Accept-Once File Filtering

File inbound adapters typically use a filter to avoid repeatedly picking up files already seen within the same tracking state. However, **in-memory** filters or metadata stores lose state when the application restarts. Also distinguish "file selected and sent to channel" from "business processing completed".

If restart safety is needed, design explicitly:

1. A filter or metadata store backed by appropriate persistent state.
2. Procedures to ingest only completely written files.
3. Moving or marking files after processing.
4. A business idempotency key, such as **partnerId + orderId**, to prevent duplicate side effects.

## 6. Message-Driven Endpoints: Listeners and Consumers Have Their Own Lifecycles

JMS, AMQP, and Kafka sources typically rely on a **listener container** or protocol-managed consumer. When an inbound endpoint starts, the framework activates or resumes receiving per configuration; when stopped, ingestion is requested to halt.

| Source | On Start | What to Watch on Stop |
| --- | --- | --- |
| **JMS** | Starts message listener container to receive from destination | Transactions/acks of in-flight messages, potential redelivery, shutdown timeout |
| **AMQP** | Starts queue listener container or consumer mechanism | ACK/NACK, requeue, prefetch, and unacknowledged messages |
| **Kafka** | Starts listener/consumer, joins consumer group via client | Committed offsets, in-flight records, rebalances, potential redelivery |
| **HTTP inbound gateway** | Web endpoint registered and ready to accept requests in server infra | Stopping the endpoint does not shut down the whole HTTP server or abort every waiting request |

For Kafka, the consumer client runs its own internal poll loop; do not assume every Kafka inbound endpoint needs a **Spring Integration poller**. Likewise, JMS/AMQP acknowledgments are not gateway business replies.

Crucial point: **stop() is not a command to purge messages from the broker.** Messages still in queues/topics, in flight, or already acknowledged/committed follow the rules of each protocol, consumer group, transaction, and configuration.

### 6.1. Avoid Confusing Endpoint Restarts with Application Restarts

Calling **stop()/start()** on an endpoint inside a live ApplicationContext differs from restarting the whole process:

- Shared beans, clients, and schedulers remain alive when only one endpoint stops.
- Messages inside internal queues may persist within the same process.
- An application restart recreates beans, resets in-memory state, or re-establishes consumer groups/sessions.
- Closing the ApplicationContext normally closes shared resources; do not expect to call start() on beans after the context has closed.

## 7. Outbound Adapters and Gateways Also Have Running States

Lifecycle is not only for inbound adapters. An outbound adapter's **consumer endpoint** pulls messages from a channel; it must also be registered and active to process data.

An **event-driven consumer** typically registers a subscriber with a **SubscribableChannel** like DirectChannel. When the endpoint stops, that subscriber may be unsubscribed; producers still sending to DirectChannel may fail if no subscriber remains to receive messages.

A **polling consumer** pulls messages from a **PollableChannel** like QueueChannel. When the endpoint stops, pending messages may remain in the queue (depending on configuration and storage). Resuming can cause the consumer to begin draining the backlog.

**Outbound gateways** must also consider reply messages. If an endpoint stops or a connection closes mid request–reply, the caller may not receive a response within its timeout. **A timeout does not prove the external operation did not run**; retries require idempotency and reconciliation.

~~~mermaid
flowchart LR
    P["Producer"] --> Q["QueueChannel"]
    Q --> PC["Polling consumer<br/>has lifecycle"]
    PC --> OA["Outbound adapter"]
    OA --> EXT["Broker / File / API"]
    CTRL["Toggle endpoint"] -.-> PC
    NOTE["Messages may wait in queue"] -.-> Q
~~~

An outbound adapter may use a shared HTTP client, Kafka producer, JMS connection factory, or SFTP session bean. Stopping the consumer endpoint does not automatically close shared resources or halt the external target.

## 8. Java DSL Hands-On: Toggling a File Inbound Endpoint

Goal: build a file inbound polling adapter reading **./data/inbox**, sending File payloads to MessageChannel **incomingFiles**, and a consumer printing filenames. The endpoint is configured with **autoStartup(false)** so it does not scan immediately at application startup. We start and stop the endpoint via **SmartLifecycle**.

With Spring Boot, you need Spring Integration core (typically via **spring-boot-starter-integration**) and **spring-integration-file** matching the Boot-managed version.

### 8.1. Configuring Two Independent Flows

~~~java
import java.io.File;
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.file.dsl.Files;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class FileEndpointConfiguration {

    @Bean
    public MessageChannel incomingFiles() {
        return new DirectChannel();
    }

    // Only this inbound endpoint does not auto-start.
    @Bean
    public IntegrationFlow fileInboundFlow() {
        return IntegrationFlow
            .from(
                Files.inboundAdapter(new File("./data/inbox"))
                    .autoCreateDirectory(true)
                    .patternFilter("*.csv"),
                endpoint -> endpoint
                    .id("ordersFileInbound")
                    .autoStartup(false)
                    .poller(Pollers.fixedDelay(Duration.ofSeconds(5))
                        .maxMessagesPerPoll(5)))
            .channel("incomingFiles")
            .get();
    }

    // The consumer flow auto-starts by default.
    @Bean
    public IntegrationFlow inspectInboundFiles() {
        return IntegrationFlow.from("incomingFiles")
            .handle(File.class, (file, headers) -> {
                System.out.println("Received: " + file.getName());
                return null;
            })
            .get();
    }
}
~~~

In this configuration:

1. **Files.inboundAdapter(...)** creates a polling source returning File objects without parsing CSV.
2. **id("ordersFileInbound")** assigns an endpoint identifier so the lifecycle-managed bean can be referenced.
3. **autoStartup(false)** prevents the inbound endpoint from registering its poll schedule at context startup.
4. **Pollers.fixedDelay(...)** defines the polling cadence once started; **maxMessagesPerPoll(5)** caps messages per poll.
5. **incomingFiles** is a DirectChannel delivering messages to the consumer; the consumer flow has its own lifecycle and does not stop simply because the inbound endpoint pauses.

### 8.2. Control Service for Start/Stop

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Service;

@Service
public class InboundEndpointControl {

    private final SmartLifecycle inboundEndpoint;

    public InboundEndpointControl(
            @Qualifier("ordersFileInbound")
            SmartLifecycle inboundEndpoint) {
        this.inboundEndpoint = inboundEndpoint;
    }

    public void resume() {
        if (!inboundEndpoint.isRunning()) {
            inboundEndpoint.start();
        }
    }

    public void pause() {
        if (inboundEndpoint.isRunning()) {
            inboundEndpoint.stop();
        }
    }

    public boolean isRunning() {
        return inboundEndpoint.isRunning();
    }
}
~~~

**Place both classes in appropriate Java files.** The control service injects the bean by the inbound endpoint's ID. Calling **resume()** starts poller scanning; calling **pause()** stops the endpoint from initiating new pickups per lifecycle rules. **isRunning()** checks the endpoint's state within this process, not the health of the filesystem or the entire system.

This is an internal management API. If you expose start/stop actions over HTTP or a control bus, enforce authorization and audit logging because toggling endpoints directly affects active data ingestion.

### 8.3. How to Test and Expected Behavior

1. Start the application; confirm **InboundEndpointControl.isRunning()** initially returns **false**.
2. Place **orders-001.csv** into **./data/inbox**. While the endpoint is paused, this polling endpoint does not pick up the file.
3. Call **resume()**. Once the poll schedule runs, the consumer prints the received filename.
4. Call **pause()**, then drop **orders-002.csv** into the directory. The paused endpoint does not initiate new polls to pick it up.
5. Call **resume()** again and observe the waiting file being picked up per filter policy.
6. Test **notes.txt** to confirm **patternFilter("*.csv")** ignores non-matching files.

If pause is called right while a poll or handler is executing, in-flight work may still finish after the stop call. Therefore, evaluate test outcomes by checking task start times, handler logs, and actual state rather than expecting instantaneous synchronous halting in every scenario.

**Scope of this example:** it only prints filenames. It does not ensure files finished writing before pickup, parse CSV content, or provide persistent filters or idempotency across restarts. Re-enabling an endpoint does not automatically repair business state if an earlier error occurred mid-flight.

## 9. Start and Stop Ordering with SmartLifecycle Phases

When a system comprises multiple endpoints and resources, activation order directly impacts message send/receive reliability.

Spring SmartLifecycle uses **phase**:

- Components with a **lower phase** generally **start before** components with a higher phase.
- On context close, components with a **higher phase** generally **stop before** components with a lower phase.
- An endpoint with **autoStartup(false)** will not auto-start regardless of its phase.

~~~mermaid
flowchart TD
    A["1. Prepare resources<br/>connections / schedulers / consumers"] --> B["2. Start downstream handlers<br/>and outbound endpoints"]
    B --> C["3. Start inbound listeners<br/>or polling sources"]
    C --> R["RUNNING"]
    R --> D["4. Tell inbound to stop accepting new work"]
    D --> E["5. Allow in-flight work to finish<br/>or persist checkpoints"]
    E --> F["6. Stop downstream and resources"]
~~~

The standard operational rule is **prepare consumers before letting sources emit data**, and **stop inbound sources before shutting down consumers**. You can use phases and bean dependencies to aid coordination, without assuming default phases always guarantee the desired ordering for every flow.

### 9.1. Example of Wrong Ordering Risk

If a file inbound endpoint starts running and sends to a DirectChannel while the outbound consumer is stopped or not yet subscribed, sends can fail with **no subscribers**. With a message broker source, this error affects ACK/redelivery timing. With an ExecutorChannel, a producer might assume sending succeeded even though the downstream task is later rejected by a shutting-down executor.

Shutdown order must therefore account for **actual channels**, in-flight message handling, transactions, queue capacity, and checkpoint persistence.

## 10. Graceful Shutdown: Stop Ingestion, Drain Queues, Close Connections

A safe shutdown must distinguish **stopped accepting new work** from **finished processing every message**.

### 10.1. Reference Procedure

1. **Prevent new work:** ask inbound adapters/listeners to stop receiving per each source's mechanism.
2. **Monitor in-flight messages:** observe active handlers, pending replies, queue depths, and active transactions.
3. **Wait or persist safe state:** allow tasks to finish within operational time limits; if unfinished, rely on recovery or redelivery mechanisms.
4. **Stop consumers and outbound paths:** after draining backlogs, stop outbound endpoints, workers, and shared components in order.
5. **Close resources:** release connections/sessions/executors via Spring and client lifecycles.
6. **On restart:** rely on durable checkpoints/offsets/metadata stores and business keys to avoid data loss or duplicate processing.

Never claim **stop() = successful drain**. Lifecycle APIs request stopping, but they do not provide a distributed transaction across files, databases, brokers, and HTTP. Waiting for active tasks, cancellation, or redelivery depends on each specific endpoint and client.

### 10.2. Abrupt Process Termination

Not every shutdown runs gracefully. Power loss or killing the process can lose messages buffered in memory, drop connections before ACKs, or leave files written without updated checkpoints.

For critical business flows, choose durable storage, transactional outbox/inbox, idempotent consumers, and reconciliation processes to recover after crashes. **In-memory QueueChannel defaults** do not provide these guarantees.

## 11. Monitoring Endpoint State and Integration Health

Combine lifecycle signals with connectivity, throughput, and processing outcomes:

| Metric Group | Examples to Observe | Meaning |
| --- | --- | --- |
| **Lifecycle** | Endpoint ID, isRunning, start/stop timestamps | Shows whether the component has been enabled |
| **Connectivity** | SFTP session health, broker connectivity, DB pool, HTTP client | Detects endpoints that are running yet unable to communicate |
| **Polling** | Poll count, empty polls, poll errors, last pickup timestamp | Distinguishes an idle source from a failing source |
| **Listener** | Kafka consumer lag, JMS/AMQP queue depth, redelivery count | Detects bottlenecks or repeated deliveries |
| **Processing** | Throughput, handler latency, active tasks, queue depth | Shows whether downstream keeps pace with source rate |
| **Errors** | ErrorMessages, retries, dead-letters, timeouts, exceptions | Pinpoints failure locations and recovery paths |
| **Business** | Completed orders, duplicate keys, items needing reconciliation | Evaluates real outcomes, not just message-send milestones |

You can integrate logging, Micrometer/Actuator, and management tools suited to your application version and configuration. Do not assume every endpoint exports metrics or exposes HTTP management out of the box without enabling the necessary features and dependencies.

When logging, include endpoint ID, event ID, or correlation ID; avoid printing credentials, sensitive payloads, or unnecessary partner data. When managing endpoints by ID, keep IDs stable and descriptive so logs and metrics remain traceable across deployments.

## 12. Scenarios Requiring Lifecycle Decisions

| Scenario | Appropriate Thinking |
| --- | --- |
| Partner SFTP maintenance | Pause inbound SFTP endpoint, track file states, and resume per policy |
| Database migration | Pause inbound work-generating sources before schema changes; account for in-flight transactions |
| Rising Kafka consumer lag | Measure throughput, concurrency, downstream latency; scale consumers only in line with partitions and capacity |
| JMS listener lost connection | Inspect container, broker, reconnect behavior, redelivery, and ACK timing |
| File inbound reports running but no files appear | Check if source has new files, pattern filter, read permissions, empty polls, and exceptions |
| Outbound consumer stopped while QueueChannel holds messages | Inspect backlog, queue capacity/durability, perform controlled resume |
| HTTP gateway has pending requests on shutdown | Define timeouts, response status, and handling for requests that already caused side effects |
| Application boots after crash | Reconcile checkpoints, sent records, idempotency, and source/target states |

### 12.1. Special Case: "Running" With No Subscriber

Suppose a File inbound adapter runs normally and sends messages to a DirectChannel. The downstream flow might not have started yet or may be paused for maintenance. Here the error does not necessarily originate from the file source, but from the channel lacking an active consumer. Inspect **both sending and receiving endpoints**, not just one isRunning flag.

### 12.2. Special Case: Target Processed Request Before Application Timed Out

An outbound HTTP gateway or broker producer may time out after the target system already accepted the request. Stopping and restarting the endpoint will not resolve this ambiguous state on its own. You need stable idempotency keys, confirmation contracts, and reconciliation tools against the target.

## 13. Common Mistakes

**"Beans are initialized, so the endpoint is receiving data."** An endpoint may configure autoStartup(false), not be started yet, or already be stopped.

**"isRunning() = true means connections and business processing are healthy."** That is only a lifecycle signal reported by the component; monitor connections, errors, throughput, and business outcomes as well.

**"Stopping inbound means all prior messages have finished processing."** Messages may still be inside handlers, executors, queues, or external targets.

**"Stopping an endpoint stops shared schedulers and connection factories too."** Shared resources have their own lifecycles; stopping one endpoint should not break other endpoints sharing the same resource.

**"Resuming will always pick up exactly unprocessed messages with zero duplicates."** Behavior depends on file filters, offsets, ACKs, checkpoints, transactions, and retry policies.

**"Increasing concurrency fixes ingestion failures."** If the root cause is bad SFTP credentials, an unreachable broker, or filtered-out files, adding workers will not help.

**"Gateway timeout means the target did nothing."** The target may have executed the side effect before the reply was lost; reconcile before retrying.

**"Phase doesn't matter because Spring handles everything automatically."** Phases and dependencies can dictate which side starts or stops first. Verify your actual architecture.

## 14. Self-Check Questions

1. How do Lifecycle and SmartLifecycle differ? What are **autoStartup** and **phase** used for?
2. Why is **isRunning()** insufficient to conclude that an SFTP server or Kafka broker is reachable?
3. When a polling inbound endpoint is stopped, what can happen to a poll cycle that already started?
4. If an inbound adapter sends to a DirectChannel while the consumer endpoint is stopped, what error can occur?
5. A QueueChannel holds pending messages while its outbound polling consumer is stopped. What should you check before resuming?
6. In the Java DSL example, why are input files not processed before **resume()** is called?
7. Why is it often safer to start downstream before inbound, and stop inbound before downstream?
8. Why can Kafka offset commits, JMS ACKs, and file filters alter recovery behavior after a restart?
9. An endpoint is running yet continuously performs empty polls. Which metrics help determine whether this is normal operation or a failure?
10. When an HTTP gateway times out right as the application shuts down, why must resending the request account for idempotency?

## Summary

**Endpoint lifecycle** controls when adapters, listeners, and consumers begin or stop moving messages in Spring Integration. **Lifecycle/SmartLifecycle** provide start, stop, isRunning, autoStartup, and phase to coordinate startup and shutdown. However, **running** differs from **connection readiness** and **business completion**. Across files, SFTP, HTTP, JMS, AMQP, Kafka, and databases, monitor endpoint state, pollers/listeners, MessageChannels, backlogs, delivery acknowledgments, and connection resources together. A safe design starts downstream before accepting data, stops ingestion before shutting down processors, and applies checkpoints, retries, and idempotency to recover cleanly from failures.
