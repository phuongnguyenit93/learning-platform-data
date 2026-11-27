# Retryable status code

## 1. What is a retryable status code?

gRPC ends an RPC with a status, such as `OK`, `UNAVAILABLE`, or `INVALID_ARGUMENT`. A **retryable status code** is a status code for which the client is configured to retry the call when receiving that status and when other retry conditions are still satisfied.

Not every error should be retried. If the client sends an invalid payload, resending the same payload usually just produces another failure. If the service is temporarily unavailable, retrying with backoff can help the call succeed once the system recovers.

In Spring gRPC, it is important to distinguish two responsibilities:

- **Server** returns a status that accurately reflects the cause: transient error, invalid data, authentication error, or business state.
- **Client** configures the retry policy to decide which statuses are retried, the maximum number of attempts, and the delay between attempts.

Retry is an **RPC**-level behavior. A business error sent as a response message inside a stream does not automatically trigger the gRPC retry policy.

## 2. Classifying statuses by retryability

The following table is a common selection guide, not a mandatory rule for every system. The final decision must be based on the root cause of the error and the safety of re-executing the operation.

| Status | Common meaning | Retry policy |
| --- | --- | --- |
| `UNAVAILABLE` | Service or dependency is temporarily unavailable | **Usually suitable** for retry with backoff |
| `RESOURCE_EXHAUSTED` | Quota or resources exhausted, or currently overloaded | Retry only when the cause is recoverable; requires backoff/pushback |
| `ABORTED` | Transaction aborted due to concurrency conflict | Usually retry at a higher operation/transaction level, after re-reading state |
| `DEADLINE_EXCEEDED` | RPC exceeded its deadline | Retry only if time budget remains and the operation is safe; the server may have already completed it |
| `INTERNAL` | Unexpected internal error | Do not enable blanket retry; retry only when the cause is confirmed to be transient |
| `CANCELLED` | Call was cancelled | Normally do not retry if cancellation originated from the caller |
| `INVALID_ARGUMENT` | Invalid input data | Do not retry without fixing the input data |
| `FAILED_PRECONDITION` | System state does not meet preconditions | Do not retry until the condition has been changed |
| `UNAUTHENTICATED`, `PERMISSION_DENIED` | Missing authentication or insufficient permissions | Do not retry automatically; credentials/permissions must be fixed |
| `NOT_FOUND`, `ALREADY_EXISTS`, `OUT_OF_RANGE` | Not found, already exists, or out of range | Usually business errors; do not retry blindly |
| `UNIMPLEMENTED`, `DATA_LOSS` | Method not supported or data lost/corrupted | Do not retry automatically by default |

### 2.1. Three easily confused statuses

- **`UNAVAILABLE`**: usually means the current call cannot be processed because the service is temporarily not ready. This is the classic retry candidate.
- **`ABORTED`**: usually indicates a conflict in a transactional operation. The client may need to re-read the data, recompute changes, and retry the entire business operation, rather than simply resending the exact same RPC.
- **`FAILED_PRECONDITION`**: the system is not yet in a state that allows execution. Retrying only makes sense after the state is fixed, for example completing an initialization step or unlocking a resource.

`RESOURCE_EXHAUSTED` also requires careful analysis. Temporary overload may recover after a waiting period; an exhausted fixed quota or a message exceeding the size limit will not resolve itself by retrying immediately.

## 3. Retry policy is configured on the client

gRPC uses a **service config** to attach a retry policy to a service/method. The main fields are:

| Field | Meaning |
| --- | --- |
| `maxAttempts` | Maximum total number of attempts, **including the initial attempt** |
| `initialBackoff` | Initial waiting interval before retrying |
| `maxBackoff` | Upper bound of the waiting interval |
| `backoffMultiplier` | Factor by which the backoff increases after each failure |
| `retryableStatusCodes` | List of statuses eligible for retry |

Example service config for the unary method `inventory.v1.InventoryService/GetItem`:

```json
{
  "methodConfig": [
    {
      "name": [
        {
          "service": "inventory.v1.InventoryService",
          "method": "GetItem"
        }
      ],
      "retryPolicy": {
        "maxAttempts": 4,
        "initialBackoff": "0.2s",
        "maxBackoff": "2s",
        "backoffMultiplier": 2,
        "retryableStatusCodes": [
          "UNAVAILABLE",
          "RESOURCE_EXHAUSTED"
        ]
      }
    }
  ]
}
```

With this configuration, the client tries at most four times in total. If it receives `INVALID_ARGUMENT`, the call is not retried according to the policy above. Backoff increases progressively and gRPC applies jitter to reduce the chance of many clients retrying simultaneously at the exact same moment.

### 3.1. Configuring on a gRPC Java channel

You can represent the service config as a `Map` and attach it to `ManagedChannelBuilder`:

```java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import java.util.List;
import java.util.Map;

Map<String, Object> retryPolicy = Map.of(
        "maxAttempts", 4.0,
        "initialBackoff", "0.2s",
        "maxBackoff", "2s",
        "backoffMultiplier", 2.0,
        "retryableStatusCodes",
        List.of("UNAVAILABLE", "RESOURCE_EXHAUSTED"));

Map<String, Object> methodConfig = Map.of(
        "name", List.of(Map.of(
                "service", "inventory.v1.InventoryService",
                "method", "GetItem")),
        "retryPolicy", retryPolicy);

Map<String, Object> serviceConfig =
        Map.of("methodConfig", List.of(methodConfig));

ManagedChannel channel = ManagedChannelBuilder
        .forAddress("localhost", 9090)
        .defaultServiceConfig(serviceConfig)
        .build();
```

In a Spring gRPC application, apply the service config to the channel created by the configuration/factory of the Spring gRPC version in use. The exact integration point depends on how the project creates channels; what matters is that the policy resides on the **client channel**, matching the exact service and method names. Do not place this retry policy on the server and expect the client to retry automatically.

Configure only methods that can be retried safely. Do not apply a broad policy to the entire service if methods have different semantics.

## 4. The server must return the right status

The client can only classify retries accurately when the server uses the status that matches the root cause. Example of a temporary dependency error:

```java
throw io.grpc.Status.UNAVAILABLE
        .withDescription("Inventory service is temporarily unavailable")
        .asRuntimeException();
```

Example of an invalid request:

```java
throw io.grpc.Status.INVALID_ARGUMENT
        .withDescription("item_id must not be empty")
        .asRuntimeException();
```

If the server returns `INTERNAL` for every type of error, the client cannot distinguish a transient error from an invalid input error. If the server returns `UNAVAILABLE` for a persistent data error, the client may retry uselessly and increase load.

For `RESOURCE_EXHAUSTED`, the server should provide appropriate retry information if the implementation mechanism supports pushback. When the server indicates not to retry, the client should respect that signal; do not build an application-layer retry loop to bypass overload policies.

## 5. Safe retries depend on idempotency

A retryable status only answers the question of **when a retry is permitted by policy**. It does not guarantee that the operation was not already executed on the server.

For example, the client calls `CreatePayment`. The server successfully records the transaction, but the connection drops before the client receives the response. The client may observe `UNAVAILABLE` or `DEADLINE_EXCEEDED`. If it resends the payment creation command without idempotency, the server could create two transactions.

To retry safely:

1. Generate a stable `idempotency_key` for one logical operation; keep the key unchanged across retry attempts.
2. The server stores the key together with the result or processing state in storage with appropriate consistency.
3. If an already-completed key is received again, return the stored result instead of executing it again.
4. If the key is currently being processed, return an appropriate status or let the client continue tracking it.
5. If the same key arrives with a different payload, reject it to prevent misusing the key.

Read operations are generally easier to retry than write operations. However, even a read operation can have side effects such as billing, writing audit logs, or creating snapshots; evaluate the actual semantics rather than relying solely on the method name.

## 6. Limiting retries: deadlines, budgets, and load

Retries increase the number of requests sent to the server. When the server is overloaded, uncontrolled retries can cause a **retry storm** and worsen the outage.

A practical policy should:

- Limit `maxAttempts`; never retry indefinitely.
- Set a deadline for the entire call and ensure enough time remains for the next attempt.
- Use exponential backoff with jitter.
- Select only statuses that are genuinely recoverable.
- Respect server pushback or wait-time guidance if supported.
- Monitor attempt counts, retry success rate, final status, and total latency.

`DEADLINE_EXCEEDED` is especially sensitive: the server may have completed the operation, with the response arriving late. Before retrying a write operation, use an idempotency key or a status-query mechanism by request ID.

## 7. Retries with client streaming and bidirectional streaming

gRPC retry does not mean an active stream will automatically resume from the exact failed message. Automatic retry is constrained by the **commit** state of the RPC. Once a call is committed—for example, when the client has received response headers or the request data exceeds the retry buffer limit—gRPC cannot replay the call as it could before commit.

Because a bidi stream typically receives response headers when the exchange begins and can send/receive messages continuously, automatic retry is usually only useful in the initial phase, before the call commits. Once the stream is active, if the connection fails, the application usually has to:

1. Open a new RPC.
2. Resend session information or a cursor so the server can determine the continuation point.
3. Replay unacknowledged commands according to idempotency rules.
4. Use `request_id`/sequence so the server can detect duplicate messages and the client can detect missing messages.
5. Avoid replaying unsafe commands without verifying processing state on the server.

A business response message such as `TaskRejected` or `TaskFailed` is not a terminal gRPC status and does not trigger the retry policy. To retry an individual command inside a bidi stream, the client should handle it at the application layer using a request ID, task state, and separate backoff; do not restart the entire RPC just because a single command was rejected.

## 8. Testing retryable status codes

Both server decisions and client retry behavior should be tested:

| Scenario | Expected result |
| --- | --- |
| Server returns `UNAVAILABLE` then succeeds | Client retries per policy and eventually receives the result |
| Server returns `INVALID_ARGUMENT` | Not retried under the sample policy |
| Server returns transient `RESOURCE_EXHAUSTED` | Retried with backoff or according to pushback |
| Server returns `RESOURCE_EXHAUSTED` due to fixed quota | Does not create a continuous retry loop |
| `maxAttempts` exhausted | Client receives the final status |
| Deadline insufficient for next attempt | Call ends; does not exceed the deadline |
| Write operation executed but response lost | Retry with the same idempotency key causes no duplicate side effects |
| Bidi stream disconnected after commit | Client opens a new session and resumes per application contract, without assuming the old stream is replayed in full |

In automatic retry tests, use a mock server that returns a controlled sequence of statuses before succeeding and configure the channel with a real service config. Verify the number of requests received by the server, the final status, and idempotency. Avoid only asserting that the client received a result; that does not prove the policy retried the expected number of times or skipped disallowed statuses.

## 9. Common mistakes

1. **Retrying every status:** invalid data, permission errors, or business state errors will not disappear after resending.
2. **Treating `RESOURCE_EXHAUSTED` as always retryable:** fixed quotas and transient overload require different policies.
3. **Retrying `ABORTED` by resending the exact same RPC:** you may need to re-read data and rerun the entire business transaction.
4. **Ignoring idempotency:** the server may have already executed the operation before the client received the error.
5. **Setting `maxAttempts` too high or omitting a deadline:** increases load and latency.
6. **Assuming bidi streams auto-resume:** automatic retry does not recover an already-committed stream.
7. **Confusing message errors with gRPC status:** an error response in Protobuf does not trigger the RPC retry policy.
8. **Returning a status that mismatches the root cause:** the client cannot choose a reliable retry policy if the server classifies errors inaccurately.

## 10. Practice exercises

For the `inventory.v1.InventoryService` service:

1. Configure a retry policy for `GetItem` with `UNAVAILABLE` and specific `RESOURCE_EXHAUSTED` cases identified as transient.
2. Do not enable automatic retry for `CreateItem` before implementing an idempotency key.
3. Write a test where the server returns `UNAVAILABLE` twice and then succeeds; verify that total attempts do not exceed `maxAttempts`.
4. Write a test where `INVALID_ARGUMENT` results in only one call.
5. Simulate `DEADLINE_EXCEEDED` after a write operation has completed; verify that retrying with the same idempotency key does not create a second record.
6. For a bidi stream, simulate an error after the call has committed and implement reconnect/resume using a cursor instead of relying on automatic retry.

**Completion criteria:** learners choose the right statuses for transient vs. non-recoverable errors, configure bounded retries on the client, protect write operations with idempotency, and understand the limits of automatic retry for streaming RPCs.

### References

- [gRPC Retry](https://grpc.io/docs/guides/retry/): retry policy, backoff, commit, and retry limits.
- [gRPC Status Codes](https://grpc.io/docs/guides/status-codes/): meanings of statuses returned by applications and the gRPC library.
- [gRPC Service Config](https://grpc.io/docs/guides/service-config/): configuring client behavior per service and method.
- [gRPC Java ManagedChannelBuilder](https://grpc.github.io/grpc-java/javadoc/io/grpc/ManagedChannelBuilder.html): configuring service config on a client channel.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): gRPC client/server integration in Spring.
