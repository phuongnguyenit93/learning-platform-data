# Maximum attempts

## 1. What does maximum attempts limit?

In gRPC, a logical call can be executed across multiple **attempts** if the client retries after an eligible failure. The `maxAttempts` field in a retry policy sets the limit on the total number of attempts for an RPC, **including the initial attempt**.

For example, `maxAttempts = 4` means:

- Attempt 1 is the initial call.
- If Attempt 1 fails with a retryable status and the call is still eligible, the client can perform Attempt 2.
- Similarly, there can be at most Attempt 3 and Attempt 4.
- The maximum number of additional retries is **3**, not 4.

This limit helps control the load generated when a dependency fails. It does not guarantee the client will perform all attempts: a non-retryable status, deadline expiration, an already-committed call, or a server request to stop retrying can terminate the process earlier.

In Spring gRPC, `maxAttempts` belongs to the **client-side retry policy**, usually attached to a service/method via gRPC service config. The server does not set this field to force the client to retry.

## 2. Distinguishing attempts and retries

Two concepts are frequently confused:

| Concept | Meaning |
| --- | --- |
| Attempt | A single RPC execution at the transport layer |
| Initial attempt | The first attempt initiated by the client |
| Retry | An additional attempt after a previous attempt failed eligibly |
| `maxAttempts` | Maximum total number of attempts, including the initial one |
| Maximum retries | `maxAttempts - 1` |

With `maxAttempts = N`, the actual number of attempts (A) satisfies:

[
1 \le A \le N
]

and the actual number of retries is:

[
R = A - 1 \le N - 1
]

Example:

| `maxAttempts` | Initial attempt | Max additional retries |
| ---: | ---: | ---: |
| 2 | 1 | 1 |
| 3 | 1 | 2 |
| 4 | 1 | 3 |
| 5 | 1 | 4 |

Do not log "retry 1" for the initial call. Distinguish `attempt=1` from `retry_number=0`, or use a consistent attempt field from 1 to N.

## 3. Configuring maxAttempts per method

Example policy for the unary RPC `catalog.v1.CatalogService/GetItem`:

```json
{
  "methodConfig": [
    {
      "name": [
        {
          "service": "catalog.v1.CatalogService",
          "method": "GetItem"
        }
      ],
      "retryPolicy": {
        "maxAttempts": 4,
        "initialBackoff": "0.2s",
        "maxBackoff": "2s",
        "backoffMultiplier": 2,
        "retryableStatusCodes": ["UNAVAILABLE"]
      }
    }
  ]
}
```

This policy allows up to four attempts when the method ends with `UNAVAILABLE` and other retry conditions still hold. `INVALID_ARGUMENT` does not trigger a retry under the list above. Backoff is applied between attempts; waiting time does not increase `maxAttempts`.

The service and method names must match the full names in Protobuf. A policy dedicated to `GetItem` does not automatically apply to `CreateItem` or other methods.

### 3.1. Attaching the policy to a gRPC Java channel

You can build the service config as a `Map` and attach it to the channel:

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
        "retryableStatusCodes", List.of("UNAVAILABLE"));

Map<String, Object> methodConfig = Map.of(
        "name", List.of(Map.of(
                "service", "catalog.v1.CatalogService",
                "method", "GetItem")),
        "retryPolicy", retryPolicy);

Map<String, Object> serviceConfig =
        Map.of("methodConfig", List.of(methodConfig));

ManagedChannel channel = ManagedChannelBuilder
        .forAddress("catalog.internal", 9090)
        .defaultServiceConfig(serviceConfig)
        .build();
```

In a Spring gRPC application, the retry configuration must be applied to the client channel created by the project's configuration or factory. The exact integration depends on the Spring gRPC version; the invariant is that the policy belongs to the client and must match the method to be retried.

## 4. Why should maxAttempts not be set too high?

Each attempt can generate an additional request to the server. If many clients experience errors simultaneously, a large number of attempts increases load right when the system is already weak.

For example, suppose 2,000 clients call a method simultaneously:

| Configuration | Max requests if every client exhausts all attempts |
| --- | ---: |
| `maxAttempts = 1` | 2,000 |
| `maxAttempts = 2` | 4,000 |
| `maxAttempts = 3` | 6,000 |
| `maxAttempts = 5` | 10,000 |

This is a simple upper-bound calculation assuming every attempt reaches the server. Some attempts may fail before reaching the server, and not every call uses the full limit. Nevertheless, the example shows that raising `maxAttempts` can significantly amplify load.

Choose the limit based on:

- How transient the error is and the probability of recovering within a short window.
- Processing cost per attempt on the server and its dependencies.
- The deadline acceptable to the caller.
- Idempotency of the operation.
- The retry policy, backoff, jitter, throttling, and pushback in place.

A small value with clear backoff and deadline is usually easier to operate than a large limit aimed at masking prolonged failures.

## 5. maxAttempts and deadline must be designed together

`maxAttempts` only limits the **count**, while the deadline limits **total time**. A policy might allow four attempts, yet the deadline may only leave enough time for one or two tries.

Example:

- Total deadline: 1.5 seconds.
- First attempt consumes 700 ms.
- Backoff before the next attempt: 500 ms.
- Only about 300 ms remain for the next attempt.

If the new attempt no longer has enough time to do useful work, the call may end with `DEADLINE_EXCEEDED` before exhausting `maxAttempts`.

Therefore:

1. Choose the deadline based on business requirements.
2. Choose `maxAttempts` and backoff so there is a realistic chance to run useful attempts within that deadline.
3. Do not treat `maxAttempts` as a guarantee of the actual number of calls made.
4. Once the deadline expires, do not start a new retry loop outside the caller's deadline.

## 6. Retry only occurs when other conditions also hold

Remaining attempt budget is not the only condition for retrying. The previous attempt must have ended with a status allowed by the policy, the call must not be committed, and time budget must remain.

| Condition | Impact on maxAttempts |
| --- | --- |
| Status is in `retryableStatusCodes` | Can use the next attempt |
| Status is not in the policy | Stops, even if attempts remain |
| Call has committed | Does not automatically replay that call |
| Deadline expired | Stops, even if the limit has not been reached |
| Server pushback requests stopping | Stops retrying per signal |
| Retry throttling restricts retries | May reduce or prevent the next attempt |
| `maxAttempts` exhausted | Returns the final error to the caller |

**Commitment** is a critical boundary: once gRPC receives response headers or the request exceeds the retry buffer limit, the call can be considered committed. After that, the runtime cannot automatically replay the entire RPC as it could while sufficient data remained and the call was uncommitted.

For write operations, even an uncommitted call does not replace idempotency. The server may have performed side effects before the client received a response. Use a stable idempotency key so multiple attempts of the same operation do not produce duplicate results.

## 7. maxAttempts with streaming RPCs

Do not interpret `maxAttempts` as the number of times a bidi stream reconnects from the last message. gRPC automatic retry is bounded by commitment and the retry buffer:

- Before the call commits, the runtime can replay buffered request messages upon an eligible failure.
- Once response headers are received or data exceeds the retry buffer limit, the call is committed and is no longer automatically replayed.
- Streaming RPCs can send/receive many messages and usually commit during operation; you cannot rely on `maxAttempts` to recover a long-running stream session.

If a stream disconnects after commit, the application must open a new RPC and perform resume:

1. Keep a stable `request_id` for each command.
2. Store the acknowledged cursor or sequence.
3. Resend unacknowledged commands according to idempotency rules.
4. The server deduplicates processed requests and returns the appropriate state/result.
5. The client ignores duplicate events and detects sequence gaps.

Retrying a command inside a bidi stream is application-layer logic, not increasing `maxAttempts` for the whole RPC. Likewise, a `TaskRejected` response message is not a gRPC status and does not automatically trigger the retry policy.

## 8. Distinguishing attempt limits from other limits

| Limit | Scope | Goal |
| --- | --- | --- |
| `maxAttempts` | One logical RPC | Limit the total number of RPC executions |
| Deadline | One logical RPC | Limit total elapsed time |
| Backoff/`maxBackoff` | Between attempts | Pace retry timing |
| Semaphore/concurrency limit | One stream or entire service | Limit concurrently running work |
| Rate limit | One client, tenant, or service | Limit request rate over time |
| Idempotency | One logical operation | Prevent duplicate side effects on retry |

For example, `maxAttempts=3` does not mean the server handles at most three concurrent requests. A thousand logical RPCs can exist simultaneously, each with a budget of three attempts. Concurrency and rate limits are needed at the appropriate layer to protect the server.

## 9. Testing maxAttempts

A reliable test must count the attempts the server actually receives and verify early-stop cases. Use a test server that returns statuses in a controlled sequence:

| Scenario | Expected result |
| --- | --- |
| `maxAttempts=4`, first three `UNAVAILABLE`, fourth succeeds | At most four attempts; client receives the result |
| `maxAttempts=4`, all `UNAVAILABLE` | Does not exceed four attempts; returns final status |
| First attempt returns `INVALID_ARGUMENT` | Only one attempt if status is non-retryable |
| Deadline expires before next retry | Stops early, does not exceed deadline |
| Server returns stop-retry pushback | Does not blindly exhaust the attempt budget |
| Call commits before failing | Do not expect automatic replay of the committed call |
| Writing data with the same idempotency key | Multiple attempts cause no duplicate side effects |
| Streaming call disconnects after commit | Reconnect/resume according to application contract |

When testing, distinguish **attempts started by the client** from **requests received by the server**. An attempt can fail before reaching the handler. Use client-side metrics or logs to count attempts while recording the requests the server actually receives to understand the failure path.

## 10. Common mistakes

1. **Treating `maxAttempts=4` as four retries.** In reality it is four total attempts, including the initial one.
2. **Expecting the attempt budget to always be exhausted.** Status, commitment, deadline, pushback, and throttling can stop retries early.
3. **Setting the limit too high to boost reliability.** This can amplify load and prolong failure durations.
4. **Ignoring the deadline.** An attempt may be allowed by count yet lack enough time to execute.
5. **Using maxAttempts to control concurrency.** It is a per-logical-RPC limit, not a limit on total server tasks.
6. **Retrying non-idempotent write operations.** Multiple attempts can cause duplicate side effects.
7. **Using maxAttempts to resume a bidi stream.** A committed streaming call needs an application-layer reconnect/resume protocol.

## 11. Practice exercises

For `catalog.v1.CatalogService/GetItem`:

1. Configure `maxAttempts=3`, `initialBackoff=100ms`, `maxBackoff=1s`, and retry only `UNAVAILABLE`.
2. Write a test server that returns `UNAVAILABLE` twice and then succeeds; verify the successful call is the third attempt.
3. Write a test where `INVALID_ARGUMENT` is not retried and a test where the deadline expires before the next attempt.
4. Increase the number of concurrent clients and measure total requests generated by retries; assess the impact of raising `maxAttempts`.
5. For a write operation, use an idempotency key and prove multiple attempts produce no duplicate side effects.
6. For a committed bidi stream, implement reconnect/resume and explain why `maxAttempts` does not restore the old stream.

**Completion criteria:** learners accurately compute maximum retries from `maxAttempts`, configure per-method limits, explain early-termination conditions, coordinate deadlines/idempotency, and do not confuse retry attempts with concurrency or stream resume.

### References

- [gRPC Retry](https://grpc.io/docs/guides/retry/): retry policy, attempts, commitment, and retry limits.
- [gRPC Service Config](https://grpc.io/docs/guides/service-config/): configuring retries per service and method.
- [gRPC Status Codes](https://grpc.io/docs/guides/status-codes/): meanings of RPC-ending statuses.
- [gRPC Java ManagedChannelBuilder](https://grpc.github.io/grpc-java/javadoc/io/grpc/ManagedChannelBuilder.html): attaching service config to a client channel.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): gRPC client/server integration in Spring.
