# Managing Runtime Endpoints with JMX in Spring Integration Adapters

## 1. Context: Why Control Endpoints While the Application Is Running?

In Spring Integration, an integration flow can ingest data from **File, SFTP, HTTP, JMS, AMQP, Kafka, or databases**, pass it through **MessageChannel**s, transformers, routers, filters, and service activators, and send it to a target system via an **outbound adapter/gateway**. When an external system slows down, a connector disconnects, or malformed data arrives in bulk, operations teams need immediate answers:

- Is the inbound adapter running and receiving new messages?
- Is a poller continuing to read files/records even though downstream is overloaded?
- How many messages are handlers, consumers, or MessageChannels processing?
- Can we **pause intake**, observe the backlog, and resume without restarting the entire JVM?
- Which nodes in a multi-instance cluster are affected by runtime changes?
- After a JMX operation, are **in-flight** messages, transactions, offsets, broker sessions, and unprocessed data preserved safely?

**Java Management Extensions (JMX)** is a mechanism for managing and monitoring objects inside a JVM through **MBean**s. In Spring Integration, JMX can expose information about integration components and—**when the bean and library version actually expose matching operations**—support runtime endpoint lifecycle changes. This lesson belongs to the **Observability** chapter of the **SPRING_INTEGRATION_ADAPTERS** module, directly tying into inbound/outbound adapters, gateways, pollers, MessageChannels, **message contracts, errors, and connection lifecycles**.

The goal is not “expose every JMX operation to operators.” The goal is **observing real state and executing controlled changes when needed**, with clear security, approvals, verification, and recovery.

> **Important limitation:** Not every endpoint exposes the same attributes or `start`/`stop` operations in JMX. MBeans, `ObjectName`s, metrics, operations, and enablement vary by Spring Integration/Spring Boot version, bean type, and exporter configuration. Every example must be verified against `MBeanInfo` in the **actual running application** before automating.

### Learning Outcomes

1. Explain **JMX, MBeanServer, ObjectName, attribute, operation**, and how they relate to Spring Integration endpoints.
2. Enable and inspect **Integration MBean** exposure without confusing it with Spring Boot Actuator JMX.
3. Distinguish **read-only status observation** from **start/stop/pause** and their impact on in-flight messages.
4. Build safe runbooks for File, SFTP, HTTP, JMS, AMQP, Kafka, JDBC, and channel types.
5. Manage multiple instances, access control, audits, change/incident tracking, and restoration steps.
6. Combine JMX with Micrometer, logs, traces, MessageHistory, and broker/target metrics.

## 2. What Is JMX?

JMX is a facility for managing and monitoring Java resources inside a JVM. Managed components can be exposed as **MBean**s with published metadata and capabilities.

| Concept | Role | Usage Tip |
|---|---|---|
| **MBean** | Managed object exposing attributes and/or operations | An exported endpoint/handler/bean |
| **MBeanServer** | In-JVM registry holding MBeans and handling queries/invocations | Intermediary for management tools |
| **ObjectName** | MBean identity by domain and key properties | Locate the exact bean in the exact JVM |
| **Attribute** | Readable value or, if exposed, writable property | Running state, counts, specific config |
| **Operation** | Invocable MBean method | Present only when exported; may alter runtime state |
| **Notification** | Events an MBean may emit if supported | Track state changes; not all beans emit them |
| **JMX client** | JConsole, VisualVM, monitoring agents, or Java clients | Inspect `MBeanInfo` and read values |
| **JMX exporter** | Exports a set of Java beans as MBeans | Configure exposure with tight scope and security |

### 2.1. ObjectName Example

An MBean may appear as:

~~~text
<domain>:type=<type>,name=<component-name>,...
~~~

This is an **illustrative pattern**, not a fixed Spring Integration ObjectName. **Do not hardcode** a domain, MBean type name, or attribute from this example without inspecting your active configuration and version.

### 2.2. Local In-JVM JMX vs. Remote JMX

**Local JMX** lets authorized local processes inspect a JVM's MBeans. **Remote JMX** opens a network management path to the JVM and expands the attack surface. Whenever remote JMX is enabled, enforce real security: network restrictions, authentication/authorization, TLS, or protected management tunnels—never disable auth or encryption for “quick debugging.”

## 3. MBeans in Spring Integration: Observation and Control

Spring Integration beans may include:

- **MessageChannel:** transports messages between endpoints.
- **Inbound channel adapter:** receives, polls, or listens to a source.
- **Inbound gateway:** receives requests and creates a reply flow.
- **Message handler/outbound adapter:** transforms, calls APIs, publishes, or persists resources.
- **Polling consumer / SourcePollingChannelAdapter:** coordinates a poller and source.
- **Event-driven consumer / message producer:** receives or dispatches messages on events.
- **IntegrationFlow:** defines flow structure; the flow object itself is not automatically an MBean with start/stop.

Spring Integration provides JMX management support such as **`IntegrationMBeanExporter`** and corresponding enablement configuration in supported versions. **Distinguish between beans registered in the Spring context, beans managed by Spring Integration, and beans actually exported as MBeans**.

### 3.1. Two Separate Capability Groups

| Group | Conceptual Examples | Principle |
|---|---|---|
| **Read-only observation** | `isRunning`, send/receive counts, error counts, component info | What can be read depends on `MBeanInfo` |
| **State-changing management** | `start`, `stop`, setters, or control operations | Invoke only when exposed by MBean and authorized/approved |

Do not infer from `running=true` that “nothing is wrong.” An endpoint can be running while ingesting zero data because the remote source is empty, a session broke, a queue is backed up, or the poller has no runnable tasks.

### 3.2. Why Must Runtime Operations Be Governed?

Calling `stop` on a source may halt new intake without stopping processing of messages already queued. Conversely, calling `stop` on a consumer can leave queues piling up with nobody draining them. For a broker listener, lifecycle changes also affect consumer groups, message acknowledgments, rebalances, and redelivery.

**Seeing an operation does not mean it is harmless.** Every invocation must go through change/incident controls with before/after evidence and a recovery plan.

## 4. Architecture for Observing and Controlling via JMX

~~~mermaid
flowchart LR
    EXT[File / SFTP / HTTP / JMS / AMQP / Kafka / DB] --> IN[Inbound Endpoint]
    IN --> CH[MessageChannel]
    CH --> H[Handler / Router / Transformer]
    H --> OUT[Outbound Endpoint]
    OUT --> TARGET[Remote System]
    IN -. management info .-> MX[MBeanServer in JVM]
    CH -. management info .-> MX
    H -. management info .-> MX
    OUT -. management info .-> MX
    CLIENT[Authorized JMX Client] -->|Query / Invoke| MX
    MX -. Attributes / Operations .-> CLIENT
    IN --> MET[Metrics / Logs / Traces]
    OUT --> MET
    TARGET --> MET
    MET --> CHECK[Verify outcomes & audit]
    CLIENT --> CHECK
~~~

JMX provides a **per-JVM/bean** view. If the application runs three replicas, you may be viewing **only one replica**. Brokers, SFTP sources, databases, and remote HTTP services maintain their own state, which cannot be fully inferred from an adapter's MBean.

### 4.1. The Unit of Impact Is a Component Inside One Process

A `stop` operation on an endpoint in node A **does not automatically stop the identically named endpoint in node B**, unless the project explicitly implements coordination. Across multiple pods/VMs, track instance identity, deployment, lease/lock ownership, and duplicate-polling prevention.

## 5. Enabling JMX Export for Spring Integration

In supported Spring Integration versions, the **`@EnableIntegrationMBeanExport`** annotation configures exporting integration MBeans. Starter declaration example:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.config.EnableIntegrationMBeanExport;

@Configuration
@EnableIntegration
@EnableIntegrationMBeanExport
public class IntegrationJmxConfiguration {
    // Verify which MBeans actually appear with the version in use.
}
~~~

**Version note:** annotations, exporter beans, default domains, and exported components must be checked against your active Spring Integration version. Spring Boot may already configure management/export behavior via auto-configuration; avoid adding duplicate configurations without understanding the impact.

### 5.1. Distinguishing `@EnableIntegrationManagement` from JMX Export

| Mechanism | Primary Purpose | What It Does Not Guarantee |
|---|---|---|
| **Integration management/observation** | Instruments channels/handlers and management/metric signals per version | Does not guarantee a specific MBean appears |
| **Integration MBean export** | Registers integration components into the JMX `MBeanServer` per config | Does not enable Prometheus or distributed tracing |
| **Spring Boot Actuator** | Health/metrics/management endpoints over configured transports | Does not allow `start/stop` on every adapter by default |
| **Custom MBean** | Exposes an application-defined management interface | Not automatically safe or lifecycle-aware unless designed properly |

Do not pick configuration based solely on annotation names. During rollout, verify that **MBeans exist, metadata is accurate, permissions are tight, and operations behave as expected**.

### 5.2. With Spring Boot JMX

Spring Boot can export certain beans and Actuator endpoints to JMX through its own properties (e.g., `spring.jmx.enabled` and `management.endpoints.jmx.exposure.*` depending on version). **Exposing Actuator JMX endpoints does not automatically activate Spring Integration's `MBeanExporter`**. Separate the checks:

1. Are Boot/Actuator MBeans registered?
2. Is Spring Integration's exporter registering endpoints/channels?
3. Are there `ObjectName`/domain conflicts with another exporter?
4. Is runtime JMX access restricted per policy?

### 5.3. Enable Only What You Actually Need

If an environment only needs metrics and health, you do not necessarily need remote JMX with invoke permissions. Prefer **read-only monitoring**, and grant state-changing permissions only to an authorized workflow or group.

## 6. Discovering MBeans Before Writing Runbooks

Do not start with `invoke("stop")`. A safe discovery pass should:

1. Connect to the **exact target JVM** over an authorized channel.
2. List domains, `ObjectName`s, and beans related to Spring Integration.
3. Read **`MBeanInfo`** to verify which attributes/operations are actually exposed.
4. Match each bean to its **component ID** in the `IntegrationFlow`.
5. Read several non-mutating attributes, distinguishing cumulative counters from point-in-time gauges.
6. Document names, types, descriptions, read/write capabilities, and operation signatures.
7. Verify the MBean belongs to the right instance/tenant/environment.
8. Only add state-changing operations to runbooks after testing them in a non-production environment.

### 6.1. Java Example Reading MBean Metadata Only

~~~java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import java.util.Set;

public final class LocalMBeanInspector {
    private LocalMBeanInspector() {}

    public static void inspectDomain(String domain) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName pattern = new ObjectName(domain + ":*");
        Set<ObjectName> names = server.queryNames(pattern, null);

        for (ObjectName name : names) {
            MBeanInfo info = server.getMBeanInfo(name);
            System.out.println("MBean: " + name.getCanonicalName());
            for (MBeanOperationInfo operation : info.getOperations()) {
                System.out.println("  operation: " + operation.getName());
            }
        }
    }
}
~~~

**This snippet illustrates reading metadata inside a running JVM**, not a remote client or privilege-escalation tool. Pass only trusted/permitted domains. In real environments, avoid dumping full `ObjectName`s into public logs if they expose topology or tenants; filter and control outputs.

### 6.2. Never Guess Operation Names from Java Methods

A Spring bean having a `start()` method does not mean the MBean exports that operation. **`MBeanInfo` is the source of truth for exposed operations**, while authorization and operational impact must be verified through policy and testing.

## 7. Naming Endpoints Stably for Easy JMX Discovery

Spring Integration's auto-generated names can change after refactoring or dynamic flow registration. A flow with explicit endpoint IDs is much easier to correlate:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class OrderIntegrationFlowConfiguration {
    @Bean
    IntegrationFlow ordersFlow() {
        return IntegrationFlow.from("ordersInput")
                .filter(String.class, s -> !s.isBlank(),
                        e -> e.id("validateOrderInput"))
                .transform(String.class, String::trim,
                        e -> e.id("normalizeOrderInput"))
                .handle(message -> {
                    // Execute business logic; do not log raw payload.
                }, e -> e.id("ordersSink"))
                .get();
    }
}
~~~

**Assigning IDs helps locate components**, without guaranteeing that every DSL endpoint in the snippet is a lifecycle endpoint or MBean. When a handler does not expose stop/start, target the appropriate upstream inbound/consumer endpoint if halting intake is the business goal.

### 7.1. Naming Rules

- Name by function: `invoiceSftpInbound`, `ordersKafkaConsumer`, `billingHttpOutbound`.
- Avoid secrets, customer names, runtime values, emails, or file paths.
- Keep names stable across deployments when operational procedures depend on them.
- With multiple instances, attach **instance identity in inventory/monitoring**, rather than mutating component IDs per message.
- Prevent naming collisions across dynamic flows or multiple contexts.

## 8. Endpoint Lifecycle in Spring Integration

Spring Integration endpoints/producers/consumers may participate in Spring's **`Lifecycle`/`SmartLifecycle`** mechanism, yet **not every handler or adapter shares the same lifecycle behavior**. Some endpoints start and stop with the `ApplicationContext` and support `start`/`stop`; others are pure processing logic with no active source to halt.

### 8.1. Four Questions to Answer

1. Which bean is actually being **started/stopped**—inbound producer, polling consumer, listener container, or handler?
2. Does `stop` halt **receiving new messages**, halt **dispatch**, or halt **sending to target**?
3. What happens to messages already **in-flight**, queued, in transactions, or un-ACKed on a broker?
4. After `start`, could it re-read files/records, rebalance Kafka, redeliver JMS/AMQP, or create duplicate side effects?

### 8.2. Separate Three States

| State | Example | Why It Matters |
|---|---|---|
| **Bean lifecycle** | Endpoint reports `isRunning=true` | Reflects only that the bean considers itself running |
| **Connectivity/health** | SFTP/HTTP/broker connects successfully | Running does not guarantee the network works |
| **Business progress** | Files/records are processed and confirmed | Can be running yet receiving no data or backed up |

Closing an incident requires verifying all three layers where applicable, not just an `isRunning` flag.

## 9. Start, Stop, Pause, and Drain Are Different

In operations, these four terms are often used interchangeably even though they carry distinct effects:

| Action | Intent | What Must Be Verified |
|---|---|---|
| **Start** | Resume endpoint activity | Poller/listener actually runs; no duplicates produced |
| **Stop** | Halt source or consumer per bean semantics | Stops new intake entirely or only one part? |
| **Pause** | Temporarily suspend part of the work, if supported | Keeps connections/assignments? Auto-resumes? |
| **Drain** | Stop ingress and finish in-flight/backlog per strategy | When is it considered drained? Transactions/acks completed? |

**JMX does not provide a universal “drain all flows” button.** Draining is usually a coordinated sequence: stop ingress, monitor queues/in-flight work, confirm checkpoints and target outcomes, and only then stop downstream consumers per adapter.

### 9.1. Do Not Stop Outbound Adapters Before Stopping Ingress

If inbound keeps ingesting 10,000 messages/minute while outbound is stopped, `QueueChannel` or executors can overflow. The right shutdown order depends on flow topology, typically:

1. Inspect sources and pending volume.
2. Halt or throttle ingress.
3. Let downstream finish messages that must complete.
4. Monitor queue age, in-flight counts, and remote acknowledgments.
5. Stop remaining components only when no messages/transactions will be lost.

Do not follow this sequence mechanically during credential compromise or malicious data incidents; in security incidents, immediate **containment** may outweigh full draining.

## 10. SOP-JMX-01 — Inspecting Runtime Endpoint State

**Trigger:** system receives no data, backlog alert fires, adapter connection errors occur, or post-deployment endpoint verification is needed.

**Inputs:** incident/change ID, instance, environment, component ID, target system, symptom, and operator permissions.

1. Confirm the **exact application/instance**, timestamp, and deployment version.
2. Open a JMX client over a secured admin channel; locate `ObjectName` via inventory/`MBeanInfo`.
3. Read legitimate, permitted attributes: running state, counters, counts, or gauges.
4. Map the Spring Integration endpoint ID to the flow topology and real adapter/gateway.
5. Inspect the matching **poller/listener/consumer**, not just `MessageChannel`.
6. Check logs/metrics: last poll time, queue depth, oldest age, handler errors, retries, remote timeouts.
7. Check external state: SFTP session/remote listing, Kafka lag, JMS/AMQP queues, DB connections/rows.
8. Form an initial classification: `RUNNING_NO_INPUT`, `STOPPED`, `DOWNSTREAM_BLOCKED`, `CONNECTION_FAILURE`, or `UNKNOWN`.
9. Request a state change only if needed and approved; otherwise stay in read-only triage.

### 10.1. Read-Only Observation Record Template

~~~yaml
observation_id: JMX-OBS-EXAMPLE-081
environment: staging
instance_ref: integration-worker-02
component_ref: invoiceSftpInbound
component_kind: inbound-channel-adapter
observed_at: "2026-11-23T15:30:00+07:00"
bean_running: true
poll_last_success_ref: poll-event-1081
source_file_age_bucket: 10m-30m
downstream_queue_age_bucket: 1m-5m
connectivity_status: CONNECTED
business_progress: DELAYED
evidence_refs:
  - jmx-snapshot-081
  - flow-dashboard-081
operator_decision: INVESTIGATE_DOWNSTREAM
~~~

**This example is an application/operations-defined audit record**, not a default JSON/YAML format emitted by JMX.

## 11. SOP-JMX-02 — Controlled State Changes

**Trigger:** confirmed need to stop/pause/start an endpoint, e.g., upstream sending continuous malformed data or downstream unable to handle load.

### 11.1. Mandatory Pre-Change

1. Valid **incident or change ID**, clear target, and policy-compliant approver.
2. Select the exact **instance, component, and operation**, verified against `MBeanInfo`.
3. Verify actor authorization and operational readiness; JMX readers do not automatically get invoke rights.
4. Capture a **before snapshot**: state, source age, backlog, in-flight count, error rate, external connections.
5. Assess impact on ingress/egress, users, transactions, retries, and pending data.
6. Define recovery criteria, rollback/restore steps, and next check-in time.
7. Notify app owner/SRE/SOC if there is security risk or production impact.

### 11.2. Execution

- Execute only the approved operation; never experiment with unfamiliar methods.
- Record timestamp/actor/instance/ObjectName/operation **without credentials**.
- Read back MBean state after invoking.
- Verify **real signals**: did source intake stop, queue age, broker consumer assignment, connectivity, and business processing?
- If the outcome is unclear, mark `UNKNOWN`; never retry invocations endlessly.

### 11.3. Post-Change

1. Monitor in-flight messages and remaining side effects.
2. Confirm no data loss or duplicates beyond retry/idempotency contracts.
3. Verify backlog/health over a representative window.
4. Update the incident/change ticket and responsible owner.
5. If stopped temporarily, document **resume conditions and who is authorized to restart**.

## 12. Example: Observe Before Invoking an Operation

Pseudocode for a workflow independent of a hardcoded MBean name:

~~~text
manage_endpoint(request):
    assert authorized_requester(request.actor)
    assert approved_change_or_incident(request.id)

    jvm = resolve_exact_instance(request.instance_ref)
    object_name = discover_target_mbean(jvm, request.component_ref)
    info = read_mbean_info(object_name)

    assert target_component_identity_verified(info, request.component_ref)
    assert requested_operation_is_exposed(info, request.operation)
    assert operation_is_allowed_for_role(request.actor, request.operation)

    before = collect_mbean_and_external_state(request)
    assess_backlog_inflight_and_protocol_risk(before)
    if not safe_to_proceed:
        escalate_and_stop()

    invoke_once_with_approval(request)
    after = read_mbean_and_external_state(request)
    verify_requested_effect(after, request)
    audit_before_after_and_follow_up(request, before, after)
~~~

Never assume `start` or `stop` exists automatically. For production control, invoke operations through an **approved, role-restricted management workflow**, not ad-hoc scripts from unmanaged laptops.

## 13. Control Bus and JMX: Two Distinct Management Paths

Spring Integration also provides **Control Bus**, a pattern sending control messages to a management endpoint inside the application context under permitted configuration. JMX and Control Bus can both support runtime management, yet **they are not the same interface**:

| Management Path | Entry Point | Risk |
|---|---|---|
| **JMX** | MBeanServer / ObjectName / operation | Remote management exposure, invoke permissions |
| **Control Bus** | Control messages via configured channel/handler | Unintended invocations if ingress is exposed or expressions are broad |
| **Dedicated Admin API** | Organization-designed REST/CLI | Authentication, RBAC, auditing, and remote invocation safety |
| **Orchestrator** | Platform-level deployment/replica/consumer control | Multi-instance scope, rollout/race conditions |

Never confuse `Control Bus` with any business inbound `MessageChannel`. If a control channel accepts commands from users or external systems, enforce **authentication, authorization, command allowlists, and never expose arbitrary expressions**. Which path to use depends on your security architecture and policy.

## 14. File Inbound Adapter: Stopping the Poller Does Not Delete Files

A polling File inbound adapter scans a directory, filters files, creates Spring Messages, and sends them to a channel.

### 14.1. What to Verify via JMX and Metrics

- Whether the endpoint/poller reports `running`, if exposed.
- Whether the poller actually ticks and discovers eligible files.
- Whether files are partially written, locked, or already recorded by an accept-once filter.
- Whether the external directory backlog is growing.
- Whether internal queues and outbound handlers finished processing already-ingested data.

### 14.2. On Stop

Stopping the right inbound polling endpoint aims to **halt reading new files**. Source files remain on disk; **never assume** they will process exactly once after restart—that depends on metadata stores, filters, rename/move states, transactions, and deduplication.

### 14.3. After Start

Read back running state, wait at least one representative poll interval, check eligible/accepted file counts, and verify processed/confirmed outcomes at the target. If zero messages arrive, inspect source filters before concluding JMX start failed.

## 15. SFTP Adapter: Remote Sessions and Management Paths

SFTP inbound/outbound involves **session factories**, remote directories, permissions, retries, and file states.

### 15.1. Stopping SFTP Inbound

1. Check for transfers currently in progress.
2. Identify which bean owns polling and session lifecycle.
3. Assess partially copied local files, remote metadata/filters, and temporary files.
4. Stop the poller/endpoint using tested capabilities.
5. Verify no new fetches start; do not assume remote sessions close instantaneously while I/O is active.
6. Upon recovery, verify file completeness, remote rename/handoff, and duplicate acceptance.

### 15.2. When SFTP Outbound Fails

Stopping an outbound handler can cause upstream queues to back up. If forced to pause due to an unstable remote server, consider **throttling/blocking ingress, handling DLQ/retries, and bounding queue capacity**. Never use JMX to “reset” a session by mutating secrets outside the vault/owner workflow.

### 15.3. JMX Does Not Replace Remote Monitoring

An MBean reporting `running` only means the component is considered active. Remote SSH authentication, transfer confirmations, server disk health, and remote file states require SFTP/client telemetry; message counts or history cannot prove successful file transfers.

## 16. HTTP Inbound Gateway and HTTP Outbound Gateway

### 16.1. HTTP Inbound

An HTTP inbound gateway often depends on the web container/router rather than a polling endpoint with `start/stop` on an MBean. Stopping an integration endpoint **does not necessarily stop the HTTP listener** or cause every route to return expected maintenance responses.

For emergency ingress blocking:

- Identify the right control point: web route, gateway, reverse proxy, load balancer, or business handler.
- Pick a mechanism that returns controlled errors, rate-limits traffic, or switches to maintenance mode per policy.
- Never accept requests and silently drop them without clear response semantics.
- Check in-flight HTTP requests, timeouts, and idempotency before reopening.

### 16.2. HTTP Outbound

When outbound HTTP fails, halting handlers or stopping downstream can cause backlogs and retries. A timeout **does not prove** the remote side failed to commit. After reopening, check idempotency keys, request correlation, remote status, and retry budgets.

### 16.3. JMX Operations Differ from Web Routing

Never assume an integration bean's MBean `stop` toggles the entire servlet container or WebFlux handler mapping; test this against your exact app architecture and framework version.

## 17. JMS Inbound/Outbound: Acks and Transactions Matter More Than Running Flags

JMS inbound typically runs via listener containers, consumers, and sessions. Stopping a listener is not equivalent to purging a queue.

| On Runtime Change | What to Verify |
|---|---|
| Stop consumer | Did new intake stop? How were in-flight messages committed/rolled back? |
| Start consumer | Did connections/sessions recover? Are redeliveries occurring? |
| Stop outbound | Where do pending messages go? Are queues/retries/DLQs growing? |
| Connection reset | Were messages redelivered, causing duplicate side effects or locks? |

### 17.1. Verification Sequence

1. Identify which JMS listener container or endpoint is actually being controlled.
2. Check transaction/ack mode and in-flight state.
3. Before stopping, evaluate how much **draining** is needed and set a deadline.
4. After stopping, inspect broker queue depth, consumer count, and un-ACKed/delivery state.
5. After starting, monitor redeliveries, terminal failures, DLQ, and business outcomes.

Never use `isRunning=false` on an MBean to declare “zero messages lost.” Durability depends on the broker, acks/transactions, and business logic.

## 18. AMQP/RabbitMQ: Listeners, Ack/Nack, and Requeue

For Spring Integration AMQP adapters and listener containers, monitor **consumer count, ready/unacked messages, publisher confirms, reconnects, nack/requeue rates, and DLQs**.

### 18.1. Stop and Redelivery

Depending on ack and transaction config, stopping a consumer with in-flight messages may cause the broker to redeliver un-ACKed messages. After starting:

- Verify duplicate delivery handling and idempotent receivers.
- Watch redelivery ratios, DLQs, and poison-message loops.
- Reconcile publisher confirms with consumer outcomes.
- Never scale consumers up indefinitely if schema errors cause every message to nack/requeue.

### 18.2. Do Not Manage the Broker via Assumptions About Adapter MBeans

Stopping an adapter inside one JVM does not alter queue policies, exchanges, routing keys, or consumers on other nodes. Any broker-level changes must go through authorized broker tooling and owners.

## 19. Kafka Inbound/Outbound: Consumer Groups, Lag, and Rebalance

Kafka carries major runtime consequences:

- Stopping a consumer/listener can affect **partition assignments** and trigger rebalances.
- Polled records without committed offsets may be reprocessed.
- Consumer lag rises while a node is stopped if the topic keeps receiving records.
- Producer send success does not mean business consumers processed the record.
- Restarting can trigger retries, replays, or transaction/idempotency conflicts.

### 19.1. Kafka Consumer Runbook

1. Inspect consumer group, topic, partition assignment, lag, and retry/DLQ state using dedicated telemetry.
2. Identify the exact listener/container or integration endpoint under management.
3. Assess impact on other consumers in the group and partition distribution.
4. Choose stop/pause/resume via APIs **actually supported**, without assuming MBeans expose every operation.
5. Check offset commits and in-flight transactions before and after changes.
6. Observe rebalances, lag, throughput, duplicate processing, and data freshness upon restart.
7. Document evidence and owners if backlogs remain unresolved.

### 19.2. Do Not Halt an Entire Group Out of Scope

A JMX invocation on one JVM may affect only a single consumer instance. If an incident requires halting the entire group, coordinate via platform/broker/app orchestration rather than invoking operations blindly across nodes without clear ownership.

## 20. JDBC/Database Inbound: Pollers, Checkpoints, and Transactions

JDBC inbound polling typically selects rows by condition and tracks processed state/checkpoints. On stop/start:

- **Stopping the poller** prevents querying new batches without deleting source rows.
- Already-SELECTed rows may still be processing, updating status, or awaiting commit.
- If a transaction rolls back before marking processed, rows can be re-read.
- As source backlogs grow, monitor watermarks/cursors, oldest row age, and connection pool saturation.
- If the DB connector is timing out, poll retries can add load and lock contention.

### 20.1. Avoid Counting SELECTs as Business Completion

`rows_selected`, `messages_emitted`, `rows_processed`, and `transactions_committed` are distinct milestones. JMX running state only supplements adapter visibility; it does not ensure transactional correctness or idempotency.

### 20.2. JDBC Outbound/Gateway

If an outbound handler stops while inbound keeps running, queues back up. On recovery, watch transaction outcomes, deadlocks, duplicate updates, and record states. Never print raw SQL bind parameters or sensitive row data during investigations.

## 21. MessageChannel and Runtime Manageability

### 21.1. DirectChannel

`DirectChannel` usually dispatches synchronously to subscribers. Send or error counts from instrumentation/JMX measure signals at the channel boundary—they **do not isolate pure network latency** or confirm target commits.

### 21.2. QueueChannel

`QueueChannel` buffers messages for consumers/pollers to retrieve later. Monitor queue depth, capacity, oldest age, and enqueue/dequeue rates. Stopping consumers makes **depth climb**. Stopping upstream does not empty the queue by itself.

### 21.3. ExecutorChannel

`ExecutorChannel` dispatches through an executor. An accepted send does not prove the handler ran. Monitor executor active threads, queue waits, task rejections, and tracing context—not just send counts.

### 21.4. PublishSubscribeChannel

A single send may reach multiple subscribers; stopping one subscriber can leave others running. Track per-branch outcomes and error policies. Never use one channel MBean counter as proof that every branch succeeded.

| Channel | Observation Focus | Limitation of Looking Only at JMX |
|---|---|---|
| Direct | Sends/errors and linked handlers | Downstream latency may sit inside the call path |
| Queue | Depth, consumer state, wait | Does not measure external backlogs |
| Executor | Accepted tasks, executor state | Does not guarantee tasks finished executing |
| Publish-subscribe | Fan-out/subscriber activity | Does not prove all subscribers completed |

## 22. JMX and Polling Lifecycle: When Does Stop Take Effect?

A polling source has at least three layers:

~~~mermaid
sequenceDiagram
    participant O as Operator
    participant MX as MBeanServer
    participant P as Polling Endpoint
    participant S as File / SFTP / JDBC Source
    participant Q as Internal Queue / Channel
    O->>MX: Invoke stop (if authorized)
    MX->>P: Lifecycle operation
    P-->>MX: Operation completed / accepted
    MX-->>O: JMX response
    Note over P,S: An already-started poll may still have in-flight work
    P->>S: No new polls initiated under stopped state
    Q-->>O: Backlog / in-flight work may still exist
    O->>MX: Read state
    Note over O,Q: Verify further with poll/queue/target telemetry
~~~

### 22.1. Distinguish “Operation Return” from “Business Effect”

A successful JMX invocation confirms only that the MBean method ran per its operation semantics. It **does not guarantee**:

- An active poll stopped instantaneously.
- Remote connections closed.
- In-flight messages committed.
- In-JVM queues are empty.
- Other replicas stopped.
- Remote targets stopped receiving data from other sources.

Always perform **readback + external verification** over a window suited to the polling cadence.

## 23. Dynamic Flow Management: Do Not Confuse Lifecycle with Bean Registration

Spring Integration supports dynamic flow registration where appropriate for the version, such as APIs around **`IntegrationFlowContext`**. **Registering/unregistering a flow** differs from `start/stop` on an existing endpoint:

| Action | Conceptual Impact | Note |
|---|---|---|
| **Start endpoint** | Activates a lifecycle endpoint | Does not register new configuration |
| **Stop endpoint** | Halts activity per bean capability | Does not delete definitions or queues automatically |
| **Register flow** | Registers new structure/beans at runtime | Needs IDs, owner, cleanup, and conflict prevention |
| **Remove/unregister flow** | Tears down flow/beans per supported API | May affect in-flight work, references, and resources |
| **Reconfigure flow** | Changes mappings, pollers, or handlers | Requires change/versioning and restart/rollout strategy |

Never use JMX as an ad-hoc backdoor to create/delete flows unless the application **explicitly exposes safe operations** with RBAC and tested teardown.

## 24. Multi-Instance Systems: JMX Is Local State, SLO Is System-Wide

~~~mermaid
flowchart TD
    ROUTE[Load Balancer / Broker / Shared Source] --> A[Integration Instance A]
    ROUTE --> B[Integration Instance B]
    ROUTE --> C[Integration Instance C]
    A --> JA[JMX A]
    B --> JB[JMX B]
    C --> JC[JMX C]
    JA --> OPS[Authorized Operations]
    JB --> OPS
    JC --> OPS
    A --> DATA[Shared Queue / DB / Remote Target]
    B --> DATA
    C --> DATA
~~~

### 24.1. Cluster Traps

1. JConsole connected to node A shows inbound stopped, while B and C keep polling.
2. A Kubernetes pod restarts, and the old `ObjectName` no longer lives in the same JVM.
3. Stopping one Kafka consumer triggers a rebalance, shifting lag/assignments onto remaining consumers.
4. Two SFTP pollers on the same source cause duplicates without shared distributed locks/metadata filters.
5. Cluster-wide aggregate dashboards hide a single failing node.
6. Two on-call operators run stop/start twice concurrently.

### 24.2. Safe Coordination

- Identify **instance/replica/deployment identity** before invoking.
- Enforce clear authorization and **locking/serialization** for changes to the same component.
- Maintain a live inventory of nodes and rollout/restart status.
- Verify both per-instance state and end-to-end flow metrics.
- When stopping an entire service, use proper orchestration instead of guessing node counts.

## 25. JMX vs. Actuator, Micrometer, Health, and Tracing

| Mechanism | Strengths | Limitations |
|---|---|---|
| **JMX/MBean** | Inspects bean metadata and in-JVM management operations | Bean/version-dependent; hard to aggregate cluster-wide |
| **Spring Boot Actuator** | Health/info/metrics/management endpoints over configured transports | Does not replace operations across all Integration endpoints |
| **Micrometer** | Counters, timers, gauges; SLIs/SLOs, alerts, dashboards | Aggregated telemetry; no runtime control by default |
| **Distributed tracing** | Call paths and cross-service latency | Requires propagation/sampling; no control operations |
| **MessageHistory** | Local list of traversed components when enabled | Not a timer, durable audit, or remote confirmation |
| **Structured logs/audits** | Specific errors, actors, decisions, and evidence | Requires sanitization, retention, and access control |

### 25.1. When to Use Metrics Instead of JMX

For throughput, p95/p99, error rates, backlog age, and SLO tracking across multiple instances, time-series metrics are usually better suited. JMX works best as **one specialized signal source or control plane** when MBeans actually expose needed info.

### 25.2. When Do You Need JMX?

When inspecting a specific bean inside a JVM or executing an **approved, supported lifecycle operation**, JMX can be direct and helpful. Avoid enabling remote JMX across every process merely to view counters already exported via Micrometer.

## 26. Securing JMX: Operational Safety First

**Remote JMX can expose internal details and execute sensitive operations.** Left unprotected, it creates a management backdoor outside application workflows.

### 26.1. Mandatory Principles

1. **Never expose JMX/RMI to the public Internet** or untrusted networks.
2. Enforce JVM/platform authentication and authorization restricted to required actors only.
3. Protect transport with TLS or an organization-approved secure admin tunnel.
4. Separate read-only monitoring from invoke/modify permissions; never grant all operations to exporter accounts.
5. Export only needed MBeans, excluding secrets and dangerous operations.
6. Audit connections/invocations per tooling and workflow: actor, instance, target, before/after.
7. Store management credentials/certificates in a secret manager with lifecycle rotation and offboarding.
8. Audit sockets/ports/RMI registry and firewall rules, especially in containers/Kubernetes.
9. Never disable SSL/authentication just so “JConsole can connect.”
10. Alert on JMX usage outside change windows, from unapproved sources, or across unusual instance counts.

### 26.2. Do Not Assume Native JMX Has Fine-Grained RBAC

Per-**MBean, attribute, and operation** authorization depends on the server/access mechanism, proxy/gateway, and security configuration. If native JMX cannot enforce narrow enough permissions, wrap actions in an **admin workflow/service** with allowlisted operations, approvals, and auditing instead of opening broad invoke rights.

### 26.3. Never Put Secrets in MBean Attributes

An MBean can expose Java bean properties. Never export passwords, client secrets, private keys, or sensitive config as readable attributes. For diagnostics, expose flags like `credentialPresent=true`, safe secret version/fingerprint, or last rotation time.

## 27. Auditing and Change Management via JMX

### 27.1. Sample Change Record

~~~yaml
change_id: JMX-CHANGE-EXAMPLE-271
incident_ref: INC-EXAMPLE-271
environment: production
application_ref: invoice-integration
instance_ref: invoice-worker-03
component_ref: invoiceSftpInbound
object_name_ref: approved-jmx-object-reference
operator_ref: iam-integration-oncall
approver_ref: integration-owner
action: STOP_IF_SUPPORTED
reason: downstream-database-overloaded
approved_at: "2026-11-23T15:15:00+07:00"
before:
  running: true
  backlog_age_bucket: 5m-10m
  inflight_category: LOW
applied_at: "2026-11-23T15:20:00+07:00"
after:
  mbean_running: false
  inbound_polls_stopped: VERIFIED
  in_flight_status: TRACKED
  downstream_dependency: STILL_UNAVAILABLE
verification_refs:
  - jmx-readback-271
  - integration-metrics-271
restore_owner_ref: application-oncall
restore_condition: db-healthy-and-backlog-plan-approved
status: CONTAINED_PENDING_RESTORE
~~~

This is a **synthetic example**, not values automatically written by JMX or mandatory field names. Actual `ObjectName`s may contain internal details, so audit records can store an approved reference instead.

### 27.2. Incident Status Is More Than Just “Done”

| Status | Meaning |
|---|---|
| `REQUESTED` | Action requested |
| `APPROVED` | Actor/scope verified and approved |
| `APPLIED` | Invocation executed and returned |
| `EFFECT_VERIFIED` | Intended operational effect verified |
| `RESTORE_PENDING` | Contained, still awaiting restoration |
| `RESTORED_VERIFIED` | Flow restored, target and backlog healthy |
| `EXCEPTION_OPEN` | Insufficient evidence or unresolved risk |

Never close a change simply because JMX returned success. **Restoration** may warrant its own change/decision record.

## 28. When a Stopped Endpoint Restarts with the Application

A real-world hazard: an operator stops an endpoint via JMX, and later the JVM restarts or a deployment rolls out. Depending on lifecycle config, the endpoint may **auto-start back to its initial configuration**.

### 28.1. Questions to Clarify

- Is the stopped state persisted outside the JVM?
- Is there a config flag at the source of truth to disable ingress longer than one JVM run?
- Does startup policy block intake if an incident remains open?
- Might the orchestrator restart the process because a health check fails?
- Who owns verification after a rollout?

### 28.2. Operational Practice

If the pause must persist, **never rely solely on local JMX stop**. Apply durable configuration or managed workflow state with owner, TTL/restore condition, and reconciliation. After any restart, verify actual endpoint state, poll counts, and remote traffic.

## 29. Common JMX Errors and Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| No MBeans visible | Export not enabled, wrong context, wrong JVM | Verify enablement and target process |
| MBeans present, endpoint missing | Bean not exported, wrong ID/version/scope | Inspect bean inventory, `MBeanInfo`, naming |
| Invoke throws `ReflectionException` or signature mismatch | Operation not exported or wrong signature | Read exposed operations/parameter types instead of guessing |
| `InstanceNotFoundException` | Bean/JVM restarted, `ObjectName` changed | Refresh listing, check deployment instances |
| `AttributeNotFoundException` | Attribute absent in `MBeanInfo` | Discover exact attribute name and readability |
| `SecurityException` / access denied | Insufficient permissions or policy block | Follow escalation/approval; never bypass |
| Connection timeout | Firewall, TLS, RMI host/port, JVM down | Check admin channel and process health |
| `stop` returns success yet source keeps emitting | Wrong bean/instance, in-flight work, or another replica | Check per-node state and external telemetry |
| `start` succeeds yet zero messages arrive | Empty source, poller disabled, connection error, filters | Check poll ticks, source age, error logs |
| Duplicates appear after `start` | Unsafe offset/ack/metadata filter/transaction state | Enforce dedupe/idempotency, audit replays |

**Never retry invocations endlessly** when status is unknown. Read back state and capture evidence before retrying or escalating.

## 30. Runbook JMX-03 — “Started, Yet Zero Data Arriving”

1. Verify `start` was invoked on the **right MBean in the right JVM** with supported operations.
2. Read `isRunning` (if exposed); distinguish lifecycle state from connectivity.
3. For polling sources: inspect scheduler, triggers, poller last tick, task executor, and locks.
4. For File/SFTP: inspect file eligibility, filters, remote directory, sessions, and permissions.
5. For JMS/AMQP/Kafka: inspect connection/consumer count, subscriptions, assignments, lag, broker permissions, and error channels.
6. For JDBC: inspect query, watermark/last processed ID, connection pool, transactions, and eligible rows.
7. Verify `MessageChannel`, handlers, and outbound have active subscribers/consumers.
8. Inspect error logs, traces, metrics, and message history if enabled—without dumping raw payloads.
9. Run an approved canary/synthetic event if policy permits to verify end-to-end behavior.
10. Escalate to the owner if state is `running` while business progress remains zero.

## 31. Runbook JMX-04 — “Stopped, Yet Messages Keep Processing”

1. Verify you stopped the **right inbound endpoint**, not a handler/channel by mistake.
2. Check for multiple instances or a second input path feeding the same channel.
3. Distinguish **messages received before stop** from newly ingested messages.
4. Inspect pending `QueueChannel`/executors, broker prefetch, JMS un-ACKed messages, or Kafka polled records.
5. Check mid-flight polls, retry schedulers, or DLQ replays.
6. Determine whether external producers keep sending while the app stopped ingesting, or the app still ingests via another route.
7. Gather per-node evidence; never call stop blindly on unfamiliar MBeans.
8. If active data exposure is underway, coordinate containment at the right layer with Security/Platform.
9. Check whether a restart/rollout auto-started the endpoint again.
10. Close only after verifying ingress/processing semantics match intent and a backlog plan is in place.

## 32. Testing Correctness Before Using JMX in Production

### 32.1. Test Levels

| Level | Scope | Goal |
|---|---|---|
| **Unit/component** | Does the endpoint expose lifecycle and MBean metadata? | Confirm operations actually exist |
| **Integration test** | Start/stop on a representative flow | Verify source/consumer behavior changes |
| **Failure test** | Stop while queue has messages and target fails | Understand in-flight, retries, rollbacks |
| **Restart test** | JVM restarts after stop | Know whether state persists |
| **Cluster test** | Stop one replica while others run | Understand scope and rebalances |
| **Security test** | Read-only operator attempts write/invoke | Verify unauthorized actions are blocked |
| **Audit test** | Invoke via workflow, record before/after | Ensure traceability and investigation readiness |
| **Load test** | Large backlog, slow target, repeated restarts | Identify throughput limits and leftover state |

### 32.2. Sample Test Specification

~~~text
Given:
  - Polling endpoint is exported via JMX in the test environment
  - Source contains 3 valid files; downstream uses a fake handler
  - Test has permission to invoke the discovered operation

When:
  - Stop endpoint per MBeanInfo
  - Wait across a representative poll window

Then:
  - No new polls occur per endpoint semantics
  - No source data is lost
  - In-flight items are clearly classified, not assumed finished

When:
  - Start endpoint again

Then:
  - Polling recovers
  - Files process per retry/dedup contract
  - Flow outcome and audit records are verified
~~~

This is a **test specification**, not an executed test. Never use File adapter test results to assume semantics for a Kafka listener or HTTP inbound gateway.

## 33. Alerts and Operational Metrics Around JMX

### 33.1. Recommended Metrics

| Metric | Question |
|---|---|
| **Endpoint desired vs. actual state** | Is the endpoint in its policy-intended state? |
| **Unexpected stop/start count** | Were changes made outside change/incident windows? |
| **Last poll success age** | Is the poller still executing? |
| **Source pending oldest age** | How long have files/records been waiting? |
| **Channel queue depth/age** | Is backlog accumulating after a stop? |
| **Handler attempts/success/failure** | Is business processing progressing? |
| **Outbound confirmation rate** | Is the target confirming per protocol? |
| **JMS/AMQP unacked/redeliver** | Did stop/start trigger replays? |
| **Kafka lag/rebalance count** | How did consumer lifecycle affect the group? |
| **JMX access/operation audit** | Who invoked what, and did it match time/target? |
| **Restoration overdue** | Is a paused endpoint past its restore deadline without an owner? |

### 33.2. Useful Alerts

- Endpoint **unexpectedly stopped** outside a change window.
- Endpoint **running while poll success age grows high** despite eligible source items.
- Queue age/backlog exceeds deadline after a stop operation.
- Consumer group lag or DLQ spikes after start.
- Unauthorized JMX operations or operations lacking incident references.
- Temporarily stopped endpoint past its **restore deadline**.
- JMX monitoring loses data; distinguish **no data** from `isRunning=false`.

**Never fire P0 pages for approved endpoint stops.** Tie alerts to desired state and change windows.

## 34. Practice Scenarios

### Scenario A — SFTP Inbound Stopped Yet Remote Files Keep Growing

An operator stopped the poller via JMX and observed `isRunning=false`; the partner kept uploading files.

**Analysis:** remote file growth is normal while the partner keeps publishing and local inbound stops polling. Monitor oldest source file age and capacity. When restarting, verify accept-once metadata, file completeness, and downstream business confirmations.

### Scenario B — One Kafka Consumer Pod Stopped, Lag Rises

On-call stopped a Kafka endpoint on node A while the topic kept receiving records and nodes B/C stayed active.

**Analysis:** JMX affected only node A; inspect consumer group rebalances, partition assignments, and total/per-instance lag. Never assume the whole group stopped; cluster-wide maintenance requires orchestrator coordination.

### Scenario C — HTTP Inbound Still Accepts Requests After Stop

A handler's MBean reported stopped, yet the reverse proxy kept sending HTTP traffic to the app.

**Analysis:** handler lifecycle does not necessarily control the HTTP listener or web routes. Check component ownership and apply ingress maintenance/routing policies instead of disabling TLS/SSO verification.

### Scenario D — JMS Redeliveries After Start

A JMS consumer was stopped with in-flight messages; upon restart, the same business event processed again.

**Analysis:** inspect transactions/ack/rollback, idempotent receivers, source redeliveries, and DLQs. An MBean reporting `running` does not guarantee exactly-once behavior; verify business side effects.

### Scenario E — QueueChannel Keeps Filling After Stopping Outbound

An operator stopped the outbound HTTP handler while File inbound kept producing 5,000 messages/minute.

**Analysis:** block/throttle ingress according to plan, monitor queue capacity, oldest age, and in-flight work. On remote timeouts, reconcile outcomes before retrying. Never simply increase heap to hold an unbounded queue.

### Scenario F — An MBean Lacks a `start` Operation

The JMX client lists a handler yet shows no `start` operation.

**Analysis:** it may be a pure processing component rather than a lifecycle endpoint, or the exporter did not expose that operation. Read `MBeanInfo` and locate the right consumer/producer; never try invoking missing operations.

### Scenario G — Stop Loses Effect After Rollout

On-call stopped polling for containment, then a deployment rolling update created new pods that resumed polling.

**Analysis:** local JMX state is non-persistent. Use a source-of-truth disable flag or orchestration procedure, assign a change owner, and verify actual state post-rollout.

### Scenario H — Remote JMX Open Without Authentication

A staging server exposed its JMX port broadly across the network with invoke access enabled.

**Analysis:** trigger a Security review, restrict network and permissions, inspect access logs, and enforce TLS/authn/authz per policy—never leave auth disabled to save admin effort.

### Scenario I — JDBC Poller Stopped Yet DB Rows Still Update

After stopping, a few DB rows still transitioned to `processed`.

**Analysis:** this may be an already-running poll/transaction or another instance processing rows. Check timestamps, row watermarks, node IDs, and commit evidence; do not declare `stop` broken solely from post-invocation updates.

### Scenario J — AMQP Consumer Stopped, Ready Rises While Unacked Drops

An operator observed ready messages rising and unacked messages falling after stopping.

**Analysis:** this can reflect the consumer halting intake while the broker settles in-flight deliveries; check ack/nack/requeue behavior, queue state, and other consumers. Never interpret a single gauge as lost messages.

### Scenario K — MBean Counts Look Healthy Yet Users Receive No Data

JMX send count climbed and `isRunning=true`, while an outbound HTTP gateway received no remote replies.

**Analysis:** send counters measure only part of the flow. Inspect HTTP status/timeouts, circuit breakers, retries, remote audits, and business confirmations. `Running` is not an end-to-end SLO.

### Scenario L — Two Operators Invoke Concurrently

One operator stopped inbound to investigate while another started it because the dashboard showed errors.

**Analysis:** enforce change serialization/ownership, incident bridges, auditing, and desired-state tracking. Never let two automations or operators fight each other via JMX without locks/reconciliation.

## 35. Quick Operations Checklist

### 35.1. Before Reading JMX

- [ ] Correct JVM, instance, environment, and deployment version?
- [ ] JMX channel secured; never exposed publicly?
- [ ] Read `MBeanInfo` instead of assuming attributes/operations?
- [ ] Mapped `ObjectName` to the exact component ID and flow?
- [ ] Distinguished lifecycle, connectivity, and business progress?

### 35.2. Before Invoking

- [ ] Valid incident/change ID, approval, and actor authorization?
- [ ] Exact operation verified as exported and impact on the endpoint understood?
- [ ] Assessed in-flight messages, queues, transactions, acks/offsets, and retries?
- [ ] Clarified scope: single instance vs. full cluster?
- [ ] Captured before snapshot, restore conditions, owner, and deadline?
- [ ] Coordinated with App Owner/SRE/Security if production is impacted?

### 35.3. After Invoking

- [ ] Read back MBean state; checked whether result is `UNKNOWN`?
- [ ] Confirmed poll/listener/consumer/connection actually changed as intended?
- [ ] Checked for remaining source/queue/broker backlogs or in-flight work?
- [ ] Checked Kafka rebalances, JMS/AMQP redeliveries, and DB transactions where relevant?
- [ ] Verified target/business confirmation evidence?
- [ ] Recorded actor/time/target/operation/before/after in audit?
- [ ] If paused temporarily, assigned owner and time to restart?
- [ ] Ensured desired state survives JVM restarts if required?

## 36. Summary

**Managing runtime endpoints with JMX** gives operations deep visibility into Spring Integration components inside a JVM and, when MBeans expose suitable operations, lets them adjust lifecycles without restarting the whole application. JMX's value lies in **inspecting the right bean, verifying true state, and controlling the right scope**—not merely being able to call a `start` or `stop` method.

In the **Spring Integration Adapters** module, File, SFTP, HTTP, JMS, AMQP, Kafka, and database flows each have distinct **ingestion, acknowledgment, retry, transaction, and connection semantics**. A successful MBean operation is only the first step: reconcile MessageChannels, pollers, consumers, backlogs, in-flight work, broker/remote state, and business outcomes. Combining **role-restricted JMX + Micrometer metrics + logs/tracing + MessageHistory + destination readback**, alongside owned change, audit, and restoration workflows, provides a safe and verifiable way to manage runtime endpoints.
