# Circuit Opens Too Early Because Multiple Operations Share Statistics

## Lesson Objectives

A circuit breaker is designed to evaluate the health of a protected call. If multiple distinct business operations share one breaker instance, their outcomes enter the same sliding window. One operation that frequently fails or runs slowly can push the combined failure rate over the threshold, causing the breaker to OPEN and block another operation that is otherwise healthy.

In Spring Cloud CircuitBreaker with Resilience4j, you must clearly distinguish between **breaker id** and **groupName**. Sharing an id can cause multiple calls to share state and statistics. Sharing a groupName is for selecting a common configuration policy; groupName itself does not merge the state of breakers with different ids.

After this lesson, you will be able to:

- Recognize symptoms indicating that multiple operations share a breaker instance.
- Explain why errors from one operation cause the breaker to block another operation.
- Distinguish a breaker's id from a groupName used to select configuration.
- Choose breaker boundaries based on dependency, error semantics, and operation SLOs.
- Configure multiple separate breakers that share a single Resilience4j policy.
- Check sliding window, minimumNumberOfCalls, and exception classification.
- Diagnose actual breaker names via metrics, events, and logs.
- Avoid splitting breakers too finely to the point where there are not enough samples to evaluate.

## 1. Symptom: One Failing Operation Blocks Another Operation

Suppose order-service calls inventory-service through two operations:

- `readAvailability(sku)` reads inventory stock. This is a fast call and usually succeeds.
- `reserveStock(sku, quantity)` reserves stock. This operation can be rejected due to out-of-stock conditions or business conflicts.

If both operations share a breaker named `inventory`, their outcomes may enter the same sliding window. For example, in the last 10 calls there are 5 failed reserve calls and 5 successful availability reads. With `minimumNumberOfCalls: 10` and `failureRateThreshold: 50`, the breaker can open as soon as 10 samples are collected.

Once the breaker transitions to OPEN, subsequent availability read calls can also be rejected, even though the read operation itself is healthy. Operators see errors on the read endpoint and assume inventory-service is down, while the real cause is failures from the reserve operation driving up the shared breaker's failure rate.

Illustrative flow:

    readAvailability  ---- success ----+
    reserveStock      ---- error ------+
    readAvailability  ---- success ----+--> breaker: inventory
    reserveStock      ---- error ------+       shared window
    reserveStock      ---- error ------+
    readAvailability  ---- success ----+
    reserveStock      ---- error ------+
    reserveStock      ---- error ------+
    readAvailability  ---- success ----+
    reserveStock      ---- error ------+
                                                |
                                                v
                                      failure rate reaches threshold
                                                |
                                                v
                                         breaker OPEN
                                                |
                          +---------------------+------------------+
                          |                                        |
                   readAvailability                         reserveStock
                    rejected                                  rejected

Common symptoms:

- The breaker is OPEN even though some endpoints still have a high success rate.
- Errors or slow calls are concentrated in one operation, yet metrics show only a single breaker name.
- Rejected call counts increase across multiple methods sharing the breaker.
- The healthy operation's fallback runs as well because the breaker opened before the Supplier executed.
- Operators cannot tell from current breaker metrics which operation contributes the most errors.

## 2. Why Do Multiple Operations Share Statistics?

A circuit breaker maintains state and a sliding window per instance. If the application retrieves the same breaker instance for multiple operations, those calls update the same statistics.

Common causes include:

1. **Reusing the same id:** multiple gateways or methods call `factory.create("inventory")`.
2. **Breaker name normalized too broadly:** a custom resolver drops the method name and returns only the service ID.
3. **Same wrapper used for multiple operation types:** a helper hardcodes the breaker name even though the Supplier calls different endpoints.
4. **Feign configuration using a shared name:** multiple methods are mapped to the same breaker name due to the application's naming rules or resolver.
5. **Breaker wrapping an entire multi-step workflow:** errors from multiple dependencies or business logic are recorded into one breaker.

Example prone to shared statistics:

    public InventoryResponse read(String sku) {
        return circuitBreakerFactory.create("inventory").run(
            () -> inventoryClient.read(sku),
            error -> InventoryResponse.unknown(sku)
        );
    }

    public ReservationResponse reserve(String sku, int quantity) {
        return circuitBreakerFactory.create("inventory").run(
            () -> inventoryClient.reserve(sku, quantity),
            error -> ReservationResponse.pending(sku)
        );
    }

Both methods use the same id `inventory`. In Resilience4j, the instance name is the breaker's lookup key. Calling the factory with the same id typically retrieves the same breaker instance managed in the factory/registry, so state and the sliding window are shared.

Sharing a service ID or a groupName does not automatically mean breakers share statistics. Check the actual id used by the factory.

## 3. Distinguish Between id and groupName

In Spring Cloud CircuitBreaker, the two parameters serve different roles:

- **id** identifies the breaker instance. This is the name tied to the breaker's state, sliding window, and metrics.
- **groupName** selects the group configuration used for the breaker when the implementation supports group-based configuration resolution.

Example:

    CircuitBreaker readBreaker =
        circuitBreakerFactory.create("inventory-read", "inventory");

    CircuitBreaker reserveBreaker =
        circuitBreakerFactory.create("inventory-reserve", "inventory");

The two breakers have different ids, so they have separate state and statistics. They share the groupName `inventory` to receive a common configuration policy.

Visualized as:

    groupName: inventory
       |
       +-- id: inventory-read
       |      state: CLOSED / OPEN / HALF_OPEN
       |      sliding window: separate
       |
       +-- id: inventory-reserve
              state: CLOSED / OPEN / HALF_OPEN
              sliding window: separate

Comparison table:

| Usage | State and Statistics | Configuration |
| --- | --- | --- |
| Same id, same groupName | Can share the breaker instance and window. | Same configuration context. |
| Different id, same groupName | Separate per breaker. | Can share a group policy. |
| Different id, different groupName | Separate per breaker. | Can use different policies. |

Key point to remember: groupName is not a label that merges multiple breakers into one set of statistics. If your goal is to isolate impact between read and reserve, assign different ids. If your goal is to share a sliding window, intentionally use the same id and accept that errors in one operation affect the other.

## 4. Choose Breaker Boundaries Based on Operational Behavior

Not every HTTP endpoint needs its own breaker. Boundaries should reflect operations that share similar operational characteristics.

Consider these factors:

- **Target dependency:** do the two operations call the same remote dependency or two different systems?
- **Error semantics:** is an error a sign of dependency unavailability or a normal business outcome?
- **SLOs and deadlines:** do both operations share the same latency budget and slow-call threshold?
- **Load and frequency:** is one operation high-traffic while the other is low-traffic?
- **Consequences when OPEN:** does it make sense to block both operations together?
- **Fallback:** do both operations have the same ability to return safe fallback data?

Examples:

| Operation | Characteristics | Suggested Boundary |
| --- | --- | --- |
| Read inventory | Fast read, can use cache with freshness metadata. | `inventory-read` |
| Reserve stock | Write operation, requires idempotency and has uncertain outcome state on timeout. | `inventory-reserve` |
| Export inventory report | May run long and return a large stream. | `inventory-export` |
| Read pricing | Depends on pricing-service, with its own SLO and fallback. | `pricing-read` |

If read and reserve share the same failure modes, deadlines, and need to protect inventory-service as a unified capability, sharing a breaker can be intentional. However, if business errors from reserve do not reflect service health, merging statistics usually distorts the signal. Clarify which errors are recorded before deciding to share.

## 5. Classify Exceptions Before Tuning Thresholds

A breaker can open prematurely because business errors are recorded as dependency failures. For example, reserve returns HTTP 409 when stock is insufficient. If the client turns this status into an exception and the breaker records all exceptions, out-of-stock occurrences can inflate the failure rate even though inventory-service is functioning properly.

Distinguish between:

- **Infrastructure/dependency errors:** connection refused, timeout, HTTP 5xx, or communication errors that indicate an unhealthy service.
- **Business outcomes:** out of stock, version conflict, invalid request, or disallowed state.
- **Programming bugs:** NullPointerException, broken mapping, or invariant violations in the calling application.

Resilience4j lets you configure which exceptions are recorded or ignored:

    resilience4j:
      circuitbreaker:
        instances:
          inventory-reserve:
            recordExceptions:
              - java.io.IOException
              - java.util.concurrent.TimeoutException
            ignoreExceptions:
              - com.example.inventory.OutOfStockException
              - com.example.inventory.ReservationConflictException

The exception names in the example are application-defined classes and should be adapted to your actual HTTP client. If status 409 is mapped to a dedicated exception, it can be classified as a business outcome and ignored for the failure rate. Do not mechanically ignore every HTTP 4xx; 429 may indicate overload or rate limiting and require its own policy.

If one operation frequently returns business errors while another shares the breaker, verify whether those business errors are counted toward the failure rate. Splitting breakers does not replace exception classification; the two address different causes.

## 6. Configure Multiple Breakers Sharing a Policy

You can define a shared policy under `configs`, then declare each breaker under `instances` with its own id:

    resilience4j:
      circuitbreaker:
        configs:
          inventory-policy:
            slidingWindowType: COUNT_BASED
            slidingWindowSize: 20
            minimumNumberOfCalls: 10
            failureRateThreshold: 50
            slowCallDurationThreshold: 800ms
            slowCallRateThreshold: 60
            waitDurationInOpenState: 10s
            permittedNumberOfCallsInHalfOpenState: 3

        instances:
          inventory-read:
            baseConfig: inventory-policy

          inventory-reserve:
            baseConfig: inventory-policy
            minimumNumberOfCalls: 8

          inventory-export:
            baseConfig: inventory-policy
            slowCallDurationThreshold: 5s
            slowCallRateThreshold: 70

This configuration creates three independent breaker instances. All three inherit the `inventory-policy`, yet each instance has its own sliding window and state. `inventory-reserve` overrides `minimumNumberOfCalls`; `inventory-export` overrides the slow-call thresholds.

If using the Spring Cloud CircuitBreaker factory with `groupName`, you can pass the corresponding groupName when creating breakers:

    CircuitBreaker readBreaker =
        circuitBreakerFactory.create("inventory-read", "inventory");

    CircuitBreaker reserveBreaker =
        circuitBreakerFactory.create("inventory-reserve", "inventory");

Check the configuration resolution rules for your Spring Cloud CircuitBreaker version and verify the effective configuration via logs/metrics. Do not assume that declaring a YAML block automatically makes every factory or customizer select the right group if id and groupName do not align.

## 7. Fix Code Using Separate IDs per Operation

A direct fix is to replace the shared id with operationally meaningful ids:

    @Service
    public class InventoryGateway {

        private final InventoryClient inventoryClient;
        private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;

        public InventoryGateway(
                InventoryClient inventoryClient,
                CircuitBreakerFactory<?, ?> circuitBreakerFactory) {
            this.inventoryClient = inventoryClient;
            this.circuitBreakerFactory = circuitBreakerFactory;
        }

        public InventoryResponse read(String sku) {
            return circuitBreakerFactory
                .create("inventory-read", "inventory")
                .run(
                    () -> inventoryClient.read(sku),
                    error -> InventoryResponse.unknown(sku)
                );
        }

        public ReservationResponse reserve(String sku, int quantity) {
            return circuitBreakerFactory
                .create("inventory-reserve", "inventory")
                .run(
                    () -> inventoryClient.reserve(sku, quantity),
                    error -> ReservationResponse.pending(sku)
                );
        }
    }

In this example, read and reserve use the same groupName but different ids. If reserve fails continuously, the `inventory-reserve` breaker can OPEN while `inventory-read` remains CLOSED and continues serving queries.

Fallbacks also differ because the two operations have different semantics:

- A failed inventory read can return UNKNOWN or valid cached data.
- A timed-out reservation can return PENDING/UNKNOWN and require checking status via an operation ID; do not assert that the write failed if the server may have executed it.

The `InventoryResponse` and `ReservationResponse` types are application-defined contracts. Ensure the calling layer can distinguish primary data from fallback data.

## 8. Avoid Splitting Breakers Too Finely

Splitting breakers isolates statistics, yet each breaker needs enough samples to evaluate. If you create a separate breaker per URL, SKU, user, or request, traffic is fragmented into tiny buckets and many breakers never reach `minimumNumberOfCalls`.

Avoid dynamic ids:

    // Avoid: the number of breakers can grow with request data.
    circuitBreakerFactory.create("inventory-" + sku);

Instead, use stable operation-scoped names:

    circuitBreakerFactory.create("inventory-read");
    circuitBreakerFactory.create("inventory-reserve");

A breaker with too few samples can stay CLOSED even with a 100% failure rate across a handful of calls, because `minimumNumberOfCalls` has not been met. When splitting, review:

- Normal traffic volume per operation.
- `minimumNumberOfCalls` and `slidingWindowSize`.
- Time required to collect enough samples.
- Number of breaker instances created per JVM.
- Additional metric series and events generated.
- Ability to configure and monitor each breaker.

Only split when differences in errors, SLOs, timeouts, fallbacks, or consequences when OPEN are large enough to justify independent statistics. If operations share the same behavior and all need to trip when a shared dependency degrades, sharing a breaker can be a sensible choice.

## 9. Check the Actual Breaker Name

In a Spring Cloud CircuitBreaker application, the actual breaker name depends on how the factory is invoked or the client integration's naming rules. With OpenFeign, names can be generated from the client and method; a custom `CircuitBreakerNameResolver` can alter naming. These details may vary across versions.

During diagnosis, do not guess the name from the service ID alone. Check:

- The breaker name appearing in logs upon creation or state transition.
- The `name` tag in Resilience4j metrics.
- The instance list from the Actuator endpoint if that integration is enabled.
- State transition events and call-not-permitted events.
- The id passed to `factory.create(id)` or `factory.create(id, groupName)`.
- Any custom Feign resolver used by the application.

For example, a Prometheus metric query can filter by the `name` tag:

    resilience4j_circuitbreaker_state{name="inventory-read",state="open"}

Metric names are normalized for Prometheus by Micrometer and may vary by registry/version. The illustrative query shows the need to filter by breaker name and state rather than aggregating all circuit breaker metrics into a single series.

If a dashboard only shows `name=inventory` while the application has read, reserve, and export, the operations may have been mapped to a single breaker name. Verify the resolver and factory calls before changing thresholds.

## 10. Inspect the Sliding Window to Identify Which Operation Tripped the Breaker

When a breaker opens, inspect the samples that contributed to the window:

- Number of recorded calls.
- Number of failures and exception types.
- Number of slow calls.
- Failure rate and slow-call rate.
- Timestamps when failed calls occurred.
- Which business operation emitted those calls.

With `COUNT_BASED`, `slidingWindowSize` is the number of most recent outcomes kept for rate calculation. With `TIME_BASED`, the window represents a time interval and outcomes are aggregated in buckets. `minimumNumberOfCalls` determines the minimum sample count before rate evaluation.

Example configuration:

    resilience4j:
      circuitbreaker:
        instances:
          inventory:
            slidingWindowType: COUNT_BASED
            slidingWindowSize: 10
            minimumNumberOfCalls: 10
            failureRateThreshold: 50

When 10 samples exist and at least 5 errors are recorded, the failure rate reaches 50% and the breaker can open. If all 5 errors come from reserve while 5 read calls succeed, the shared breaker opens for both operations.

If ids have been separated, inspect each window individually. `inventory-reserve` may reach a high failure rate and OPEN; `inventory-read` may stay CLOSED. However, if reserve only has 3 samples while `minimumNumberOfCalls` is 10, the separate reserve breaker does not yet have enough data to open. Do not lower `minimumNumberOfCalls` just to make dashboards react faster without examining traffic and statistical stability.

## 11. Fallbacks Should Not Distort Statistics

Where errors are handled affects the outcomes the breaker observes. If the application catches an exception inside the Supplier and returns a default value, the breaker may record the call as a success.

Unsuitable example:

    return breaker.run(() -> {
        try {
            return inventoryClient.reserve(sku, quantity);
        } catch (RuntimeException error) {
            return ReservationResponse.pending(sku);
        }
    });

The Supplier turned the error into a normal outcome before the breaker received an error signal. The failure rate may appear lower than reality.

Let the error escape the Supplier and attach the fallback at the protection layer:

    return breaker.run(
        () -> inventoryClient.reserve(sku, quantity),
        error -> ReservationResponse.pending(sku)
    );

With reactive operators, place the fallback after `CircuitBreakerOperator` so the breaker receives the error before it is converted into a successful publisher. If the fallback is configured via the Spring Cloud CircuitBreaker factory, use the `run` overload with a fallback and verify the implementation's behavior.

Distinguish between business errors intentionally mapped to outcomes and infrastructure errors. If out-of-stock is a normal business outcome, the client can map HTTP 409 to a domain response without counting it as a circuit breaker failure. But timeouts or connection failures must still be recorded according to policy. Do not use a generic fallback to mask all exceptions.

## 12. Monitor Cross-Operation Impact

After splitting breakers, dashboards should display each id separately:

| Breaker | State | Calls | Failure rate | Slow call rate | Not permitted |
| --- | --- | --- | --- | --- | --- |
| inventory-read | CLOSED | 240 | 2% | 4% | 0 |
| inventory-reserve | OPEN | 80 | 62% | 18% | 35 |
| inventory-export | CLOSED | 12 | 0% | 25% | 0 |

These numbers are illustrative. They show `reserve` can be OPEN while `read` and `export` are still permitted to run. If you want an overall health view of `inventory-service`, build an aggregate dashboard from the individual breaker metrics and server-side metrics; do not collapse state into a single breaker if doing so sacrifices isolation.

Metrics to monitor:

- State gauge by breaker name.
- Calls by outcome and duration.
- Failure rate, slow-call rate.
- Not-permitted calls.
- State transition events.
- Fallback count per operation.
- Server-side HTTP latency and status per endpoint or instance at the dependency.

In a multi-pod environment, each JVM typically maintains its own breaker state. Dashboards should retain the pod/instance tag to distinguish one pod being OPEN from the entire service being OPEN. Avoid tagging metrics with SKU, request ID, or exception message because cardinality can grow unbounded.

## 13. Hands-On Exercise: Reproduce and Fix Premature Breaker Opening

Create an `InventoryGateway` with two operations, `read` and `reserve`. Start with a configuration sharing the id `inventory` to observe the issue, then split into two breakers.

**Part A — Reproduce**

1. Use `factory.create("inventory")` for both `read` and `reserve`.
2. Configure `COUNT_BASED` with window size 10, `minimumNumberOfCalls` 10, and `failureRateThreshold` 50.
3. Make 5 `reserve` calls throw a recorded exception.
4. Make 5 `read` calls succeed.
5. Observe the breaker transition to OPEN once 10 samples are reached.
6. Call `read` again and verify the Supplier does not run because the breaker is OPEN.

**Part B — Fix the Boundaries**

1. Change `read` to `factory.create("inventory-read", "inventory")`.
2. Change `reserve` to `factory.create("inventory-reserve", "inventory")`.
3. Keep the `inventory` group configuration policy identical.
4. Repeat 5 `reserve` failures and 5 successful `read` calls.
5. Verify `inventory-reserve` can OPEN while `inventory-read` remains CLOSED.
6. Verify metrics and events report two distinct breaker names.

**Part C — Verify Policy and Sample Counts**

1. Have `reserve` return an out-of-stock business error and configure that exception as ignored if the domain contract defines it as not a health error.
2. Have `reserve` time out to confirm dependency failures are still recorded.
3. Reduce `reserve` traffic and observe the effect of `minimumNumberOfCalls`.
4. Test a dynamic breaker id keyed by SKU in a test environment to observe instance/metric growth; then replace it with a stable id.
5. Verify the fallback does not swallow timeout errors before the breaker records them.

Upon completion, you should be able to explain that sharing an id shares state and the sliding window, sharing a `groupName` only shares configuration policy, and why splitting breakers must balance fault isolation against having enough samples. Use metrics and events to prove which operation tripped the breaker rather than simply raising `failureRateThreshold` to hide the symptom.

## References

- Spring Cloud CircuitBreaker — Resilience4J configuration: https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html
- Resilience4j — CircuitBreaker and sliding window: https://resilience4j.readme.io/docs/circuitbreaker
- Spring Cloud OpenFeign — CircuitBreaker support and naming: https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html
