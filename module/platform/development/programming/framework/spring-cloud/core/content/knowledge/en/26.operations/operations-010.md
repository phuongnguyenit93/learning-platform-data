# Verifying Behavior During Network, Registry, or Configuration Source Failures

This lesson belongs to the **Operations** chapter of the **SPRING_CLOUD_CORE** module. A Spring Cloud application depends on multiple out-of-process components: networking, DNS, service registries, Config Server, the Spring Cloud Bus message broker, and downstream services invoked via LoadBalancer. These dependencies can become slow, lose connectivity, return stale data, or recover asynchronously. Applications must be verified under those conditions before production deployment.

Operational failure testing goes beyond confirming requests fail. You must observe how the application reacts, failure detection time, retry limits, ability to serve from cached data, readiness state, and recovery behavior after dependencies come back up. For configuration sources, clearly define which settings are mandatory at startup, which can use local fallbacks, and how refreshes behave while Config Server is unavailable.

This lesson builds repeatable scenarios across three outage categories: **network loss**, **unavailable registries**, and **disrupted configuration sources**. Examples use Testcontainers Toxiproxy to inject latency, jitter, and connection cuts in an isolated test environment, combined with tests for startup, runtime refresh, LoadBalancer caching, health/readiness, and recovery workflows.

## 1. Learning Outcomes

After this lesson, you can:

1. Classify network failures into DNS, connection refused, timeout, latency, dropped connections, and TLS errors.
2. Construct failure scenarios with start conditions, durations, and recovery criteria.
3. Use Testcontainers Toxiproxy to simulate TCP disruptions in integration tests.
4. Distinguish registry outages from service instance outages and stale registrations.
5. Test `DiscoveryClient` and Spring Cloud LoadBalancer behavior when the registry disconnects.
6. Understand the impact of instance list caching and TTLs on requests during registry outages.
7. Test Config Client when Config Server is unavailable at startup.
8. Distinguish `optional:configserver:` from mandatory config imports.
9. Test fail-fast, retries, backoff, and connect/read timeouts.
10. Test multiple Config Server endpoints and distinguish network errors from authentication errors.
11. Verify configuration refresh while remote sources are disrupted.
12. Test refresh propagation via Spring Cloud Bus when the broker or select instances fail.
13. Design intentional fallbacks and last-known-good configuration.
14. Distinguish health, readiness, and liveness during external dependency failures.
15. Measure detection time, recovery time, retry counts, and request failure rates.
16. Run chaos tests with small blast radii, explicit stop conditions, and clear recovery paths.

## 2. Defining the Behavioral Contract Before Injecting Failures

### 2.1. Do Not Start by Randomly Killing Dependencies

Before each experiment, write down exactly what must be verified. For example:

- When Config Server is unreachable at startup, must the app stop or is local configuration allowed?
- When the registry disconnects for 20 seconds, how are requests handled while instance lists remain cached?
- When the cache expires while the registry is still down, what error does the caller receive?
- Once the registry recovers, how long does the app take to see new instances?
- When the Bus broker disconnects, can a single instance still refresh locally?
- When refreshing a bean fails, what state do health indicators and subsequent requests reflect?

A scenario is only valuable when expected outcomes are defined upfront. Never treat any thrown exception as a PASS; getting the right exception type while retrying infinitely, exhausting connection pools, or triggering fleet-wide restarts is still an operational failure.

### 2.2. Failure Scenario Template

| Component | Question to Answer |
| --- | --- |
| Dependency | Which registry, Config Server, DNS, broker, or downstream service is affected? |
| Failure mode | Disconnection, latency, timeout, returning 401/403/404/500, or stale data? |
| Injection point | Toxiproxy, container stop, mock server, or test configuration? |
| Duration | How long does the fault last or until what condition is met? |
| Expected behavior | Request failure, fallback, retry, caching, readiness transition, or startup abort? |
| Recovery | New connections needed, cache refresh, instance re-registration, or restart? |
| Evidence | Which logs, metrics, traces, health responses, and assertions prove the outcome? |
| Stop condition | When must the experiment stop to protect the environment? |

### 2.3. Separate Three Observation Phases

A dependency can fail across three distinct lifecycle phases:

1. **Startup:** the application is fetching configuration or registering itself.
2. **Steady state:** the application is running and serving requests.
3. **Recovery:** the dependency has recovered, yet clients may still hold stale caches, broken sockets, or error states.

Testing startup alone does not prove runtime outage resilience. Testing only failed requests during an outage does not prove the application self-recovers afterward.

## 3. Classifying Network Failures

### 3.1. Common Failure Modes

| Failure Mode | Symptom | What to Verify |
| --- | --- | --- |
| DNS lookup failure | Hostname fails to resolve. | DNS retries, DNS caching, recovery time, and error messages. |
| Connection refused | Host is reachable, but port is not listening. | Connect timeout, retry budget, and circuit breaker. |
| Connect timeout | TCP handshake fails to complete in time. | Client enforces finite deadlines and does not block threads excessively. |
| Read timeout | Connected, but server fails to return response in time. | Request cancels, connection is handled cleanly, and retries do not duplicate side effects. |
| Latency/jitter | Responses arrive slowly and erratically. | Deadlines, timeouts, retry amplification, and p95/p99 latency. |
| TCP interruption | Connection drops mid-flight. | Client detects broken socket and opens a fresh connection. |
| Bandwidth restriction | Data transfers slowly or stalls. | Backpressure, request queues, and memory usage. |
| TLS handshake/certificate error | Connection fails at the TLS layer. | Truststores, certificate expiry, hostname verification, and error classification. |
| Partial network impairment | Only one direction or route is impaired. | Asymmetric behavior and proper timeouts. |

### 3.2. Do Not Lump Every Error into "Network Down"

`Connection refused` and timeout carry different meanings. Likewise, HTTP 401/403, 404, and 500 must be classified separately:

- Connection refused usually indicates no process is listening on that address/port.
- Timeouts can result from packet drops, overloaded servers, broken routes, or overly tight deadlines.
- HTTP 401/403 usually indicate credential or authorization errors; retrying them like network blips only adds load.
- HTTP 404 may mean a wrong application/profile/label or nonexistent resource.
- HTTP 5xx indicates server errors, though responses and causes should be inspected before retrying blindly.

Test scenarios should isolate each error category to confirm clients classify and handle them accurately.

### 3.3. Connect Timeouts and Read Timeouts Must Be Bounded

A client without finite timeouts can pin request threads or connection pool slots indefinitely. For every dependency, define:

- Connect timeout.
- Read/response timeout.
- Overall operation deadline.
- Retry count and backoff.
- Maximum elapsed time before returning an error to callers.

Total retry duration should not exceed the deadline allowed by callers or gateways. If each retry uses long timeouts and large backoffs, a seemingly simple request can tie up resources for minutes.

### 3.4. Testing Asymmetric (One-Way) Failures

Outbound requests may reach the server while responses never return. This differs from a clean connection cut. It can stall the client until read timeout, leaving ambiguity about whether the server processed the request even though the caller received no result.

For operations with side effects, test idempotency keys or status-query mechanisms after timeouts. Never blindly retry a mutating command that the server may already have executed.

## 4. Simulating Network Faults with Testcontainers Toxiproxy

### 4.1. Where Does Toxiproxy Fit?

Toxiproxy is a TCP proxy you can place between test code and containers, or between containers. Testcontainers provides a Toxiproxy module for testing network failure modes in integration tests and CI.

You can proxy:
- Applications connecting to a service registry.
- Config Clients connecting to Config Server.
- Services calling downstream TCP endpoints.
- Application containers connecting to a message broker.
- Test code connecting to containerized dependencies.

Placing a proxy between client and dependency lets tests alter network conditions while the application is running rather than merely stopping containers before tests begin.

### 4.2. Adding the Test Dependency

With Gradle, when Testcontainers versions are managed via BOM:

~~~kotlin
dependencies {
    testImplementation("org.testcontainers:testcontainers-toxiproxy")
}
~~~

With Maven, add `org.testcontainers:testcontainers-toxiproxy` in `test` scope using the version managed by your project's Testcontainers BOM.

Do not independently bump the Toxiproxy module to a version mismatched with your other Testcontainers modules.

### 4.3. Creating Networks and Proxies

The example below uses a sample TCP service as an illustration target. In real Spring Cloud integration tests, swap the target container for your registry, Config Server, or broker image.

~~~java
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.Network;
import org.testcontainers.containers.ToxiproxyContainer;

import eu.rekawek.toxiproxy.ToxiproxyClient;
import eu.rekawek.toxiproxy.model.Proxy;

Network network = Network.newNetwork();

GenericContainer<?> dependency =
        new GenericContainer<>("redis:6-alpine")
                .withExposedPorts(6379)
                .withNetwork(network)
                .withNetworkAliases("dependency");

ToxiproxyContainer toxiproxy =
        new ToxiproxyContainer("ghcr.io/shopify/toxiproxy:2.5.0")
                .withNetwork(network)
                .withNetworkAliases("toxiproxy");

dependency.start();
toxiproxy.start();

ToxiproxyClient toxiproxyClient =
        new ToxiproxyClient(
                toxiproxy.getHost(),
                toxiproxy.getControlPort()
        );

Proxy proxy = toxiproxyClient.createProxy(
        "dependency-proxy",
        "0.0.0.0:8666",
        "dependency:6379"
);

String proxyHost = toxiproxy.getHost();
int proxyPort = toxiproxy.getMappedPort(8666);
~~~

Clients running on the host must connect to `proxyHost:proxyPort`. If the application runs inside the same Docker network, configure it to connect to the Toxiproxy hostname and internal proxy port.

In real tests, ensure all client requests traverse the proxy. If some requests still connect directly to the registry or Config Server, adding toxics will not affect them.

Manage network and container lifecycles via JUnit/Testcontainers extensions or close them in cleanup blocks. Never leave stray proxies or containers running after tests, as they can interfere with subsequent runs.

### 4.4. Injecting Latency and Jitter

Toxiproxy allows adding latency and jitter to TCP streams:

~~~java
import eu.rekawek.toxiproxy.model.ToxicDirection;

proxy.toxics()
        .latency(
                "registry-latency",
                ToxicDirection.DOWNSTREAM,
                1_100
        )
        .setJitter(100);
~~~

With this configuration, downstream latency fluctuates around 1,100 ms with roughly 100 ms of jitter per Toxiproxy's model. You can add upstream toxics as well to test bidirectional latency.

Metrics to measure:
- Request latency p50/p95/p99.
- Requests exceeding deadlines.
- Retry counts.
- Pending/waiting connections.
- Caller error rates.
- Whether thread/connection pools grow continuously.

### 4.5. Cutting Bidirectional Connectivity

You can block traffic through the proxy using zero-limit bandwidth toxics:

~~~java
proxy.toxics().bandwidth(
        "cut-downstream",
        ToxicDirection.DOWNSTREAM,
        0
);

proxy.toxics().bandwidth(
        "cut-upstream",
        ToxicDirection.UPSTREAM,
        0
);
~~~

To restore connectivity, remove both toxics:

~~~java
proxy.toxics().get("cut-downstream").remove();
proxy.toxics().get("cut-upstream").remove();
~~~

Testcontainers Toxiproxy also supports timeouts, slow closes, and other stream mutations. Choose toxics matching the failure mode under test.

### 4.6. Testing Both Failure and Recovery

An outline test can follow this sequence:

~~~java
@Test
void clientRecoversAfterNetworkIsRestored() {
    assertThat(registryGateway.listServices())
            .contains("inventory-service");

    cutConnection(proxy);

    assertThatThrownBy(() -> registryGateway.listServices())
            .isInstanceOf(RegistryUnavailableException.class);

    restoreConnection(proxy);

    await().atMost(Duration.ofSeconds(10)).untilAsserted(() ->
            assertThat(registryGateway.listServices())
                    .contains("inventory-service")
    );
}
~~~

`RegistryGateway` and `RegistryUnavailableException` are application-defined wrappers in this example. Actual exceptions depend on the `DiscoveryClient`/provider; inspect real exception types and normalize them in an application layer if needed.

This example uses Awaitility for time-bounded assertions; add the corresponding test dependency if your project lacks it. During recovery, clients may need to open fresh connections. If a pool holds broken sockets, check pool validation/eviction mechanisms. Never use fixed `Thread.sleep` calls to wait for recovery; use bounded polling and repeated assertions.

### 4.7. Limitations of Toxiproxy

Toxiproxy operates on TCP streams. It excels at latency, jitter, bandwidth caps, timeouts, and dropped connections. It does not replace tests for DNS resolvers, certificate authorities, or HTTP application-layer errors.

To test DNS failures, use a dedicated DNS server/container or a test environment controlling resolution. To test TLS, use expired test certificates, wrong hostnames, or untrusted truststores. To test HTTP 401/404/500, use mock servers or test servers returning those status codes.

## 5. Verifying Behavior When the Registry Disconnects

### 5.1. Separating Registry Outages from Instance Outages

These scenarios are distinct:

- **Registry outage:** clients cannot reach the system storing/resolving service registrations.
- **Service instance outage:** the registry is up, yet one or more instances stopped serving.
- **Stale registration:** the registry retains dead instances or clients hold outdated instance lists.
- **Registration delay:** a new instance has booted but is not yet registered or visible to clients.

Each scenario impacts a different layer. Never run a single "registry down" test and conclude the system handles all service discovery failures well.

### 5.2. Testing Startup When the Registry Is Not Ready

Write tests starting the application while the registry container is stopped or blocked by the proxy.

Define the policy upfront:

| Policy | Expected Behavior |
| --- | --- |
| Discovery is mandatory to serve requests | Startup may fail or readiness stays out of accepting traffic. |
| Discovery is optional | App can start in designed local mode/fallback. |
| Registry is used only for instance registration | App may run, but must not claim successful registration. |
| Registry is used to locate Config Server | Startup also depends on discovery-first lookup and Config Client policy. |

Never let the application report ready when a mandatory dependency has not been verified. Conversely, do not let an auxiliary registry put every instance into a restart loop if the app can safely serve via tested fallback mechanisms.

### 5.3. Testing Registry Disconnection After Startup

Execute tests in sequence:

1. Start registry and application.
2. Register at least two instances of a service.
3. Send requests to warm the instance list cache if LoadBalancer caching is enabled.
4. Cut connectivity between the application and registry.
5. Keep sending requests for less than the cache TTL.
6. Send requests after the cache expires.
7. Restore connectivity.
8. Verify clients fetch the updated instance list and requests succeed.

The goal is distinguishing behavior with a warm cache from behavior once the cache is empty or expired.

### 5.4. Caching Is Not a Last-Known-Good Guarantee

Spring Cloud LoadBalancer caches `ServiceInstanceListSupplier`. Current defaults set a 35-second TTL. Caching avoids querying discovery on every instance selection, but it is not a blanket guarantee that clients always fall back to old lists when the registry fails.

Behavior after cache expiration depends on suppliers, providers, caching layers, and exception handling. Explicitly test:
- Cache populated before outage.
- Cache cold (never populated).
- Cache expiring while registry remains down.
- Registry returning an empty list without throwing an exception.
- Registry recovering and instance lists changing.

If an application requires stale-instance fallback, explicitly design TTLs, staleness limits, and eviction rules for known-unhealthy instances. Never rely on untested implicit cache behavior.

### 5.5. Testing HealthCheckServiceInstanceListSupplier

`HealthCheckServiceInstanceListSupplier` periodically checks instances supplied by a delegate supplier. Spring Cloud documentation notes this is especially helpful with `SimpleDiscoveryClient` or services with few instances; with real registries, health status is usually provided by the registry itself.

One detail to verify: when zero instances pass health checks, this supplier may fall back to returning the entire retrieved list instead of an empty list. Therefore, do not assume the health-check supplier guarantees filtering out failing instances in every scenario.

When using `HealthCheckServiceInstanceListSupplier`, test:
- Initial delay and interval.
- Per-service-ID health-check paths.
- Timeout per health request.
- Behavior when health endpoints stop responding.
- Behavior when all instances are unhealthy.
- Supplier caching and instance list refetching.

Do not stack health-check polling on top of registry-backed discovery by default; it can generate extra traffic without adding fresh information.

### 5.6. Testing Registration and Deregistration

Spring Cloud Commons provides the `ServiceRegistry` abstraction with register/deregister operations. Tests should verify:

- Registry unavailable when an instance tries to register.
- Registration failures are logged/metered and retried per policy.
- The instance does not claim it registered when the provider returns errors.
- Re-registration works once the registry recovers.
- Normal shutdown triggers deregistration.
- Abrupt process termination relies on provider leases/heartbeats/TTLs to evict stale instances as configured.

`spring.cloud.service-registry.auto-registration.fail-fast` and provider properties can alter startup behavior. Check your BOM and specific provider before defining expected behavior.

## 6. Verifying Config Server Disconnection at Startup

### 6.1. Distinguishing Optional vs. Mandatory Config Imports

With Spring Boot Config Data imports, an optional example:

~~~properties
spring.config.import=optional:configserver:
~~~

The `optional:` prefix allows startup to continue when Config Server is unreachable. Omitting `optional:` makes Config Client fail startup when Config Server data cannot be retrieved.

This is an architectural decision:

| Configuration | Expected Behavior When Config Server Is Down |
| --- | --- |
| `optional:configserver:` | Startup can continue; application must have safe local defaults. |
| `configserver:` | Startup fails if Config Server cannot supply the property source. |
| Legacy bootstrap with `spring.cloud.config.fail-fast=true` | Client aborts startup with an exception when unable to connect. |
| Legacy bootstrap with fail-fast false | Behavior depends on bootstrap/config client and retry/fallback options. |

Never use `optional:` solely to keep deployments green. If missing remote config causes the application to hit the wrong database, skip authentication, or run in the wrong mode, a successful startup is unsafe.

### 6.2. Designing Explicit Local Fallbacks

When Config Server is optional, classify local values:

- **Mandatory:** database endpoints, security modes, credential references, tenants, or encryption policies.
- **Safe to default:** log levels, cache bounds, features not affecting integrity.
- **Never auto-default:** secrets, signing keys, trust policies, or sensitive production endpoints.

Tests must prove missing remote properties never cause the application to use dangerous defaults. Startup validation can fail whenever mandatory properties remain absent.

### 6.3. Testing Fail-Fast and Retries

Spring Cloud Config Client supports fail-fast and retries. Per current documentation, retry configuration requires:
- Enabling `spring.cloud.config.fail-fast=true`.
- Adding `spring-retry` and `spring-boot-starter-aop` to the classpath.
- Default retries: six attempts, 1,000 ms initial backoff, and 1.1 multiplier.
- Tuning via `spring.cloud.config.retry.*`.

Example configuration:

~~~yaml
spring:
  cloud:
    config:
      fail-fast: true
      retry:
        max-attempts: 8
        initial-interval: 1000
        max-interval: 5000
        multiplier: 1.5
~~~

This configuration is illustrative; total startup time also depends on connect timeouts, read timeouts, number of Config Server URLs, and server response times.

With Config Data imports, omitting `optional:` achieves equivalent fail-fast behavior. If `spring.config.import` resides in a profile-specific file, retry options may need to be passed as URL query parameters on the import per your version's documentation.

### 6.4. Testing Connect and Read Timeouts

Spring Cloud Config Client exposes:

~~~yaml
spring:
  cloud:
    config:
      request-connect-timeout: 2000
      request-read-timeout: 5000
~~~

Values are in milliseconds:
- Connect timeout bounds connection establishment time.
- Read timeout bounds waiting for a response once connected.

In tests, create at least two separate scenarios:
1. Config Server refuses TCP connections.
2. Config Server accepts connections but delays responses beyond read timeout.

Testing only a stopped server leaves read timeouts untested.

### 6.5. Testing Multiple Config Server URLs

Config Client can try multiple Config Server URLs in order. With `spring.cloud.config.uri`, the default strategy is `always`; `connection-timeout-only` limits failover to certain connection/timeout errors. HTTP 401 or 500 is not equivalent to a normal connection outage and does not necessarily trigger failover to the next URL.

When specifying multiple URLs via `spring.config.import`, processing rules differ from `spring.cloud.config.uri`; do not blindly apply `multiple-uri-strategy` across all import styles.

Tests must verify:
- First URL unreachable, second URL works.
- First URL returns 401 due to bad credentials.
- First URL returns 500.
- Both URLs fail.
- Config Server returns a property source missing a required key.

### 6.6. Separating Config Server Outages from Git Backend Outages

Config Server may remain up and serve HTTP responses while its backing Git repository is unreachable. This is a distinct failure mode because Config Server can hold a local working copy after a successful clone.

With a Git backend:
- By default, Config Server clones the repository on the first request. Thus the server can boot even if the Git URI is wrong or the Git server is down; errors surface only when clients request configuration.
- Set `spring.cloud.config.server.git.clone-on-start=true` to check the repository at startup and fail fast if cloning fails.
- After cloning succeeds, Config Server retains a local working copy. If the Git remote disconnects, the server can keep serving revisions from its local copy as long as the requested branch and files exist.
- `spring.cloud.config.server.git.refresh-rate` defaults to `0`, meaning Git fetches on every request. Positive values set the refresh interval in seconds. While remote is down, fetches fail and the local copy remains on the last fetched revision; once remote recovers, the next fetch updates the local copy.
- If Config Server restarts while the Git remote is down without a local clone, configuration requests fail. Clients retain existing configuration across failed refreshes as documented.

Test three separate scenarios:
1. Config Server cloned successfully, then cut connectivity to Git remote and verify the server continues serving the old revision.
2. Restart Config Server while Git remote is down with lazy cloning enabled; verify the first request fails.
3. Enable `clone-on-start` and start Config Server while Git remote is down; verify startup fails fast.

Do not confuse Config Server's local working copy with client-side caching in Config Client. They live in separate processes with separate lifecycles and update timings. For Vault, filesystem, or custom `EnvironmentRepository` backends, design matching scenarios for that backend's semantics.

## 7. Verifying Configuration Source Loss After Startup

### 7.1. Successful Startup Does Not Prove Refresh Will Succeed

After loading remote config, values in the `Environment` and beans remain usable if Config Server temporarily goes offline. However, do not assume subsequent refreshes automatically retain last-known-good configuration across every version and bootstrap style.

Test the exact mechanism your application uses:
- Config Data import.
- Legacy bootstrap.
- Refresh endpoint.
- Spring Cloud Bus.
- Custom `PropertySourceLocator` or other config sources.

### 7.2. Config Client Does Not Poll the Environment by Default

Spring Cloud Config Client does not continuously poll Config Server for changes by default. For multi-instance applications, Spring Cloud recommends broadcasting `EnvironmentChangeEvent` via Spring Cloud Bus rather than having every instance poll independently.

Consequently, when testing runtime outages, trigger an actual refresh or emit a Bus event. Simply stopping Config Server without any refresh/polling will not test refresh failure handling.

### 7.3. Testing /actuator/refresh

Spring Cloud Context provides `RefreshScope` and `/actuator/refresh`. Refresh reloads property sources/bootstrap contexts per current mechanics, rebinds eligible `@ConfigurationProperties`, and invalidates `@RefreshScope` bean target caches.

A test should:
1. Start Config Server with revision A.
2. Start the client and confirm beans read value A.
3. Update remote config to revision B.
4. Cut connectivity to Config Server.
5. Call the refresh endpoint.
6. Record responses, exceptions, `Environment`, and bean behavior.
7. Restore Config Server.
8. Trigger refresh again.
9. Verify beans and properties reflect revision B.

Do not conclude success solely from the endpoint's HTTP response. Invoke consuming beans or inspect properties to confirm values actually took effect.

### 7.4. Rebinding and RefreshScope Have Different Semantics

`EnvironmentChangeEvent` can rebind `@ConfigurationProperties`. `@RefreshScope` uses proxies and target caches; refreshing invalidates the cache so beans recreate on next access.

In outage tests, separately observe:
- Non-refreshing singleton beans.
- Rebound `@ConfigurationProperties` beans.
- Recreated `@RefreshScope` beans.
- Non-refreshable beans or beans listed in `never-refreshable`.
- Constructor-bound configuration properties, including Java records, which do not refresh via the same mechanism.

A refresh event does not mean every object in the `ApplicationContext` is replaced.

### 7.5. Testing Deleted Configuration Keys

When a remote property is removed and refreshed, property presence does not necessarily update the same way as a value change. Spring Cloud Context notes that removing a configuration value and refreshing does not automatically update key presence in all cases.

Test separately:
- Changing value A to B.
- Removing a key from remote config.
- Setting a key to empty or null if supported by the source.
- Refreshing and inspecting consumers.

If logic depends on key absence, design explicit semantics and test against your active version.

## 8. Verifying Spring Cloud Bus During Broker Outages

### 8.1. Bus Introduces Another Dependency

`/actuator/busrefresh` and `/actuator/busenv` use Spring Cloud Bus to propagate changes across instances. Beyond Config Server, this flow depends on a broker and binder (such as RabbitMQ or Kafka).

Therefore isolate:
- Config Server down.
- Message broker down.
- Client disconnected from broker.
- Single instance temporarily disconnected from broker.
- Message dispatched, not yet consumed.
- Consumer received message, yet refresh failed.

### 8.2. Verifying Each Stage

| Stage | Required Evidence |
| --- | --- |
| Admin sends command | Request authenticated and accepted. |
| Bus publish | Producer publishes message per binder contract. |
| Broker receives message | Broker accepts/persists message as configured. |
| Instance consumes | Consumer receives event with correlation ID. |
| Instance refreshes | Instance `Environment`/beans reflect new config revision. |
| Entire rollout | Target instances report applied or failure state. |

An HTTP 2xx response from the bus endpoint does not prove all instances applied the configuration. Track events and revisions per instance.

### 8.3. Broker Outage Scenario

1. Start the broker and multiple service instances.
2. Trigger a normal bus refresh to establish a baseline.
3. Disconnect the broker.
4. Send a bus refresh command.
5. Verify the command fails or reports binder-appropriate status.
6. Restore the broker.
7. Verify consumers reconnect and channels/bindings recover.
8. Issue a fresh refresh or run reconciliation.
9. Verify all target instances applied the expected revision.

Do not assume messages sent while the broker was down will automatically replay upon recovery. That depends on producer retries, broker durability, consumer offsets/acks, and binder configuration.

## 9. Designing Fallbacks and Last-Known-Good Configuration

### 9.1. Classifying Configuration by Criticality

| Configuration Group | When Remote Source Fails | Recommended Policy |
| --- | --- | --- |
| Security-critical | Never use permissive defaults. | Fail startup or reject operations relying on it. |
| Connection-critical | Needed to reach DB/registry. | Fall back only to pre-approved endpoints. |
| Business-critical | Affects pricing, quotas, or routing. | Use verified revision or halt affected business operations. |
| Operational tuning | Safe local defaults possible. | Allow running with alerts and recorded config revision. |
| Optional feature | Can disable feature when config missing. | Bounded degradation with explicit status reporting. |

### 9.2. Recording Config Revisions

When loading configuration, capture non-sensitive revision metadata such as:
- Git commit/label.
- Config bundle version.
- Environment/profile.
- Last fetch timestamp.
- Config source.
- Last refresh outcome.

Never write secret values into logs or metrics. Revision metadata identifies which instances still run stale config during remote source or Bus outages.

### 9.3. Do Not Hide Fallback State

If an application runs on last-known-good config, expose:
- Active revision.
- Current unreachable status of config source.
- Timestamp of last successful fetch.
- Count of instances running stale revisions.
- Maximum allowed duration for running stale config.

Once that duration expires, transition readiness to refusing traffic or block sensitive operations. Never blindly report health UP just because the process is still running.

### 9.4. Never Auto-Fallback on Bad Credentials

Config Server returning 401/403 usually indicates authentication/authorization failures. Switching to another source or local defaults here can mask expired credentials or misconfigurations. Fail over to another endpoint only when policy defines it as an equivalent replica and credential rules are verified.

## 10. Failure Matrix Across Three Dependency Groups

| ID | Fault | Starting Point | Expected Behavior to Verify |
| --- | --- | --- | --- |
| N1 | DNS resolution failure | Before startup | Startup/retry/fail-fast per policy. |
| N2 | Registry port connection refused | Runtime | Finite request timeout, categorized logs/metrics. |
| N3 | High registry latency | Runtime | Deadlines, retry budget, pools unexhausted. |
| N4 | TCP connection cut | Runtime | Client errors cleanly and reconnects after recovery. |
| N5 | Upstream-only connection drop | Runtime | Client does not hang forever or duplicate side effects. |
| R1 | Registry down before startup | Startup | Registration/readiness per policy. |
| R2 | Registry down with warm cache | Runtime | Verify cache behavior within TTL. |
| R3 | Registry down after cache expires | Runtime | Verify supplier/provider behavior without instance list. |
| R4 | Registry returns empty list | Runtime | Caller handles no-instance clearly. |
| R5 | Dead instance still registered | Runtime | Detect stale instance and retry/fallback. |
| R6 | Registry recovers | Recovery | Instance list updates and requests normalize. |
| C1 | Config Server down, mandatory import | Startup | Startup fails within timeout/retry limits. |
| C2 | Config Server down, optional import | Startup | Startup proceeds only if local config is safe. |
| C3 | Slow Config Server | Startup | Read timeout and retry budget honored. |
| C4 | Config Server returns 401 | Startup | Auth error reported clearly, not disguised as network outage. |
| C5 | Config Server returns 500 | Startup | Verify failover/retry per policy. |
| C6 | Config Server down during refresh | Runtime | Old/new values and refresh errors clearly observed. |
| C7 | Config Server recovers | Recovery | Next refresh loads target revision. |
| B1 | Bus broker down | Runtime | Publish/consume failure detected. |
| B2 | Single consumer offline | Runtime | Verify delivery/reconciliation for that instance. |
| B3 | Bus recovers | Recovery | Instance reconnects and applies right revision. |

## 11. Measuring Resilience and Recovery

### 11.1. Metrics to Collect

| Metric | Meaning |
| --- | --- |
| Failure detection time | Time from fault onset until application detects it. |
| Recovery time | Time from dependency recovery until application resumes normal operation. |
| Retry attempts | Retries per operation. |
| Retry exhaustion | Operations exhausting retry budget. |
| Request error rate | Error ratio during and after outage. |
| Request latency | p50/p95/p99 when dependency is slow. |
| Connection pool saturation | Active/idle/pending connections and acquire timeouts. |
| Cache age | Age of active instance list/config revision. |
| Config revision lag | Revision skew across instances. |
| Registry registration lag | Time from startup until instance appears in registry. |

### 11.2. Retries Must Have a Budget

Retries boost success during brief glitches, but synchronized retries across hundreds of instances can create a retry storm right as a dependency recovers.

Verify:
- Exponential backoff.
- Jitter.
- Maximum attempts.
- Maximum elapsed time.
- Retrying only transient errors.
- Not retrying validation or authorization errors.
- Not retrying non-idempotent operations without an idempotency key.

For Config Client, use Spring Cloud Config's retry properties. For other service calls, verify client retry policies, Spring Cloud CircuitBreaker, or integrated resilience mechanisms.

### 11.3. Circuit Breakers and Bulkheads

If callers use a circuit breaker, test:
- Circuit opens after failure threshold.
- New requests fail fast or fall back.
- Circuit moves to HALF_OPEN after wait duration.
- Successful probes close the circuit.
- Failed probes keep the circuit OPEN.
- One failing dependency does not exhaust the application's entire thread/connection pool.

Bulkheads bound concurrent requests to a dependency. Verify queues do not grow unboundedly when dependencies slow down.

### 11.4. Testing Retry Amplification

For example, if each request retries four times and 100 instances send 50 requests/second, the dependency can receive far more calls than original traffic. In tests, measure total requests reaching the registry/Config Server, not only caller-originated requests.

During dependency recovery, watch whether queued backlogs trigger a traffic spike.

## 12. Health, Readiness, and Liveness During Outages

### 12.1. Health Endpoints Do Not Define Traffic Policy Alone

Actuator displays health contributor statuses. Whether a downed dependency stops an instance from receiving traffic depends on health groups and orchestration policies.

Do not add every external dependency to every health group. Identify which dependencies are truly essential for accepting new requests.

### 12.2. Do Not Blindly Put Registry or Config Server in Liveness

Liveness should reflect whether the process can keep running. If the registry or Config Server drops briefly and liveness turns `DOWN`, Kubernetes can restart all instances and worsen the outage.

Readiness can include a dependency if lacking it prevents handling new requests. If the application has caches/fallbacks/circuit breakers and still serves traffic, excluding that dependency from readiness may be better.

### 12.3. Checking Health Groups

Spring Boot provides health groups:
- `/actuator/health/liveness`
- `/actuator/health/readiness`

You can configure the readiness group to include custom or existing contributors:

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,discoveryComposite
~~~

`discoveryComposite` here is an example contributor ID that must be verified against your application's actual response. If the ID differs, use the exact ID published by Actuator.

### 12.4. Checking Both Management Port and Application Port

If Actuator runs on a separate management port, health checks may pass while the main application port or connection pool is broken. On Kubernetes, consider exposing probe paths on the main server port and testing the exact connector serving live traffic.

## 13. Testing Config Client and Config Server Across Layers

### 13.1. Unit Tests for Policies

Use unit tests to verify:
- Transient vs. permanent error classification.
- Retry counts.
- Backoff calculations.
- Fallback decisions.
- Config revision validation.
- Rejecting configuration missing mandatory properties.

No real registry or Config Server needs to run for pure policy logic.

### 13.2. Integration Tests with a Real Config Server

Use containers or test servers to verify:
- Config Client fetches properties from Config Server.
- Application/profile/label match expectations.
- Server down before startup.
- Server slower than read timeout.
- Server recovers within retry attempts.
- Config revision updates and refreshes apply cleanly.

When using `spring.config.import`, tests should boot `SpringApplication` or a real application process/container. Plain `ApplicationContextRunner` does not fully simulate the Config Data bootstrap phase unless corresponding environment processing is configured.

### 13.3. Testing Wrong Profiles and Labels

Several errors get mistaken for network outages:
- Wrong `spring.application.name`.
- Wrong active profile.
- Nonexistent label/branch.
- Property source lacking expected keys.
- Config Server returning 404 because repo/label was not found.

Write dedicated tests for identity/label misconfigurations. Never retry an invalid label forever.

### 13.4. Testing Runtime Refresh

With `/actuator/refresh`, test all of:
- Config Server up.
- Config Server down.
- Config Server returning old config.
- Config Server returning new revision.
- Bean refresh succeeding.
- Bean refresh/rebind failing.
- Subsequent refresh after server recovery.

Inspect actual consuming beans, not just the endpoint's HTTP response.

## 14. Practice Test Scenario: Registry Outage and Recovery

### 14.1. Objective

Verify a service client handles registry disruption properly both while cache is warm and after cache expires; then verify requests recover when the registry returns.

### 14.2. Setup

- One test registry instance.
- One service with at least two registered instances.
- One client using Spring Cloud LoadBalancer.
- Toxiproxy between the client and registry.
- A downstream endpoint returning deterministic responses.
- Metrics/logs for requests, retries, and discovery.

### 14.3. Execution

1. Start the registry and provider instances.
2. Verify both instances appear in the registry.
3. Send requests via LoadBalancer to warm the instance list cache.
4. Cut connectivity between client and registry via Toxiproxy.
5. Send continuous requests briefly.
6. Record selected instances and request success rate.
7. Wait for the configured test cache TTL to expire.
8. Send more requests and record errors/no-instance/fallback behavior.
9. Restore registry connectivity.
10. Wait for the client to fetch fresh instance lists.
11. Send requests and verify successful responses.
12. Check cache age, retry counts, and recovery time.

### 14.4. PASS Criteria

- No requests hang indefinitely.
- Retries stay within budget.
- While cache is valid, behavior matches chosen policy.
- After cache expires while registry remains down, errors return within deadline.
- Once registry recovers, client retrieves fresh instance lists.
- No application restart required if policy mandates self-recovery.
- Logs/metrics clearly distinguish registry outages from downstream instance outages.

Do not enforce one universal outcome across all providers. Different `DiscoveryClient` implementations have different caches and semantics; expected results must match your actual provider and configuration.

## 15. Practice Test Scenario: Config Server Outage

### 15.1. Objective

Verify startup policy when Config Server is unreachable and verify applications load new revisions after the config source recovers.

### 15.2. Variants to Run

| Variant | Configuration | Expected Result |
| --- | --- | --- |
| A | `optional:configserver:` with complete local config | App starts, records remote source unavailable. |
| B | Mandatory `configserver:`, server down | App fails startup within timeout/retry budget. |
| C | Mandatory config import, server recovers within retry window | App starts once fetch succeeds. |
| D | Mandatory config import, server recovers after retry window | Startup fails; deployment retries per policy. |
| E | Server returns 401 | Auth error reported clearly, not disguised as network outage. |
| F | Server returns 404 due to wrong label | Resource/profile/label error reported. |
| G | Server slower than read timeout | Client times out per configuration. |
| H | Server recovers after app is running | Next refresh fetches new revision. |

### 15.3. PASS Criteria

- Optional and mandatory imports behave distinctly as designed.
- No dangerous defaults/secrets used when remote config is missing.
- Retries stop within budget.
- Connect/read timeouts are enforced.
- 401/404 errors are never misclassified as DNS errors.
- New config revision applies after recovery.
- Instances can be reconciled by revision after refresh.

## 16. Practice Test Scenario: Bus and Multi-Instance Refresh

### 16.1. Objective

Verify configuration changes propagate to target instances and un-updated instances are detected.

### 16.2. Execution

1. Start the broker and three service instances.
2. Verify each instance runs config revision A.
3. Update Config Server to revision B.
4. Trigger bus refresh.
5. Record dispatch ID/correlation ID.
6. Disconnect the broker or pause one consumer.
7. Observe which instances applied B and which remain on A.
8. Restore the broker/consumer.
9. Trigger refresh/reconciliation per policy.
10. Verify all target instances applied B or are flagged out-of-sync.

### 16.3. PASS Criteria

- Successfully dispatched messages are distinguishable from instance-applied state.
- Offline instances are never silently assumed updated.
- Consumers reconnect per policy.
- Reconciliation exists for instances that missed events.
- Final config revisions converge or emit clear drift alerts.

## 17. Observability and Diagnostics During Testing

### 17.1. Logs

Logs should capture:
- Dependency/service ID.
- Operation and request ID.
- Failure category: DNS, connect timeout, read timeout, HTTP status, TLS.
- Retry attempt and backoff.
- Config revision or registry cache age.
- Recovery outcome.

Never write passwords, tokens, private keys, or full configuration values into logs. Use reason codes and allowlisted metadata.

### 17.2. Metrics

Track:
- Request counts/error counts per dependency.
- Latency histograms.
- Retry counts.
- Circuit breaker states.
- Connection pool active/idle/pending counts.
- LoadBalancer selected instances and no-instance outcomes.
- Cache hits/misses/evictions if exposed by implementation.
- Config refresh successes/failures.
- Config revision lag across instances.

Never create high-cardinality metric tags such as request IDs, trace IDs, or full URLs.

### 17.3. Tracing

Traces show time spent in discovery lookups, Config Server requests, broker publish/consume, and downstream calls. During fault injection, compare normal traces against latency-injected traces to pinpoint added overhead.

Sampling may drop some traces; corroborate with metrics and logs. Never place secrets in baggage or span attributes.

### 17.4. Health and Condition Reports

Actuator health reflects current status. Condition evaluation reports help when discovery/config client beans fail to auto-configure as expected. However, health UP does not prove every service ID has instances or every config property is synced.

Read health alongside config revisions, registry status, and request behavior.

## 18. Safe Chaos Testing Procedure

1. Run locally or in CI first with isolated dependencies/containers.
2. Choose one service instance or single connection path as the initial blast radius.
3. Establish a baseline before injecting faults.
4. Keep fault durations short and bounded.
5. Set stop conditions: error rate, latency, queue depth, or resource usage thresholds.
6. Keep proxy/container restoration commands ready and verify connectivity returns.
7. Test one failure mode at a time before combining faults.
8. Record test inputs, toxic parameters, start/end timestamps, and results.
9. Re-run the exact scenario to verify repeatability.
10. Expand to staging/production only with approvals, monitoring, and rollback readiness.

Never run chaos tests against shared production registries, Config Servers, or brokers without blast-radius isolation. One network experiment can disrupt every service sharing that dependency.

## 19. Common Issues and Fixes

| Symptom | Possible Cause | Remediation |
| --- | --- | --- |
| Test unaffected when cutting proxy | Client still connects directly to dependency. | Verify URLs and full network path route through proxy. |
| Test timeouts last longer than expected | Unbounded connect/read timeouts or retry budgets. | Separate per-layer timeouts and compute total deadline. |
| Requests still succeed when registry is down | LoadBalancer uses still-valid cached instance list. | Test warm/cold cache and TTL explicitly. |
| Requests fail immediately when registry goes down | Cache empty, expired, or provider does not cache. | Inspect cache config and provider behavior. |
| Registry recovers yet client keeps failing | Connection pool holds stale sockets or cache unrefreshed. | Check reconnect logic, cache eviction, and fresh requests. |
| Health UP yet service not found | Health check only tests discovery API reachability, not specific service IDs. | Inspect service registrations and add targeted dependency checks if needed. |
| App boots yet misses critical properties | Optional config import or insufficient local fallback validation. | Classify required properties and fail startup when missing. |
| App fails startup even after Config Server recovers | Retry window elapsed or client not configured to retry. | Check fail-fast, retry dependencies, import URL params, and timeouts. |
| Config Server 401 retried like an outage | Retry/failover policy ignores auth errors. | Check credentials, multiple URI strategy, and status classification. |
| Refresh succeeds yet bean uses old value | Bean not in `RefreshScope`, not rebound, or consumer holds stale reference. | Inspect bean scope, config binding, and consumer lifecycle. |
| Some instances miss bus refresh | Offline consumer, broker delivery/ack issue, or misrouted event. | Track per-instance status and add reconciliation. |
| Readiness unchanged when dependency goes down | Contributor excluded from readiness group or policy does not require it. | Review health group and decide whether dependency is traffic-critical. |
| Kubernetes restarts all instances on registry failure | External dependency placed in liveness. | Remove external dependencies from liveness; evaluate readiness. |
| Flaky Toxiproxy tests | Fixed sleeps, unready containers, or connection reuse. | Use readiness checks, polling deadlines, and fresh connections after recovery. |
| Latency test fails to trigger read timeout | Injected latency shorter than read timeout. | Inject latency exceeding timeout and check upstream/downstream directions. |
| DNS failure not simulated | Toxiproxy acts on TCP only after hostname resolution. | Use a dedicated DNS server/container or resolver test. |
| Retries surge when dependency recovers | Synchronized retries across instances without jitter or budget. | Add backoff/jitter, cap concurrency, and track retry amplification. |
| Config revisions diverge across instances | Missed Bus messages or local refresh failures. | Track revision per instance and run reconciliation. |

## 20. Operational Principles

1. **Define expected behavior upfront.** Every failure scenario needs expected outcomes and PASS criteria.
2. **Distinguish startup from runtime.** Applications can handle the two phases differently.
3. **Separate network errors from HTTP errors.** 401, 404, and 500 are not the same class of outage.
4. **Bound timeouts and retries.** Every dependency call needs predictable deadlines.
5. **Test warm and cold caches.** Caches can mask outages temporarily.
6. **Never treat cache as infinite fallback.** Define TTLs and stale-data policies.
7. **Classify required vs. optional config.** Missing critical config must trigger clear action.
8. **Record config revisions.** Know which instances hold stale config.
9. **Test real refreshes.** Trigger refresh operations and verify consuming beans.
10. **Distinguish Bus dispatch from apply.** Track per-instance status.
11. **Never blindly put external dependencies in liveness.** Prevent restart storms.
12. **Measure recovery time.** Dependency recovery does not mean immediate application recovery.
13. **Use isolated fault injection.** Toxiproxy/test containers keep scenarios reproducible.
14. **Keep blast radius small.** Enforce time limits and stop conditions.
15. **Correlate logs, metrics, traces, and health together.** Never rely on a single signal.
16. **Verify against your release train.** Retry, bootstrap, cache, and health behaviors can vary across Spring Cloud/Spring Boot versions.

## 21. Completion Checklist

- [ ] Distinguish DNS, connection refused, connect timeout, read timeout, latency, and TCP interruption.
- [ ] Author failure scenarios with expected behavior, recovery, and evidence.
- [ ] Place Toxiproxy between clients and dependencies in integration tests.
- [ ] Simulate latency/jitter and bidirectional connection cuts.
- [ ] Restore the proxy and confirm clients open fresh connections.
- [ ] Test registry outages both before and after startup.
- [ ] Test LoadBalancer with warm cache, cold cache, and expired TTL.
- [ ] Distinguish registry outages, stale registrations, and service instance outages.
- [ ] Test startup with optional and mandatory Config Server imports.
- [ ] Test fail-fast, retries, backoff, connect timeout, and read timeout.
- [ ] Test Config Server 401, 404, 500, and network timeouts separately.
- [ ] Test refresh while Config Server is down and after it recovers.
- [ ] Verify `@ConfigurationProperties` and `@RefreshScope` consumers.
- [ ] Test Bus broker outages and individual instance consumers.
- [ ] Track config revisions across instances.
- [ ] Distinguish health, readiness, and liveness.
- [ ] Measure retry amplification, request latency, failure detection time, and recovery time.
- [ ] Define stop conditions, rollbacks, and blast radii for chaos tests.
- [ ] Ensure logs/metrics/traces suffice for diagnosis without leaking secrets.

**Official documentation to check against your project's versions:**

- [Spring Cloud Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html): Config Data import, optional/fail-fast, retries, timeouts, and multiple Config Server URLs.
- [Spring Cloud Config – Git Backend](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/git-backend.html): lazy clone, clone-on-start, local working copy, refresh rate, and behavior when Git remote is unreachable.
- [Spring Cloud Commons – Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): per-service-ID child contexts, caching, TTL, health-check supplier, and service instance selection.
- [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): `DiscoveryClient`, `ServiceRegistry`, auto-registration, and registry lifecycle.
- [Spring Cloud Context – Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): `EnvironmentChangeEvent`, rebinding, `RefreshScope`, and refresh endpoint.
- [Spring Cloud Bus – Bus Endpoints](https://docs.spring.io/spring-cloud-bus/reference/spring-cloud-bus/bus-endpoints.html): `busrefresh`, `busenv`, and multi-instance updates.
- [Spring Boot Actuator – Endpoints and Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): health groups, readiness/liveness, and checking external state.
- [Testcontainers for Java – Toxiproxy Module](https://java.testcontainers.org/modules/toxiproxy/): creating TCP proxies, latency/jitter, bandwidth restrictions, timeouts, and disconnections in tests.

Each release train may alter properties, retry semantics, or cache implementations. Use your project's Spring Boot/Spring Cloud BOM, run these scenarios against the exact dependency versions, and record real results before finalizing production operational policies.
