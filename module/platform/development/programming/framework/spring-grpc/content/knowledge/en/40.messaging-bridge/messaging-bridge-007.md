# Deadlines Across the Message Boundary

## 1. Deadlines Do Not Cross the Broker Automatically

In **SPRING_GRPC**, gRPC clients call services according to a Protocol Buffers contract. When a service converts a request into a command and publishes it to a message broker, execution crosses an asynchronous boundary: the RPC may finish before the consumer receives or processes the message.

A gRPC deadline bounds how long an RPC is allowed to continue. It is managed within the gRPC runtime and bound to the current call. The broker does not natively understand `io.grpc.Deadline`, and a consumer running in another process cannot read `Context.current()` from an already-ended RPC.

Therefore, if a deadline matters for processing behind the broker, the ingress must translate that time constraint into explicit data in the command envelope or message headers. The consumer reads this data, calculates the remaining budget, and decides whether to continue processing.

~~~mermaid
sequenceDiagram
    participant C as gRPC client
    participant G as Spring gRPC ingress
    participant B as Message broker
    participant W as Consumer
    participant D as Downstream service
    C->>G: RPC + deadline
    G->>G: Read remaining RPC budget
    G->>B: Command + explicit expiry/budget
    G-->>C: ACCEPTED (if durably stored)
    Note over B,W: Queue delay consumes time budget
    B->>W: Deliver command
    W->>W: Recalculate remaining budget
    W->>D: RPC with remaining deadline
    D-->>W: Result or deadline exceeded
~~~

Key point: time spent in the queue also consumes the budget if the deadline applies to the entire workflow. The consumer must not start a fresh full timer upon receiving the message.

## 2. Distinguishing RPC Deadline from Command Expiry

These are two different concepts and should not be collapsed into one field:

| Concept | Meaning | Who decides? |
|---|---|---|
| RPC deadline | How long the client waits for a single gRPC call | Client, possibly capped by server/gateway |
| Command expiry | Point in time when the command is no longer valid to start or continue | Business contract and server policy |
| Processing budget | Maximum duration a worker may spend on a processing step | Service/workflow policy |
| Operation SLA | Target completion time for the entire operation | Product/operations |

For example, a client sends `SubmitOrder` with a 500 ms deadline. The ingress may write the command to the outbox in 20 ms and return `ACCEPTED`. The RPC completed quickly, yet the command might take several seconds for a worker to process. If you use the RPC deadline as the command expiry, the command will expire even though the system accepted responsibility for processing it.

Only map an RPC deadline to command expiry when the API explicitly defines that the business request is only valid until that instant. For ordinary asynchronous commands, the RPC deadline mainly bounds how long the ingress takes to respond; command expiry must come from business policy or a dedicated field validated and bounded by the server.

## 3. Determining the Deadline at the Ingress

In gRPC Java, the current deadline can be read from `Context.current().getDeadline()`. `timeRemaining(...)` returns the remaining budget using the monotonic clock gRPC uses for the call:

~~~java
import io.grpc.Context;
import io.grpc.Deadline;
import io.grpc.Status;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.TimeUnit;

public final class DeadlinePolicy {
    private final Clock clock;

    public DeadlinePolicy(Clock clock) {
        this.clock = clock;
    }

    public Duration remainingRpcBudget() {
        Deadline deadline = Context.current().getDeadline();
        if (deadline == null) {
            return null; // No deadline set by the caller.
        }

        long remainingNanos =
                deadline.timeRemaining(TimeUnit.NANOSECONDS);
        if (remainingNanos <= 0) {
            throw Status.DEADLINE_EXCEEDED
                    .withDescription("RPC deadline has expired")
                    .asRuntimeException();
        }
        return Duration.ofNanos(remainingNanos);
    }

    public Instant toAbsoluteTime(Duration remaining) {
        return clock.instant().plus(remaining);
    }
}
~~~

`Deadline` is based on monotonic time, suitable for measuring remaining time within a process. Do not serialize a `Deadline` object or `nanoTime` value directly to the broker because monotonic values are only meaningful within the current runtime environment.

When a point in time must cross a process boundary, convert it to an absolute UTC timestamp (`Instant`) or a standard time format. When the consumer receives the message, it recomputes the remaining duration against the consumer's clock.

If an RPC has no deadline, the service needs a clear policy: reject requests without a deadline, apply a default ingress deadline, or set command expiry purely by business policy. Never treat "no deadline" as safely infinite time.

## 4. Do Not Automatically Turn RPC Deadline into Command Expiry

For asynchronous commands, store two separate fields if both are needed:

~~~json
{
  "commandId": "cmd-100",
  "correlationId": "corr-100",
  "rpcDeadlineAt": "2026-11-19T10:15:30.500Z",
  "commandExpiresAt": "2026-11-19T10:25:00Z",
  "payload": {
    "orderId": "order-42"
  }
}
~~~

`rpcDeadlineAt` can serve diagnostics or analysis of when the caller stopped waiting. It is not a command to cancel the command. `commandExpiresAt` is the business cutoff after which processing is no longer allowed, if the command contract includes an expiry.

If the command has no business expiry, omit that field and use a separate operation SLA/retention policy. Do not fill in an arbitrary timestamp just to make the message envelope look complete.

## 5. Computing Command Expiry from Business Policy

If a command has a time limit, the server should determine or enforce it. If the client is allowed to request an expiration timestamp, the server must validate that value, cap the maximum lifetime, and disallow extending beyond policy.

Conceptual example:

~~~java
public Instant resolveCommandExpiry(
        Instant requestedExpiry,
        Duration maximumLifetime,
        Clock clock) {

    Instant now = clock.instant();
    Instant serverMaximum = now.plus(maximumLifetime);

    if (requestedExpiry == null) {
        return serverMaximum;
    }
    if (!requestedExpiry.isAfter(now)) {
        throw new IllegalArgumentException("command expiry is in the past");
    }
    return requestedExpiry.isBefore(serverMaximum)
            ? requestedExpiry
            : serverMaximum;
}
~~~

This is an illustrative policy. Some APIs should reject timestamps exceeding the limit instead of clamping; what matters is documenting the behavior clearly. Do not trust client-supplied timestamps without validation, as client clocks can drift or callers may intentionally set overly distant expiries.

## 6. Including Deadlines in the Command Envelope

The envelope should distinguish creation time, business expiration time, and correlation:

~~~java
import java.time.Instant;

public record CommandEnvelope<T>(
        String messageId,
        String commandId,
        String correlationId,
        String messageType,
        int schemaVersion,
        Instant createdAt,
        Instant commandExpiresAt,
        T payload) {}
~~~

If you need to retain the RPC deadline for analysis, add `rpcDeadlineAt` as diagnostic metadata. Avoid a generic `deadline` field because consumers will not know whether it refers to the gRPC call deadline, command expiry, or SLA.

Serialize timestamps in standard UTC, such as ISO-8601 or protobuf `google.protobuf.Timestamp`. Avoid date-time strings without timezones or epoch numbers with ambiguous units.

## 7. Consumers Compute Remaining Budget

Upon receiving a message, the consumer calculates the remaining time from `commandExpiresAt`. If already expired, do not start business side effects:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

public final class CommandTimeBudget {
    private final Clock clock;

    public CommandTimeBudget(Clock clock) {
        this.clock = clock;
    }

    public Duration remainingUntil(Instant expiresAt) {
        if (expiresAt == null) {
            return null; // Command has no business expiry.
        }

        Duration remaining = Duration.between(clock.instant(), expiresAt);
        if (remaining.isZero() || remaining.isNegative()) {
            throw new CommandExpiredException();
        }
        return remaining;
    }
}
~~~

Do not recompute the budget from `createdAt + fullProcessingTimeout` at each consumer. That ignores queue time and grants every hop a full time allocation, allowing workflows to stretch indefinitely.

If a command passes through multiple workers, each worker must use the same `commandExpiresAt` or a shorter expiry defined by that branch's policy. Never unilaterally extend the expiry at each hop.

## 8. Propagating Remaining Budget to Downstream gRPC Calls

If a consumer calls another gRPC service, construct a new deadline from the remaining budget:

~~~java
Duration remaining = timeBudget.remainingUntil(
        envelope.commandExpiresAt());

if (remaining != null) {
    long remainingNanos = remaining.toNanos();
    if (remainingNanos <= 0) {
        throw new CommandExpiredException();
    }

    downstreamStub
            .withDeadlineAfter(remainingNanos, TimeUnit.NANOSECONDS)
            .reserveInventory(request);
} else {
    downstreamStub.reserveInventory(request);
}
~~~

The example assumes `downstreamStub` is a generated blocking stub; async/future stubs need the corresponding call pattern. In practice, reserve a portion of the budget for serialization, commit, and cleanup, and enforce a maximum per-dependency timeout.

Do not pass the original full timeout down to every service. If the ingress already consumed 300 ms out of a 1-second total budget, downstream should receive roughly the remaining 700 ms, not a fresh 1-second budget.

With parallel fan-out, branches may share the same expiry timestamp, while each branch enforces its own timeout and concurrency cap. One slow branch should not hold resources indefinitely once the operation has expired.

## 9. Monotonic Clocks and Wall Clocks

Internal deadlines within a process should rely on a monotonic clock because wall clocks can jump during NTP adjustments or machine clock changes. Timestamps sent across a broker must be absolute points in time, usually UTC, because consumers in other processes do not share the same monotonic origin.

| Time type | Where used | Serialize over broker? |
|---|---|---|
| Monotonic deadline / remaining nanos | Measuring remaining time in the same process | No |
| UTC `Instant` | Passing creation/expiry timestamps across services and brokers | Yes |
| Remaining duration | Temporary budget within a single hop | Can be passed, but consumer must subtract elapsed time; never reset per hop |

Because clocks across machines can drift, consumers should apply clock synchronization, bound acceptable skew, and choose a safe policy. For security- or finance-critical expiries, clock skew must not extend command validity; use database/server time or a canonical time source per your architecture.

`Instant.now()` can be injected via `Clock` for testing and control. Avoid scattering wall-clock calls across the codebase, which complicates testing and causes inconsistent results.

## 10. Broker TTL Does Not Replace Consumer Expiry Checks

Brokers may offer TTL or retention mechanisms, but semantics depend on the product:

- RabbitMQ supports message TTL and queue/message expiration by configuration; expired messages may be dropped or dead-lettered per policy.
- Kafka retention generally applies at log-segment time/size granularity, not an exact independent TTL per command record. Consumers still need to check `commandExpiresAt`.
- Other brokers may have visibility timeouts, scheduled delivery, or their own expiry semantics.

Do not rely solely on the broker to guarantee commands expire at the exact cutoff. Consumers must check expiry right before performing significant side effects. Broker TTL is an operational optimization to reduce stale messages, not the single source of business truth.

## 11. Retries Must Not Refresh the Deadline

When a consumer retries due to a transient error, keep `commandId`, idempotency key, and `commandExpiresAt` unchanged:

~~~text
Command created: 10:00:00
Command expires: 10:05:00

Attempt 1: 10:01:00 -> transient database error
Attempt 2: 10:02:30 -> downstream timeout
Attempt 3: 10:04:50 -> only 10 seconds remain
After 10:05:00 -> do not execute; mark expired / dead-letter
~~~

Do not reset expiry to `now + 5 minutes` on each retry. Doing so lets a continually failing command live forever.

Backoff must fit within the remaining budget. If the planned retry delay exceeds the expiry, transition the command to expired or dead-letter per policy instead of scheduling a futile attempt.

If business rules allow extending an expiry, that must be a new decision with authorization and auditing, not an implicit side effect of retrying.

## 12. Handling Expiry After a Command Has Been Accepted

When a consumer detects an expired command, determine the final state and action:

- Do not start side effects if the command has not yet executed.
- Record operation state `EXPIRED` or an equivalent failure code.
- Ack/commit the message after the expired state has been durably persisted.
- Optionally emit `CommandExpired` if callers or other services need notification.
- Preserve `correlationId` and `operationId` for traceability.

If the command already partially executed, expiry does not automatically undo side effects. A compensating workflow or compensating command is required by business rules. Never delete historical messages to pretend the operation never ran.

## 13. Deadlines and Cancellation Are Two Different Signals

When a client cancels an RPC or the RPC deadline expires:

- The ingress may stop waiting and release the pending future.
- If the command has not yet been durably persisted, the ingress may abort before publishing.
- If the outbox transaction has committed or the broker has received the message, the command may still be processed.
- Workers do not receive `io.grpc.Context` cancellations from the original RPC.

If callers need to cancel business processing after a command has been accepted, provide a separate `CancelOperation` RPC/command. The worker checks operation state and cancellation requests before cancellable side-effect steps. Handle races between completion and cancellation: an already-completed operation may no longer be cancellable.

Do not use RPC deadlines as a cross-broker cancellation mechanism. A deadline only indicates a time budget has run out; cancellation is a control signal that must be propagated and handled under its own contract.

## 14. Mapping Deadlines and Expiries to gRPC Status

RPC status and command state must be kept separate:

| Scenario | Appropriate outcome |
|---|---|
| RPC deadline expires before ingress persists command | `DEADLINE_EXCEEDED`; do not return `ACCEPTED` |
| Outbox commit succeeds before RPC deadline expires | `OK` with operation state `ACCEPTED`, if defined by contract |
| Broker/consumer processes after RPC already ended | Update operation state; cannot send response on old RPC |
| Consumer receives command past `commandExpiresAt` | Operation `EXPIRED` or business failure code |
| Downstream gRPC call exhausts remaining budget | Handle timeout per retry/business policy; do not grant a full budget |
| Client cancels after durable acceptance | Command still follows policy; business cancellation needs a separate request |

If the RPC returns `DEADLINE_EXCEEDED`, the client cannot conclude with certainty that the command was not accepted. The outcome may be uncertain if the timeout occurred right around commit/ack. Clients should query by idempotency key or operation ID before creating a new intent.

## 15. Observing Deadlines Across the Message Boundary

Track timing milestones:

- RPC deadline budget at ingress and remaining budget before persistence.
- Message `createdAt` and `commandExpiresAt`.
- Queue age when the consumer begins processing.
- Remaining budget at each worker/hop.
- Downstream RPC latency and `DEADLINE_EXCEEDED` counts.
- Commands expired before processing, during retries, and mid-execution.
- Retry counts, backoff durations, and dead-letter reasons.
- Detected clock skew between producers and consumers, if any.

Logs/traces should carry `operationId`, `commandId`, `correlationId`, message ID, and controlled expiry timestamps. Do not use these IDs as high-cardinality metric labels; metrics should group by message type, consumer, outcome, and expiry reason.

When commands consistently exceed deadlines, check queue age, retry backoff, clock skew, consumer concurrency, and whether any hop resets the budget. If RPCs time out while operations still execute, verify whether the API separates RPC deadlines from command expiries.

## 16. Testing Deadlines Across the Message Boundary

Tests should use a fake or controllable `Clock` to avoid wall-clock flakiness:

| Scenario | What to verify |
|---|---|
| RPC with sufficient deadline | Ingress reads remaining budget accurately |
| RPC deadline expires before persistence | Returns `DEADLINE_EXCEEDED`, command not recorded |
| RPC without deadline | Applies published default/reject policy |
| Command with business expiry | Envelope stores exact UTC timestamp |
| Queue delay consumes most of budget | Consumer uses only the remaining time |
| Command expires before consumer runs | No side effects executed; operation transitions to `EXPIRED` |
| Downstream gRPC call | Deadline set to remaining budget |
| Multiple retries | `commandExpiresAt` is never refreshed |
| Backoff exceeds expiry | No futile retry scheduled |
| Clock skew | Skew policy enforces limits properly |
| Client cancels after outbox commit | Durable command is not deleted automatically |
| Partially executed command | Expiry does not auto-rollback; business compensation runs |
| Varying broker TTL behavior | Consumer expiry gate still protects side effects |

Integration tests must verify that the message envelope serializes/deserializes accurately, queue delay is accounted for, retries preserve expiry, and consumers execute no side effects past expiry. With Kafka, tests must not assume retention acts as per-message TTL; verify consumer-side expiry enforcement.

## 17. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Assuming gRPC deadline propagates automatically through broker | Consumer does not know remaining budget | Serialize expiry/budget explicitly |
| Using monotonic `nanoTime` as a message timestamp | Value is meaningless in another process | Convert to UTC `Instant` |
| Using RPC deadline as default command expiry | Accepted commands are dropped when caller stops waiting | Separate RPC deadline and business expiry |
| Granting a fresh full timeout at each consumer | Workflow can stretch indefinitely | Keep one absolute expiry and compute remaining |
| Refreshing expiry on retries | Commands never expire | Preserve original expiry |
| Relying solely on broker TTL | Some brokers lack exact per-message expiry | Consumer checks expiry before side effects |
| Ignoring clock skew | Commands expire too early or too late | Synchronize clocks and define skew policy |
| Treating RPC cancellation as command cancellation | Worker still executes after caller cancels | Provide dedicated command cancellation |
| Omitting expiry from outbox | Relays/retries lose original deadline | Persist expiry alongside the command |

**Key takeaway:** gRPC deadlines do not automatically cross the message boundary. The ingress must convert required time limits into explicit UTC timestamps or budgets; consumers compute remaining budget and pass the remainder downstream. Separate RPC deadlines from command expiries, preserve expiry across retries, enforce expiration right before side effects, and never rely solely on broker TTL. RPC cancellation does not automatically cancel durably recorded commands.
