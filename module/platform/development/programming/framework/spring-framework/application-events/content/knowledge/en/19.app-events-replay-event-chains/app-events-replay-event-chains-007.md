# Preventing Event Publishing Loops in Spring Application Events

## 1. Problem Statement: An Event Chain Can Loop Back to Itself

In Spring Framework, `ApplicationEventPublisher` helps beans coordinate through events instead of calling each other directly. A normal flow might look like:

~~~text
OrderCreated -> OrderValidated -> NotificationScheduled
~~~

Trouble starts when a listener receives an event and **re-publishes the same event or an event that leads back to an earlier step**, forming a cycle:

~~~text
A -> B -> C -> A -> B -> C -> ...
~~~

Under the default synchronous configuration, calling `publishEvent(...)` from a listener causes **nested listener calls on the same call stack**. Without a stopping condition, the application can hit `StackOverflowError`, prolonged transactions, log spikes, or failed use cases. Moving to async processing or a broker may stop the call stack from growing immediately, yet the loop turns into an **event storm**, causing queues, CPU, memory, or processing costs to grow without bound.

This lesson belongs to **Replay and Event Chains** and focuses on stopping loops at the right boundary rather than treating symptoms by increasing thread pools or throttling logs.

By the end of this lesson, you should know:

- The paths that cause follow-up events to be published in Spring and why loops occur.
- Differences between synchronous recursion, asynchronous feedback, and redelivery/retries.
- How to block loops using **business rules**, **visited-state/cycle detection**, **hop budgets**, **idempotency**, and **correlation/causation IDs**.
- How to write a runnable Java 17+ example with `ApplicationEventPublisher` and `@EventListener`.
- Limitations of each safeguard, system observability, and loop testing strategies.

## 2. Mechanisms That Emit Sequential Events in Spring

### 2.1. A Listener Actively Publishing a New Event

Spring allows a listener to inject `ApplicationEventPublisher` to continue a processing flow:

~~~java
// Illustration: types A, B, and the Spring bean must be defined separately.
@Component
public class StageListener {
    private final ApplicationEventPublisher publisher;

    public StageListener(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @EventListener
    public void onA(A event) {
        publisher.publishEvent(new B(event.processId()));
    }
}
~~~

This is a valid way to build an event chain **when the flow has a terminal point**. If another listener receives `B` and emits `A` for the same process, the path becomes `A → B → A`.

`ApplicationEventPublisher.publishEvent(...)` is a **handoff** to the multicaster mechanism. It does not check whether this event was already handled, nor does it resolve loops on its own. With the default `SimpleApplicationEventMulticaster`, normal listeners receive events on **the publishing thread**; each nested publish deepens the call stack.

### 2.2. `@EventListener` Methods Returning an Event

This is an easily overlooked source of loops. An `@EventListener` method returning a **non-`void`** value can cause Spring to treat that return value as a **new event**. If it returns a collection or array, each element can also be published as a separate event.

~~~java
// Anti-pattern illustration only, DO NOT run:
@EventListener
public Ping onPing(Ping event) {
    return event; // Spring can automatically republish Ping itself!
}
~~~

If `Ping` is received again by `onPing`, a loop can be created **without a single `publisher.publishEvent` call in the method body**.

Do not return the same event type just to “return a result” to the publisher. To return a synchronous result to a caller, use an ordinary service method or a contract suited to the actual requirement; if you intentionally emit a follow-up event, ensure a clear stopping condition exists.

**Note:** publishing events via the return value of `@EventListener` is not supported for asynchronous `@Async` listeners. Inside an async listener, to produce a follow-up event, inject `ApplicationEventPublisher` and publish explicitly. That does not mean async prevents loops automatically.

### 2.3. Indirect Cycles Across Multiple Listeners

It is not only `A → A`. Example:

~~~text
OrderCreated
  -> InventoryReserved
      -> OrderUpdated
          -> OrderCreated
~~~

A listener may have no idea that the event it emits triggers itself at another layer. The more modules and listeners there are, the harder cycles are to spot without flow diagrams and trace metadata.

### 2.4. Loops from Integration, Retries, or State Feedback

Some loops do not live on a single call stack:

- Service A sends `CustomerUpdated` to B; B syncs data back to A; A sees a change and sends `CustomerUpdated` again.
- A consumer retries a poison message indefinitely; each failure recreates the same work.
- A webhook receives an update and calls an API that causes the system to emit the webhook again.
- A listener rewrites an entity even though the actual data did not change; a persistence hook or CDC emits the event again.

These cases require **idempotency**, business-transition checks, retry limits, and durable deduplication; an in-JVM `ThreadLocal` guard cannot solve a cycle spanning multiple services.

## 3. Why Is Infinite Recursion Dangerous?

### On the Default Synchronous Multicaster

Suppose `A` is published and callback A creates B. The synchronous dispatcher invokes B before callback A returns. If B creates A again, the stack looks like:

~~~text
publish(A)
  onA(A)
    publish(B)
      onB(B)
        publish(A)
          onA(A)
            ...
~~~

Impacts can include `StackOverflowError`, multiplying side effects, long-held transactions, prolonged database locks, or hung requests. **Increasing the stack size is not a fix**; it only lets the loop run a few extra steps before still failing.

Exceptions from synchronous listeners (under the default setup without a swallowing error handler) can propagate back to the publisher. If the publisher is inside an `@Transactional` transaction, it can also roll back the use case. `StackOverflowError` is an `Error` and should not be treated as a business error to catch and “ignore”.

### When Using `@Async`, Executors, or Message Brokers

Asynchronous flows may not grow the call stack that way, yet still cause:

- Events continuously generating new events, driving up queue backlogs and latency.
- Wasted CPU, DB connections, and network calls.
- The same event being processed repeatedly, producing duplicate emails/payments/records.
- Retries “waking up” existing cycles; delivery counts multiply across consumers.

Switching to async **changes the failure mode** rather than removing the loop cause. When hopping across threads, `ThreadLocal`, transaction context, and MDC do not follow automatically, making `ThreadLocal`-based guards even less reliable for controlling distributed chains.

## 4. Solution 1 — Block at Business State Transition Rules

Often the best safeguard is **never publishing a new event if state did not genuinely change**.

For example, an `Order` may only transition `CREATED → VALIDATED → APPROVED`. If a listener receives `APPROVED` and calls `approve()` again, the domain model should reject it or treat it as idempotent and **not emit another `OrderApproved`**.

~~~java
// Illustrative domain logic, not a standalone program.
public boolean approve() {
    if (status == Status.APPROVED) {
        return false; // No transition, no new event emitted.
    }
    if (status != Status.VALIDATED) {
        throw new IllegalStateException("Invalid state transition");
    }
    status = Status.APPROVED;
    return true;
}
~~~

The application service publishes the event only when the method returns `true` (or the aggregate records a valid new event). This rule stops loops at the **emission source**, not just in listeners.

Watch out for:

- If business rules permit returning to the same state (e.g., `REVIEW → DRAFT → REVIEW`), blocking solely by state name is too coarse. Guard **specific transitions**, aggregate version, and **a real business action**.
- Checking and updating state must stay consistent under concurrency; with databases, use optimistic locking, unique constraints, or proper transactions.
- `@EventListener(condition = "...")` can filter events before invoking a listener, but condition expressions do not replace invariant checks in the domain model.

## 5. Solution 2 — Track Visited Steps Within the Same Chain

When executing a finite event chain, you can attach metadata **per processing chain**:

- `flowId` or `correlationId`: identifies the same chain.
- `step`: current processing step.
- `visited`: set of steps or transition keys already traversed in the chain.
- `hop`: number of transitions from the initial event to the current event.

Before publishing the next event, the listener checks:

1. Is the next step already in `visited`?
2. Has `hop` reached the limit?
3. Is this transition valid under the current workflow?

If a blocking condition triggers, stop publishing and emit structured logs/traces. **Metadata must travel with the event** if the chain can cross threads/processes; a global variable or static set will cause independent workflows to interfere with one another.

### Limitations of `visited`

`visited` by step name fits **workflows where steps must not repeat**. It does not fit problems with legitimate business loops such as “retry the VERIFY step up to three times”. In those cases, use **transition keys**, `attempt`, version, or a state machine with bounded repeat rules rather than banning all returns to the same state.

Do not let the `visited` set grow unbounded inside events sent over a broker. For long chains, replace it with compact state flags and a step budget; full trace storage belongs in the observability system.

## 6. Solution 3 — Limit the Number of Hops (Hop Budget)

Even before spotting an explicit cycle, each event can carry a **hop count** as a safety ceiling:

~~~text
hop = 0 : OrderCreated
hop = 1 : OrderValidated
hop = 2 : InventoryReserved
...
hop = max : STOP, do not publish further
~~~

Rule: **every time a child event is emitted, `hop` must increment by exactly 1**, and `maxHops` must have a finite bound. For the initial event, `hop=0`.

A hop limit is a **secondary defense layer**, not a sufficient business condition to declare “success”. If a valid workflow is stopped at the hop limit, emit an observable error signal rather than silently treating it as complete.

In distributed systems, the hop budget must be preserved when moving to message envelopes or an outbox, avoiding each service resetting it to 0 so cycles never reach the limit.

## 7. Runnable Java 17+ Example: Two-Layer Loop Guard

This project uses **Spring Framework 6.2.12**, JDK 17+, and Maven. No Spring Boot or database is needed.

The flow is intentionally designed with a cycle:

~~~text
CREATED -> VALIDATED -> NOTIFIED -> CREATED
~~~

Without guards, the listener receives CREATED and produces VALIDATED; receives VALIDATED and produces NOTIFIED; receives NOTIFIED and produces CREATED again, repeating forever.

The program enforces **two independent conditions**:

1. If the next step already appears in `visited`, print `stop cycle` and do not publish.
2. If `hop >= MAX_HOPS`, print `stop hop limit` and do not publish.

A Java record copies `visited` into an immutable set so no mutable set is shared across listeners. The second example intentionally feeds an event whose hop budget is already exhausted to demonstrate the limit guard.

Create the structure:

~~~text
spring-event-cycle-guard/
├── pom.xml
└── src/main/java/demo/EventCycleGuardDemo.java
~~~

### 7.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>spring-event-cycle-guard</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 7.2. `src/main/java/demo/EventCycleGuardDemo.java`

~~~java
package demo;

import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class EventCycleGuardDemo {

    public record FlowEvent(
            String flowId,
            String step,
            int hop,
            Set<String> visited) {

        public FlowEvent {
            if (flowId == null || flowId.isBlank()) {
                throw new IllegalArgumentException("flowId is required");
            }
            if (step == null || step.isBlank()) {
                throw new IllegalArgumentException("step is required");
            }
            if (hop < 0) {
                throw new IllegalArgumentException("hop cannot be negative");
            }
            if (visited == null || !visited.contains(step)) {
                throw new IllegalArgumentException("visited must contain step");
            }
            visited = Set.copyOf(visited);
        }
    }

    public static class GuardedFlowListener {
        private static final int MAX_HOPS = 3;
        private final ApplicationEventPublisher publisher;

        public GuardedFlowListener(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        @EventListener
        public void handle(FlowEvent event) {
            System.out.println(
                "receive " + event.flowId()
                + " " + event.step()
                + " hop=" + event.hop());

            String next = switch (event.step()) {
                case "CREATED" -> "VALIDATED";
                case "VALIDATED" -> "NOTIFIED";
                case "NOTIFIED" -> "CREATED"; // Intentionally creates a cycle.
                default -> null;
            };

            if (next == null) {
                return; // No next step.
            }

            // Guard 1: each step in this flow can only be visited once.
            if (event.visited().contains(next)) {
                System.out.println(
                    "stop cycle " + event.step() + " -> " + next);
                return;
            }

            // Guard 2: limit chain length, even without repeating steps.
            if (event.hop() >= MAX_HOPS) {
                System.out.println(
                    "stop hop limit " + event.step() + " -> " + next);
                return;
            }

            Set<String> newVisited = new LinkedHashSet<>(event.visited());
            newVisited.add(next);

            publisher.publishEvent(new FlowEvent(
                event.flowId(), next, event.hop() + 1, newVisited));
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public GuardedFlowListener guardedFlowListener(
                ApplicationEventPublisher publisher) {
            return new GuardedFlowListener(publisher);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            context.publishEvent(new FlowEvent(
                "flow-1", "CREATED", 0, Set.of("CREATED")));

            // Simulates an envelope that has already exhausted its hop budget.
            context.publishEvent(new FlowEvent(
                "flow-2", "CREATED", 3, Set.of("CREATED")));

            System.out.println("finished");
        }
    }
}
~~~

Run from the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.EventCycleGuardDemo
~~~

Lines printed by **the program itself**:

~~~text
receive flow-1 CREATED hop=0
receive flow-1 VALIDATED hop=1
receive flow-1 NOTIFIED hop=2
stop cycle NOTIFIED -> CREATED
receive flow-2 CREATED hop=3
stop hop limit CREATED -> VALIDATED
finished
~~~

Some environments may show additional Maven/Spring logs. The stdout block above shows only the lines printed by `System.out` in the example.

### 7.3. Why Is the Output Deterministic?

- `flow-1` starts at CREATED with `visited={CREATED}` and `hop=0`.
- The listener receives CREATED, sees VALIDATED is not yet in `visited` and `hop` has not reached 3, so it publishes VALIDATED with `hop=1`.
- The listener continues by publishing NOTIFIED with `hop=2`.
- At NOTIFIED, the next step would be CREATED, but CREATED already exists in `visited`, so `stop cycle` is printed and the chain halts.
- `flow-2` starts with `hop=3`, and `visited` does not yet contain VALIDATED. The visited check does not block it, but `MAX_HOPS=3`, so `stop hop limit` is printed.
- With the default synchronous multicaster, both chains finish before `main` prints `finished`. There is no `Thread.sleep` or race condition in the example.

The example intentionally uses one generic `FlowEvent` with a `step` field so the cycle is easy to observe. In production code, business events should have **explicit types** (such as `OrderCreated`, `OrderValidated`) and explicit transitions/state machines; there is no requirement to collapse all events into a single stringly typed class.

### 7.4. Why Must `visited` Be Copied?

If the same mutable `HashSet` were passed across multiple events, another listener could mutate the event history, especially when `@Async` or multiple subscribers are enabled. The record constructor uses `Set.copyOf` to protect the payload. Before each new event, the listener creates a `LinkedHashSet` from the old `visited`, adds the new step, and constructs a new record.

The example structure is a **per-event snapshot**, with no global state and no cross-talk between two distinct flows.

## 8. Solution 4 — Event ID and Idempotent Processing

`visited`/hop stops **infinite recursive call chains**, yet does not solve the case where the same event is delivered **multiple times** (retries, redelivery, consumer restarts).

A practical event envelope can carry:

~~~java
// Data illustration: not a standalone program.
public record EventEnvelope<T>(
        String eventId,
        String correlationId,
        String causationId,
        String aggregateId,
        long aggregateVersion,
        int hop,
        T payload
) {}
~~~

- **eventId:** identifies a single event occurrence. Redelivery of the same event should keep the same ID for deduplication.
- **correlationId:** ties together events within the same business flow/request.
- **causationId:** identifies which event or command directly caused the new event.
- **aggregateId/version:** helps subscribers validate current state, ordering, and stale updates.
- **hop:** chain-length budget; a child event uses its parent's hop plus 1.

Do not expect distinct `eventId` values to detect loops by themselves: an A→B→A cycle normally mints a **new ID for each event**. Detecting cycles requires examining **causality/transitions** or workflow state, not merely duplicate `eventId` values.

For durable consumers, one idempotency pattern is inserting `(consumerName, eventId)` into a table with a **unique constraint** in the same transaction as the side effect. When the same event is reprocessed, a duplicate key or processed-state check skips the side effect; a non-atomic check-then-insert is prone to race conditions. For HTTP webhooks, an equivalent idempotency key can be used.

Example SQL schema:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Depending on the database, perform the idempotent insert and business update within the same transaction; if either fails, both roll back together.

## 9. Solution 5 — Forbid No-Op Feedback and Coordinate with a State Machine

A classic root cause of loops is modules reacting simply because **“an event exists”** without checking **“did the data actually change?”**:

~~~text
InventoryUpdated -> OrderSync -> InventoryUpdated -> ...
~~~

Business-layer solution:

1. The listener reads the current state/version.
2. Computes the desired state.
3. If the desired state **equals the current state**, stop and **do not emit a new event**.
4. If a valid transition genuinely occurs, commit the change and emit only the event describing that transition.
5. Use versioning/optimistic locking or appropriate locks to handle concurrent updates.

For multi-state workflows, declare a finite state transition graph:

~~~text
CREATED --validate--> VALIDATED --approve--> APPROVED
                      |
                      +--reject--> REJECTED
~~~

If a callback after APPROVED requests CREATED for the same version without an explicit rollback rule, the state machine rejects it. When a business loop must be allowed (such as resubmitting a review request), include `revision`, `attempt`, or `cycleNumber` in state and bound the count.

In multi-service systems, consider an **orchestrator/process manager** instead of letting every listener emit arbitrary events. The orchestrator defines state transitions, timeouts, compensation, and completion criteria; events simply report steps that occurred.

## 10. Solution 6 — Prevent Loops Across Brokers, Webhooks, and Retries

For integration events, additional safeguards are usually necessary:

| Cause | Safeguard |
| --- | --- |
| A syncs data to B, B sends the same update back to A | `originService`, `correlationId`, entity version, and real-change check |
| Consumer hits a poison message and retries infinitely | Retry limit, backoff, dead-letter queue, alert |
| Broker redelivers the same event | Idempotency key and processed-event store |
| Webhook echoes back a change it created itself | Source marker + version, avoid re-creating the same transition |
| Event chain exceeds expectations | Propagate `hop`/TTL, enforce max limit, and log block reason |
| Two publishers simultaneously emit the same transition | Transaction, unique constraint, optimistic locking |
| Relay sends message successfully before marking outbox | Idempotent consumer, explicit relay state |

**Transactional outbox** (writing events to send in the same transaction as business data, with a relay publishing after commit) prevents message loss on process crashes. However, an outbox **does not by itself prevent loops**; if consumers keep emitting infinite feedback events, an outbox can make the cycle **durable and longer-lived**. You still need state machines, deduplication, and hop budgets.

With `@TransactionalEventListener(AFTER_COMMIT)`, events are handled after commit, but the annotation **has no cycle-detection capability** and is not a replayable message queue. Reaction chains spanning multiple transactions can still loop back to step one if code keeps creating invalid business transitions.

## 11. Designing Guards by Scope

No single guard fits all systems. Choose guards based on **the unit you want to protect from looping**:

| Scope | Appropriate key/metadata | What it prevents |
| --- | --- | --- |
| Within a single method/call stack | Local visited set, recursion depth, state transition | Immediate self-republication |
| Within a single flow/request | correlationId, visited transitions, hop budget | Event loops across multiple listeners/threads |
| On a single aggregate | aggregateId, version, valid state transitions | Re-applying the same business change |
| Per delivery | consumerName + eventId | Redelivery/retry of the same event |
| Across multiple services | correlation/causation, origin, version, TTL, outbox + idempotency | Echo loops and retry storms |

Important note: **a global static set storing every event ever seen is not a solution**. It can mistakenly block new workflows, leak memory, and fail when the application runs across multiple instances. If history must be retained, define keys and retention TTLs by business rules; use distributed storage when multiple instances process events concurrently.

## 12. Observability and Incident Response

Event loops are usually caught early via metrics/tracing when every event carries metadata:

- Log `eventType`, `eventId`, `correlationId`, `causationId`, `aggregateId`, `hop`, and outcome `processed/skipped/blocked`.
- Measure published event counts and child events generated per input event (**fan-out**).
- Alert when a `correlationId` accumulates too many events, abnormal hop counts, or rapid repeated state transitions.
- Monitor queue backlogs, retry counts, DLQs, CPU/thread pools, and transaction latency.
- When blocking occurs, log the reason `cycle_detected`, `hop_limit`, `duplicate`, or `invalid_transition`; never swallow business errors silently.
- Use tracing span links to represent causal relationships when events cross async boundaries or brokers.

During a production loop incident, the safe move is throttling at **the publishing source or feedback-emitting consumer**, tracing the correlation/causation chain, and fixing the event-emission rule. Merely turning off logging or scaling up workers hides symptoms and increases system pressure.

## 13. What Scenarios Should Be Tested?

### Synchronous Tests

- Publish CREATED and verify each step CREATED → VALIDATED → NOTIFIED runs exactly once.
- Verify NOTIFIED does not re-emit CREATED once `visited` already contains it.
- Verify the chain terminates and the caller returns; no `Thread.sleep` needed.
- Set `hop` to max and verify no child event is emitted.
- Send two independent `flowId`s to ensure one flow's `visited` does not block the other.

### State Machine and Concurrency Tests

- When a command does not alter state, assert **no new event is published**.
- When an aggregate is already APPROVED, repeating approve does not emit another pointless `OrderApproved`.
- When two requests process the same aggregate/version concurrently, verify optimistic locking or unique constraints prevent emitting two conflicting transitions.
- Test workflows with **valid** bounded loops (limited attempts), avoiding overly naive `visited` checks that break business behavior.

### Async and Integration Tests

- Enable an executor for applicable listeners and verify `hop`/correlation propagate across threads.
- With a broker, simulate redelivery of the same `eventId` and assert side effects execute only once.
- Simulate a poison message; after finite retries, verify it moves to a DLQ without spawning infinite feedback events.
- With an outbox, verify crashes/restarts neither drop messages nor re-trigger already-idempotent side effects.
- For bidirectional webhooks, verify origin markers and versions prevent echo loops.

## 14. Common Mistakes

| Mistake | Consequence | Proper practice |
| --- | --- | --- |
| `@EventListener` returns the same event to “return a result” | Spring republishes it, risking infinite recursion | Use `void` for callbacks that emit nothing; return new events intentionally with a stopping point |
| A emits B, B emits A with no guard | Stack overflow or event storm | State machine, visited transitions, hop budget |
| Switching to `@Async` thinking it fixed the loop | Merely turns recursion into a queue storm | Stop the loop at the source and propagate metadata across threads |
| Deduplicating solely by `eventId` | Each loop iteration mints a new `eventId`, so the cycle continues | Check correlation/transitions/state |
| Blocking all events of the same name across the whole JVM | Blocks unrelated flows and leaks memory | Guard per flowId/aggregate/version with TTL |
| Limiting hops without alerts | Valid workflows are silently cut short, masking bugs | Report blocked status and investigate |
| Retrying poison messages infinitely | Queue backlog and duplicate side effects | Bounded retries, backoff, DLQ |
| Thinking `@Order` eliminates loops | Order only sorts priority; it does not remove A→B→A edges | Fix the state graph and publish conditions |
| Believing `AFTER_COMMIT`/outbox prevents feedback loops | Cycles can span multiple transactions | Idempotency, state machine, and hop/TTL |

## 15. Application Checklist

1. Who emits which event? Draw the **event type → listener → new event** graph and look for cycles.
2. Does each new event represent a **genuine state change**?
3. Is there a terminal step or invariant preventing return to an invalid state?
4. Do events carry `correlationId`, `causationId`, `eventId`, and `hop` where needed?
5. Are cycle guards scoped to the **right flow/aggregate**, not a global static set?
6. Is the hop limit propagated across executors/brokers and logged when triggered?
7. Are consumers idempotent on redelivery of the same `eventId`?
8. Do retries have max attempts, backoff, DLQ, and monitoring?
9. Does any code accidentally use `@EventListener` return values to re-emit the same event type?
10. Do tests prove termination under both synchronous and asynchronous modes?

**Conclusion:** Preventing event publishing loops in Spring does not mean “never let listeners publish other events”; it means ensuring **every transition edge is domain-meaningful, every chain is bounded, and every processing step is loop-resistant**. Build on state machines and idempotency; add visited/hop budgets, trace metadata, bounded retries, and alerts so a valid event never turns into an infinite feedback loop.

## Official References

- Spring Framework 6.2 — ApplicationContext events, synchronous listeners, `@EventListener` return values, and `@Async`: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework 6.2 — `@EventListener` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/EventListener.html
- Spring Framework 6.2 — `ApplicationEventPublisher` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework 6.2 — `SimpleApplicationEventMulticaster` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework 6.2 — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
