# Filter and Business Validation

## 1. Objectives and context

In a Spring Integration flow, receiving a message does not mean the request is allowed to execute. An order placement request can be readable and have all fields populated, yet still violate business rules: the order is already cancelled, the total exceeds the limit, or the currency is unsupported.

This lesson belongs to the **Filter** chapter of the **SPRING_INTEGRATION_CORE** module. The focus is on using `Message`, `MessageChannel`, endpoints, and Java DSL to place a validation gate before business processing steps. We combine a transformer to produce a validation result, a filter to decide whether to proceed, and a separate flow to handle rejected requests. From this, learners can:

- Distinguish malformed structural data, business-invalid requests, and infrastructure failures.
- Choose a rejection policy that fits the flow's contract.
- Retain error codes, reasons, and correlation metadata for each request.
- Write tests for both the accepted branch and the rejected branch.
- Recognize the limits of validating before data-mutation operations.

The running example ingests order submission requests. **Accepted by the filter** in this lesson only means passing the admission rule set; persisting the order, reserving inventory, or processing payment belongs to downstream steps.

## 2. Placing the filter in the right role

### 2.1. Three different questions

| Validation layer | Question | Example | Outcome to design |
|---|---|---|---|
| Input structure and constraints | Is there enough data to understand the request? | Missing `orderId`, `total` is `null`, malformed JSON | Invalid-data reply or route to error ingestion branch |
| Business rules | Given current data and state, may the request proceed? | Order is no longer in draft status, total exceeds intake limit | Rejection result with code and reason |
| Technical executability | Can the system complete the check or processing? | Database connection lost, limit service timed out | Technical error mechanism, conditional retry, or operational handling |

These layers are not tied to a single API. Bean Validation can express business rules too via custom constraints. Conversely, a plain Java method can also check required fields. The division here helps clarify the meaning of results and how to handle them next.

Unreadable JSON must be handled at the ingestion boundary or conversion step. A filter expecting `OrderSubmission` does not turn a broken JSON string into a validation result on its own.

### 2.2. Selectors answer yes or no

A filter delegates its decision to a selector. The core interface is:

~~~java
boolean accept(Message<?> message);
~~~

`true` allows the message to continue; `false` enters the rejection policy. A filter does not use the boolean value as the output payload. The [Filter documentation](https://docs.spring.io/spring-integration/reference/filter.html) describes this contract.

For the order placement problem, the appropriate question is:

> Is this request eligible to enter the order processing branch?

Tasks such as saving the order, deducting inventory, and calling the payment gateway belong in downstream execution endpoints. Placing them inside the selector can repeat side effects if conditions are re-evaluated.

### 2.3. How do filter, transformer, and router collaborate?

| Component | Responsibility in the example |
|---|---|
| Pre-filter transformer | Evaluates rules and builds `CheckedOrder` containing the request and violations |
| Filter | Reads the evaluated result to decide whether to proceed |
| Accepted-branch transformer | Extracts `OrderSubmission` so downstream steps do not depend on the validation model |
| Discard branch | Converts invalid results into `OrderRejected` |
| Router, when needed | Selects among multiple business outcomes such as accept, manual approval required, and reject |

For a proceed-or-reject gate, a filter expresses intent clearly. When there are multiple peer business destinations, a result model paired with a router is usually easier to read than nested filter chains.

## 3. Choosing the contract on rejection

### 3.1. Basic policies

The table below applies when the selector returns `false` and sending to the discard channel, if present, completes normally:

| `discardChannel` | `throwExceptionOnRejection` | Behavior |
|---|---|---|
| Not configured | `false`, default | Does not forward the message |
| Configured | `false` | Sends message to the discard channel |
| Not configured | `true` | Throws `MessageRejectedException` |
| Configured | `true` | Sends to the discard channel, then throws `MessageRejectedException` |

`discardChannel` and `throwExceptionOnRejection` are two independent options; configuring both does not disable throwing the exception. The [FilterEndpointSpec API](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/FilterEndpointSpec.html) describes this ordering.

In the default configuration with no discard channel, Spring Integration 6.1+ logs a warning for dropped messages. A log warning does not replace a business reply or storage for rejected requests. [Filter documentation](https://docs.spring.io/spring-integration/reference/filter.html)

In the main example, an invalid request is an expected outcome. We choose **discard channel without throwing an exception** so we can record reasons without pushing all rejections into the technical error mechanism.

### 3.2. False differs from an exception in the selector

If a validator returns a result containing violations and the selector returns `false`, that is a rejection under the filter policy.

If a validator calls an external service and times out, or a selector hits a `NullPointerException`, processing fails with an exception. The filter does not automatically convert that exception into `false`, nor does it synthesize a list of violations. The rejection mechanism governs only the branch where the selector does not accept the message. [MessageFilter API](https://docs.spring.io/spring-integration/api/org/springframework/integration/filter/MessageFilter.html)

Therefore, avoid writing:

~~~java
// Cannot distinguish invalid requests from a system unable to validate.
try {
    return customerService.canPlaceOrder(order.customerId());
} catch (Exception ex) {
    return false;
}
~~~

A timeout is insufficient evidence to conclude a customer is ineligible. Let technical errors follow an appropriate error-handling policy or explicitly represent an unverified state.

## 4. Designing the rule set for the example

Suppose the order-intake business rules state:

1. `orderId`, `customerId`, and `currency` must not be blank; `total` and `status` must be present.
2. Only accept orders with status `DRAFT`.
3. `total` must be greater than 0 and not exceed 50,000,000.
4. Only `VND` is supported.

These are illustrative rules for a specific service, not built-in Spring Integration limits. Input data has already been converted into a Java object before entering the flow.

### 4.1. Evaluate once, use the result on both branches

If a selector returns only a boolean, the rejection branch typically does not know which rule failed. Calling the validator again in that branch increases cost and can yield different results if external conditions changed.

In this lesson, we create a wrapper object:

~~~text
CheckedOrder
├── order: OrderSubmission
└── validation: ValidationResult
    └── violations: List<Violation>
~~~

The filter reads `validation.valid()`. The rejection branch uses the exact list of violations already computed. Do not store the "latest validation result" in a singleton bean field; multiple messages may be processed concurrently.

Each violation contains:

| Property | Purpose |
|---|---|
| `code` | Stable code for callers, tests, and analytics |
| `field` | Field or scope related to the error |
| `message` | Human-readable explanation |

For example, `TOTAL_LIMIT_EXCEEDED` is more stable than asserting on the string `"Total exceeds intake limit"`, because human-readable text may be translated or revised.

### 4.2. Message flow

~~~mermaid
flowchart TD
    A["ordersIn: OrderSubmission"] --> B["Transformer: evaluate rules"]
    B --> C["CheckedOrder"]
    C --> D{"Filter: validation.valid()"}
    D -->|true| E["Transformer: extract OrderSubmission"]
    E --> F["ordersAccepted"]
    D -->|false| G["ordersRejected: CheckedOrder"]
    G --> H["Transformer: build OrderRejected"]
    H --> I["rejectionEvents"]
~~~

The name `ordersAccepted` indicates the order passed intake validation. It does not yet indicate that the order has been persisted or paid.

## 5. Implementation using Java DSL

### 5.1. Requirements for the example

The example uses Java 17+ syntax, Spring Context, and Spring Integration Core with the `IntegrationFlow.from(...)` API. Required foundational dependencies:

- `org.springframework:spring-context`.
- `org.springframework.integration:spring-integration-core`.
- `org.junit.jupiter:junit-jupiter` for the test section later.

Select compatible versions via your project's dependency management platform. If using Spring Boot, you can bring in the main dependencies via the Integration starter. The example requires no broker, database, or external service.

### 5.2. Configuration, models, and validator

The snippet below is one complete class; data types are nested inside the configuration class to keep the self-contained example easy to follow:

~~~java
package example.integration;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class OrderValidationConfig {

    public enum OrderStatus {
        DRAFT, SUBMITTED, CANCELLED
    }

    public record OrderSubmission(
            String orderId,
            String customerId,
            BigDecimal total,
            String currency,
            OrderStatus status) {
    }

    public record Violation(
            String code,
            String field,
            String message) {
    }

    public record ValidationResult(List<Violation> violations) {

        public ValidationResult {
            violations = List.copyOf(violations);
        }

        public boolean valid() {
            return violations.isEmpty();
        }
    }

    public record CheckedOrder(
            OrderSubmission order,
            ValidationResult validation) {
    }

    public record OrderRejected(
            String orderId,
            List<Violation> violations) {

        public OrderRejected {
            violations = List.copyOf(violations);
        }
    }

    public static class OrderPolicy {

        private static final BigDecimal MAX_TOTAL =
                new BigDecimal("50000000");

        public ValidationResult validate(OrderSubmission order) {
            List<Violation> violations = new ArrayList<>();

            if (blank(order.orderId())) {
                violations.add(new Violation(
                        "MISSING_ORDER_ID", "orderId",
                        "Order ID must be provided"));
            }
            if (blank(order.customerId())) {
                violations.add(new Violation(
                        "MISSING_CUSTOMER_ID", "customerId",
                        "Customer ID must be provided"));
            }
            if (order.total() == null) {
                violations.add(new Violation(
                        "MISSING_TOTAL", "total",
                        "Total amount must be provided"));
            }
            if (blank(order.currency())) {
                violations.add(new Violation(
                        "MISSING_CURRENCY", "currency",
                        "Currency must be provided"));
            }
            if (order.status() == null) {
                violations.add(new Violation(
                        "MISSING_STATUS", "status",
                        "Order status must be provided"));
            }

            // Evaluate business rules only when all required fields are present.
            if (!violations.isEmpty()) {
                return new ValidationResult(violations);
            }

            if (order.status() != OrderStatus.DRAFT) {
                violations.add(new Violation(
                        "ORDER_NOT_DRAFT", "status",
                        "Only orders in DRAFT status are accepted"));
            }
            if (order.total().signum() <= 0) {
                violations.add(new Violation(
                        "TOTAL_NOT_POSITIVE", "total",
                        "Total amount must be greater than 0"));
            }
            if (order.total().compareTo(MAX_TOTAL) > 0) {
                violations.add(new Violation(
                        "TOTAL_LIMIT_EXCEEDED", "total",
                        "Total amount exceeds intake limit"));
            }
            if (!"VND".equals(order.currency())) {
                violations.add(new Violation(
                        "CURRENCY_NOT_SUPPORTED", "currency",
                        "Service accepts orders in VND only"));
            }

            return new ValidationResult(violations);
        }

        private boolean blank(String value) {
            return value == null || value.isBlank();
        }
    }

    @Bean
    public OrderPolicy orderPolicy() {
        return new OrderPolicy();
    }

    @Bean
    public MessageChannel ordersIn() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel ordersRejected() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel ordersAccepted() {
        return new QueueChannel(100);
    }

    @Bean
    public QueueChannel rejectionEvents() {
        return new QueueChannel(100);
    }

    @Bean
    public IntegrationFlow orderValidationFlow(OrderPolicy orderPolicy) {
        return IntegrationFlow.from("ordersIn")
                .transform(OrderSubmission.class,
                        order -> new CheckedOrder(
                                order, orderPolicy.validate(order)))
                .filter(CheckedOrder.class,
                        checked -> checked.validation().valid(),
                        endpoint -> endpoint
                                .id("businessValidationFilter")
                                .discardChannel("ordersRejected")
                                .throwExceptionOnRejection(false))
                .transform(CheckedOrder.class, CheckedOrder::order)
                .channel("ordersAccepted")
                .get();
    }

    @Bean
    public IntegrationFlow rejectedOrdersFlow() {
        return IntegrationFlow.from("ordersRejected")
                .transform(CheckedOrder.class,
                        checked -> new OrderRejected(
                                checked.order().orderId(),
                                checked.validation().violations()))
                .channel("rejectionEvents")
                .get();
    }
}
~~~

### 5.3. Reading the example by responsibility

`OrderPolicy` does not depend on messaging APIs. It creates a fresh violation list per invocation. `List.copyOf(...)` prevents downstream branches from mutating the result list after evaluation. Monetary comparison uses `BigDecimal.compareTo(...)`; do not use `equals(...)` for value comparisons because scales may differ.

The validator collects structural errors first. When errors exist at this layer, it returns immediately to avoid reading missing properties. When all data is present, it collects all business violations in the example, enabling callers to fix multiple issues in one pass.

`ordersIn` and `ordersRejected` are `DirectChannel` beans. The two `QueueChannel` beans at the ends of the flows hold results for tests to pull; sending to them does not trigger a downstream business step yet. An endpoint consuming from a queue later will need an appropriate poller. Queues by default in this configuration store messages in memory and are not durable storage. [MessageChannel implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)

Capacity 100 serves only the small example. When no consumer exists and the queue fills up, sends can block; in real deployments, design consumers, wait bounds, and overload policies.

### 5.4. What is the payload on the discard channel?

At the filter position, the payload is `CheckedOrder`. Thus `ordersRejected` receives this model, not the original `OrderSubmission` and not an `ErrorMessage`. The rejection-branch transformer explicitly builds `OrderRejected` from the evaluated result.

The filter does not pre-populate codes like `ORDER_NOT_DRAFT`. They are part of the application-defined business model.

## 6. Testing the contract of both branches

### 6.1. What needs to be proven

Checking only that `ordersIn.send(...)` returns `true` is insufficient. A successful send does not mean the request is business-valid: a message rejected by the filter can still be processed normally by the discard flow.

For this example, each test must observe the outputs:

| Situation | `ordersAccepted` | `rejectionEvents` |
|---|---|---|
| Draft order, VND, positive total within limit | One `OrderSubmission` | None |
| Exactly at threshold 50,000,000 | One `OrderSubmission` | None |
| Cancelled order, over limit, currency USD | None | One `OrderRejected` with three violation codes |
| Missing `total` | None | One `OrderRejected` with `MISSING_TOTAL` |

For pure data rules, add cases for zero total, negative total, one unit above threshold, whitespace-only ID, and `null` status. You do not need to spin up the full flow to test every individual comparison in `OrderPolicy`.

### 6.2. Testing example using JUnit Jupiter

The class below uses the types nested in `OrderValidationConfig`. Each test creates a fresh context so messages from a previous test do not remain in queues for the next test:

~~~java
package example.integration;

import java.math.BigDecimal;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

import example.integration.OrderValidationConfig.OrderRejected;
import example.integration.OrderValidationConfig.OrderStatus;
import example.integration.OrderValidationConfig.OrderSubmission;
import example.integration.OrderValidationConfig.Violation;

import static org.junit.jupiter.api.Assertions.*;

class OrderValidationFlowTest {

    private AnnotationConfigApplicationContext context;
    private MessageChannel input;
    private QueueChannel accepted;
    private QueueChannel rejected;

    @BeforeEach
    void setUp() {
        context = new AnnotationConfigApplicationContext(
                OrderValidationConfig.class);
        input = context.getBean("ordersIn", MessageChannel.class);
        accepted = context.getBean("ordersAccepted", QueueChannel.class);
        rejected = context.getBean("rejectionEvents", QueueChannel.class);
    }

    @AfterEach
    void tearDown() {
        context.close();
    }

    @Test
    void acceptsOrderAtUpperLimitAndPreservesRequestId() {
        var order = new OrderSubmission(
                "ORD-1001", "CUS-01",
                new BigDecimal("50000000"),
                "VND", OrderStatus.DRAFT);

        boolean sent = input.send(MessageBuilder.withPayload(order)
                .setHeader("requestId", "REQ-1001")
                .build());

        assertTrue(sent);
        Message<?> message = accepted.receive(0);
        assertNotNull(message);
        assertEquals(order, message.getPayload());
        assertEquals("REQ-1001",
                message.getHeaders().get("requestId"));
        assertNull(accepted.receive(0));
        assertNull(rejected.receive(0));
    }

    @Test
    void rejectsOrderWithAllBusinessViolations() {
        var order = new OrderSubmission(
                "ORD-1002", "CUS-02",
                new BigDecimal("60000000"),
                "USD", OrderStatus.CANCELLED);

        assertTrue(input.send(MessageBuilder.withPayload(order).build()));

        Message<?> message = rejected.receive(0);
        assertNotNull(message);
        OrderRejected event = assertInstanceOf(
                OrderRejected.class, message.getPayload());
        assertEquals("ORD-1002", event.orderId());
        assertEquals(3, event.violations().size());
        Set<String> codes = event.violations().stream()
                .map(Violation::code)
                .collect(Collectors.toSet());
        assertEquals(Set.of(
                "ORDER_NOT_DRAFT",
                "TOTAL_LIMIT_EXCEEDED",
                "CURRENCY_NOT_SUPPORTED"), codes);
        assertNull(accepted.receive(0));
        assertNull(rejected.receive(0));
    }

    @Test
    void turnsMissingTotalIntoValidationResult() {
        var order = new OrderSubmission(
                "ORD-1003", "CUS-03",
                null, "VND", OrderStatus.DRAFT);

        assertTrue(input.send(MessageBuilder.withPayload(order).build()));

        Message<?> message = rejected.receive(0);
        assertNotNull(message);
        OrderRejected event = assertInstanceOf(
                OrderRejected.class, message.getPayload());
        assertEquals(1, event.violations().size());
        assertEquals("MISSING_TOTAL",
                event.violations().get(0).code());
        assertNull(accepted.receive(0));
        assertNull(rejected.receive(0));
    }
}
~~~

`receive(0)` does not block. It fits here because rule evaluation and queuing run synchronously over `DirectChannel` instances before `send(...)` returns. If you switch the flow to execute via an executor or broker, use an appropriate bounded timeout; do not keep synchronous assumptions. [MessageChannel implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)

Tests for the rejected branch check both error codes and the absence of any message on the accepted branch. This catches configuration bugs that let invalid messages slip forward, rather than only verifying that a rejection event was emitted.

## 7. Combining with Bean Validation

In the full example, required fields are checked in Java so no extra provider is needed. If your project already uses Jakarta Bean Validation, you can replace the structural checks with constraints on an input DTO:

~~~java
import java.math.BigDecimal;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import example.integration.OrderValidationConfig.OrderStatus;

public record OrderInput(
        @NotBlank String orderId,
        @NotBlank String customerId,
        @NotNull BigDecimal total,
        @NotBlank String currency,
        @NotNull OrderStatus status) {
}
~~~

Spring provides `LocalValidatorFactoryBean` to supply `jakarta.validation.Validator` when a compatible Bean Validation provider is on the classpath. Constraints are evaluated only when validation is triggered, such as by calling `validator.validate(input)` at the start of the flow. [Java Bean Validation in Spring](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)

One way to organize this is:

~~~text
OrderInput
  -> validator.validate(input)
  -> constraint violations present: produce invalid-data result
  -> no violations: convert to OrderSubmission
  -> evaluate admission rules
  -> filter
~~~

Do not assume that putting `@Valid` on an arbitrary object automatically validates every message passing through Java DSL. If using proxy-based method validation or HTTP-boundary validation, verify which call path actually triggers it.

When mapping constraint violations into application `Violation` records:

- Map to stable contract error codes; do not use translated messages as codes.
- Do not rely on violation iteration order; sort if responses need deterministic ordering.
- Avoid leaking sensitive input values into rejection messages or events.

After this step, you can still use the same `ValidationResult` model and the same rejection-branch handling. There is no need to duplicate required-field checks in both Bean Validation and `OrderPolicy`.

## 8. When you want to throw an exception on rejection

Some contracts require the caller to receive an error immediately when a request is blocked. In that case, you can replace the filter configuration with the following snippet:

~~~java
.filter(CheckedOrder.class,
        checked -> checked.validation().valid(),
        endpoint -> endpoint
                .id("strictBusinessValidationFilter")
                .throwExceptionOnRejection(true))
~~~

This is an **alternative configuration**, not a second filter to append to the main example. It produces `MessageRejectedException` when the selector returns `false`; that exception does not automatically turn into an HTTP response with status code and application-defined violation list.

If you need to propagate detailed business errors via exceptions, design a custom exception carrying `ValidationResult` at an appropriate processing step, then map it at the boundary. Explicitly choose one contract: result reply, rejection event, or exception.

### 8.1. Exception propagation depends on execution style

Direct sends over `DirectChannel` run the handler on the caller's thread; exceptions can propagate back to the send call, possibly wrapped by the framework in a messaging exception. With asynchronous tasks such as a poller, errors are typically published as `ErrorMessage` through the error handler mechanism. You cannot treat the `errorChannel` header as a directive that always catches all synchronous errors. [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)

`ordersRejected` in the example is a business channel. `errorChannel` is part of exception handling. Even though both can lead to incident recording, their payloads and contract semantics differ.

### 8.2. Retries must understand what is being repeated

Resending the exact same cancelled order will not make it valid. Fixed rule violations should end in a rejection result; transient technical failures are the candidates for bounded retries.

If you wrap the filter in a retry advice, by default the discard action sits inside the advice scope. Failures in the discard branch or the rejection exception can cause processing to repeat. You can configure `discardWithinAdvice(false)` to move the discard action outside that advice, though you must still design reliability for the rejection branch separately. [Advising Filters](https://docs.spring.io/spring-integration/reference/handler-advice/advising-filters.html)

For example, writing an audit record and then throwing an exception can create multiple records if the entire section is retried. Define request identifiers and deduplication for operations with side effects.

## 9. Request-reply gateways need a reply for every outcome

The sample flow ends at output queues to illustrate ingestion and result observation. It is not configured as a complete request-reply API.

Suppose a gateway declares:

~~~java
OrderReply submit(OrderSubmission order);
~~~

If the success branch builds `OrderReply` while the rejection branch only logs and terminates, the caller has no business reply for blocked cases. The caller may wait until reply timeout or receive a no-reply outcome depending on configuration.

Gateways use the reply channel to receive answers; routing messages to a separate discard channel does not automatically guarantee an answer returns to the caller. Wire the reply path explicitly and configure timeouts according to the contract. [Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html)

Three common choices:

| Contract | Appropriate design |
|---|---|
| One-way send, receive outcome later | `void` gateway or one-way producer; emit accept/reject events with correlation metadata |
| Return immediate result for both cases | `OrderReply` model with status and error codes; ensure both branches produce a reply |
| Caller handles errors via exception | Configure rejection exception and clear error mapping at the boundary |

For requirements expecting an immediate reply, you can evaluate with a transformer and then use a router to pick the reply-building branch. A filter remains useful as a control gate, yet a selector's boolean is not a business reply.

If using a discard subflow to produce replies, test that messages actually reach the gateway's reply channel. Seeing a return value from a handler in one branch is not enough to prove the entire request-reply contract works.

## 10. Limitations when rules depend on external state

### 10.1. Early validation does not guarantee downstream operations succeed

The example read `status` from the incoming request itself for simplicity. In a real system, current state must be fetched from an authoritative source such as a database; never trust a caller-supplied status to authorize an important state transition.

Even when reading from the authoritative source, two points in time can still differ:

~~~text
T1: Validator reads order ORD-2001 in DRAFT status.
T2: Another flow cancels order ORD-2001.
T3: The stale request passes the filter based on the T1 result.
T4: Execution endpoint attempts to transition order to SUBMITTED.
~~~

The filter at T3 cannot replace condition protection at T4. The write step must re-verify under an appropriate consistency mechanism: optimistic locking with version, transactional locking, or a conditional update statement.

Illustrative update operation:

~~~sql
UPDATE orders
SET status = 'SUBMITTED',
    version = version + 1
WHERE id = :orderId
  AND status = 'DRAFT'
  AND version = :expectedVersion;
~~~

If zero rows are updated, the execution step must classify the outcome: status changed, version no longer matches, or no matching order exists. Never assume success merely because an earlier filter accepted the message.

For inventory or spending limits, checking and reserving the resource must also be designed where that resource is managed. Separate "read enough available" and "update" steps can allow multiple concurrent requests to slip through.

### 10.2. Static rules vs. lookup-dependent rules

| Rule | Characteristic | Design approach to consider |
|---|---|---|
| Positive total, supported currency | Evaluated from existing data | Pure-data validator as in the example |
| Customer permitted to transact | Depends on external state | State-fetching step with timeout, then policy evaluation |
| Price applicable at receipt time | Depends on time and rule version | Record exact timestamp and rule version used in evaluation |
| Does not exceed shared inventory or limit | Contended across concurrent requests | Check and reserve/update via appropriate consistency mechanism |

When reading time, inject a `Clock` into the validator instead of scattering system-clock calls. Tests can pin the clock to verify exact time boundaries.

If calling an external service is required, put an explicit data-fetching step before the validator to separate service-call errors from rule outcomes. The evaluation result should indicate which data snapshot it relied on if tracing or replay is needed.

### 10.3. Do not equate validation with duplicate prevention

A valid request can be submitted multiple times. A filter checking total amount and status does not automatically guarantee order persistence or payment executes only once.

When retries exist or a broker can redeliver messages, steps with side effects need deduplication keyed by a business identifier, such as a consistently managed request ID or an appropriate uniqueness constraint. `MessageHeaders.ID` should not be used as a stable business identifier across redeliveries.

## 11. Designing an operable rejection branch

### 11.1. Information to retain

In a real application, a rejection outcome typically needs the following information depending on the contract:

| Information | Purpose |
|---|---|
| Request ID or correlation ID | Links requests, logs, and replies |
| Order ID if present | Looks up the related business entity |
| List of violation codes | Helps callers fix data and enables cause analytics |
| Evaluation timestamp | Explains outcomes when rules depend on time |
| Rule version | Identifies which policy applied if policies change |
| Event ID or deduplication key | Prevents duplicate recording or processing |

Request ID is especially valuable when `orderId` itself is missing. In the example, the custom `requestId` header is preserved across ordinary payload transformations and verified on the accepted branch. You can add a similar check for the rejected branch.

If results need to be published to a broker or stored long-term, put required correlation fields into the event contract or supported headers. Do not assume all internal header objects serialize cleanly across system boundaries.

### 11.2. Distinguishing message counts from violation counts

One order can violate three rules. When observing the system, distinguish:

- Count of evaluated requests.
- Count of accepted requests.
- Count of rejected requests.
- Occurrence count of each violation code.
- Count of evaluations unable to complete due to technical errors.

Three violations on one order still correspond to one rejected request. You can use violation codes as bounded-cardinality metric labels; avoid using individual order IDs or request IDs as metric labels.

Keep logs concise enough to trace by identifier. Do not dump full payloads if they contain personal information or payment data.

### 11.3. A discard channel does not guarantee durable persistence

In the example, `rejectionEvents` is an in-memory queue. Putting a result onto this queue does not mean the result survives a process restart. When rejection outcomes must be preserved, add durable storage or an appropriate event-publishing mechanism.

If sending on the discard branch fails, the flow can raise a technical error. Configuring `throwExceptionOnRejection(false)` only disables the intentional rejection exception; it does not suppress exceptions from other endpoints.

If updating data and emitting events consistently are required, design transaction boundaries or patterns such as outbox where those operations run. A discard channel alone does not provide atomicity between a database and a broker.

## 12. Common design mistakes

| Practice | Resulting issue | Fix |
|---|---|---|
| Checking only `send(...) == true` | Cannot tell whether request was accepted or routed to discard | Check outputs and response contract |
| Selector returns `false` without saving reasons | Callers and operators do not know which rule failed | Evaluate into `ValidationResult` before the filter |
| Calling validator again in discard branch | Extra cost, may get different results than first run | Carry the evaluation result with each message |
| Storing errors in a singleton validator field | Results across concurrent messages overwrite each other | Use local variables and immutable result objects |
| Persisting data or charging payment inside selector | Validation has side effects and is unsafe to repeat | Place execution operations after the validation gate |
| Turning every exception into `false` | Infrastructure failures are reported as business errors | Separate rejection outcomes from inability to validate |
| Reading `status` from request and trusting it blindly | Caller may supply stale or incorrect status | Read state from authoritative source and guard writes |
| Enabling retries for every rejection | Repeats invalid requests with unchanged outcome | Bounded retries only for recoverable errors |
| Using the sample flow directly as request-reply | Rejection branch produces no reply to caller | Design and test return paths for all outcomes |
| Treating an in-memory queue as final error storage | Data lost when process stops | Choose durable storage if required by contract |

## 13. Applying this to a new flow

When adding business validation to a message flow, start from the request contract:

1. Identify the outcome the caller needs: immediate reply, later event, or exception.
2. List admission rules and separate data violations from inability-to-validate errors.
3. Produce an evaluation result with violation codes, not just a boolean.
4. Place the filter before side-effecting steps and define the rejection branch clearly.
5. Re-guard mutable conditions at the actual update step.
6. Test both branches, boundary values, and preservation of correlation metadata.
7. Decide where rejection outcomes are stored and how the system behaves when that store is unavailable.

For the lesson's order-intake flow, a sensible hands-on extension is adding a rule "customer is permitted to transact". Create two distinct scenarios: the customer service returns not-permitted, and the customer service times out. The first scenario must produce a business rejection code; the second must preserve technical error semantics. This exercise verifies that the filter gates admission while error handling still accurately reflects system executability.
