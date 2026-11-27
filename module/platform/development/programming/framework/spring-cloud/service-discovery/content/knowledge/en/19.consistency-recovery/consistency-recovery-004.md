# Cold Start When the Registry Is Unreachable

## Objectives

After this lesson, you will be able to:

- Distinguish between application startup, instance registration, and readiness to receive traffic.
- Choose a fail-fast or start-degraded policy when the registry is unreachable.
- Configure bounded retries, backoff, and timeouts for each registry.
- Understand differences among Eureka, Consul, ZooKeeper, and Kubernetes discovery during startup.
- Handle the special case where the registry also serves as a remote configuration source.
- Avoid restart storms, duplicate registrations, and advertising instances before they are ready.
- Test startup behavior when the registry is down, recovering, and disconnecting again.

## 1. Registry Unavailable at Application Startup

A microservice can start its JVM and Spring ApplicationContext cleanly yet still fail to register with the service registry. That does not necessarily mean the application has completely failed. The right behavior depends on whether the registry is a mandatory prerequisite for the application to perform its business function.

For example, inventory-service can open its HTTP server and serve management endpoints while Eureka is down. However, if consumers only locate inventory-service via Eureka, the unregistered instance will not be discovered. The application is running, yet cannot participate in the discovery system.

Distinguish three milestones:

| Milestone | Meaning | What to verify |
| --- | --- | --- |
| Process started | JVM and Spring Boot initialized enough for the process to stay up. | Context, server, and core beans have started. |
| Registered | Registry accepted the registration per the client contract. | Registered instance, service ID, host, port, and metadata. |
| Ready to serve | Instance can accept new requests per the service contract. | Mandatory dependencies, warm-up, and routing are ready. |

A successful registration also does not guarantee every consumer sees the instance immediately. Caching, replication, and refresh cycles can introduce latency. Therefore, if the system must confirm the instance appears in the registry view, verify visibility separately instead of relying solely on the register call not throwing an exception.

## 2. Identify What Role the Registry Plays

Before choosing retry or fail-fast, determine how deeply the application depends on the registry:

1. **Service discovery only:** the application needs the registry to register itself or locate other services.
2. **Registry as a configuration source:** the application loads mandatory config from Consul KV, ZooKeeper Config, Spring Cloud Config, or Kubernetes ConfigMap/Secret.
3. **Kubernetes native DNS:** the application calls Kubernetes Services via DNS and does not need to self-register instances via Spring Cloud DiscoveryClient.
4. **Fallback path available:** the application can use DNS, static endpoints, a validated cache, or a restricted business mode while the registry is temporarily down.

In particular, remote configuration loading failures can occur before service discovery is initialized. For instance, Consul Config or Spring Cloud Config can halt ApplicationContext startup during property source loading. In that case, discovery registration retry settings will not resolve a bootstrap config failure.

## 3. Choosing Between Two Startup Policies

### Policy A: fail-fast

Use when the registry is strictly required for the application to operate safely.

Examples:

- An API gateway needs instance lists to route all incoming requests.
- A worker cannot process jobs if it cannot find its coordinator or mandatory services.
- The application must register with the registry before being allowed to participate in the system.
- Mandatory configuration must be loaded from the registry and no safe local copy exists.

Workflow:

1. Initialize the application and local dependencies.
2. Attempt to connect to the registry.
3. Retry within a bounded time budget.
4. If registration or mandatory lookup still fails, abort startup with a clear error.
5. The orchestrator can restart the instance according to its restart policy.

The upside is preventing a half-ready instance from entering the system. The downside is that during prolonged registry outages, many pods may repeatedly start and exit. Bounded retries, backoff, and monitoring are essential to avoid adding extra load onto an already struggling registry.

### Policy B: start-degraded

Use when the application can still start safely without the registry immediately available.

Examples:

- Health and management endpoints still function.
- The application can serve a subset of requests via Kubernetes Service DNS.
- The application holds a valid cache or verified local configuration.
- The registry is only needed to advertise the instance to consumers; internal initialization does not depend on the registry.

Workflow:

1. Start the process and HTTP server.
2. Attempt to connect and register with the registry.
3. If the registry is not ready yet, record a degraded state.
4. Keep readiness at REFUSING_TRAFFIC if consumers cannot yet safely route to the instance.
5. Retry registration in the background with backoff and jitter.
6. Once registration succeeds, verify metadata/visibility before flipping readiness to ACCEPTING_TRAFFIC.

Start-degraded does not mean accepting traffic as soon as the HTTP port opens. Switch to ready only when the instance can genuinely serve per its service contract.

### Decision Matrix

| Condition | Recommended policy |
| --- | --- |
| Cannot serve any business requests if registry is missing | Fail-fast after bounded retries, or stay unready within a bounded wait. |
| Can serve via a tested fallback path | Start-degraded and advertise readiness according to actual capability. |
| Registry is only used for inbound discovery | Allow process startup while keeping readiness false until registration completes. |
| Remote config is mandatory with no fallback | Fail-fast during the config bootstrap phase. |
| Remote config has an approved, safe local fallback | Allow continuing with fallback, logging config version and degraded status clearly. |

Do not pick a policy solely to shorten startup time. Evaluate the consequences if consumers call an unregistered instance or run with stale configuration.

## 4. Startup and Registration Lifecycle

A typical startup sequence:

~~~~mermaid
flowchart TD
    A[Process starts] --> B[Load local configuration]
    B --> C[Initialize Spring context]
    C --> D[Start embedded server]
    D --> E[Connect to registry]
    E --> F{Registry reachable?}
    F -- Yes --> G[Register service instance]
    F -- No --> H{Startup policy?}
    H -- Fail-fast --> I[Retry with bounded backoff]
    I --> J{Retry budget exhausted?}
    J -- No --> E
    J -- Yes --> K[Fail startup]
    H -- Start-degraded --> L[Mark registry unavailable]
    L --> M[Keep readiness REFUSING_TRAFFIC]
    M --> N[Retry in background]
    N --> O{Registration succeeds?}
    O -- No --> N
    O -- Yes --> P[Verify registration and dependencies]
    G --> P
    P --> Q[Readiness ACCEPTING_TRAFFIC]
~~~~

Specific steps depend on the implementation. Eureka can initialize the client and continue refreshing/replicating on a scheduler; Consul has a registration retry mechanism; Curator connects to ZooKeeper following a session lifecycle; Kubernetes discovery can read Services/Endpoints via the API or rely on native Service DNS.

## 5. Retries Must Be Bounded and Use Backoff

Retries help overcome transient failures such as a registry restart, unready network routes, or unpropagated DNS. Unbounded continuous retries can worsen an incident.

A retry policy should define:

- **Initial delay:** wait duration before the first retry.
- **Multiplier:** factor increasing the wait between attempts.
- **Maximum delay:** upper cap on wait duration.
- **Maximum attempts or deadline:** max retry count or total time budget.
- **Jitter:** random offset so multiple instances do not retry at the exact same instant.
- **Per-call timeout:** time limit for a single connect/register request.
- **Error classification:** retry only recoverable errors.

Backoff example:

~~~~text
Attempt 1: call immediately
Attempt 2: wait roughly 1 second
Attempt 3: wait roughly 2 seconds
Attempt 4: wait roughly 4 seconds
Subsequent attempts: keep increasing without exceeding max interval
~~~~

Values are examples, not universal defaults for every registry. Total startup budget must account for both per-request timeouts and backoff durations. If each call can hang for tens of seconds, six retries can still stretch startup dramatically.

### Which Errors Should Be Retried?

| Error | Suggested action |
| --- | --- |
| Connection refused during registry restart | Retry with backoff. |
| Transient DNS lookup failure | Retry; check resolver and service name. |
| HTTP 503 or server failing over | Bounded retry. |
| Timeout from flaky network | Retry with sensible timeout. |
| HTTP 401/403 or ZooKeeper NOAUTH | Stop tight retries; fix credentials/ACLs. |
| Wrong hostname, port, or fixed path | Report configuration error; do not retry indefinitely. |
| Expired TLS certificate or broken trust chain | Fix certificate/truststore; retrying will not self-heal. |
| Wrong service ID or namespace | Fix configuration or permissions; do not treat as transient outage. |

Do not catch all exceptions and retry them identically. For configuration and authentication failures, retries only delay error detection.

## 6. Spring Cloud Consul

Spring Cloud Consul uses the Consul Agent HTTP API to register and discover services. If the agent is not ready yet at startup, Spring Cloud Consul provides retry support.

Current Spring Cloud Consul documentation describes a default retry of six attempts, 1,000 ms initial interval, and 1.1 multiplier. To enable this mechanism, the classpath requires Spring Retry and the AOP/AspectJ starter matching your version branch. Spring Cloud Consul 5.0.x currently points to spring-boot-starter-aspectj; 4.3.x documentation uses spring-boot-starter-aop. Check your project's release train documentation before adding dependencies.

Configuration example:

~~~~yaml
spring:
  cloud:
    consul:
      host: consul-agent.internal
      port: 8500
      discovery:
        enabled: true
        register: true
        fail-fast: false
      retry:
        enabled: true
        initial-interval: 1000
        max-attempts: 6
        max-interval: 2000
        multiplier: 1.1
~~~~

Key properties:

- spring.cloud.consul.discovery.register: enables/disables automatic service registration.
- spring.cloud.consul.discovery.fail-fast: if true, registration errors can fail startup; current default is true. If false, errors log a warning and startup can proceed.
- spring.cloud.consul.retry.enabled: enables retry; current default is true.
- spring.cloud.consul.retry.max-attempts: total attempts, including the initial call per Spring Retry.
- spring.cloud.consul.retry.initial-interval, max-interval, multiplier: control backoff.

Distinguish spring.cloud.consul.discovery.fail-fast from spring.cloud.consul.config.fail-fast. The first applies to discovery registration; the second applies to loading configuration from Consul KV. An application can permit discovery registration to fail while still failing startup because mandatory configuration could not load.

To customize retries completely, declare a RetryOperationsInterceptor bean named consulRetryInterceptor. Avoid stacking an extra retry wrapper on top of built-in retries without calculating total actual attempts, because nested retry layers can multiply request volume.

## 7. Spring Cloud Netflix Eureka

Eureka Client registers automatically when spring-cloud-starter-netflix-eureka-client is present and an appropriate service URL is configured. The client can also fetch the registry to discover other services.

Configuration example:

~~~~yaml
eureka:
  client:
    service-url:
      defaultZone: https://eureka-a.internal/eureka/,https://eureka-b.internal/eureka/
    register-with-eureka: true
    fetch-registry: true
    should-enforce-registration-at-init: false
~~~~

Three distinct properties:

- register-with-eureka: whether the client registers its own instance details.
- fetch-registry: whether the client fetches the registry to discover other instances.
- should-enforce-registration-at-init: whether initial registration must succeed during Eureka Client initialization.

According to current config properties, should-enforce-registration-at-init defaults to false. When set to true, Eureka Client throws an exception if the initial registration to the server fails; when false, the application is not forced to stop just because initial registration failed. Subsequent retry/heartbeat and refresh behavior depends on the Eureka Client version.

Fail-fast selection example:

~~~~yaml
eureka:
  client:
    should-enforce-registration-at-init: true
~~~~

Enable this only when registration is strictly required for the instance to be allowed to run. If the application can start degraded, leave it false and use readiness to withhold traffic until registration succeeds.

Do not set fetch-registry: false just to bypass registration errors if the application still needs to discover other services. Self-registration and fetching the registry are two independent behaviors.

Eureka also supports backup-registry-impl to provide fallback registry data during initial startup for applications needing an initial service list. This is a fallback for initial discovery data, not a replacement for self-registration and not a synchronized replica of Eureka Server.

If the client uses multiple Eureka Server URLs, verify each URL, DNS, TLS, authentication, and failover behavior. Configuring multiple URLs does not guarantee peers are in sync or that the client can reach all peers.

## 8. Spring Cloud Zookeeper

Spring Cloud Zookeeper uses Apache Curator to connect to the ensemble and handle registration/discovery. Registration is enabled by default via spring.cloud.zookeeper.discovery.register.

Connection and retry properties:

~~~~yaml
spring:
  cloud:
    zookeeper:
      connect-string: zk-1.internal:2181,zk-2.internal:2181,zk-3.internal:2181
      connection-timeout: 10000
      session-timeout: 30000
      base-sleep-time-ms: 50
      max-retries: 10
      max-sleep-ms: 500
      block-until-connected-wait: 10
      block-until-connected-unit: seconds
      discovery:
        enabled: true
        register: true
~~~~

Meaning:

- connect-string: list of ensemble members the client can connect to.
- connection-timeout: time limit for establishing a connection.
- session-timeout: configured/negotiated session timeout.
- base-sleep-time-ms, max-retries, max-sleep-ms: Curator retry policy parameters.
- block-until-connected-wait and block-until-connected-unit: initial connection wait time per Spring Cloud Zookeeper configuration; 4.3.x docs state a default of 10 seconds.

Tune illustrative values according to network latency and the ensemble's session timeout. An initial wait limit does not mean the client retries forever or that a session is guaranteed to be established.

If the app also uses ZooKeeper as a Config Server, spring.cloud.zookeeper.config.fail-fast governs configuration loading failures. The default in current docs is true. This is config lookup behavior and should not be confused with Curator creating connections or ServiceRegistry registering ephemeral znodes.

Once connected after a disruption, verify whether the session is still valid or expired. If the old session was lost, the old ephemeral registration znode is deleted; the client must open a new session and re-register. Do not manually create a second CuratorFramework to re-register if Spring Cloud already manages the client and lifecycle.

## 9. Spring Cloud Kubernetes and Kubernetes Service DNS

There are two ways to use Kubernetes for service lookup:

### Kubernetes Service DNS

If the application simply calls a Kubernetes Service via DNS, such as inventory.commerce.svc.cluster.local, there is no need to initialize Spring Cloud DiscoveryClient just to register the instance. Kubernetes manages Services and EndpointSlices based on Pod labels, selectors, and readiness.

In this setup:

- The Pod is created and the application starts.
- The readiness probe decides whether the Pod qualifies to receive traffic through the Service.
- Kubernetes updates EndpointSlices as Pod status changes.
- DNS provides a stable Service name to callers.

If the Kubernetes API server is temporarily unreachable, some data-plane requests via Service/DNS can keep working using previously configured state. However, Pod/Service/EndpointSlice changes and new endpoint updates can be delayed.

### Spring Cloud Kubernetes DiscoveryClient

When using Fabric8 or the Kubernetes Java Client, the application queries the Kubernetes API for Services, Endpoints, or EndpointSlices. Check:

- Are the ServiceAccount token and CA certificate mounted properly?
- Does the Role/ClusterRole have get/list/watch permissions on the needed resources?
- Is the discovery namespace correct?
- Do the API server URL and network policies permit connectivity?
- Does the EndpointSlices API exist and is it supported by the cluster if use-endpoint-slices is enabled?

Example enabling EndpointSlices:

~~~~yaml
spring:
  cloud:
    kubernetes:
      discovery:
        use-endpoint-slices: true
~~~~

If the cluster does not support the EndpointSlices API while the application enables this feature, Spring Cloud Kubernetes docs warn that the application may fail immediately during startup. This configuration also requires RBAC for the endpointslices resource in the discovery.k8s.io API group.

Do not confuse spring.cloud.kubernetes.config.fail-fast with DiscoveryClient. Config fail-fast controls loading ConfigMaps; it is not a master switch for Kubernetes API discovery connections.

## 10. Remote Configuration Can Halt Startup Before Discovery

Sometimes a registry serves as both the service discovery source and the configuration source. Identify which stage is failing.

| Component | Behavior when unreachable | Related properties |
| --- | --- | --- |
| Spring Cloud Config Client | Can fail startup if import is mandatory or fail-fast is enabled. | spring.cloud.config.fail-fast, spring.config.import. |
| Consul Config | Can throw an exception when config fails to load. | spring.cloud.consul.config.fail-fast, current default true. |
| Consul Discovery registration | Can throw an exception when registration fails or log a warning to continue. | spring.cloud.consul.discovery.fail-fast. |
| ZooKeeper Config | Can fail startup when config lookup fails. | spring.cloud.zookeeper.config.fail-fast. |
| Kubernetes ConfigMap/Secret | Can proceed with a warning or fail per configuration. | spring.cloud.kubernetes.config.fail-fast, spring.cloud.kubernetes.secrets.fail-fast. |

With Spring Cloud Config using spring.config.import, the optional: prefix allows the application to proceed when Config Server is unavailable, whereas a mandatory import can fail startup. If remote config contains mandatory credentials, URLs, or feature flags, do not casually mark it optional.

A safe fallback config needs a clear version, origin, and expiration limit. Do not automatically reuse old config indefinitely if it might point to revoked endpoints or expired credentials.

## 11. Keeping Readiness Accurate in Degraded Mode

When the registry is unreachable, avoid using liveness probes to force continuous container restarts. Liveness should reflect whether the process is internally broken; a registry outage is an external dependency state.

A common design:

- The process starts and liveness stays healthy.
- Readiness stays at REFUSING_TRAFFIC while the service is not yet advertised or cannot reach mandatory dependencies.
- Retry registration in the background with backoff.
- Once registration succeeds and business prerequisites are met, flip readiness to ACCEPTING_TRAFFIC.
- If retries exceed the deadline and the registry is mandatory, terminate startup or emit alerts per chosen policy.

In Spring Boot, you can publish an AvailabilityChangeEvent to change ReadinessState:

~~~~java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;
import org.springframework.stereotype.Component;

@Component
public class StartupReadiness {

    private final ApplicationContext context;

    public StartupReadiness(ApplicationContext context) {
        this.context = context;
    }

    public void refuseTraffic() {
        AvailabilityChangeEvent.publish(
                context,
                ReadinessState.REFUSING_TRAFFIC
        );
    }

    public void acceptTraffic() {
        AvailabilityChangeEvent.publish(
                context,
                ReadinessState.ACCEPTING_TRAFFIC
        );
    }
}
~~~~

This is only the mechanism to change readiness. It does not register the service in the registry by itself. Connect these two methods to the lifecycle/registration outcome of your specific implementation, or use framework-supported readiness probes and health integrations.

Do not call acceptTraffic() merely because a TCP connection to the registry opened. Verify successful registration, accurate instance metadata, and readiness of mandatory dependencies.

## 12. Avoiding Duplicate Registrations During Retries

When the registry recovers, multiple callbacks or retry layers might simultaneously attempt to register the instance. This easily creates duplicate records or overwrites another replica's registration.

Guidelines:

- Use a unique instance ID per process/replica.
- Keep the instance ID stable across a process's lifecycle.
- Distinguish retrying one logical registration from creating a brand-new registration.
- Rely on idempotent registry/client mechanisms whenever possible.
- Do not call ServiceRegistry.register() from every reconnect event if the framework already manages re-registration.
- While retries fail, keep readiness false until registration is verified.
- On shutdown, deregister if the registry is still reachable; otherwise rely on technology-specific lease/heartbeat/session cleanup.

With ZooKeeper, ephemeral nodes are tied to sessions. With Consul, registrations have a service ID and health check/TTL. With Eureka, instance ID and lease renewals let the server track the instance. Because cleanup mechanisms differ, retry logic must match the exact implementation.

## 13. Timeouts and Startup Budgets

Define timeouts layer by layer:

| Layer | Limit to define |
| --- | --- |
| DNS | Time to resolve the registry hostname. |
| TCP connect | Time to open a socket to the registry. |
| TLS handshake | Time to establish the TLS channel and validate certificates. |
| Registry request | Wait time for register/lookup responses. |
| Retry backoff | Total wait time between attempts. |
| Startup deadline | Total budget from process start until failure or degraded transition. |
| Readiness | Conditions and maximum duration an instance may stay unready. |

Never set a per-request timeout much larger than the startup deadline. For example, if startup is allowed to wait only 30 seconds while a single connect timeout is 3 minutes, the retry policy cannot honor its budget.

A simple calculation:

~~~~text
Startup wait budget
= sum of request timeouts
+ sum of backoff delays
+ local initialization time
~~~~

This is a conservative sum; some operations may run concurrently. Measure actual startup behavior to pick deadlines.

## 14. Kubernetes Orchestration and Restart Storms

When running on Kubernetes, the three probes serve distinct roles:

- startupProbe: gives the application time for initial startup.
- livenessProbe: detects a process/container that cannot continue running.
- readinessProbe: decides whether the Pod receives traffic from a Service.

If the registry goes down, do not fail liveness by default. Otherwise all Pods may restart, reconnect simultaneously, and pile extra load onto the registry. That is a restart storm.

With start-degraded:

- The startup probe checks that the app finished local initialization.
- Liveness checks for internal failures.
- Readiness checks traffic-serving conditions, including registration if the service needs discovery to be called.
- The Pod stays alive while the registry is down and keeps retrying with backoff.

If the policy is fail-fast, the application should retry up to a deadline and exit with a non-zero exit code. Kubernetes will apply restart backoff. Configure rollouts and autoscaling so they do not spawn waves of new replicas while the registry remains down.

## 15. Diagnostic Procedure When Startup Fails

When an application fails to start because of the registry, check in order:

1. **Identify the phase:** did the error occur while loading remote config, creating DiscoveryClient, opening connections, or registering the instance?
2. **Read the root exception:** connection refused, timeout, DNS, TLS, 401/403, NOAUTH, or API resource not found?
3. **Inspect endpoints:** hostname, port, scheme, path, and namespace.
4. **Inspect authentication:** token, username/password, certificates, ACLs, and RBAC permissions.
5. **Inspect registry health:** server/agent/ensemble/quorum and leader state.
6. **Inspect retries:** attempt count, timeouts, backoff, jitter, and retry budget.
7. **Inspect registration:** service ID, instance ID, host, port, metadata, and health status.
8. **Inspect readiness:** has the instance entered routing or is it still REFUSING_TRAFFIC?
9. **Inspect cache/visibility:** do consumers already see the instance or are they reading a stale registry view?
10. **Inspect recovery:** when the registry returns, does the client retry/re-register automatically or require operational action?

### Common Errors

| Symptom | Possible cause | Remediation |
| --- | --- | --- |
| Consul agent unavailable fails startup | discovery.fail-fast=true and retries exhausted. | Check retry dependencies, fail-fast policy, and agent health. |
| Consul Config fails despite Discovery fail-fast false | config.fail-fast=true during property source loading. | Determine if config is mandatory; use a controlled fallback if permitted. |
| Eureka client fails initialization immediately | should-enforce-registration-at-init=true or severe config error. | Check service URLs, connectivity, and fail-fast policy. |
| Eureka app runs but is absent from registry | Initial registration failed and init is not enforced. | Check register/heartbeat logs, peer URLs, and retries. |
| ZooKeeper connection timeout | Ensemble lacks quorum, DNS/network issue, or timeout too short. | Check quorum, connection string, session, and retry policy. |
| ZooKeeper NOAUTH | Incorrect ACL or credentials. | Fix identity/ACL; do not keep retrying rapidly. |
| Kubernetes API returns 403 | ServiceAccount lacks get/list/watch permissions. | Grant least-privilege RBAC for the right namespace/resource. |
| Kubernetes EndpointSlice API not found | EndpointSlices enabled on an unsupported cluster. | Check discovery.k8s.io/v1 API or disable the setting if needed. |
| Pod Running but not Ready | Registration or mandatory dependency not ready yet. | Inspect readiness endpoint and registry visibility. |
| Many pods retry simultaneously | Missing jitter or nested retry policies. | Add jitter, cap concurrency, and remove duplicate retry wrappers. |

## 16. Testing Startup When the Registry Is Unavailable

Do not test only the happy path. Simulate these scenarios:

| Scenario | Expected outcome |
| --- | --- |
| Registry down before app starts, fail-fast enabled | Application retries within budget and exits with clear logs. |
| Registry down before app starts, start-degraded | Process starts, readiness is false, controlled retries continue. |
| Registry recovers after 20 seconds | Instance registers successfully and readiness turns true after verification. |
| Registry recovers but credentials are wrong | Retries are bounded; logs classify authentication failure and instance is not advertised. |
| Wrong registry DNS | Error is identified as DNS/configuration; no retry storm occurs. |
| Multiple replicas start concurrently | Jitter spreads requests; registry suffers no excessive retry burst. |
| Registry drops after app is already ready | App does not restart solely due to registry loss; cache and readiness follow policy. |
| Registry restarts during rolling deployment | Old and new instances do not register duplicates; consumers can fail over. |
| EndpointSlice API does not exist | Discovery client reports a clear startup error when the feature is enabled. |
| Config registry unavailable | Config fail-fast/optional policy is tested independently from discovery registration. |

A start-degraded test must verify all three states: process alive, readiness false, and registration created after registry recovery. Seeing `Started Application` in logs alone is insufficient.

## 17. Design Checklist

- [ ] Determined whether the registry is a mandatory or optional dependency.
- [ ] Separated remote configuration from service discovery.
- [ ] Selected fail-fast or start-degraded per the business contract.
- [ ] Bounded retry attempts and total startup deadline.
- [ ] Configured backoff, max interval, and jitter.
- [ ] Classified transient errors separately from config/auth errors.
- [ ] Verified retry behavior for the exact Spring Cloud version.
- [ ] Distinguished Consul Config fail-fast from Consul Discovery fail-fast.
- [ ] Checked Eureka's should-enforce-registration-at-init.
- [ ] Checked ZooKeeper Curator connection wait, session, and retry policies.
- [ ] Verified Kubernetes ServiceAccount, RBAC, namespace, and EndpointSlice API.
- [ ] Kept readiness false until the instance can safely receive traffic.
- [ ] Avoided using liveness probes to restart pods merely for temporary registry downtime.
- [ ] Ensured registration retries do not create duplicate instances.
- [ ] Tested registry down, recovery, bad credentials, and concurrent replica startups.
- [ ] Added logs, metrics, and alerts for registration failures, retry exhaustion, and registry wait duration.

## Key Takeaways

- Process started, registered, and ready are three distinct states.
- An unreachable registry does not always require the application to exit; the decision depends on whether the registry is mandatory for business functionality.
- Fail-fast suits cases where serving safely is impossible without the registry or remote config.
- Start-degraded must hold readiness false until registration and serving conditions are verified.
- Retries must enforce timeouts, attempt limits, backoff, and jitter.
- Consul provides registration retries; discovery fail-fast and config fail-fast are separate policies.
- Eureka provides should-enforce-registration-at-init, which currently defaults to false.
- ZooKeeper uses Curator sessions and retry policies; connection wait does not imply infinite retries.
- Kubernetes Service DNS differs from Spring Cloud Kubernetes DiscoveryClient calling the API server.
- Never use liveness to handle registry outages; doing so can trigger a restart storm.
- Always test registry recovery after an application has started in degraded mode.

## Official References

- [Spring Cloud Consul – Retry](https://docs.spring.io/spring-cloud-consul/reference/retry.html)
- [Spring Cloud Consul – Common Application Properties](https://docs.spring.io/spring-cloud-consul/reference/appendix.html)
- [Spring Cloud Consul – Service Discovery](https://docs.spring.io/spring-cloud-consul/reference/discovery.html)
- [Spring Cloud Netflix – Eureka Client](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Cloud Netflix – Configuration Properties](https://docs.spring.io/spring-cloud-netflix/reference/configprops.html)
- [Spring Cloud Zookeeper – Common Application Properties](https://docs.spring.io/spring-cloud-zookeeper/reference/appendix.html)
- [Apache Curator – Retry Policies](https://curator.apache.org/docs/retry-policy/)
- [Spring Cloud Kubernetes – DiscoveryClient](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html)
- [Spring Cloud Config – Client Fail Fast and Retry](https://docs.spring.io/spring-cloud-config/reference/client.html)
- [Spring Cloud Commons – DiscoveryClient](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Kubernetes – Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/)
