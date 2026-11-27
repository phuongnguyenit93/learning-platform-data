# Graceful retry and idempotent commands

**Chapter:** Reliability  
**Scope:** Spring gRPC (`SPRING_GRPC`) using Protocol Buffers contracts, generated Java code, and client/server implementations for unary or streaming RPCs. This lesson presents how to perform controlled retries when transient failures occur and how to design idempotent commands so that an operation can be re-sent without creating duplicate side effects. Both mechanisms must be designed together: retry improves communication resilience, while idempotency protects business correctness.

## 1. Retry handles transient errors, not business errors

A gRPC call can fail because a server is temporarily unavailable, a connection is reset, a proxy closes the connection, or a dependency is overloaded. Some errors exist only briefly and the next call can succeed. Retry allows the client to try again within a finite time budget and attempt count.

Retry is not appropriate for every error. If a request violates the schema, the caller lacks permission, or the business state does not allow the operation, re-sending the same request usually just repeats the failure. Overly broad retries can also overload the system further: when a server is slow, waves of clients retrying simultaneously generate extra traffic right when the server needs load relief.

A reliable design must answer four questions:

1. Which statuses are retryable?
2. How much time remains in the deadline to retry?
3. How many attempts are allowed and how should backoff work?
4. If the server already executed the command but the response was lost, will a repeated request trigger the side effect again?

## 2. Retry and idempotency are two distinct responsibilities

Retry decides **when** the client re-sends a call. Idempotency decides **what happens** if the same command is sent multiple times.

For example, a client sends a command to create a payment. The server writes the payment to the database, but the connection drops before the response reaches the client. The client cannot know whether the server committed or not. If the client re-sends with a new command, the system might create two payments.

If the command carries the same idempotency key and the server stores the processed result, the re-sent request can return the exact stored response without executing the operation again.

| Mechanism | Question answered | Responsibility |
| --- | --- | --- |
| Retry policy | Should the call be retried? | Status classification, attempts, backoff, deadline |
| Idempotency key | Is this the same command? | Identifying repeated commands across multiple requests |
| Deduplication store | Has this command already been processed? | Storing the key, fingerprint, and result |
| Transaction/outbox | How are side effects safely committed? | Synchronizing business data and intent to call external systems |

Retry without idempotency can duplicate side effects. Idempotency without retry is still useful when a client explicitly re-sends after a timeout or lost connection.

## 3. Classify gRPC statuses before retrying

The status code is the first signal for deciding whether to retry. Classification must be based on RPC semantics, not just the code name:

| Status | Common policy | Reason |
| --- | --- | --- |
| UNAVAILABLE | Can retry with limits | Server or dependency is temporarily unavailable |
| RESOURCE_EXHAUSTED | Retry only when the contract allows and with backoff | May indicate quota or overload; immediate retry can worsen the situation |
| ABORTED | Can retry the entire transaction/command if business rules allow | Concurrency conflict or aborted transaction |
| DEADLINE_EXCEEDED | Retry only if the logical call still has deadline remaining and the command is idempotent; stop if the deadline has expired | The server may have already processed it but the response arrived late |
| CANCELLED | Typically do not auto-retry | Caller cancelled or the call was cancelled by lifecycle |
| INVALID_ARGUMENT | Do not retry | Request violates the contract |
| UNAUTHENTICATED | Do not retry with the same credentials | Needs re-authentication or credential refresh via a separate flow |
| PERMISSION_DENIED | Do not retry | Caller is not permitted to perform the operation |
| NOT_FOUND | Typically do not retry | Resource does not exist under current semantics |
| FAILED_PRECONDITION | Do not retry blindly | Business state must change first |
| INTERNAL / UNKNOWN | Do not auto-retry by default | May be a code bug or unknown failure; only retry if clearly classified by contract |

UNAVAILABLE is usually the most suitable status for recoverable transient errors. However, if a server returns UNAVAILABLE for a permanent condition, retrying still will not help. Server and client must agree on status semantics.

Do not convert every exception into UNAVAILABLE just to enable retries. Doing so causes clients to retry business errors, data errors, or programming bugs.

If a logical call has already ended because the deadline actually expired, retries cannot continue inside that call. If the workflow still wants to retry later, it creates a new logical call with a new deadline while keeping the same idempotency key and payload for the same command.

## 4. Retry policies must be bounded

A retry policy typically includes:

- **maxAttempts:** total maximum number of calls, including the initial attempt.
- **initialBackoff:** wait duration before the first retry.
- **maxBackoff:** upper bound on the wait duration.
- **backoffMultiplier:** factor by which backoff increases after each failure.
- **retryableStatusCodes:** set of statuses allowed to retry.
- **deadline:** total time limit for the entire logical call.
- **retry budget:** cap on total retry traffic to avoid amplifying incidents.

For example, `maxAttempts` equal to 4 means at most one initial call and three retries. If the first attempt fails, the client waits before retrying; never create an infinite loop.

Do not set `maxAttempts` overly high to mask an unstable service. Retry is a short-term recovery mechanism, whereas persistent failures must be addressed with capacity, circuit breakers, load shedding, health checks, and fixing the root cause.

## 5. Exponential backoff and jitter

If every client retries after the exact same fixed interval, they can hit the server simultaneously and create a retry storm. Exponential backoff gradually increases the wait time; jitter randomizes when the retry fires.

One way to compute full jitter:

\[
cap_n = \min(maxBackoff,\ initialBackoff \times multiplier^{n-1})
\]

\[
delay_n = random(0,\ cap_n)
\]

Where `n` is the retry attempt number. For example, with initial backoff 100 ms, multiplier 2, and max backoff 1 s:

| Retry attempt | Backoff cap | Delay range with full jitter |
| --- | ---: | ---: |
| 1 | 100 ms | 0–100 ms |
| 2 | 200 ms | 0–200 ms |
| 3 | 400 ms | 0–400 ms |
| 4 | 800 ms | 0–800 ms |
| 5 onward | 1,000 ms | 0–1,000 ms |

Jitter reduces the chance of multiple clients synchronizing their retries. For high-load systems, combine a retry budget and a circuit breaker to cap total retry volume.

## 6. Deadline is the shared budget across all attempts

A gRPC deadline limits how long the caller waits for one logical RPC. Each retry consumes part of that budget; you must not grant a fresh full deadline for every attempt.

For example, a caller sets a 2-second deadline. The first attempt takes 900 ms and backoff takes 200 ms, leaving only about 900 ms for processing and network on the second attempt. If there is not enough time left for a meaningful attempt, the client should stop and return an error rather than sending a request guaranteed to expire.

When calling downstream services, the server should propagate the remaining deadline via gRPC Context. Do not create a new deadline longer than the original request's deadline; otherwise, a slow dependency may keep running after the caller has given up.

In Java:

~~~java
OrderServiceGrpc.OrderServiceBlockingStub stub =
        OrderServiceGrpc.newBlockingStub(channel)
                .withDeadlineAfter(2, TimeUnit.SECONDS);

GetOrderResponse response = stub.getOrder(request);
~~~

If the channel has a retry policy, this deadline covers the logical call and the attempts managed by gRPC. For custom application-level retry, calculate the remaining time before each attempt and backoff; never create a stub with a fresh unbounded deadline on every loop iteration.

## 7. Configuring retry via gRPC service config

gRPC Java supports retry policies through service config. Example configuration for the unary method `payments.v1.PaymentService/CreatePayment`:

~~~json
{
  "methodConfig": [
    {
      "name": [
        {
          "service": "payments.v1.PaymentService",
          "method": "CreatePayment"
        }
      ],
      "retryPolicy": {
        "maxAttempts": 4,
        "initialBackoff": "0.1s",
        "maxBackoff": "1s",
        "backoffMultiplier": 2,
        "retryableStatusCodes": [
          "UNAVAILABLE"
        ]
      }
    }
  ]
}
~~~

Service config binds a policy to a specific service/method. Do not apply retry globally to all RPCs when read methods, write methods, and non-idempotent methods have different semantics.

The gRPC retry engine only retries when a call has not been committed according to runtime rules. Once the client receives response headers, the call is committed and automatic retry stops; certain buffering limits also affect request replayability. Therefore, a retry policy cannot replace application-layer idempotency.

In gRPC Java, a channel builder can accept a service config and enable retry:

~~~java
ManagedChannel channel = ManagedChannelBuilder
        .forAddress(host, port)
        .defaultServiceConfig(serviceConfig)
        .enableRetry()
        .build();
~~~

`serviceConfig` is a map matching the JSON structure above. In Spring gRPC, channels are typically created and managed by the starter. Configure the service config through the channel builder customizer or extension point supported by your starter version before the channel is built. Do not create a second channel just to bypass the starter's configuration, as that makes lifecycle and observability harder to control.

Verify your gRPC Java version and that the retry feature is enabled at runtime. Versions, channel providers, or service discovery resolvers can affect how service config is supplied. Test the configuration with in-process/transport tests and observe the actual attempt count.

## 8. Do not stack multiple retry layers

A call can be retried at multiple layers: gRPC channel, application service, Spring Retry, an underlying HTTP client, or a downstream service. If each layer allows 3 attempts, a single logical request can generate far more calls than expected.

For example, three independent retry layers, each allowing up to 3 attempts, can amplify to 27 calls at the deepest layer in the worst case.

Choose one layer responsible for retrying each dependency boundary. If retries across multiple layers are necessary, calculate total attempts and the deadline budget explicitly. Never wrap a gRPC stub that already has a retry policy in another unbounded retry loop.

## 9. Designing idempotent commands in Protocol Buffers

For commands with side effects such as creating a payment, transferring funds, creating an order, or making a reservation, include an idempotency key in the request contract:

~~~proto
syntax = "proto3";

package payments.v1;
option java_package = "com.example.payments.grpc";
option java_multiple_files = true;

service PaymentService {
  rpc CreatePayment(CreatePaymentRequest)
      returns (CreatePaymentResponse);
}

message CreatePaymentRequest {
  string idempotency_key = 1;
  string source_account_id = 2;
  string destination_account_id = 3;
  int64 amount_minor_units = 4;
  string currency = 5;
}

message CreatePaymentResponse {
  string payment_id = 1;
  string state = 2;
}
~~~

The client generates the key once per business intent and keeps that same key across all retries. Never generate a new UUID on each attempt, because the server will treat each UUID as a different command.

~~~java
import java.util.UUID;
import java.util.concurrent.TimeUnit;

String idempotencyKey = UUID.randomUUID().toString();

CreatePaymentRequest request = CreatePaymentRequest.newBuilder()
        .setIdempotencyKey(idempotencyKey)
        .setSourceAccountId("account-A")
        .setDestinationAccountId("account-B")
        .setAmountMinorUnits(25_000)
        .setCurrency("USD")
        .build();

CreatePaymentResponse response = paymentStub
        .withDeadlineAfter(3, TimeUnit.SECONDS)
        .createPayment(request);
~~~

If the client times out and the user or workflow decides to re-send the same operation, it must reuse the key and the exact same command content. If the user initiates a new operation, a new key must be generated.

## 10. Rules for idempotency keys

A useful idempotency key needs clear scope and lifecycle rules:

1. **Unique within scope:** keys are typically unique per tenant/caller, operation, and key value.
2. **Stable across retries:** every attempt of the same command uses the same key.
3. **Bound to the payload:** the server stores a fingerprint of the business fields.
4. **Not a credential:** knowing a key does not grant permission to view the result.
5. **Sufficient retention:** keep records at least as long as clients/workflows may retry or replay.
6. **Check authorization before replay:** the current caller must still have permission to access the result.

The fingerprint should be computed from a canonical representation of the business fields: source account, destination account, amount, currency, and operation version. Do not include trace IDs, request timestamps, deadlines, or observability metadata in the fingerprint because those values can change between attempts.

Do not assume a hash of `request.toByteArray()` is a suitable business fingerprint. Unknown fields, schema evolution, or serialization changes can alter the fingerprint even when the command's meaning has not changed. Normalize business fields according to a versioned rule and hash that representation.

## 11. Behavior when a key is re-sent

The server must distinguish three cases:

| Case | Behavior |
| --- | --- |
| Key has never existed | Execute the command and store the result |
| Same key, same fingerprint, already completed | Return the stored result without executing side effects again |
| Same key, different fingerprint | Reject because the key is already used for a different command |

If two requests with the same key arrive concurrently, a unique constraint in the database must prevent two transactions from both executing side effects. Checking for the key with a `SELECT` followed by an `INSERT` is not enough: two requests can both see "not found" before either writes data.

When a key already exists in an in-progress state, the API needs a clear policy. In a design that commits a separate `IN_PROGRESS` record, duplicate requests can wait briefly or return a retryable status with backoff. In a design that persists the record, mutation, and response within a single transaction, duplicate requests wait for the unique conflict to resolve; once the first transaction commits, the subsequent request reads the completed result. Pick one model and test concurrency.

## 12. Persisting deduplication records durably

An idempotency table can store:

| Column | Purpose |
| --- | --- |
| tenant_id | Caller/tenant scope |
| operation | Command name/version |
| idempotency_key | Client-generated key |
| request_hash | Fingerprint of the business payload |
| state | IN_PROGRESS or COMPLETED if using a state machine |
| response_payload | Serialized response for replay |
| created_at, expires_at | Retention and cleanup |

Create a unique constraint on `(tenant_id, operation, idempotency_key)`. You can add principal/client scope if the contract requires distinguishing callers within the same tenant. When replaying, still verify current authorization before returning the stored response.

Condensed DDL example for PostgreSQL:

~~~sql
CREATE TABLE rpc_idempotency (
    tenant_id         text        NOT NULL,
    operation         text        NOT NULL,
    idempotency_key   text        NOT NULL,
    request_hash      bytea       NOT NULL,
    state             text        NOT NULL,
    response_payload  bytea,
    created_at        timestamptz NOT NULL DEFAULT now(),
    expires_at        timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, operation, idempotency_key)
);
~~~

The claim operation can use `INSERT ... ON CONFLICT DO NOTHING RETURNING idempotency_key`. If it returns a row, the transaction claimed the key. If no row is returned, read the existing record and compare fingerprints. This is PostgreSQL syntax; other databases need an equivalent upsert/unique-conflict mechanism.

For commands that can execute quickly within a single database transaction, one pattern is:

1. `INSERT ... ON CONFLICT DO NOTHING` for the key/scope and fingerprint.
2. If the insert succeeds, this transaction owns the command; perform the domain mutation.
3. Persist an outbox record if an external system must be called.
4. Serialize the response and update the idempotency record to `COMPLETED`.
5. Commit the mutation, outbox, and response record in the same transaction.
6. If the insert does not succeed, read the existing record; return a conflict if the fingerprint differs, or replay the stored response if it matches.

The unique constraint forces competing transactions with the same key to wait for the first transaction's outcome. If the first transaction rolls back, the next request can claim the insert; if the first transaction commits, the next request reads the completed result. In PostgreSQL at `READ COMMITTED`, the subsequent `SELECT` after the `INSERT` conflict resolves sees the committed record. At other isolation levels or on other databases, snapshot/locking behavior may differ; handle serialization failures and retry transactions according to database semantics. Therefore, integration tests against the module's actual database are essential.

## 13. Example of handling a command in a Spring transaction

The following code illustrates orchestration; the repository methods are abstractions that must be implemented with SQL suited to your database:

~~~java
@Service
public class CreatePaymentService implements CreatePaymentUseCase {

    private final IdempotencyRepository idempotencyRepository;
    private final PaymentRepository paymentRepository;
    private final OutboxRepository outboxRepository;
    private final PaymentResponseCodec responseCodec;

    @Transactional
    @Override
    public CreatePaymentResponse create(
            CreatePaymentCommand command,
            IdempotencyScope scope) {
        String fingerprint = fingerprint(command);

        boolean claimed = idempotencyRepository.tryInsert(
                scope,
                command.idempotencyKey(),
                fingerprint);

        if (!claimed) {
            IdempotencyRecord existing = idempotencyRepository
                    .findRequired(scope, command.idempotencyKey());

            if (!existing.requestHash().equals(fingerprint)) {
                throw new IdempotencyKeyConflictException();
            }
            if (existing.isCompleted()) {
                return responseCodec.decode(existing.responsePayload());
            }

            throw new CommandStillInProgressException();
        }

        Payment payment = paymentRepository.create(command);
        outboxRepository.append(PaymentCreatedEvent.from(payment));

        CreatePaymentResponse response =
                CreatePaymentResponse.newBuilder()
                        .setPaymentId(payment.id())
                        .setState("CREATED")
                        .build();

        idempotencyRepository.complete(
                scope,
                command.idempotencyKey(),
                responseCodec.encode(response));

        return response;
    }
}
~~~

In this example, `tryInsert` must be an atomic operation backed by a unique constraint, not a plain `SELECT` followed by `INSERT`. `complete` updates the record in the same transaction as the payment and outbox. Do not call an external system directly inside the transaction and assume a database rollback will undo the external side effect.

If the command fails before producing side effects and the transaction rolls back, the idempotency record rolls back as well; a subsequent retry can execute again. If the API needs to replay failed business outcomes too, clearly define which statuses are stored as completed results and implement that policy accordingly.

Idempotency here protects side effects within the defined key, transaction, and retention scope; it does not provide a general exactly-once guarantee across multiple independent systems. A transactional outbox typically delivers events with at-least-once semantics, so consumers or downstream commands also need their own deduplication/idempotency.

## 14. Key conflict and status mapping

When the same key is reused with a different payload, the server must reject it rather than returning the old command's result for a new command. You can use `ALREADY_EXISTS` or `INVALID_ARGUMENT` per your contract; pick one stable status and document it clearly.

Example:

~~~java
import io.grpc.Status;
import io.grpc.StatusRuntimeException;

StatusRuntimeException toGrpcStatus(Throwable failure) {
    if (failure instanceof IdempotencyKeyConflictException) {
        return Status.ALREADY_EXISTS
                .withDescription(
                        "Idempotency key was already used for another command")
                .asRuntimeException();
    }
    if (failure instanceof CommandStillInProgressException) {
        return Status.ABORTED
                .withDescription("Command is still being processed")
                .asRuntimeException();
    }
    return Status.INTERNAL
            .withDescription("Internal server error")
            .asRuntimeException();
}
~~~

`ABORTED` for an in-progress state is only appropriate for models that commit a separate `IN_PROGRESS` record and where clients have a retry/backoff policy that preserves the key. In the single-transaction claim + mutation + response model, duplicates usually wait for the first transaction to resolve the unique conflict and then read the `COMPLETED` result; the `IN_PROGRESS` branch is not an externally visible committed state in that model. Do not retry immediately in a tight loop; use a delay and check remaining deadline. If the system can wait briefly for the result, the server may wait for the record to complete instead of failing immediately.

## 15. Safe retry with streaming RPCs

Retrying unary commands is more deterministic because the request is a single complete message. Streaming adds sent/received state:

- Client-streaming may have sent multiple messages and the server may have already processed part of them.
- Server-streaming may have received several responses before the connection dropped.
- Bidirectional streaming may have exchanged messages in both directions.

Once a stream has committed or the client has received responses, automatically re-running the entire stream can replay side effects or produce duplicate responses. For large uploads or event streams, design application-level resume:

- Each chunk/message has an operation key and sequence number.
- The server persists the accepted checkpoint or offset.
- The client reconnects with the same stream/session ID and resumes from the unacknowledged sequence.
- The server rejects duplicate sequences with differing payloads and replays acknowledgements for already-processed sequences.

Do not treat channel retry policies as a safe replay guarantee for every streaming workflow. For streams with side effects, idempotency must be enforced per command/message or per session.

## 16. Combining retry budgets, circuit breakers, and load shedding

A retry policy should sit within a broader reliability strategy:

- **Retry budget:** caps the ratio or count of retries relative to original requests.
- **Circuit breaker:** temporarily stops sending traffic to a consistently failing dependency to avoid wasting resources.
- **Load shedding:** rejects requests early when the server is overloaded instead of accepting work it cannot process.
- **Bulkhead:** limits concurrency per dependency so one slow system does not exhaust all threads/connections.
- **Deadline propagation:** stops work when the caller is no longer waiting for the result.

Not every `RESOURCE_EXHAUSTED` error should be retried. If the server is actively load shedding, clients should back off or stop per policy rather than immediately sending more traffic.

## 17. Testing retry and idempotency

Tests should verify both retry behavior and uniqueness of side effects:

| Scenario | Expectation |
| --- | --- |
| First UNAVAILABLE, next OK | Client retries within limits and receives result |
| INVALID_ARGUMENT | No retry |
| maxAttempts exhausted | Stops and returns final error |
| Deadline expires before next attempt | No further attempt sent |
| Same key, same payload, sent sequentially | Identical response, mutation occurs once |
| Same key, same payload, sent concurrently | Unique constraint allows only one transaction to execute |
| Same key, different payload | Returns conflict status |
| Server commits but response is lost | Retry returns stored response, no new mutation created |
| First transaction rolls back | Subsequent request can claim key and execute |
| Outbox event redelivered | Consumer/downstream handles idempotently |

For backoff, use a controllable clock/random/sleeper or verify the retry policy with an appropriate test harness. Avoid tests that rely on long sleeps. For concurrent duplicates, use a barrier/latch to launch two requests simultaneously and assert the final row/payment/outbox count in the database.

### Example test for sequential same idempotency key

~~~java
@Test
void repeatedCommandReturnsStoredResultWithoutSecondMutation() {
    CreatePaymentCommand command = validCommand("key-123");

    CreatePaymentResponse first = service.create(command, scope);
    CreatePaymentResponse second = service.create(command, scope);

    assertEquals(first, second);
    assertEquals(1, paymentRepository.countByIdempotencyKey("key-123"));
    assertEquals(1, outboxRepository.countByCommandKey("key-123"));
}
~~~

This is an integration test against a real repository/database or suitable test database; a mock repository does not prove that unique constraints and transaction isolation work.

To simulate a lost response after commit, call the service once and verify that the payment, outbox, and idempotency record committed; then discard the result on the client side as if the connection dropped. Re-send the same request/key and verify the response is read from the stored record while payment/outbox counts do not increase. This test exercises the most critical scenario for retrying write commands.

## 18. Observing retry and deduplication

Metrics and traces should distinguish logical calls from individual attempts:

- Total logical RPC calls.
- Attempts per logical call.
- Retry count by service/method/status.
- Retries exhausted and deadlines exceeded.
- Backoff duration and calls dropped due to expired deadlines.
- Idempotency replay count.
- Idempotency key conflict count.
- Command in-progress duration if committed state exists.
- Deduplication store latency, conflict/lock waits, and retention cleanup.

Do not use idempotency keys or tenant/customer IDs as metric labels because of high cardinality and potential data exposure. A redacted identifier may be logged/traced where policy permits, but never put raw keys or sensitive payloads into telemetry.

When investigating duplicates, compare trace IDs and protected idempotency keys. One logical operation can generate multiple client attempts; the server may commit only one command while subsequent attempts replay the same response.

## 19. Common mistakes

- Retrying every status code, including validation and authorization errors.
- Omitting `maxAttempts` or an overall deadline.
- Retrying immediately without backoff/jitter.
- Generating a new idempotency key on every attempt.
- Checking keys only with `SELECT` then `INSERT`, without a unique constraint.
- Returning the old result when the same key is sent with a different payload.
- Storing dedup records in a separate transaction from the business mutation, creating an inconsistency window.
- Assuming a database rollback undoes side effects in an external HTTP/payment provider.
- Stacking retries at gRPC, application, and downstream client layers without accounting for total attempts.
- Automatically replaying an entire streaming call after the server has partially processed it.
- Deleting idempotency records too early while clients may still retry.
- Using idempotency keys as credentials or metric labels.

## 20. Checklist for designing retryable commands

Before enabling retry on a write RPC, verify:

1. Retryable statuses are clearly defined and reflect only transient failures.
2. Max attempts, backoff, jitter, retry budget, and deadline are bounded.
3. The client generates a key once per logical command and preserves it across retries.
4. The server scopes keys by caller/tenant and operation.
5. The server compares fingerprints to detect key reuse with a different payload.
6. A database unique constraint prevents two requests with the same key from executing side effects concurrently.
7. Mutation, dedup result, and outbox are committed consistently.
8. Completed responses are replayed for duplicate requests.
9. Retention is long enough and authorization is verified before replay.
10. Streaming workflows have sequence/checkpoint tracking or a dedicated resume policy.
11. Tests cover transient failures, post-commit timeouts, concurrent duplicates, and payload conflicts.
12. Metrics distinguish logical calls, attempts, and dedup replays.

## 21. Self-practice

1. Why can `DEADLINE_EXCEEDED` happen after the server has already committed a command?
2. Distinguish between a retry policy and an idempotency key.
3. Why must the exact same key be preserved across all attempts?
4. How does a unique constraint protect two concurrent requests using the same key?
5. Why should the fingerprint only include canonicalized business fields?
6. When should you use a transactional outbox for commands with external side effects?
7. Why can retrying a streaming RPC after receiving responses be unsafe?
8. Design a test for the scenario where the server commits but the response is lost.

**Key takeaway:** Retries require status classification, max attempts, exponential backoff with jitter, a retry budget, and a shared deadline. For commands with side effects, the client generates a stable idempotency key and the server stores the fingerprint and result under a unique constraint; duplicates with the same payload are replayed, while the same key with a different payload is rejected. Transactions/outbox and concurrency tests protect side effects; streaming requires sequence/checkpoint tracking or a dedicated resume protocol.
