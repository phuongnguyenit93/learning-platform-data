# Backoff and jitter

## 1. Why do retries need backoff and jitter?

In a **SPRING_GRPC** service, when a dependency is temporarily unavailable, many clients may simultaneously receive `UNAVAILABLE` and retry. If all of them resend immediately, the recovering server receives another sudden burst of load. This phenomenon can create a feedback loop: overload causes errors, errors trigger retries, and retries worsen the overload.

**Backoff** increases the waiting interval between attempts. **Jitter** adds randomness to retry timing so clients do not synchronize and flood requests at the exact same moment.

The two mechanisms solve related but distinct problems:

- Backoff reduces the retry frequency of **a single client** when errors continue to occur.
- Jitter spreads out retries across **multiple clients** experiencing the same outage.

In gRPC, a client's retry policy can configure exponential backoff using `initialBackoff`, `maxBackoff`, and `backoffMultiplier`. Jitter is part of the retry runtime mechanism; service config does not have a `jitter` field to select a specific random distribution. When implementing custom retries at the application layer, the development team must choose the jitter algorithm and control the number of retries themselves.

## 2. Exponential backoff

Exponential backoff increases the waiting time after each failure. Let:

- (B_0): `initialBackoff`, the waiting time before the first retry.
- (M): `backoffMultiplier`, the growth factor.
- (B_{max}): `maxBackoff`, the upper bound.
- (k): the retry index, starting from 0.

The base waiting interval for the (k)-th retry is:

[
B_k = \min(B_0 \times M^k,\ B_{max})
]

Example with `initialBackoff = 200 ms`, `backoffMultiplier = 2`, `maxBackoff = 2 s`:

| Retry attempt | Base waiting interval |
| --- | ---: |
| 1 | 200 ms |
| 2 | 400 ms |
| 3 | 800 ms |
| 4 | 1,600 ms |
| 5 onward | 2,000 ms |

The `maxBackoff` cap prevents the waiting time from growing indefinitely. It does not mean the client is guaranteed to perform all those retries: `maxAttempts`, deadline, retryable status, commitment, and pushback can still stop retries earlier.

## 3. Jitter spreads out retry timing

If one thousand clients fail at 10:00:00 and all wait exactly 1 second, almost all of them will retry at 10:00:01. Backoff can reduce frequency, but it does not by itself eliminate synchronized request bursts. Jitter randomizes the waiting interval to spread out retry attempts.

There are several ways to generate jitter. The formulas below describe common choices when **implementing retries yourself at the application layer**; they are not configuration field names in gRPC service config.

### 3.1. Full jitter

Generates a random waiting time between 0 and the backoff cap:

[
D_k \sim U(0, B_k)
]

The advantage is strong dispersion and a bounded maximum waiting time. The drawback is that some attempts may happen very early; therefore, you must cap attempts and evaluate total load.

### 3.2. Equal jitter

Keeps at least half of the base backoff and randomizes the remaining half:

[
D_k = \frac{B_k}{2} + U(0, \frac{B_k}{2})
]

This avoids retries clustered too closely together as can happen with full jitter, at the cost of a higher minimum waiting time.

### 3.3. Decorrelated jitter

A variant that uses the previous waiting interval to compute the new interval:

[
D_k = \min(B_{max}, U(B_0, 3D_{k-1}))
]

This variant can produce waiting sequences that are less synchronized across clients. Lower/upper bounds must be enforced and the actual distribution should be tested before use.

There is no single optimal jitter algorithm for every workload. With gRPC built-in retry, use the policy supported by the runtime and do not depend on a specific internal jitter distribution. If implementing retries yourself, pick a well-evaluated algorithm, inject a random source for testing, and avoid stacking jitter across multiple layers.

## 4. Configuring backoff for a gRPC client

Example service config for the unary method `catalog.v1.CatalogService/GetItem`:

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

Meaning:

- `maxAttempts: 4` means at most four attempts **including the initial attempt**, not four additional retries.
- `initialBackoff` sets the initial base waiting interval.
- `backoffMultiplier` increases the waiting interval after each eligible failure.
- `maxBackoff` caps the base waiting interval.
- `retryableStatusCodes` permits retries only when the ending status is in the list.

The gRPC runtime applies jitter to retries according to its own mechanism. Do not add an outer retry loop just to add jitter if the channel already has configured retry; two layers can multiply attempts and make load hard to predict.

### 4.1. Attaching the policy to a Java channel

Example of creating a service config using a `Map`:

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

In a Spring gRPC application, the policy must be attached to the client channel managed by the application's configuration/factory. How the channel is injected depends on the Spring gRPC version and how the project creates stubs; backoff values still belong to the client-side service config. Verify that service/method names match the full names in Protobuf.

## 5. Backoff must fit within the deadline

The deadline is the time budget for the entire RPC, not reset from scratch on each attempt. A retry is only useful if enough time remains for the waiting interval and the next attempt.

Example:

- Remaining deadline is 700 ms.
- Expected backoff for the next attempt is 800 ms.
- The client should not wait the full 800 ms only to start an attempt that almost certainly has no budget left.

Set deadlines according to business requirements, accounting for queue, network, processing, and backoff time. If a client needs to return a result within 2 seconds, backoff settings and attempt counts must fit within that budget.

For `DEADLINE_EXCEEDED`, be cautious: the server may have executed the operation while the response arrived late. Retrying a write operation is only safe when there is an idempotency key or a status-checking mechanism.

## 6. Server pushback and retry throttling

The client does not always decide retry timing on its own. Under overload, the server can send **retry pushback** to instruct the client to wait longer or stop retrying. In gRPC, pushback is conveyed via the special metadata `grpc-retry-pushback-ms`:

- A positive numeric value tells the client to wait the specified number of milliseconds before retrying.
- A negative value tells the client not to retry that call.
- If the metadata is invalid or cannot be parsed, behavior follows the gRPC runtime's rules; do not infer an arbitrary waiting interval at the application layer.

gRPC retry throttling can also reduce retries as error rates rise. Throttling configuration and pushback are service-protection tools; do not build an outer manual retry loop to bypass the server's stop or wait signals.

Pushback does not turn a non-retryable status into a retryable one. The client must still satisfy retry policy, attempt budget, and commitment conditions.

## 7. Avoiding retry amplification

A request may pass through multiple layers: client API, internal service, proxy, and dependency client. If every layer retries three times, a single initial operation can generate far more downstream requests than expected.

Example where two layers each allow up to three attempts:

```text
Client calls service: max 3 attempts
  Service calls dependency: max 3 attempts per outer attempt

Theoretical maximum at dependency: 3 × 3 = 9 calls
```

To limit amplification:

1. Choose one layer responsible for primary retries for each dependency.
2. Cap `maxAttempts` and the overall deadline.
3. Use backoff, jitter, and retry throttling/pushback.
4. Do not retry statuses caused by invalid data or permission errors.
5. Set concurrency limits and rate limits on the server.
6. Record attempt counts to detect nested retries.

Jitter only spreads out timing; it **does not reduce the total number of attempts**. To reduce load, you must reduce retry counts, reject early, or throttle request rates.

## 8. When implementing jitter at the application layer

Implement custom retries only when you need semantics not covered by gRPC policies, such as retrying an individual command in a stream or retrying a business step after re-reading state. An illustrative full jitter function:

```java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

static Duration fullJitter(
        Duration initial,
        Duration maximum,
        double multiplier,
        int retryIndex) {

    double scaled = initial.toMillis()
            * Math.pow(multiplier, retryIndex);
    long cap = Math.min(maximum.toMillis(), (long) scaled);
    long delay = ThreadLocalRandom.current().nextLong(cap + 1);
    return Duration.ofMillis(delay);
}
```

`retryIndex = 0` corresponds to the first retry. This illustrative code assumes positive, finite duration values without overflow; a production implementation should validate parameters, handle overflow, and allow injecting a random source for reproducible tests.

When using this function:

- Call it only after confirming the error is eligible for retry.
- Check that enough deadline budget remains before scheduling.
- Keep the same idempotency key across attempts of the same operation.
- Stop immediately if the caller cancels or attempts are exhausted.
- Do not use it concurrently with automatic retry on the same RPC unless clearly intended.

For a committed bidi stream, retrying a command at the application layer requires correlation IDs, deduplication, and resume rules. Do not open a loop that resends the entire stream as if it were a unary call.

## 9. Testing backoff and jitter

Do not test by requiring a retry to happen after exactly 200 ms. Jitter and the scheduler cause actual timestamps to vary. Test these properties instead:

| Scenario | Assertion |
| --- | --- |
| Consecutive retries with increasing backoff | Base waiting interval does not exceed `maxBackoff` |
| Multiple clients receive errors simultaneously | Retry timestamps are dispersed, not clustered at a fixed point |
| `maxAttempts` reached | No attempt exceeds the limit |
| Deadline expires during backoff | No attempt starts past the deadline |
| Positive server pushback | Client obeys the specified waiting time |
| Negative server pushback | Client stops retrying per the supported mechanism |
| Retry throttling triggered | Retry frequency decreases according to policy |
| Caller cancels while waiting | Retry timer is cancelled, no new attempt is sent |
| Nested retries across two layers | Downstream attempts stay within the expected budget |
| Retrying a write operation | Idempotency ensures no duplicate side effects |

For custom retry logic, inject a fake `Clock`, `Scheduler`, and random source for deterministic tests. For gRPC configured retry, use a test server that returns statuses per attempt and records request arrival timestamps; verify attempt counts, deadline, and waiting intervals within a reasonable bound rather than asserting a fixed jitter value.

Metrics to track include retry attempt count, actual backoff duration, number of calls stopped by deadline, retry success rate, server pushback count, throttling count, and the rate of requests retried across multiple layers.

## 10. Common mistakes

1. **Using backoff without jitter.** Many clients may retry in lockstep and create bursts.
2. **Assuming jitter reduces the number of retries.** Jitter only spreads out timing; the attempt budget is what limits total attempts.
3. **Not capping backoff.** Waiting intervals can grow excessively and no longer fit the deadline.
4. **Configuring `maxAttempts` as the number of extra retries.** This value includes the initial attempt.
5. **Ignoring pushback/throttling.** Clients can keep adding load after the server asked them to slow down or stop retrying.
6. **Retrying across multiple layers without calculating total attempts.** One request can multiply downstream load.
7. **Adding custom jitter on top of gRPC configured retry.** This can create two sets of timers and two hard-to-control retry layers.
8. **Retrying non-idempotent write operations.** The server may have already executed them before the response was lost.

## 11. Practice exercises

For `catalog.v1.CatalogService/GetItem`:

1. Configure exponential backoff with `initialBackoff=200ms`, `maxBackoff=2s`, `backoffMultiplier=2`, and an attempt limit.
2. Simulate multiple clients receiving `UNAVAILABLE` simultaneously; observe retry timestamps and evaluate dispersion.
3. Try a deadline shorter than the total expected backoff time; verify the client sends no attempts after the deadline.
4. Simulate positive and negative server pushback; verify the client respects the guidance.
5. Write a unit test for full jitter using a fake random source, checking that values always fall within the allowed range.
6. Intentionally add retries at a dependency layer and compute total attempts to detect amplification.

**Completion criteria:** learners can explain exponential backoff, caps, and jitter; configure gRPC policies; distinguish runtime jitter from custom-implemented jitter; and coordinate deadlines, pushback, and throttling to protect the server.

### References

- [gRPC Retry](https://grpc.io/docs/guides/retry/): retry policy, exponential backoff, commitment, and pushback.
- [gRPC Service Config](https://grpc.io/docs/guides/service-config/): configuring retries per service and method.
- [gRPC Java ManagedChannelBuilder](https://grpc.github.io/grpc-java/javadoc/io/grpc/ManagedChannelBuilder.html): configuring service config on a client channel.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): gRPC client/server integration in Spring.
