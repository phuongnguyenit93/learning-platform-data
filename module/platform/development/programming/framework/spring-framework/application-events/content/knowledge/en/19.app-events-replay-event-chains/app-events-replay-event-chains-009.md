# When to Use Orchestration Instead of Event Chains in Spring Framework

## 1. Problem Statement

In a system using **Spring Framework Application Events**, you can connect processing steps with an **event chain**: a listener receives event A and publishes or returns event B; a listener receiving B emits event C. This style can be concise, loosely coupled, and suitable for multiple independent reactions.

However, when a process has **mandatory ordering**, **an overall outcome that must be confirmed**, **timeouts**, **retries**, **compensation**, or **state that must recover after an application restart**, scattering logic across listeners can erase any single owner responsible for the whole workflow. In such cases, **orchestration** is usually the clearer and safer choice.

**Orchestration** means a **workflow coordinator** (an application service, process manager, saga orchestrator, or durable workflow engine) owns the state and decides **what step runs next**, **completion conditions**, and **how failures are handled**. It can use **direct calls**, **commands**, **events**, and **message brokers** alike. Therefore, orchestration **is not opposed to event-driven architecture**; the difference is **who owns coordination authority and business outcomes**.

Quick comparison:

~~~text
EVENT CHAIN / CHOREOGRAPHY
OrderSubmitted
      |
      v
PaymentListener -> PaymentCaptured
                       |
                       v
               StockListener -> StockReserved
                                    |
                                    v
                             ShippingListener
(Each listener only knows part of the journey)
~~~

~~~text
ORCHESTRATION
CheckoutWorkflow (owns progress)
      |
      +-- reserveStock()
      |       |
      +-- chargePayment()
      |       |
      +-- scheduleShipment()
      |       |
      +-- COMPLETED -> publish OrderFulfilled
      |
      +-- error? retry / compensate / manual review
(Order, conditions, and outcome are described in one place)
~~~

For example, checkout is considered successful only when reserving stock, charging payment, and scheduling shipment all succeed. If payment succeeds but shipping fails, something must decide whether to **refund**, **retry**, or **move to manual review**. That is a classic orchestration requirement.

## 2. Distinguishing Event Chains, Choreography, Orchestration, and Sagas

### 2.1. Domain Event

An **event** expresses a fact that has occurred, such as **OrderConfirmed**, **PaymentCaptured**, or **ShipmentScheduled**. An event can have multiple subscribers. One subscriber does not inherently own control over other subscribers.

A **command** such as **ReserveStock** or **ChargePayment** requests an action to be performed. This distinction matters in workflows: an orchestrator typically issues commands and awaits results rather than assuming publishing an event means the next step has definitely finished.

### 2.2. Event Chain

An **event chain** consists of sequential events: A triggers a listener, the listener produces B, B triggers another listener. In Spring, a synchronous **@EventListener** method can **return an object** for Spring to publish as a new event; **returning a Collection/array** publishes each element separately; **returning null/void** creates no new event from the result.

Illustrative example:

~~~java
@EventListener
public PaymentRequested onOrderSubmitted(OrderSubmitted event) {
    return new PaymentRequested(event.orderId());
}
~~~

This is only an **illustrative snippet**; it requires event types, imports, and a Spring-managed bean. Return-value chaining **is not supported for asynchronous @EventListener**; when a listener runs async, emitting follow-up events requires calling **ApplicationEventPublisher.publishEvent(...)** explicitly.

A pure in-process event chain **does not automatically provide** persistent state, durable delivery, retries, compensation, or transactional atomicity.

### 2.3. Choreography

**Choreography** is a style where components coordinate via events/messages without a central coordinator deciding every step. Each participant knows on its own when to react. Choreography scales well when components are independent, yet workflows spanning many services easily lose global visibility without careful correlation, state, and observability design.

### 2.4. Orchestration

**Orchestration** places **workflow state** and **transition rules** in one component. It decides **which command to send**, **which outcomes to await**, **when to time out**, **which steps to compensate**, and **when to report succeeded/failed/in-progress**.

Orchestration can use a synchronous Spring application service for small processes or a durable saga/workflow engine for processes spanning many services. Calls do not all have to be synchronous HTTP; an orchestrator can still consume and emit events over a broker.

### 2.5. Saga

A **saga** coordinates a sequence of **local transactions** across multiple components, with **compensating actions** when recovery is needed. Sagas can be implemented via orchestration or choreography. Compensation **is not a global ACID rollback**: a refund is a compensating transaction offsetting a charge that already happened, not erasing the original transaction from history.

## 3. Signs You Should Move from Event Chains to Orchestration

### 3.1. Mandatory Ordering and Preconditions

If **you must not charge unless stock is reserved**, or **you must not create a shipment until payment succeeds**, ordering is not just listener dispatch priority—it is a **business invariant of the use case**. When there are multiple branching conditions and participant outcomes, an orchestrator expresses those rules directly.

**@Order** in Spring only helps prioritize dispatch among listeners in matching contexts; it does not create a workflow engine, store state, or guarantee completion order for asynchronous work.

### 3.2. A Single Point Accountable for the Outcome

A checkout or job-scheduling API needs to answer clearly:

- **COMPLETED**: all mandatory steps confirmed succeeded.
- **REJECTED/FAILED**: use case rejected or deterministically failed.
- **PENDING**: request accepted, with steps still in progress.
- **COMPENSATING**: a step failed and the system is compensating.
- **MANUAL_REVIEW**: cannot decide or recover automatically.

Merely publishing **OrderSubmitted** and returning **200 OK** does not mean the whole chain succeeded, especially when steps run asynchronously. For long workflows, an API can return **202 Accepted** and a **workflowId**; clients poll a status endpoint. 202 only confirms the request was accepted under contract, not the final outcome.

### 3.3. Failures, Retries, and Timeouts Need Coordination

Suppose a payment provider times out after receiving a charge request. We do not know whether the card was charged:

~~~text
Orchestrator -> PaymentProvider: charge(orderId, attemptId)
                       |
                       x timeout
                       |
          Unknown whether provider charged or not
~~~

If a listener blindly retries with a new request ID, the customer can be double-charged. An orchestrator needs a **stable idempotency key**, the ability to **query an attempt's status**, retry/backoff limits, and an **UNKNOWN** handling branch. A chain of callbacks does not solve this on its own.

### 3.4. Multiple Compensating Steps Exist

After reserving stock and charging, if shipping is rejected, the system must decide to **refund payment** and then **release stock**. If the refund fails, it must persist **COMPENSATING** state to retry rather than recording “fully rolled back”.

The orchestrator knows which steps were confirmed and decides compensation in the right order. Never let a random listener guess that all preceding steps succeeded.

### 3.5. Resume, Audit, and Operational Support Are Needed

A workflow may run for minutes, days, or across deployments. If the process dies, you must persist **workflowId**, **currentStep**, **attempts**, **deadline**, **lastError**, **step outcomes**, and next actions to take.

A durable orchestrator or workflow engine persists state and recovers; an in-memory event chain inside one ApplicationContext cannot do that on its own. Choreography can also be durable if every service maintains proper state, outbox/inbox, and monitoring; orchestration usually makes ownership easier to establish.

## 4. When Is an Event Chain Still the Better Solution?

Do not turn every reaction into an orchestration step. **Event chains/choreography** fit when handlers are **independent of the core business outcome**:

- Order confirmed; analytics updates reports.
- Search index receives the event and updates a projection.
- Cache invalidation reacts to state changes.
- Best-effort telemetry/auditing receives events after core business logic finishes.
- Multiple bounded contexts subscribe to an integration event without needing a coordinator making decisions for each service.
- A short event transformation with no critical side effects and no workflow resume requirement.

The core rule: if **analytics fails while the order is valid**, analytics should not decide whether checkout succeeded. With many independent subscribers, event-driven fan-out can lower coupling compared to an orchestrator calling each subscriber one by one.

A proper **error policy** is still required: with Spring's default synchronous **SimpleApplicationEventMulticaster**, exceptions from an observer can propagate back to the publisher. If an observer is non-critical, use a durable queue/outbox, isolated error handling, or a bounded non-blocking mechanism. **@Async** alone does not turn an in-memory callback into a durable message.

## 5. Decision Table

| Criterion | Orchestration usually fits | Event chain/choreography usually fits |
| --- | --- | --- |
| Must B strictly wait for A to succeed? | Yes, with multiple conditions | No strict business ordering |
| Does one failure determine the whole outcome? | Yes | Independent subscribers |
| Must side effects be compensated? | Yes | No, or each subscriber owns its own responsibility |
| Workflow spans multiple services? | Durable saga/workflow is easier to govern | Choreography remains viable if distributed state is thoroughly designed |
| Need timeouts/backoff/manual review? | Yes | No, or strictly local per handler |
| Need a status endpoint by workflowId? | Very suitable | Must aggregate state from many sources |
| Occurred event needs many observers? | Publish event after main step | Ideal for fan-out |
| Need extensibility without editing core workflow? | Emit events at the boundary | Strength of loose coupling |
| Must recover after restarts? | Persistent workflow + durable messaging | Event store/broker + consumer state; in-memory chains are insufficient |
| Need a synchronous result for the caller? | Service/orchestrator returns clearly | A single publication does not return the whole chain's result |

**Heuristic:** If answering “did this order succeed?” requires reading logs from five listeners and guessing event ordering, consider **a workflow owner**. If adding a reporting listener does not affect use-case correctness, **keep observers independent**.

## 6. Anti-Pattern: Payment Workflow Scattered Across Listeners

~~~java
@EventListener
public PaymentRequested onOrderSubmitted(OrderSubmitted event) {
    return new PaymentRequested(event.orderId());
}

@EventListener
public ShippingRequested onPaymentCaptured(PaymentCaptured event) {
    return new ShippingRequested(event.orderId());
}
~~~

These are **snippets**, not a complete program. Writing this is syntactically valid event chaining, yet leaves unanswered:

1. Who verifies PaymentCaptured matches the right payment attempt, amount, and order?
2. Who confirms shipping was successfully scheduled?
3. When events are lost or the broker goes down, who recovers?
4. If payment succeeded while shipping failed, who refunds?
5. If the same event arrives twice, who prevents duplicate charges?
6. After 30 seconds with no event, who times out or routes to manual review?
7. When an API asks for final status, where does the system read it from?

It is possible to solve this in choreography with durable per-participant state and strong correlation. Still, the more state-transition and compensation rules exist, the easier a stateful orchestrator is to verify—especially when the system has unified operational policies.

## 7. Runnable Java 17+ Example: Orchestration for Mandatory Steps, Spring Events for Observers

The example below uses **Spring Framework 6.2.9**, **JDK 17+**, and **Gradle 8.x**, without Spring Boot, a database, or a broker. **CheckoutWorkflow** coordinates reserving stock, charging payment, and scheduling shipping. If shipping fails, the code calls **refund** and **release**. Upon success, the workflow publishes **OrderFulfilled** for listeners to observe.

This is an **in-memory demo** with no persistence or remote services. Compensation actions are simulated with logging and cannot substitute for a real saga.

Structure:

~~~text
checkout-orchestration-demo/
  build.gradle
  src/main/java/demo/CheckoutOrchestrationDemo.java
~~~

**build.gradle**:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.9'
}

application {
    mainClass = 'demo.CheckoutOrchestrationDemo'
}
~~~

**src/main/java/demo/CheckoutOrchestrationDemo.java**:

~~~java
package demo;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class CheckoutOrchestrationDemo {

    public record OrderFulfilled(String id) {}

    public static final class Stock {
        public void reserve(String id) {
            System.out.println("stock: reserve " + id);
        }

        public void release(String id) {
            System.out.println("stock: release " + id);
        }
    }

    public static final class Payment {
        public void charge(String id) {
            System.out.println("payment: charge " + id);
        }

        public void refund(String id) {
            System.out.println("payment: refund " + id);
        }
    }

    public static final class Shipping {
        public void schedule(String id) {
            System.out.println("shipping: schedule " + id);
            if (id.equals("FAIL")) {
                throw new IllegalStateException("shipping unavailable");
            }
        }
    }

    public static final class CompletionNotifier {
        private final ApplicationEventPublisher publisher;

        public CompletionNotifier(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void notifyCompleted(String id) {
            publisher.publishEvent(new OrderFulfilled(id));
        }
    }

    public static final class CheckoutWorkflow {
        private final Stock stock;
        private final Payment payment;
        private final Shipping shipping;
        private final CompletionNotifier notifier;

        public CheckoutWorkflow(
                Stock stock,
                Payment payment,
                Shipping shipping,
                CompletionNotifier notifier) {
            this.stock = stock;
            this.payment = payment;
            this.shipping = shipping;
            this.notifier = notifier;
        }

        public void execute(String id) {
            boolean reserved = false;
            boolean charged = false;

            try {
                stock.reserve(id);
                reserved = true;

                payment.charge(id);
                charged = true;

                shipping.schedule(id);
            } catch (RuntimeException original) {
                // Simple demo: compensate in reverse execution order.
                if (charged) {
                    payment.refund(id);
                }
                if (reserved) {
                    stock.release(id);
                }
                System.out.println("workflow: failed " + id);
                throw original;
            }

            System.out.println("workflow: completed " + id);
            notifier.notifyCompleted(id);
        }
    }

    public static final class CompletionObserver {
        @EventListener
        public void on(OrderFulfilled event) {
            System.out.println("observer: fulfilled " + event.id());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        Stock stock() {
            return new Stock();
        }

        @Bean
        Payment payment() {
            return new Payment();
        }

        @Bean
        Shipping shipping() {
            return new Shipping();
        }

        @Bean
        CompletionNotifier completionNotifier(
                ApplicationEventPublisher publisher) {
            return new CompletionNotifier(publisher);
        }

        @Bean
        CheckoutWorkflow checkoutWorkflow(
                Stock stock,
                Payment payment,
                Shipping shipping,
                CompletionNotifier notifier) {
            return new CheckoutWorkflow(stock, payment, shipping, notifier);
        }

        @Bean
        CompletionObserver completionObserver() {
            return new CompletionObserver();
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            CheckoutWorkflow workflow =
                    context.getBean(CheckoutWorkflow.class);

            System.out.println("caller: OK");
            workflow.execute("OK");

            System.out.println("caller: FAIL");
            try {
                workflow.execute("FAIL");
            } catch (IllegalStateException e) {
                System.out.println("caller: " + e.getMessage());
            }
        }
    }
}
~~~

Run in the **checkout-orchestration-demo** directory with Java 17+ and Gradle 8.x:

~~~bash
gradle --console=plain -q run
~~~

**Stdout printed by the program** with the default synchronous event multicaster configuration:

~~~text
caller: OK
stock: reserve OK
payment: charge OK
shipping: schedule OK
workflow: completed OK
observer: fulfilled OK
caller: FAIL
stock: reserve FAIL
payment: charge FAIL
shipping: schedule FAIL
payment: refund FAIL
stock: release FAIL
workflow: failed FAIL
caller: shipping unavailable
~~~

Explanation:

- For **OK**, the orchestrator enforces the order: reserve, charge, then schedule. After all three succeed, it notifies completion.
- **CompletionObserver** only records **OrderFulfilled** after the success path; it does not decide payment or coordinate refunds.
- For **FAIL**, **Shipping.schedule** intentionally throws an exception. **CheckoutWorkflow** knows simulated stock and payment succeeded, so it calls refund, release, and rethrows the error to the caller.
- Because the observer is only published to after the success branch, there is no **observer: fulfilled FAIL**.
- In the demo, **refund** and **release** always succeed. In reality, those calls can fail; an exception during compensation can mask the original error or block subsequent compensating steps. Dedicated error handling, persistent workflow state, and retries are required.
- If the observer throws an exception, the default synchronous event publisher can throw back to the caller after mandatory steps already completed. Do not automatically refund a completed order because of that; design observers and error policies separately.

**Why is this orchestration?** **CheckoutWorkflow** owns ordering, success conditions, the list of confirmed steps, and the failure branch. Spring events are used **at the post-outcome observation boundary**, not to replace coordination authority.

### Safety Limitations of the Demo

The **reserved** and **charged** booleans only reflect that the simulated methods returned. With a real payment API, a timeout can happen **after the provider charged** but before the client receives a response; `charged` would still be false. Therefore, never use this code as-is to decide refunds in production.

You must distinguish **SUCCESS**, **FAILED**, and **UNKNOWN** for each remote operation; use **idempotency keys**, third-party status queries, durable step state, timeouts, and manual review.

A production orchestrator must also persist **OrderFulfilled** or the intent to publish durably if downstream consumers cannot afford to miss events. In-memory **publishEvent(Object)** only performs an in-ApplicationContext handoff.

## 8. Designing Orchestration as a State Machine

When workflows span multiple systems or need recovery, model state explicitly:

~~~text
NEW
  |
  v
STOCK_RESERVED
  |
  v
PAYMENT_CHARGED
  |
  v
SHIPPING_SCHEDULED
  |
  v
COMPLETED

If failure with side effects:
  -> COMPENSATING
  -> COMPENSATED
  -> FAILED

If compensation cannot complete automatically:
  -> MANUAL_REVIEW
~~~

A workflow record can contain:

| Field | Meaning |
| --- | --- |
| **workflowId** | Stable ID to correlate commands, events, and APIs |
| **orderId** | Related business entity |
| **state** | Confirmed state, never guessed |
| **currentStep** | Step currently or about to be processed |
| **stepOutcome** | SUCCESS/FAIL/UNKNOWN for each step |
| **attempts** | Retry count and backoff |
| **deadline** | Timeout or escalation timestamp |
| **idempotencyKey** | Prevents duplicate side effects at adapters/providers |
| **lastError** | Sanitized error information |
| **updatedAt** | Tracing and operational support |

**Transition guards** must be checked: never jump straight from NEW to COMPLETED while payment remains unverified. After a restart, the orchestrator reads state and resumes at a valid step instead of restarting from the beginning.

If a workflow consists solely of a few local operations in one database transaction, a separate engine is not necessarily needed. An **application service with @Transactional** can be a sufficient orchestrator; tool complexity should match business requirements.

## 9. Orchestration Does Not Mean Automatic Distributed Transactions

### 9.1. Local Transactions

For writes against **the same database**, a Spring application service can use **@Transactional** to preserve invariants and atomicity inside a local transaction. In that case, there is no need to split mandatory logic into listeners.

However, **@Transactional does not turn an HTTP call** to a payment gateway into part of the DB transaction. Holding a DB transaction open across slow network waits can cause lock contention, timeouts, or deadlocks.

### 9.2. Event Chains and Commit Timing

With the default synchronous **SimpleApplicationEventMulticaster**, an **@EventListener** typically runs when **publishEvent(...)** is called. If the publisher is inside **@Transactional**, the listener may run **before the transaction commits**.

~~~text
BEGIN TX
  -> save order
  -> publish OrderConfirmed
      -> @EventListener sends email
  -> exception -> ROLLBACK DB
Email was sent, yet DB changes rolled back.
~~~

**Returning a follow-up event does not mean after-commit.** Event chaining describes publication relationships; transaction phase is an independent concern.

### 9.3. AFTER_COMMIT and Outbox

Spring allows phase-bound listeners:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderConfirmed event) {
    // React after the associated transaction has committed.
}
~~~

This is only an **illustrative snippet** requiring beans, imports, and a matching transaction manager. By default **fallbackExecution=false**, so the listener does not run if the event is published outside a compatible transaction. After commit, if new data must be written with its own commit, a new transaction (**REQUIRES_NEW**) through a Spring-managed service is typically required.

**AFTER_COMMIT** avoids many pre-commit side effects, yet provides no durable delivery guarantee if the process dies immediately after commit.

If the follow-up event/work **must not be lost**, consider a **transactional outbox**:

~~~text
BEGIN DB TRANSACTION
  -> save business state
  -> save outbox command/event message
COMMIT
  -> worker reads outbox
  -> publish to message broker / next participant
  -> retry and record delivery
  -> consumer deduplicates and handles message
~~~

The outbox message and business state commit together; workers can recover after restarts. Duplicate sends can still happen if a worker publishes successfully but fails to mark delivered, so consumers must be **idempotent**. Never claim end-to-end exactly-once from an outbox alone.

A durable orchestrator can use an outbox to send commands, an **inbox/deduplication** store to process result events, and local transactions to update workflow state.

## 10. Orchestration Can Also Be Asynchronous and Event-Driven

An orchestrator does not have to invoke three synchronous HTTP APIs in a row. Coordination via commands and result events looks like:

~~~text
CheckoutOrchestrator
    -> command ReserveStock(workflowId, orderId)
StockService
    -> event StockReserved(workflowId) / StockRejected
CheckoutOrchestrator
    -> command ChargePayment(workflowId, paymentAttemptId)
PaymentService
    -> event PaymentCaptured / PaymentDeclined
CheckoutOrchestrator
    -> command ScheduleShipment(workflowId, orderId)
ShippingService
    -> event ShipmentScheduled / ShipmentFailed
CheckoutOrchestrator
    -> state COMPLETED / COMPENSATING / MANUAL_REVIEW
~~~

The orchestrator owns the next step. Participants can be implemented with Spring Boot, Kafka, or RabbitMQ, while **domain rules** and outbound ports should remain decoupled from transport frameworks where appropriate.

A common architecture:

~~~text
application/
  CheckoutWorkflow (orchestrator)
  StockGateway, PaymentGateway, ShippingGateway (ports)
domain/
  Order, payment policies, invariants, domain events
infrastructure/
  Spring adapters, HTTP/messaging adapters
  workflow state repository, outbox/inbox implementation
~~~

Switching brokers does not force the domain to import Kafka. When a process outgrows a custom state machine, consider a workflow engine with built-in persistence, durable timers, and orchestration history.

## 11. Event Replay and Event Chains

Since this topic sits within **“Replay and Event Chains”**, distinguish **replay** from an event chain emitting the next step:

- **Event chain:** a current event makes a listener emit a new event immediately. Requires no stored history.
- **Event replay:** re-emitting **stored** events from an event log, event store, or outbox to rebuild projections, reprocess, or recover.
- **Retry:** re-executing a step per policy; can cause duplicate side effects if not idempotent.
- **Redelivery:** a broker resends a message; consumers can encounter the same event multiple times.

Risk: a listener replaying **OrderConfirmed** to rebuild a report calls charge payment or returns **ChargePaymentRequested**. Then an operation meant solely to rebuild a projection triggers new side effects. Orchestrators should separate **business state transitions** from read-model projections, alongside deduplication and replay-mode awareness when needed.

Do not use Spring **ApplicationEventPublisher** as an event store: this API provides neither historical replay nor a durable queue by default.

## 12. Distinguishing a Workflow Owner from a God Service

Orchestration brings coordination control, at a cost:

**Put in the orchestrator:**

- Selecting and invoking the next step.
- Tracking `currentStep`, `status`, `attempts`, and `deadline`.
- Deciding retries, compensation, pausing/manual review.
- Correlating result events to the right `workflowId`/`attempt`.
- Determining when the workflow succeeds or fails.

**Do not cram into the orchestrator:**

- Every aggregate invariant.
- SQL, JDBC, connection-pooling details.
- Low-level serialization and broker transport logic.
- Pricing, tax, and discount calculations that belong to the domain.
- Dozens of analytics observers that do not affect the outcome.

**Principle:** the orchestrator **only coordinates**; domain services/aggregates hold business rules; infrastructure adapters hold framework details. If a coordinator grows too large, split by use case or bounded context rather than arbitrarily fragmenting it into an ownerless event chain.

## 13. Real-World Cases

### Checkout with Charge and Shipment

**Orchestration** usually fits. Steps must produce verified outcomes, double-charge risk exists, compensation is needed, and a single final order status is required. An **OrderFulfilled** observer can update analytics independently after the core workflow finishes.

### Order Confirmed, Sync Search and Analytics Needed

**Event chain/choreography** fits. Subscribers are independent; a search-index failure does not invalidate the order state. If updates must not be lost, publish via an outbox/queue rather than relying solely on in-memory callbacks.

### Onboarding Requiring Human Approval Within 3 Days

**Durable orchestration** usually fits better than a simple event chain: you need deadlines, waiting state, approver decisions, post-restart resume, escalation, and audit trails.

### Non-Critical Marketing Notification

Use event-driven subscribers or a queue. Do not build campaign-wide orchestration just to send one notification after user signup—unless there is a multi-step outcome-dependent workflow, complex retry/opt-out policies, or approvals.

### Multi-Step Subscription Billing in One Database

An **application service with a local transaction** and domain service calls can outperform both sagas and event chains. Do not reach for a durable engine before it is needed.

## 14. Testing the Difference

### 14.1. Unit Testing the Orchestrator

In production code, abstract **Stock**, **Payment**, and **Shipping** behind interfaces so fakes/spies can be injected in tests. Use a **List<String>** to record method-call order.

Important tests:

1. **Happy path:** reserve → charge → schedule → completed → notify.
2. **Stock failure:** payment/shipping not called; appropriate error returned.
3. **Payment failure:** release reserved stock; shipping not called.
4. **Shipping failure:** refund payment then release stock; `OrderFulfilled` not published.
5. **Compensation failure:** persist incomplete-compensation state, retry/manual review, do not mask original error.
6. **Duplicate command:** same `workflowId`/`idempotencyKey` causes no new side effects.
7. **Remote timeout:** mark `UNKNOWN`, query/reconcile instead of blind retry.
8. **Observer failure:** completed core steps are not marked for refund just because analytics failed.
9. **Restart:** resume from persisted step without re-running completed steps.
10. **Cancelled workflow:** enforce cancellation boundaries and corresponding compensation branch.

Section 7's demo shows in-memory happy/failure paths; persistence/restart cases require integration tests against real infrastructure.

### 14.2. Integration Testing Spring Events and Transactions

Verify separately:

- Observer events are published only after business conditions succeed.
- Exceptions from synchronous **@EventListener**s affect the publisher as configured.
- **@TransactionalEventListener(AFTER_COMMIT)** does not run when the transaction rolls back.
- Outbox records and business state changes commit atomically in the same database.
- A worker crashing after publish but before mark-delivered does not cause consumers to apply side effects twice.
- Out-of-order or past-deadline events do not push the workflow into invalid states.

A test that only verifies **`publishEvent(...)` was called** does not prove the workflow is correct. Assert **business state** and **step outcomes**.

## 15. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using event chains for every mandatory step | Unclear ownership of success/failure | Pick a workflow owner/orchestrator |
| Using **@Order** to coordinate business state | Only prioritizes dispatch; stores no workflow state | State machine + transition guards |
| Assuming returning an event creates a new transaction | Provides no atomicity/commit | Define explicit transaction boundaries |
| Using **@Async** to guarantee eventual completion | In-memory tasks can be lost | Durable queue/outbox + retries |
| Retrying payment on timeout with a new key | Double-charge risk | Idempotency key + provider reconciliation |
| Compensation without persisted state | Crash leaves compensation half-done | Durable workflow state and background retries |
| Treating refund as an ACID rollback | Transaction history still contains charge/refund | Audit both; design states clearly |
| Holding a DB transaction across slow HTTP calls | Long locks, timeouts, deadlocks | Short local transactions + orchestration |
| Putting non-critical observers in mandatory steps | Analytics failure makes checkout fail | Move observers to events/queues with an error policy |
| Marking COMPLETED as soon as command is sent | Participant may not have acted yet | Wait for correlated result event |
| Missing `workflowId`, `eventId`, `attemptId` | Hard to trace and deduplicate | Stable identities, clear metadata |
| Replaying events causes re-charging | Duplicate side effects | Separate projections from actions, idempotency |
| Orchestrator holds all domain logic | God Service, high coupling | Domain holds invariants; coordinator only coordinates |
| Not testing failures and restarts | Happy path masks reliability gaps | Fault injection, retry/duplicate tests |

## 16. Design Selection Checklist

1. **Does the next step strictly depend on the prior step's outcome?** If yes, lean toward orchestration.
2. **Is there a single final business status to report to APIs/callers?** If yes, you need a workflow owner.
3. **Are there remote side effects that cannot automatically roll back?** If yes, plan compensation.
4. **Can timeouts leave outcomes `UNKNOWN`?** If yes, you need reconciliation/idempotency.
5. **Must a process resume if it dies mid-way?** If yes, use durable workflow state.
6. **Does the event have many non-critical observers?** If yes, keep fan-out decoupled.
7. **Is an observer failure allowed to fail the main use case?** Design explicit error boundaries.
8. **Can replay/redelivery occur?** Prevent duplicate side effects.
9. **Is the flow simple and confined to one database transaction?** An application service is usually enough.
10. **Is the orchestrator absorbing domain invariants?** Move domain rules back into aggregates/domain services.

**Conclusion:** Choose **event chains/choreography** for independent, loosely coupled reactions or fan-out after a valid fact. Choose **orchestration** when a flow demands **mandatory ordering, an overall outcome, timeouts/retries, compensation, or durable state for recovery**. Both styles can be combined: the orchestrator drives core steps, while Spring events or broker events notify observers that do not own the workflow.

### Official References

- Spring Framework Reference — *Standard and Custom Events*: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework Javadoc — *EventListener*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/EventListener.html
- Spring Framework Javadoc — *ApplicationEventPublisher*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework Reference — *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework Reference — *Declarative Transaction Management*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html
