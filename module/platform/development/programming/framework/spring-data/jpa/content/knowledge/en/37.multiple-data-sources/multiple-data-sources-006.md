# Overview of JTA, XA, and Business Compensation Options

## Objectives

A business operation may update multiple resources: two databases, a database and a message broker, or multiple independent services. A local transaction of a single database protects only the operations within that transaction. When multiple resources must be coordinated, the architecture must choose an appropriate consistency strategy.

Two common approaches are:

- **JTA/XA:** coordinates distributed transactions across XA-capable resources, typically using two-phase commit to commit or roll back together.
- **Business compensation (compensation/Saga):** splits the workflow into multiple local transactions; if a later step fails, executes compensating business actions for completed steps.

After this lesson, you will be able to:

- Distinguish local transactions, JTA, and the XA protocol.
- Describe how a transaction coordinator executes two-phase commit.
- Identify the requirements for JPA, JDBC, and JMS to participate in a distributed transaction.
- Understand in-doubt states, recovery, and heuristic outcomes.
- Recognize the limitations of XA with HTTP APIs and independent services.
- Design a Saga with forward steps, compensating steps, and progress state.
- Combine transactional outbox/inbox with retries and idempotency.
- Choose between XA and compensation based on consistency requirements, duration, and operability.

## 1. Why is a single local transaction not enough?

Suppose an order creation operation needs to:

1. Write the order to the Order database.
2. Deduct stock in the Inventory database.
3. Send a message for the delivery system to pick up the job.

If all three operations use the same transaction manager and the same database resource, a single local transaction can protect them. But if each database has its own connection or the message broker is an independent resource, one database's transaction does not automatically control the remaining resources.

A failure scenario:

- The Order database committed the order.
- The Inventory database failed before deducting stock.
- The message was never sent.

The system has an order without reserved inventory. If the entire request is retried without duplicate protection, the order could be created twice.

Three scopes must be distinguished:

| Scope | Guarantee Unit | Example |
|---|---|---|
| Local transaction | One resource manager or one database transaction | One JpaTransactionManager managing one EntityManagerFactory |
| Distributed JTA/XA transaction | Multiple XA resources coordinated by a coordinator | Two XA databases and one XA JMS resource |
| Saga workflow | Multiple sequential or event-driven local transactions | Create order, reserve stock, charge payment, ship, and compensate when needed |

Do not assume that multiple `@Transactional` methods mean multiple databases commit atomically. Identify which transaction manager is actually used and which resources have been enlisted into that transaction.

## 2. What are JTA and XA?

**JTA (Jakarta Transactions)** is the API and model for managing distributed transactions in the Java ecosystem. An application begins, commits, or rolls back transactions through a transaction manager. JPA, JDBC, and JMS can participate if configured with compatible resources.

**XA** is the standard protocol for a transaction manager to coordinate multiple resource managers. A resource manager can be an XA-capable database or message provider. XA describes how the coordinator instructs each resource to prepare to commit and then commit or roll back according to the global decision.

The relationship can be understood as follows:

- JTA is the Java-side transaction coordination API and model.
- XA is the coordination protocol between the transaction manager and XA resources.
- The transaction coordinator is the component holding the global decision state and orchestrating resources.
- A resource manager is the component managing actual data, such as a database or JMS provider.

Spring provides integration classes like **JtaTransactionManager** to participate in transactions managed by a JTA coordinator. Spring does not automatically turn two independent local transactions into an XA transaction just by adding multiple @Transactional annotations.

A JTA coordinator can be supplied by an application server or a standalone transaction manager implementation, such as Narayana or Atomikos. Configuration details depend on the Spring Boot version, JPA provider, database driver, JMS provider, and deployment platform.

## 3. How does two-phase commit work?

XA typically uses **two-phase commit (2PC)**. The coordinator must receive assurance that prepared resources can commit before issuing the global commit decision.

~~~mermaid
sequenceDiagram
    participant App as Application
    participant TM as JTA Coordinator
    participant DB1 as Order XA DB
    participant DB2 as Inventory XA DB
    App->>TM: Begin transaction
    App->>DB1: Update order
    App->>DB2: Reserve stock
    App->>TM: Commit
    TM->>DB1: Prepare
    TM->>DB2: Prepare
    DB1-->>TM: Vote YES
    DB2-->>TM: Vote YES
    TM->>DB1: Commit
    TM->>DB2: Commit
    TM-->>App: Commit completed
~~~

Two main phases:

**Phase 1 — Prepare**

1. The application requests a commit.
2. The coordinator sends prepare to each enlisted XA resource.
3. Each resource checks its ability to commit and writes the required state to a durable log.
4. The resource replies YES if ready to commit, or NO if unable to commit.

A resource that voted YES must preserve the state needed to fulfill the subsequent decision. Locks and resources may remain held while awaiting the final decision.

**Phase 2 — Commit or rollback**

- If all resources vote YES, the coordinator durably logs the commit decision and sends commit to each resource.
- If any resource votes NO or a condition forces a rollback, the coordinator decides to roll back and notifies the resources.
- Resources execute the decision and release transaction state.

The goal is to prevent one resource from committing when other resources have rolled back. The coordinator must persist logs so it can recover decisions after a crash.

Some systems optimize with one-phase commit when only a single XA resource participates. With multiple resources, the prepare/commit protocol is what enables distributed coordination.

## 4. Requirements for JPA to participate in JTA/XA

JPA can run with local transactions or JTA. For an entity manager to join a JTA transaction, the persistence unit and EntityManagerFactory must be configured with the appropriate transaction type, typically JTA. The DataSource must be XA-aware and managed by the transaction manager.

Typical requirements include:

- An active JTA coordinator configured in the application.
- DataSources using XA drivers/providers and registered with the coordinator.
- EntityManagerFactories using JTA transaction integration.
- Repositories or EntityManagers connected to the right persistence unit and JTA transaction manager.
- All resources participating in the transaction support XA and are properly enlisted.
- Transaction timeouts, recovery logs, and resource identifiers are durably configured.

At the Spring layer, a service can explicitly specify the transaction manager:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderPlacementService {

    private final OrderRepository orderRepository;
    private final InventoryRepository inventoryRepository;

    public OrderPlacementService(
            OrderRepository orderRepository,
            InventoryRepository inventoryRepository) {
        this.orderRepository = orderRepository;
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional(transactionManager = "jtaTransactionManager")
    public void placeOrder(Order order, Long productId, int quantity) {
        orderRepository.save(order);
        inventoryRepository.reserve(productId, quantity);
    }
}
~~~

This illustrative code is only meaningful when both repositories are configured on persistence units/XA DataSources enlisted with the same JTA coordinator. If the second repository uses a local JpaTransactionManager or a non-XA DataSource, the annotation on the method does not make that update part of the same distributed transaction.

The bean name jtaTransactionManager in the example is an application configuration name. With Spring Boot, how beans are created, XA DataSources declared, and providers wired depends on the version and JTA implementation used. Do not copy configurations from one provider to another without checking the corresponding documentation.

## 5. JDBC, JMS, and other resources

JTA/XA is not limited to JPA. A transaction can coordinate a database and a message broker if both expose compatible XA resources.

Examples of participating components:

| Resource | Required Components |
|---|---|
| JPA/Hibernate | JTA EntityManagerFactory and XA DataSource |
| Plain JDBC | XADataSource and matching XAConnection/XAResource |
| JMS | XA-capable ConnectionFactory/Session provided by the broker |
| Second database | Driver and XA DataSource enlisted with the same coordinator |

For example, a business operation that writes an order and sends a message can use the same JTA transaction if both the database and JMS provider are configured for XA:

~~~java
@Transactional(transactionManager = "jtaTransactionManager")
public void createOrderAndNotify(Order order) {
    orderRepository.save(order);
    jmsTemplate.convertAndSend("orders.created", order.getId());
}
~~~

This illustrates the usage flow. For the message to genuinely join the same transaction, the JMS connection factory, session, and JmsTemplate configuration must support and use the XA transaction managed by the coordinator. A JMS template using local session transactions or sending outside a transaction will not be automatically coordinated.

Not every broker or connection factory supports XA in every configuration. Verify the connection factory type and how the provider enlists resources. If XA is unavailable, consider outbox instead of assuming messages will roll back alongside the database.

## 6. Recovery and in-doubt state

The coordinator or a resource can fail between the two phases. For example, both databases prepared and voted YES, but the coordinator stops before sending the commit decision. Resources may hold the transaction in an **in-doubt** state because they do not yet know the final decision.

Recovery requires:

1. Writing transaction logs and resource identities to durable storage.
2. Restarting the coordinator with the same recovery configuration.
3. Reconnecting to the resource managers that participated in the transaction.
4. Reading the state of incomplete transactions.
5. Completing commit or rollback according to the decision recorded in the log.

Do not arbitrarily delete logs or rename XA resource identifiers while unrecovered transactions exist. If the coordinator cannot recognize the old resource, transactions may remain stuck and require operational investigation.

A **heuristic outcome** occurs when a resource independently decides to commit or roll back differently from the coordinator's decision, usually due to timeouts or administrative intervention. This can violate expected atomicity and requires manual intervention, data reconciliation, or business compensation.

Therefore, XA must be operated as stateful durable infrastructure with logs, monitoring, recovery procedures, and runbooks. Simply configuring annotations without recovery setup is insufficient for production.

## 7. Costs and limitations of XA

2PC provides strong commit coordination across XA resources, but at a cost:

- Multiple network round-trips between the coordinator and resources.
- Resources may hold locks or prepared states while awaiting a decision.
- Long-running transactions reduce concurrency and increase timeout risk.
- The coordinator and recovery logs become critical infrastructure requiring stable operation.
- All participating resources must support XA and be configured properly.
- Network or coordinator failures can leave in-doubt transactions requiring recovery.

XA is better suited for short transactions, compatible XA resources, and strict atomic commit requirements. It is usually unsuitable for workflows spanning minutes, waiting on human input, calling external APIs, or having multiple steps needing independent retries.

**XA does not turn an HTTP request to another service into an XA resource.** Regular REST APIs do not participate in XA prepare/commit. If one service performs a side effect and another service fails, the coordinator cannot automatically roll back that side effect. For service-to-service communication, Saga and compensation are generally a better fit.

## 8. What are Compensation and Saga?

**Compensation** is a business operation meant to offset the impact of a previously committed step. It is not a rollback of the old database transaction. The old transaction has committed and its history remains; compensation creates a new change to bring the system to an acceptable business state.

A **Saga** is a sequence of local transactions. Each step commits independently; if a later step fails, the system decides to retry, follow an alternate branch, or execute compensating actions for completed steps.

Order placement example:

| Forward Step | Result | Possible Compensating Action |
|---|---|---|
| Create order in PENDING state | Order created | Cancel order or set to CANCELLED |
| Reserve stock | Inventory reserved | Release reserved stock |
| Charge payment | Payment succeeded | Refund payment |
| Create shipment | Shipping requested | Cancel shipment if carrier allows |

Compensation carries business semantics. A refund does not erase the original payment event; it creates a refund transaction. Releasing stock does not pretend a reservation never happened; it records that the reservation was cancelled.

Not every action can be fully compensated. A sent email cannot be recalled from an inbox. Shipped goods may require a return workflow. Therefore, Saga designs must clearly define reachable final states and how to handle cases where compensation itself fails.

## 9. Designing an orchestration-style Saga

In **orchestration**, a business coordinator controls step order, persists progress state, and decides the next step. This approach makes flows easier to observe when there are many branches and compensations.

A Saga state record might include:

- saga_id: unique identifier of the workflow instance.
- business_key: business key, e.g., order_id.
- current_step: step currently executing.
- status: RUNNING, COMPLETED, COMPENSATING, COMPENSATED, or FAILED.
- attempt_count: number of attempts for the current step.
- last_error: most recent error.
- created_at, updated_at: timestamps for operational tracking.

Orchestration flow:

~~~text
START
  |
  v
Create pending order
  |
  v
Reserve inventory
  |
  v
Charge payment
  |
  v
Create shipment
  |
  v
Mark order confirmed
  |
  v
COMPLETED

If Charge payment fails permanently:
  Release inventory
  Cancel pending order
  COMPENSATED
~~~

Each step must update Saga state within the same local transaction or persist a corresponding event/outbox entry. Never keep progress solely in the coordinator's memory because the process can stop at any moment.

Example service handling reservation:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryStep {

    private final InventoryRepository inventoryRepository;
    private final SagaEventRepository sagaEventRepository;

    public InventoryStep(
            InventoryRepository inventoryRepository,
            SagaEventRepository sagaEventRepository) {
        this.inventoryRepository = inventoryRepository;
        this.sagaEventRepository = sagaEventRepository;
    }

    @Transactional
    public void reserve(String sagaId, Long productId, int quantity) {
        inventoryRepository.reserve(productId, quantity);
        sagaEventRepository.record(
            sagaId,
            "INVENTORY_RESERVED",
            productId.toString()
        );
    }
}
~~~

This example assumes event/state is written to the same database and in the same transaction as the reservation operation. If a message must be sent to another service, write an outbox record in that transaction as well; a worker will publish it after commit. Step status records must have a unique key or version to prevent two workers from processing the same step concurrently.

## 10. Designing safe compensation

Each forward step should specify upfront:

- Conditions under which the step is considered successful.
- Results that must be stored to allow later compensation.
- The corresponding compensation and data required to perform it.
- Whether the compensation can be retried.
- Conditions under which compensation is no longer valid.
- How to handle failed or partially completed compensation.

For example, the stock reservation step saves a reservation_id. Compensation must release that exact reservation rather than unconditionally adding stock back, which could accidentally release another reservation.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ReservationCompensation {

    private final ReservationRepository reservationRepository;

    public ReservationCompensation(
            ReservationRepository reservationRepository) {
        this.reservationRepository = reservationRepository;
    }

    @Transactional
    public void releaseReservation(String reservationId) {
        Reservation reservation = reservationRepository
            .findById(reservationId)
            .orElseThrow();

        if (reservation.getStatus() == ReservationStatus.RELEASED) {
            return;
        }

        if (reservation.getStatus() != ReservationStatus.RESERVED) {
            throw new IllegalStateException(
                "Reservation cannot be released from current state");
        }

        reservation.release();
    }
}
~~~

This snippet demonstrates state-based idempotent compensation: calling it again when already RELEASED does not add inventory a second time. Ensure the status update and quantity change are committed in the same transaction. If two release commands can run concurrently, add optimistic locking, pessimistic locking, or conditional updates to prevent double-releasing.

When compensating multiple steps, actions are usually executed in reverse order of the completed forward steps. For instance, if stock was reserved and then payment was charged, when shipment creation fails you might refund first and then release stock, depending on business rules. There is no single universal order for all workflows; determine it based on dependencies and practical risks.

## 11. Orchestration vs. choreography

In **choreography**, each service emits events after its local transaction and other services react to those events. There is no central coordinator controlling every step.

| Criterion | Orchestration | Choreography |
|---|---|---|
| Control | One orchestrator decides the next step | Services react to events |
| Progress tracking | Centralized Saga state | Must aggregate events and states across multiple services |
| Coupling | Participating services depend on the orchestrator contract | Services depend on each other's event contracts |
| Best fit | Multi-branch flows, complex compensations | Relatively simple, event-driven flows |
| Risk | Orchestrator becomes a critical component needing HA | Distributed business flow is harder to trace and prone to implicit coupling |

Choreography can reduce dependency on a central coordinating service, but it does not eliminate the need for state persistence, retries, idempotency, and observability. If one event triggers multiple consumers, each consumer needs clear ownership and its own processing state.

## 12. Transactional outbox and inbox in Saga

When a service updates a database and then publishes an event as two separate operations, two failure modes exist:

- Database commits but publish fails: other services never receive the event.
- Publish succeeds but database rolls back: other services receive an event for an uncommitted change.

Transactional outbox closes this gap by writing business data and an outbox record in the same local transaction. A worker reads the outbox and publishes the message after commit.

An outbox record typically contains:

| Field | Meaning |
|---|---|
| event_id | Unique message ID |
| aggregate_id | Order ID or business object ID |
| event_type | Event type |
| payload | Data needed by consumers |
| created_at | Creation timestamp |
| published_at | Broker acknowledgement timestamp |
| attempt_count | Number of publish attempts |

Publishing can duplicate if the worker stops after the broker receives the message but before the outbox row is marked. Therefore, consumers should use an **inbox** or processed_message table with a unique constraint on event_id. The consumer records the processed event and updates business data in the same transaction.

The common pattern is **at-least-once delivery plus idempotent processing**. Do not call it end-to-end exactly-once. The broker may deliver duplicate messages; the inbox ensures the same event does not apply business changes a second time.

## 13. Retries, timeouts, and dead-letter handling in Saga

Not every error warrants immediate compensation.

- Transient errors such as network timeouts or overloaded services: retry the current step with backoff and a cap.
- Permanent business errors such as insufficient stock: switch to the compensation branch.
- Unknown outcome due to timeout: query status using a business key or idempotency key before deciding to re-run.
- Failed compensation: keep the Saga in COMPENSATING state, record the error, and retry or route to a dead-letter queue for operational intervention.

A request timeout does not prove the target service failed to perform the operation. The service may have committed while the response was lost in transit. Calling again with a new ID could execute the business action twice. Each step needs a stable idempotency key, such as saga_id plus step name, so the target service recognizes duplicate requests.

Never retry infinitely. Persist attempt count, next_retry_at, error code, and status so workers can resume after restarts. Use exponential backoff and jitter to avoid thundering herds of retries. After a defined threshold, move to a dead-letter queue or escalate for business intervention.

## 14. Comparing JTA/XA with Saga/compensation

| Criterion | JTA/XA | Saga/compensation |
|---|---|---|
| Mechanism | Two-phase commit across XA resources | Sequence of local transactions and compensating actions |
| Consistency | Atomic commit across participating resources | Eventual consistency across the workflow |
| Duration | Suitable for short transactions | Suitable for long-running, multi-step workflows |
| Resource support | Every resource must support XA and be enlisted properly | Each service uses local transactions |
| Locking and load | May hold prepared/locked state during 2PC | Does not hold a distributed transaction throughout |
| Failure after a committed step | Coordinator recovery decides commit/rollback | Runs retry, alternate branch, or compensation |
| HTTP side effects | Cannot coordinate automatically | Can model steps and compensations |
| Complexity | Coordinator infrastructure, XA drivers, recovery | State design, retries, idempotency, and compensation |

A third helpful option is **transactional outbox** when you need to sync a database with a message broker without wanting or being able to use XA. Outbox does not make multiple services commit atomically; it guarantees that the database change and event emission request are saved in the same transaction, after which the message is delivered under at-least-once semantics.

## 15. How to choose a solution

Start from business requirements and the technical capabilities of the resources.

**Choose a local transaction** when all changes live within one database transaction and no other resources need coordination.

**Consider JTA/XA** when:

- Multiple resource managers genuinely support XA.
- The business requires atomic commits across resources.
- Transactions are short and do not wait on users or external APIs.
- The operations team can manage the coordinator, logs, timeouts, and recovery.
- Drivers, providers, and JTA configuration have been verified in the target deployment environment.

**Consider Saga/compensation** when:

- The workflow spans multiple services or independent databases.
- Steps can commit locally and intermediate states are acceptable.
- Clear compensating business actions exist.
- The workflow is long-running, needs independent retries, and may need manual intervention.
- Communication uses HTTP or message brokers that do not support XA.

If a side effect cannot be compensated, design that step at the end of the workflow or add a confirmation/authorization step before executing it. For example, send notification emails only after the order is confirmed, rather than at the start of the Saga.

## 16. Testing and operations

With JTA/XA, you must test far more scenarios than a single happy-path commit test:

1. Both resources prepare and commit successfully.
2. One resource votes NO; verify the other resources roll back.
3. Coordinator crashes after prepare; restart and verify recovery completes the decision.
4. One resource loses connection during the commit phase; test in-doubt state and recovery.
5. Timeouts, deadlocks, or heuristic outcomes are properly logged and alerted.
6. Verify each repository actually participates in the same JTA transaction rather than running on a separate local transaction.

With Saga, test:

1. All forward steps succeed.
2. A step fails transiently and succeeds upon retry.
3. A step fails permanently due to business rules and compensations run in the right order.
4. Compensation invoked multiple times produces the business effect only once.
5. Response timeout after the target service committed; duplicate requests do not create duplicate data.
6. Outbox event is republished; consumer inbox ignores already-processed events.
7. Worker crashes between steps; Saga resumes from durable state after restart.
8. Compensation fails; state is preserved for retry or operational intervention.

Monitoring should include a transaction ID or saga_id across logs, per-step duration metrics, retry counts, in-doubt transaction counts, pending compensations, and dead-letter message counts. Avoid logging only a generic message that hides which resource or step failed.

## 17. Design checklist

- Identify all resources being updated and which transaction manager manages them.
- Verify whether resources truly support XA or only local transactions.
- If using JTA, configure JTA persistence units, XA DataSources, XA JMS resources, and recovery logs.
- Define timeouts and procedures for handling in-doubt/heuristic outcomes.
- Keep XA transactions short; avoid HTTP calls or waiting on external tasks inside transactions.
- If using Saga, define durable state, business keys, forward steps, and compensating steps.
- Design compensation with business semantics; do not assume it is a physical rollback.
- Use outbox/inbox, idempotency keys, and unique constraints to prevent duplicate messages/requests.
- Bound retries with backoff, jitter, and dead-letter queues.
- Test mid-workflow crashes, restarts, duplicate deliveries, and compensation failures.
- Monitor workflow progress and prepare runbooks for manual intervention.

JTA/XA and Saga solve two different classes of problems. XA coordinates commit decisions across protocol-compliant resources; Saga manages a business workflow across independent transactions using retries and compensation. Choose based on atomicity requirements, resource types, processing duration, and operational ability to handle step failures.