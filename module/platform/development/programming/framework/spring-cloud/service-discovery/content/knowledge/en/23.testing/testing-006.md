# Waiting for Convergence Instead of Fixed Sleep Delays

Service registration and discovery are asynchronous operations. A provider may send a registration successfully, yet the registry needs time to update its catalog, replicate to peer nodes, or let the consumer refresh its cache. Consequently, a test calling DiscoveryClient.getInstances() immediately after starting the provider may receive an empty list even when the system works properly.

The reliable way to test this is to wait for **a meaningful condition** to be met within a bounded time limit. With Awaitility, the test repeatedly evaluates conditions such as “instance appeared”, “health is passing”, or “instance disappeared”. This avoids guessing a fixed number of seconds with Thread.sleep().

In the SPRING_CLOUD_SERVICE_DISCOVERY module, this lesson applies to integration tests with Eureka, Consul, ZooKeeper, and other discovery clients. The focus is on understanding eventual consistency, choosing timeouts and poll intervals, waiting for both the registry and consumer cache, and writing tests that run reliably on developer laptops and in CI.

## 1. Why avoid fixed Thread.sleep delays?

A test is often written like this:

    provider.start();
    Thread.sleep(5000);

    assertThat(discoveryClient.getInstances("payment-service"))
            .isNotEmpty();

This snippet assumes registration will finish within 5 seconds. However, actual duration depends on application startup speed, heartbeat schedules, registry fetch intervals, watchers, network latency, container startup, and CI load.

Thread.sleep(5000) has two problems:

- If the condition is satisfied after 200 ms, the test still wastes nearly 4.8 seconds.
- If the condition takes 6 seconds on a slow CI runner, the test fails even though the system eventually converges properly.

Increasing the sleep to 30 seconds only slows down the suite and still provides no guarantee. A permanent registration failure also forces the test to wait the full 30 seconds without clearly indicating which condition was never met.

Instead, specify a maximum timeout and re-check the condition periodically:

    await()
            .atMost(Duration.ofSeconds(30))
            .untilAsserted(() ->
                    assertThat(discoveryClient.getInstances("payment-service"))
                            .isNotEmpty()
            );

The test completes as soon as the assertion passes. If 30 seconds elapse without meeting the condition, Awaitility throws ConditionTimeoutException and reports that the wait timed out.

## 2. Eventual consistency in service discovery

The registry and the consumer do not necessarily observe the same state at the exact same moment. A change may pass through several steps:

1. The provider creates a registration or changes its health status.
2. The registry receives and persists the change.
3. Registry replication or the catalog index updates if the system has multiple nodes.
4. The consumer's discovery client receives an event or fetches new data.
5. Spring Cloud LoadBalancer refreshes its cached ServiceInstance list.
6. Subsequent requests use the updated list.

    sequenceDiagram
        participant P as Provider
        participant R as Registry
        participant D as Consumer DiscoveryClient
        participant L as LoadBalancer
        P->>R: Register instance
        R-->>P: Acknowledge
        Note over R,D: Registry/client propagation can be asynchronous
        D->>R: Fetch or receive watch update
        R-->>D: Updated instance list
        D-->>L: ServiceInstance list
        L->>L: Refresh cache
        Note over L: Subsequent requests see the instance

Tests must wait at the exact layer being verified. If the goal is to prove the registry persisted the registration, wait on the registry's native API. If the goal is to prove the consumer discovered the instance, wait on the consumer's DiscoveryClient. If the goal is to prove requests route correctly, send requests through LoadBalancer after the consumer's list has converged.

## 3. What is Awaitility?

Awaitility is a Java library for expressing asynchronous conditions readably. Instead of writing manual loops, clocks, and sleeps, the test declares:

- The target condition.
- The maximum wait duration.
- The interval between condition checks.
- An optional delay before the first check.

Commonly used methods:

| API | Purpose |
|---|---|
| await() | Starts declaring a wait condition. |
| atMost(...) | Caps the total wait duration. |
| pollInterval(...) | Interval between condition evaluations. |
| pollDelay(...) | Wait time before the first evaluation. |
| until(...) | Waits for an expression returning true or an expected value. |
| untilAsserted(...) | Repeatedly runs an assertion block until it succeeds. |
| alias(...) | Names the condition so timeout messages are clearer. |

Awaitility does not make the registry update any faster. It simply lets the test wait properly and stop immediately once the expected state appears.

## 4. Adding the Awaitility dependency

If the project does not have Awaitility yet, add the test dependency and let your project's dependency management control the compatible version:

    <dependency>
        <groupId>org.awaitility</groupId>
        <artifactId>awaitility</artifactId>
        <scope>test</scope>
    </dependency>

Common imports:

    import java.time.Duration;
    import java.util.List;
    import java.util.concurrent.TimeUnit;

    import org.awaitility.Awaitility;
    import org.springframework.cloud.client.ServiceInstance;
    import org.springframework.cloud.client.discovery.DiscoveryClient;

    import static org.assertj.core.api.Assertions.assertThat;
    import static org.awaitility.Awaitility.await;

Examples in this lesson use AssertJ for assertions. You can use JUnit assertions if your project does not use AssertJ.

## 5. Choosing between until and untilAsserted

### 5.1. Use until when the condition returns a boolean

When you only need to check a predicate, use until:

    await()
            .atMost(Duration.ofSeconds(20))
            .until(() -> !discoveryClient.getInstances("payment-service").isEmpty());

The expression is evaluated repeatedly. Once it returns true, the test continues; if it remains false past the timeout, Awaitility reports a timeout.

### 5.2. Use untilAsserted when verifying multiple attributes

If you need to assert instance ID, host, port, or metadata, untilAsserted is usually more readable:

    await()
            .alias("payment-service instance is registered")
            .atMost(Duration.ofSeconds(30))
            .pollInterval(Duration.ofMillis(200))
            .untilAsserted(() -> {
                List<ServiceInstance> instances =
                        discoveryClient.getInstances("payment-service");

                assertThat(instances).anySatisfy(instance -> {
                    assertThat(instance.getInstanceId()).isEqualTo("payment-01");
                    assertThat(instance.getHost()).isNotBlank();
                    assertThat(instance.getPort()).isEqualTo(8080);
                });
            });

While the list is empty or attributes do not match yet, the assertion fails and is retried on the next poll. Once the instance appears with all expected details, the test proceeds.

### 5.3. Do not assert on a single snapshot read outside the lambda

Avoid reading the list once and then asserting on that variable:

    List<ServiceInstance> instances =
            discoveryClient.getInstances("payment-service");

    await().untilAsserted(() -> assertThat(instances).isNotEmpty());

In this example, `instances` is a snapshot captured before Awaitility starts. Every poll keeps checking the exact same stale list, so it can never observe a new registration.

Place the read operation inside the lambda:

    await().untilAsserted(() ->
            assertThat(discoveryClient.getInstances("payment-service"))
                    .isNotEmpty()
    );

## 6. Waiting for a provider to appear in Consul

Suppose the provider registers payment-service with instance ID payment-01. The consumer connects to Consul using Spring Cloud Consul Discovery.

    private static final String SERVICE_ID = "payment-service";
    private static final String INSTANCE_ID = "payment-01";

    @Autowired
    DiscoveryClient discoveryClient;

    @Test
    void waitsUntilPaymentInstanceIsDiscoverable() {
        await()
                .alias("Consul registration visible to consumer")
                .atMost(Duration.ofSeconds(30))
                .pollInterval(Duration.ofMillis(250))
                .untilAsserted(() -> {
                    List<ServiceInstance> instances =
                            discoveryClient.getInstances(SERVICE_ID);

                    assertThat(instances).anySatisfy(instance -> {
                        assertThat(instance.getInstanceId()).isEqualTo(INSTANCE_ID);
                        assertThat(instance.getHost()).isNotBlank();
                        assertThat(instance.getPort()).isPositive();
                    });
                });
    }

This condition verifies the consumer's view. If you need to prove the Consul Catalog persisted the record, wait for `/v1/catalog/service/{service}` to return the expected ServiceID, ServiceAddress, and ServicePort. If you need to confirm health checks are passing, inspect `/v1/health/service/{service}` and check statuses separately.

Consul may use blocking queries/watches to update discovery state. Even after the provider registers, the consumer may need time to receive the change. Polling DiscoveryClient lets the test wait until the consumer-side cache reflects the record.

## 7. Waiting for a Eureka client to fetch the registry

Eureka involves multiple distinct states:

- Eureka Server has received the registration.
- The consumer's Eureka Client has fetched the updated registry.
- The consumer's LoadBalancer has refreshed its instance list.

Calling only the Eureka Server REST API proves the server holds the record, not that the consumer's local registry cache has updated.

Example waiting for the consumer to see the instance:

    await()
            .alias("Eureka consumer cache contains payment-01")
            .atMost(Duration.ofSeconds(40))
            .pollInterval(Duration.ofMillis(500))
            .untilAsserted(() -> {
                List<ServiceInstance> instances =
                        consumerDiscoveryClient.getInstances("payment-service");

                assertThat(instances).anySatisfy(instance ->
                        assertThat(instance.getInstanceId()).isEqualTo("payment-01")
                );
            });

The timeout must account for eureka.client.registry-fetch-interval-seconds and client startup time. If tests need faster convergence, reduce the fetch interval in a test profile; never alter production settings just to speed up tests.

When testing both server and consumer, use two separate waits: one waiting for the Eureka REST API to list the instance, and the next waiting for consumerDiscoveryClient. This pinpoints whether delay occurs during registration or during the consumer's fetch/cache step.

## 8. Waiting for a znode to appear in ZooKeeper

Spring Cloud Zookeeper Discovery typically stores instances as ephemeral znodes. You can use Curator's checkExists() to wait for the node to appear:

    String path = "/services/payment-service/payment-01";

    await()
            .alias("ZooKeeper ephemeral registration created")
            .atMost(Duration.ofSeconds(30))
            .pollInterval(Duration.ofMillis(200))
            .untilAsserted(() -> {
                Stat stat = curatorFramework.checkExists().forPath(path);

                assertThat(stat).isNotNull();
                assertThat(stat.getEphemeralOwner()).isNotZero();
            });

checkExists() returns null when the node does not exist yet. Once created, a non-zero ephemeralOwner indicates the node is tied to a ZooKeeper session. The actual path depends on spring.cloud.zookeeper.discovery.root, service ID, instance ID, and integration version; use the exact path configured by your application.

After the node appears, still check DiscoveryClient.getInstances() to verify the Spring Cloud abstraction can read it. A node existing while the consumer fails to read it can point to a mismatched root path, an unrefreshed cache, or restrictive ACLs.

## 9. Waiting for an instance to deregister or disappear

When a provider stops gracefully, the consumer does not necessarily see the instance vanish immediately. The registry must process deregistration, the client must observe the change, and the LoadBalancer cache must expire or be invalidated.

Example waiting until an instance ID is no longer in the list:

    await()
            .alias("payment-01 removed from consumer discovery view")
            .atMost(Duration.ofSeconds(30))
            .pollInterval(Duration.ofMillis(250))
            .untilAsserted(() -> {
                boolean stillVisible = discoveryClient
                        .getInstances("payment-service")
                        .stream()
                        .anyMatch(instance ->
                                "payment-01".equals(instance.getInstanceId()));

                assertThat(stillVisible).isFalse();
            });

With ZooKeeper, you can wait for the ephemeral znode to disappear:

    await()
            .atMost(Duration.ofSeconds(30))
            .untilAsserted(() ->
                    assertThat(curatorFramework.checkExists().forPath(path)).isNull()
            );

With Consul, check the Catalog API or Health API depending on your goal: deregistration can remove the service record, whereas a critical health check may leave the record present while no longer passing. With Eureka, graceful cancellation differs from an abrupt client crash waiting for lease expiration. Tests must assert the exact semantics they intend to verify.

## 10. Waiting for health status transitions

A service may already be registered while its health check is not yet passing. Do not use “instance exists” as a proxy for “instance is healthy”.

For instance, in Consul, when the consumer is configured with query-passing=true, you can wait on the instance list under the active discovery configuration:

    await()
            .alias("Consul reports payment-01 as passing")
            .atMost(Duration.ofSeconds(45))
            .untilAsserted(() -> {
                List<ServiceInstance> passingInstances =
                        discoveryClient.getInstances("payment-service");

                assertThat(passingInstances)
                        .anySatisfy(instance ->
                                assertThat(instance.getInstanceId()).isEqualTo("payment-01")
                        );
            });

The condition above only proves the consumer returns the instance under the current discovery settings. To prove a specific Consul check is passing, query the Health API and assert the corresponding Checks[].Status. Do not infer health status simply because the service appears in the Catalog API.

With Eureka, check the status published by the client such as UP or DOWN; do not assume Eureka Server actively polls every instance's Actuator health URL. With ZooKeeper, a live session only proves the client maintains its session, not that the service's HTTP endpoint is healthy.

## 11. Waiting for both the registry and consumer cache

A good test can split two stages to pinpoint convergence:

    // Stage 1: Consul Catalog has stored the registration.
    await()
            .alias("Consul catalog contains payment-01")
            .atMost(Duration.ofSeconds(20))
            .untilAsserted(() -> {
                JsonNode[] records = consulCatalog.findService(SERVICE_ID);
                assertThat(records)
                        .anySatisfy(record ->
                                assertThat(record.path("ServiceID").asText())
                                        .isEqualTo(INSTANCE_ID)
                        );
            });

    // Stage 2: Consumer DiscoveryClient has seen the registration.
    await()
            .alias("consumer discovery cache contains payment-01")
            .atMost(Duration.ofSeconds(20))
            .untilAsserted(() ->
                    assertThat(discoveryClient.getInstances(SERVICE_ID))
                            .anySatisfy(instance ->
                                    assertThat(instance.getInstanceId()).isEqualTo(INSTANCE_ID)
                            )
            );

consulCatalog.findService is a test-written helper calling the Catalog API. Splitting the conditions separates “registry has not received registration” from “consumer has not refreshed its cache”. For Eureka, replace the helper with the Eureka REST API; for ZooKeeper, use Curator checkExists() or read the znode payload.

If you only need a final outcome, waiting on every layer separately is unnecessary. However, when tests fail or when measuring propagation delay, splitting stages makes the root cause much clearer.

## 12. Choosing appropriate timeouts

A timeout is the upper bound on how long the test is willing to wait. Do not pick it arbitrarily or set it tightly to best-case laptop timings.

One way to estimate is to budget across potentially sequential steps:

    T_timeout >= T_register + T_replication + T_refresh + T_cache + T_margin

Components may include:

- Time for the provider to boot and send registration.
- Time for the registry to record or replicate the change.
- Fetch/watch cycle of the discovery client.
- Time for the LoadBalancer cache to refresh.
- Scheduler, network, and CI load overhead.

This is a conservative budget; some steps happen concurrently or do not apply to the registry in use. Measure actual behavior and pick a timeout with headroom rather than mechanically summing numbers.

| Environment | Illustrative timeout | Notes |
|---|---|---|
| In-process async unit test | 1–3 seconds | No registry network; only for fast local work. |
| Local registry container | 15–30 seconds | Depends on container readiness and client config. |
| Eureka with default registry fetch interval | 30–60 seconds or per config | Must account for fetch cycle and client startup. |
| CI with slow containers/network | 30–90 seconds or per measurements | Do not make timeouts excessively large to mask real bugs. |
| ZooKeeper session expiration | Configured session timeout plus margin | Session expiration can take longer than normal watcher notifications. |

These durations are only starting points for test design. Production-like timeouts must be derived from your specific system configuration and measurements.

## 13. Choosing poll interval and poll delay

pollInterval is the duration between checks. pollDelay is the wait before the first check.

    await()
            .alias("service registration appears")
            .pollDelay(Duration.ZERO)
            .pollInterval(Duration.ofMillis(250))
            .atMost(Duration.ofSeconds(30))
            .untilAsserted(() ->
                    assertThat(discoveryClient.getInstances("payment-service"))
                            .isNotEmpty()
            );

Guidelines for choosing values:

- Polling too aggressively does not make the registry converge faster; it only increases how often the test reads the condition.
- Polling too infrequently delays detection after the condition has already been met.
- For local containers, around 100–300 ms is usually responsive without adding noticeable load.
- For remote registries or expensive queries, consider 500 ms to a few seconds.
- Use pollDelay when an operation is known to have a minimum initialization phase; never add delay just to paper over an poorly understood race condition.

If a discovery client only refreshes every 30 seconds, polling every 50 ms will not let the consumer see new data any sooner. In that case, shorten the refresh interval in the test profile or raise the timeout appropriately.

## 14. Handling transient exceptions intentionally

A condition may temporarily throw an exception while a registry or application is starting up. However, do not ignore all exceptions because doing so can mask configuration or programming errors.

Prefer these approaches:

1. Wait for registry readiness before starting providers/consumers.
2. Write predicates safely for absent data, such as empty lists or missing znodes.
3. If a specific transient exception is well-defined, ignore only that exception type while still keeping a timeout.
4. Let unexpected exceptions fail the test immediately instead of swallowing all errors.

Example safe predicate:

    await()
            .atMost(Duration.ofSeconds(20))
            .until(() -> {
                List<ServiceInstance> instances =
                        discoveryClient.getInstances("payment-service");
                return instances.stream().anyMatch(instance ->
                        "payment-01".equals(instance.getInstanceId()));
            });

Do not overuse ignoreExceptions() for every error. If the registry URL is wrong, ACLs return 403, or the client uses the wrong serializer, ignoring exceptions until timeout only obscures logs. Only use ignoreException(...) or ignoreExceptionsMatching(...) when you have verified that exception class represents an acceptable transient state during convergence.

## 15. Waiting for a condition to stay stable over a period

Sometimes meeting a condition once is not enough. For example, an instance may appear and then vanish due to an overwritten registration or a failing health check. In that case, the test needs to verify the state remains stable over a period.

You can use Awaitility's during(...) API if supported by your version:

    await()
            .during(Duration.ofSeconds(3))
            .atMost(Duration.ofSeconds(20))
            .untilAsserted(() ->
                    assertThat(discoveryClient.getInstances("payment-service"))
                            .anySatisfy(instance ->
                                    assertThat(instance.getInstanceId())
                                            .isEqualTo("payment-01")
                            )
            );

The condition must remain true throughout the `during` window. This is useful for catching oscillating states, though it lengthens test execution and should not be used on every assertion. For most registration tests, waiting for the condition once suffices; reserve stability checks for health or lifecycle tests with explicit stability requirements.

## 16. Do not confuse Awaitility with application synchronization

Awaitility is strictly a testing tool. It does not replace:

- Eureka heartbeats, registry fetches, or lease expiration.
- Consul blocking queries, watches, TTL checks, or health checks.
- ZooKeeper watchers, session state, or ephemeral node lifecycles.
- Kubernetes watches, EndpointSlice updates, or DNS TTLs.
- Spring Cloud LoadBalancer cache invalidation.

Never put Awaitility polling loops into production code to wait for services to appear. In production applications, use discovery abstractions, timeouts/retries, circuit breakers, and proper event/watch mechanisms. Awaitility belongs in test code.

If your application uses Reactor, StepVerifier fits testing publishers/streams and emission timing. Awaitility fits when conditions are observed via synchronous APIs, registry clients, or external state. Pick the tool based on the shape of the data under test; never nest Thread.sleep inside publisher tests.

## 17. Systematic timeout diagnostics

When Awaitility times out, do not blindly increase the timeout. Check in order:

1. Is the registry container/server genuinely ready?
2. Did the provider send its registration successfully?
3. Does the registry-native API contain the record with the expected service ID and instance ID?
4. Are hostname/IP and port advertised accurately?
5. Is the consumer pointing to the same registry, namespace/root path, and credentials?
6. Is the consumer's discovery client fetching or watching updated data?
7. Is the LoadBalancer cache holding onto a stale list?
8. Is a health query filtering out the instance because it is non-passing?
9. Is the test reading an old snapshot/list outside the Awaitility lambda?
10. Is the poll timeout shorter than the fetch interval or session timeout?

Assign aliases to each condition and log service ID, instance ID, registry endpoint, host/port, and status. Never log tokens, passwords, or secrets. When needed, split waits between registry-native state and consumer state to pinpoint which step has not converged.

| Symptom | Possible cause | Resolution |
|---|---|---|
| Test fails immediately | Exception not treated as wait state or registry not ready. | Wait for readiness and inspect the root exception. |
| Test always times out even though instance is in registry | Consumer points to wrong registry, cache has not fetched, or wrong service ID. | Inspect consumer context and DiscoveryClient separately. |
| Passes locally but fails in CI | Tight timeout, slow Docker/network, or unreachable port/hostname. | Increase margin from measurements, use mapped ports and network-reachable advertised addresses. |
| Test takes many seconds despite early condition | Large poll interval or unnecessary pollDelay. | Reduce poll interval/delay appropriately. |
| Test puts heavy load on registry | Polling native API too aggressively or many tests running in parallel. | Poll less frequently, check client cache for consumer waits, and isolate tests. |
| Instance appears then disappears | Duplicate ID, failing health check, or closed provider context. | Check registration lifecycle and check status. |
| Deregistration times out | Client did not deregister, lease/session not expired, or consumer cache not refreshed. | Distinguish graceful shutdown from failure detection; wait at the right layer. |
| Exception hidden until timeout | Overly broad ignoreExceptions(). | Ignore only specific transient exceptions; let config errors fail fast. |
| Assertion always checks stale data | Snapshot captured before Awaitility lambda. | Move the read operation inside the lambda. |

## 18. A reusable helper pattern for test suites

If many tests wait for an instance, you can build a helper to avoid repeating Awaitility setup:

    import java.time.Duration;
    import java.util.List;

    import org.springframework.cloud.client.ServiceInstance;
    import org.springframework.cloud.client.discovery.DiscoveryClient;

    import static org.assertj.core.api.Assertions.assertThat;
    import static org.awaitility.Awaitility.await;

    public final class DiscoveryTestWaits {

        private DiscoveryTestWaits() {
        }

        public static ServiceInstance awaitInstance(
                DiscoveryClient discoveryClient,
                String serviceId,
                String instanceId,
                Duration timeout) {

            await()
                    .alias("instance " + instanceId + " appears in " + serviceId)
                    .atMost(timeout)
                    .pollInterval(Duration.ofMillis(200))
                    .untilAsserted(() -> {
                        List<ServiceInstance> instances =
                                discoveryClient.getInstances(serviceId);

                        assertThat(instances).anySatisfy(instance ->
                                assertThat(instance.getInstanceId()).isEqualTo(instanceId)
                        );
                    });

            return discoveryClient.getInstances(serviceId).stream()
                    .filter(instance -> instanceId.equals(instance.getInstanceId()))
                    .findFirst()
                    .orElseThrow();
        }
    }

The helper returns the instance after the condition has been satisfied. Reading again after Awaitility is necessary to return the current object; never capture a snapshot variable before waiting. If the list could still change right after the condition succeeds, the caller must still handle connection errors as normal runtime behavior.

Avoid overly generic helpers stuffed with callbacks and cryptic configuration flags. A good helper expresses one concrete condition, uses a clear alias, and takes a caller-supplied timeout.

## 19. Checklist for writing stable convergence tests

- Choose the final state to verify: registration, passing health, consumer discovery, or deregistration.
- Identify the right data source to read: registry API, DiscoveryClient, LoadBalancer, or live endpoint.
- Place state reads inside the Awaitility lambda.
- Use until for boolean predicates and untilAsserted for multi-assertion checks.
- Size timeouts based on heartbeat/fetch/watch/session/cache intervals and CI measurements.
- Choose a poll interval that is responsive without overloading the registry.
- Use pollDelay only when there is a clear reason.
- Ignore only identified transient exceptions; never swallow all exceptions.
- Use unique service IDs and instance IDs to avoid interference from other tests.
- Check registry-native state and consumer state separately when diagnosing propagation.
- Wait for deregistration according to the actual semantics of Eureka, Consul, or ZooKeeper.
- Close provider contexts and registry containers after tests.
- Use aliases so timeouts identify the condition being awaited.
- Never use Awaitility in production code as a substitute for discovery/retry mechanisms.

## Conclusion

Service registration, health updates, and deregistration all converge asynchronously across registries, discovery clients, and LoadBalancer caches. Fixed Thread.sleep() calls do not prove a condition was satisfied; they merely force tests to wait a guessed duration. Awaitility lets tests re-evaluate state until assertions succeed or time out, making tests faster when conditions arrive early and easier to diagnose when they never arrive.

Wait at the exact layer your test aims to verify: the registry-native API for records, DiscoveryClient for the consumer view, the health API for status, and real requests for the data plane. Choose timeouts based on system refresh cycles, set sensible poll intervals, avoid overly broad exception suppression, and always clean up registrations after tests.

## References

- Awaitility — Usage and DSL: https://github.com/awaitility/awaitility/wiki/Usage
- Awaitility — Javadoc: https://javadoc.io/doc/org.awaitility/awaitility/latest/index.html
- Spring Cloud Commons — DiscoveryClient: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html
- Spring Cloud Netflix — Eureka Client: https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html
- Spring Cloud Consul — Service Discovery: https://docs.spring.io/spring-cloud-consul/reference/discovery.html
- Spring Cloud Zookeeper — Service Discovery: https://docs.spring.io/spring-cloud-zookeeper/reference/discovery.html
