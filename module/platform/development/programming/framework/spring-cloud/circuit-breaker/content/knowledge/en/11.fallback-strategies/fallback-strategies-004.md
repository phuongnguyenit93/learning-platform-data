# Rejecting Critical Operations Instead of Faking Success

Fallback helps an application keep responding when a dependent service fails or a circuit breaker is `OPEN`. However, not every request can be replaced by a default value. For operations that mutate business state—such as payments, order creation, inventory reservation, money transfers, or granting permissions—returning a fake success result can mislead users and downstream systems into believing the operation completed when there is no evidence of it.

In these cases, the safe fallback is typically to reject the operation in a controlled manner, return a transient error, or report an undetermined outcome so the caller can look up the status using a transaction ID. A circuit breaker protects a dependency by blocking new calls when the circuit is open; it does not complete the business operation on its own, store requests for replay, or guarantee rollback of an operation that already reached the dependent system.

## 1. Distinguishing Read Operations from Write Operations

A backup value can be useful for read queries. For instance, when the catalog service does not respond, the application can return stale cached data along with its update timestamp. For critical write operations, returning default data or simulating a success state can corrupt business state.

| Operation Type | Example | Typically Appropriate Fallback |
| --- | --- | --- |
| Read tolerant of stale data | Viewing product names, page content, non-time-sensitive configuration | Bounded-age cache with stale-data indicators |
| Read requiring latest data | Checking current balance, checking stock before confirmation | Report inability to verify or ask caller to retry later |
| Write mutating business state | Payment, order creation, stock reservation, fund transfer | Reject temporarily or report undetermined outcome; do not fabricate success |
| Write queueable under business contract | Submitting a background job, creating a report export task | Confirm acceptance only after durable persistence into a queue or outbox |

The fallback decision must rest on the operation's semantics and the API contract. A `true` result, a dummy order object, an amount of `0`, or `Optional.empty()` cannot substitute for confirmation from the authoritative system.

## 2. Why Fake Success Causes Data Divergence

Suppose the Order Service calls the Payment Service to authorize a payment. The Payment Service does not respond and the circuit breaker opens. If the fallback returns `PaymentResult.approved()`, the Order Service may:

- Transition the order to a paid status.
- Deduct inventory or issue a shipping command.
- Send a payment confirmation email.
- Record an unconfirmed transaction in revenue reports.

Downstream steps may not be automatically fixable by retrying the original request. Data across multiple services has diverged while the user sees a success message.

For critical commands, state truth must be preserved: mark completion only upon receiving valid confirmation or when the system has durably stored an asynchronous processing request under an explicit contract. When confirmation is impossible, return an error or a pending-verification status instead of guessing the outcome.

## 3. Distinguishing an OPEN Circuit Breaker from a Post-Call Timeout

Two situations often lead to a fallback yet carry very different meanings:

| Situation | Did the Supplier Run? | What Can Be Concluded | Safe Response Strategy |
| --- | --- | --- | --- |
| Breaker is `OPEN` | No | The current call was blocked before sending a request through the supplier | Report dependency temporarily unavailable; ask caller to retry per policy |
| Supplier ran and received an explicit rejection | Yes | The dependency returned a concrete error outcome | Map error per business contract; never turn it into success |
| Supplier ran but timed out or lost connection | Yes | Unknown whether the dependency processed the command | Report undetermined outcome and allow lookup via operation ID / idempotency key |
| Breaker is `HALF_OPEN` and permits a probe call | Yes | This is a real request permitted to probe the dependency | Confirm only based on actual outcome; protect command with idempotency |

When the breaker is `OPEN`, `CallNotPermittedException` indicates the supplier did not run on that call. Conversely, a timeout after sending a request does not prove the operation was not executed. For example, the Payment Service may have recorded the payment while the response was lost on the network. If the caller submits a new command, the customer risks being charged twice.

Do not collapse all exceptions into a single "not processed" message. Distinguish definite rejections, dependency unavailability before sending the request, and undetermined outcomes after the request may have arrived.

## 4. Fallbacks for Critical Commands Should Fail Explicitly

With Spring Cloud CircuitBreaker, the `run(...)` fallback can throw a business exception indicating that the dependency is unavailable. The example below protects a payment authorization operation:

```java
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final PaymentClient paymentClient;

    public PaymentService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            PaymentClient paymentClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.paymentClient = paymentClient;
    }

    public PaymentAuthorization authorize(PaymentCommand command) {
        return circuitBreakerFactory.create("paymentAuthorization").run(
            () -> paymentClient.authorize(
                command,
                command.idempotencyKey()
            ),
            cause -> {
                if (cause instanceof CallNotPermittedException) {
                    throw new PaymentDependencyUnavailableException(
                        "Payment service is temporarily unavailable", cause
                    );
                }

                if (isTimeout(cause)) {
                    throw new PaymentOutcomeUnknownException(
                        command.operationId(), cause
                    );
                }

                throw new PaymentDependencyUnavailableException(
                    "Payment authorization could not be confirmed", cause
                );
            }
        );
    }

    private boolean isTimeout(Throwable cause) {
        for (Throwable current = cause; current != null; current = current.getCause()) {
            if (current instanceof java.util.concurrent.TimeoutException
                    || current instanceof java.net.SocketTimeoutException) {
                return true;
            }
        }
        return false;
    }
}
```

This is an illustrative example; business exceptions must be defined in your application. `CallNotPermittedException` is handled as the case where the breaker blocked the call before the supplier ran. Timeouts are separated because the command outcome may be unknown. Remaining errors are reported as unable to confirm authorization; in a real implementation, further classify explicit rejection errors according to the Payment Service contract.

The fallback does not return a fake `PaymentAuthorization`. Because the fallback throws an exception, the caller cannot mistake an unconfirmed operation for a successful payment.

## 5. Mapping Errors to Meaningful HTTP Responses

The API layer should translate business exceptions into appropriate HTTP statuses and payloads with enough detail for callers to decide the next step. Example using Spring MVC on Spring Framework 6:

```java
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class PaymentExceptionHandler {

    @ExceptionHandler(PaymentDependencyUnavailableException.class)
    ResponseEntity<ProblemDetail> dependencyUnavailable(
            PaymentDependencyUnavailableException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.SERVICE_UNAVAILABLE,
            "Payment authorization is temporarily unavailable. No success was confirmed."
        );
        problem.setTitle("Payment service unavailable");
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(problem);
    }

    @ExceptionHandler(PaymentOutcomeUnknownException.class)
    ResponseEntity<ProblemDetail> outcomeUnknown(
            PaymentOutcomeUnknownException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.GATEWAY_TIMEOUT,
            "The payment result could not be confirmed. Check the operation status before retrying."
        );
        problem.setTitle("Payment outcome unknown");
        problem.setProperty("operationId", ex.operationId());
        return ResponseEntity.status(HttpStatus.GATEWAY_TIMEOUT).body(problem);
    }
}
```

`503 Service Unavailable` fits when the breaker rejects calls because the dependency is unavailable. `504 Gateway Timeout` can fit when the application waits on the dependency past its deadline and receives no response. Depending on your API architecture, you may use a unified business error code, but the payload must state clearly whether the outcome was confirmed. Never return `200 OK` with `success: true` simply because a fallback ran.

Do not expose stack traces, credentials, or internal dependency details in public responses. Log the full cause in controlled logs and correlate logs with the operation ID for investigation.

## 6. Idempotency Protects When Outcomes Are Unknown

A timeout does not mean the command failed. When a request might already have been processed, the caller needs a stable idempotency key to query or safely resubmit the same operation without producing duplicate side effects.

A payment flow might work as follows:

1. The caller generates a unique `operationId` or idempotency key for the payment intent.
2. The Payment Service persists the key alongside the processing state and result once the command is received.
3. The caller sends the command with that key.
4. If the response times out, the caller keeps the same key and queries status using the operation ID.
5. If retransmission is needed, the caller reuses the original key; the Payment Service must detect the duplicate request and return the stored status or continue processing per defined rules.

Example request:

```http
POST /payments/authorizations
Idempotency-Key: pay-order-8472
Content-Type: application/json

{
  "orderId": "order-8472",
  "amount": 1250000,
  "currency": "VND"
}
```

The key must be derived from the business intent and remain unchanged across retries of the same operation. Never generate a new key on every timeout. Idempotency is only effective if the receiving side persistently stores and enforces deduplication rules; sending a header without server-side enforcement provides no guarantee.

Idempotency also does not replace status lookup. When the outcome is unclear, provide an endpoint like `GET /operations/{operationId}` or a reconciliation flow so callers can see whether the command is pending, completed, rejected, or requires intervention.

## 7. When Can a Command Be Accepted for Asynchronous Processing?

Some business flows allow the system to acknowledge receipt of a request before work completes. For example, a user requests a report export or triggers a background job. In that case, a `202 Accepted` response is not a fake success if the application has durably persisted the command and the API contract clearly defines it as receipt acknowledgment.

A common pattern is the transactional outbox:

1. Within a local transaction, save the operation record and the outbox message.
2. Only after the transaction commits successfully does the API return `202 Accepted` with the `operationId`.
3. A worker reads the outbox and dispatches the command to the dependency.
4. If the dependency is temporarily unavailable, the worker retries with bounded backoff while a circuit breaker protects the call.
5. Once processing finishes, update the operation status for caller lookup.

```text
HTTP command
     |
     v
Database transaction
  - operation record
  - outbox message
     |
   COMMIT
     |
     +------> 202 Accepted + operationId
     |
     v
Outbox worker
     |
     v
Circuit breaker -> Dependency
     |
     +---- success / rejected / retryable failure
     |
     v
Update operation status
```

Only return `202` after the acceptance record has been durably persisted. If the database or durable queue is also unavailable, reject the request. A message residing only in process memory is not enough to promise the command will run after an application restart.

Not every command can be shifted to asynchronous processing. Only use this approach when business rules permit eventual completion, callers can query status, and clear failure-handling or reconciliation procedures exist.

## 8. Avoiding Blind Retries Inside a Fallback

A fallback must not immediately call the same dependency again via another client or repeat the command with a new key. Such behavior can bypass the circuit breaker and amplify load on an already degraded system. For commands with side effects, retrying is only safe when:

- An idempotency key is durably enforced by the receiving side.
- The error type indicates the call is retryable, or status is queried before resending.
- There is a bounded retry count, exponential backoff, and jitter.
- The request or workflow deadline still has enough remaining budget.
- Retries live at a single clearly responsible layer, avoiding stacked retries across layers that multiply call counts.

When the breaker is `OPEN`, the supplier is prevented from running. If the fallback calls an alternate path to the same dependency on its own, it defeats that protection. Return a transient error or persist a durable command following a properly designed asynchronous model instead.

## 9. Testing to Ensure No Fake Success Occurs

Tests must verify both the response and the dependency invocation count. When the breaker is `OPEN`, the client must not be invoked and the service must return the appropriate error or pending state. For a timeout after the supplier has run, the service must not assume the command succeeded or failed without evidence.

Conceptual test example with Mockito:

```java
// Assume the paymentAuthorization breaker has been opened in the test fixture.
assertThatThrownBy(() -> paymentService.authorize(command))
    .isInstanceOf(PaymentDependencyUnavailableException.class);

// Supplier does not run when the breaker is OPEN.
verifyNoInteractions(paymentClient);
```

For the timeout scenario:

```java
when(paymentClient.authorize(command, command.idempotencyKey()))
    .thenThrow(new SocketTimeoutException("response timed out"));

assertThatThrownBy(() -> paymentService.authorize(command))
    .isInstanceOf(PaymentOutcomeUnknownException.class);

verify(paymentClient, times(1))
    .authorize(command, command.idempotencyKey());
```

These snippets assume tests have configured the matching breaker ID and mocks. Add tests for the following cases:

- Fallback never returns an `approved`, `completed`, or default object implying the command succeeded.
- `OPEN` breaker rejects before the client is called.
- Timeout exposes an operation ID for the caller to look up status.
- Resending the same idempotency key does not trigger duplicate payments or duplicate orders.
- If using an outbox, the API returns `202` only after the transaction saving the operation and outbox record commits.
- When the breaker is `HALF_OPEN`, probe calls are real requests; commands must be protected by idempotency like any other call.

## 10. Rules for Choosing Fallbacks on Critical Operations

- For write operations requiring immediate confirmation, return a transient error when the breaker opens; never fake success.
- For timeouts after a request may have reached the dependency, represent an undetermined outcome and provide an operation ID for lookup.
- Keep the idempotency key constant across retries of the same business intent.
- Return `202 Accepted` only after the command is durably stored and the system has tracking, retry, and reconciliation mechanisms.
- Never let a fallback call the same dependency outside the circuit breaker.
- Distinguish definite rejections, dependency failures, and unknown outcomes across logs, metrics, and API responses.
- Use cache or default values only for read operations where business rules tolerate staleness and the API exposes it explicitly.

A good fallback protects both the dependency and business correctness. For critical commands, explicit rejection or durable receipt acknowledgment tells callers what to do next; a fake success response merely hides the failure and can leave behind corrupt state that is hard to repair.
