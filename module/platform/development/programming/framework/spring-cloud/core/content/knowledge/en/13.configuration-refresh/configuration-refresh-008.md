# Local Refresh and Limits of Propagating to Other Instances

In a Spring Cloud system running multiple replicas, updating configuration in one place does not mean every instance automatically receives the new values. Two distinct tasks must be coordinated: **local refresh** so an `ApplicationContext` reloads configuration and refreshes its own beans; and **signal propagation** so other instances know they also need to refresh.

Spring Cloud Context provides the refresh mechanism within a single application. Spring Cloud Bus can broadcast a refresh event through a message broker so multiple applications/instances receive the signal. The Bus does not turn multiple JVMs into a single shared `ApplicationContext`, nor does it provide an atomic cluster-wide configuration update transaction. Each instance still executes its local refresh step according to its own lifecycle.

This lesson belongs to the **Configuration Refresh** chapter of the **SPRING_CLOUD_CORE** module. Learners explore core Spring Cloud abstractions, externalized configuration, refresh scope, discovery, and how to test/operate when configuration must change across multiple instances.

## 1. Learning Objectives

After this lesson, learners will be able to:

1. Distinguish updating `Environment`, refreshing beans in a single context, and broadcasting refresh to multiple instances.
2. Describe the local refresh flow with `ContextRefresher`, `EnvironmentChangeEvent`, and `RefreshScope`.
3. Trigger a local refresh via Actuator and identify which beans get rebound or recreated.
4. Explain the role of Spring Cloud Bus, message brokers, and remote refresh events.
5. Distinguish a refresh event from configuration content; understand why each instance must re-read its configuration source.
6. Configure bus refresh scoped cluster-wide or to a specific group of instances.
7. Understand the role of Spring Cloud Config Monitor when receiving webhooks from configuration management systems.
8. Design post-refresh verification, handling offline instances, broker failures, and uneven update states.
9. Secure management endpoints and avoid putting secrets into events or logs.
10. Write tests for local refresh and integration tests for multi-instance flows.

## 2. Three Levels to Distinguish

### 2.1. Updating the Configuration Source

Values can be changed in a Git repository, Config Server, mounted file, environment variable, or custom configuration source. This is only a **change at the source**. A running application does not automatically know that source changed.

### 2.2. Local Refresh

An instance receives a refresh command and updates `Environment` in its `ApplicationContext`. Spring Cloud can publish `EnvironmentChangeEvent`, rebind eligible configuration beans, and clear the `RefreshScope` target cache.

Local refresh only affects the context handling the command. If an application has five replicas, calling `/actuator/refresh` on one replica does not automatically refresh the other four replicas.

### 2.3. Propagating the Refresh Signal

Spring Cloud Bus provides a mechanism to send events through a broker so multiple instances receive the same signal. Each instance receiving the event executes its own local refresh.

~~~mermaid
flowchart TD
    A[Config source changes] --> B[Refresh trigger]
    B --> C{Trigger scope}
    C -->|Local| D[Instance A]
    C -->|Distributed| E[Spring Cloud Bus]
    E --> F[Message broker]
    F --> G[Instance A]
    F --> H[Instance B]
    F --> I[Instance C]
    D --> J[Refresh Environment and beans in context]
    G --> J
    H --> K[Refresh Environment and beans in context B]
    I --> L[Refresh Environment and beans in context C]
~~~

The diagram shows the logical relationships. A Bus event does not transmit an `ApplicationContext` over the network; it delivers a message for matching applications to handle themselves.

| Level | Scope | Typical components | Result |
| --- | --- | --- | --- |
| Source update | Configuration repository or external file | Git, Config Server, secret/config store | Source holds new data |
| Local refresh | One `ApplicationContext` | Spring Cloud Context, `ContextRefresher`, `RefreshScope` | One instance reloads configuration and updates appropriate beans |
| Distributed refresh | Multiple routed instances | Spring Cloud Bus and broker | Multiple instances receive signal and then perform local refresh |

## 3. Local Refresh in Spring Cloud Context

### 3.1. What Does `ContextRefresher` Do?

In Spring Cloud Context, `ContextRefresher` coordinates updating an application's configuration environment. At a high level, the refresh process includes:

1. Re-fetching or refreshing property sources per the active configuration mechanism.
2. Comparing before and after property sets to identify changed keys.
3. Updating the context's `Environment`.
4. Publishing `EnvironmentChangeEvent` with the changed key set.
5. Refreshing targets in `RefreshScope`, so old targets are evicted from the cache and recreated when needed.

Internal details and how property sources reload depend on the Spring Cloud version, Config Data vs. bootstrap mode, and installed integrations. `ContextRefresher` does not automatically turn every file on disk into a hot-reloadable source.

### 3.2. `EnvironmentChangeEvent` and Rebinding

`EnvironmentChangeEvent` notifies that a set of properties in the Environment changed. Integrated components can listen to the event to update their state.

One common effect is rebinding eligible `@ConfigurationProperties` beans. Mutable beans can receive new values via the rebinding mechanism. However, not every object created from configuration updates automatically.

Example:

~~~java
@ConfigurationProperties(prefix = "partner.api")
public class PartnerApiProperties {
    private URI baseUrl;
    private Duration readTimeout = Duration.ofSeconds(2);

    public URI getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(URI baseUrl) {
        this.baseUrl = baseUrl;
    }

    public Duration getReadTimeout() {
        return readTimeout;
    }

    public void setReadTimeout(Duration readTimeout) {
        this.readTimeout = readTimeout;
    }
}
~~~

This bean can be rebound by Spring Cloud Context's mechanism. However, if an HTTP client read `baseUrl` and `readTimeout` in its constructor and stored them in private fields, that client does not change automatically alongside the properties bean. You need to design a refreshable client or an appropriate dynamic configuration reading mechanism.

### 3.3. `RefreshScope` Refreshes Targets

A bean that needs to be recreated when configuration changes can use `@RefreshScope`:

~~~java
@Component
@RefreshScope
public class PartnerClient {
    private final PartnerTransport transport;

    public PartnerClient(PartnerApiProperties properties) {
        this.transport = PartnerTransport.open(
                properties.getBaseUrl(),
                properties.getReadTimeout()
        );
    }

    public PartnerResponse send(PartnerRequest request) {
        return transport.send(request);
    }

    @PreDestroy
    public void close() {
        transport.close();
    }
}
~~~

When local refresh refreshes the scope, the old `PartnerClient` target is destroyed and the callback closing the transport is invoked. The scoped proxy remains held by consumers; the next call creates a new target from the current configuration.

`PartnerTransport` is an application example class. Real code must properly close resources owned by the target while ensuring asynchronous tasks no longer use the transport after it closes.

### 3.4. Refresh Does Not Mean Restart

| Behavior | Refresh | Restart |
| --- | --- | --- |
| JVM/process | Preserved | Creates new process or restarts process |
| `ApplicationContext` | Continues existing; some state/beans are updated or recreated | Context is typically recreated |
| `@RefreshScope` target | Can be evicted from cache and recreated | Recreated in the new context |
| Static state and out-of-scope threads | Usually remain alive | Can be recreated with the new process |
| Changes not supporting refresh | May retain old values | Has the opportunity to pick up new values at startup |
| Risk | Beans only partially updated, old state remains | Downtime or requires rolling restart |

Do not use refresh as a substitute for restart when changes must affect components that only read configuration at startup, special logging configurations, classpath, JVM flags, or resources that cannot be replaced safely.

## 4. Triggering Local Refresh via Actuator

When an application has Spring Boot Actuator and the appropriate Spring Cloud Context, the refresh endpoint can be enabled for runtime configuration management.

Example configuration:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,refresh
~~~

Send an HTTP POST to:

~~~http
POST /actuator/refresh
~~~

You can use curl:

~~~bash
curl -X POST http://localhost:8080/actuator/refresh
~~~

The endpoint returns the changed key set depending on the version and implementation in use. Read the result alongside application logs; an HTTP success response does not prove by itself that every new bean initialized and every dependency is working.

### 4.1. Prerequisites for the Endpoint to Work

- Actuator dependency present.
- Spring Cloud Context and appropriate refresh auto-configuration present.
- Endpoint exposed via management configuration.
- Security permits the caller to perform the operation.
- Application has configuration sources that can be updated or re-read.

Merely adding `refresh` to `management.endpoints.web.exposure.include` does not create the implementation if the required dependencies are absent from the classpath.

### 4.2. Securing Management Endpoints

Refresh can change the behavior of an instance serving requests. Do not expose this endpoint to end users or public networks.

You should:

- Use authentication and authorization.
- Restrict the management interface/port and network policies.
- Grant permission only to pipelines or operators authorized to change configuration.
- Audit who triggered the refresh, when, and in which environment.
- Do not log secrets or the entire Environment contents.
- Use an approval/rollout mechanism suited to the configuration's blast radius.

Even if the endpoint is exposed on an internal network, authentication and authorization are still required. "Internal" does not mean every workload is permitted to trigger a refresh.

## 5. Why Does Local Refresh Not Spread to Other Replicas?

Each replica typically runs in its own JVM and has its own `ApplicationContext`, `Environment`, bean cache, and resources.

Suppose `orders-service` has three instances:

~~~text
orders-service-1  -> JVM 1 -> ApplicationContext 1
orders-service-2  -> JVM 2 -> ApplicationContext 2
orders-service-3  -> JVM 3 -> ApplicationContext 3
~~~

Calling:

~~~http
POST http://orders-service-1/actuator/refresh
~~~

only instructs instance 1 to refresh its context. The other two instances do not receive this command simply because they share the same Config Server or the same service name.

Primary reasons:

- `ApplicationContext` is an in-memory object of a single process.
- Scoped proxies and target caches belong to that context's scope.
- `EnvironmentChangeEvent` is an internal Spring context event, not a message broker event automatically broadcast over the network.
- Config Server stores/serves configuration; it does not push signals to every client by default when Git changes.
- Service discovery helps locate instance addresses; it is not a refresh broadcast channel.

If you want all replicas to update, you need a propagation mechanism such as Spring Cloud Bus, rollout orchestration, or a dedicated coordination system.

## 6. How Does Spring Cloud Bus Propagate Refresh?

Spring Cloud Bus connects Spring Cloud applications to a message broker to publish and receive events across nodes. Common binders integrate with RabbitMQ or Kafka.

### 6.1. Overall Processing Flow

~~~mermaid
sequenceDiagram
    participant Operator as Operator / CI
    participant A as Instance A
    participant Broker as RabbitMQ / Kafka
    participant B as Instance B
    participant C as Instance C
    participant Config as Config Server

    Operator->>A: POST /actuator/busrefresh
    A->>Broker: Publish RefreshRemoteApplicationEvent
    Broker-->>A: Deliver event
    Broker-->>B: Deliver event
    Broker-->>C: Deliver event
    A->>Config: Load current configuration
    B->>Config: Load current configuration
    C->>Config: Load current configuration
    A->>A: Refresh local Environment and beans
    B->>B: Refresh local Environment and beans
    C->>C: Refresh local Environment and beans
~~~

Flow walkthrough:

1. An operator or pipeline calls the bus refresh endpoint on one instance.
2. That instance creates a remote refresh event.
3. Spring Cloud Bus sends the event through the binder to the broker.
4. Applications matching the routing scope receive the event.
5. Each application performs a local refresh.
6. Config Client or the corresponding integration fetches new configuration from that instance's source.
7. Beans are rebound or refreshed per local policy.

A Bus event is primarily a **signal requesting a refresh**. Do not assume the event carries entire configuration files or new secrets. Each instance needs access to the configuration source and must fetch the new data itself.

### 6.2. Dependencies for Bus

With Maven, example using the RabbitMQ binder:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-bus-amqp</artifactId>
</dependency>
~~~

With the Kafka binder:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-bus-kafka</artifactId>
</dependency>
~~~

Artifact names and compatibility must be checked against your Spring Cloud release train. Manage versions via the `spring-cloud-dependencies` BOM compatible with Spring Boot; do not mix Bus, Stream binder, and Boot versions manually.

### 6.3. Broker Configuration

RabbitMQ example:

~~~yaml
spring:
  rabbitmq:
    host: rabbitmq.internal
    port: 5672
    username: ${RABBITMQ_USERNAME}
    password: ${RABBITMQ_PASSWORD}
~~~

Kafka example:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1.internal:9092,kafka-2.internal:9092
~~~

These are only minimal connection settings. Production requires TLS, authentication, publish/consume permissions, network policies, retry/backoff, and proper broker configuration. Never commit real credentials into the repository.

### 6.4. Exposing the busrefresh Endpoint

Example:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,busrefresh
~~~

Call:

~~~http
POST /actuator/busrefresh
~~~

In supported versions, you can route to a specific destination via the corresponding path, such as the endpoint with a destination segment after `/actuator/busrefresh/`. Pattern syntax and how `serviceId` and `bus id` match must be cross-checked against your release train documentation.

Do not expose this endpoint broadly. One call can cause many instances to destroy and recreate resources simultaneously, creating spikes on Config Server, databases, HTTP dependencies, or broker connections.

## 7. Cluster-Wide Refresh vs. Selective Refresh

Not every change requires refreshing all instances. Scopes can be distinguished:

| Scope | Example | How to handle |
| --- | --- | --- |
| Single instance | Testing new configuration on a canary | Local refresh or destination targeting one bus id |
| Single service | All replicas of `orders-service` | Bus destination by service ID/pattern |
| Multiple services | Shared configuration change | Bus refresh for the matching group or coordinated rollout |
| Cluster-wide | Platform config change affecting many apps | Broadly scoped event, monitor rollout and system load |

### 7.1. Destination and Instance Identifiers

The Bus needs application instance identifiers for routing and to avoid re-processing the sender's own event. Bus IDs are typically constructed from properties such as application name, profile, and instance/port details; exact configuration can vary by version.

Instances need unique IDs within the bus scope. If two nodes share the same identifier, routing and event deduplication/exclusion can behave incorrectly or make tracking difficult.

You can explicitly configure the bus ID when needed:

~~~yaml
spring:
  cloud:
    bus:
      id: ${spring.application.name}:${HOSTNAME:${random.value}}
~~~

The expression above is an illustrative example showing how to generate distinct IDs by host or random value; verify which placeholders are available in your environment and container deployment. Avoid using identical IDs across all replicas.

### 7.2. Choosing Destinations Carefully

Destination patterns help limit which applications receive the event. Before using a pattern, verify:

- The actual ID of each instance.
- Bus matching rules in your release train.
- How many nodes will receive the event.
- Whether the sender receives its own event back.
- How offline instances will handle it when they return.

Do not use broad wildcards if a change only concerns one service. Wide refreshes can cause many connection pools or clients to re-initialize together, creating load spikes on backends.

## 8. Config Server Monitor and Webhooks

When configuration is managed in Git or a repository system, pipelines can call a webhook after configuration changes. Spring Cloud Config Monitor supports receiving change notifications and working with Spring Cloud Bus to send refresh events to relevant applications.

Overall flow:

~~~mermaid
flowchart LR
    A[Git repository changed] --> B[Webhook]
    B --> C[Config Server Monitor]
    C --> D[RefreshRemoteApplicationEvent]
    D --> E[Message broker]
    E --> F[Config Client instances]
    F --> G[Fetch current config and refresh locally]
~~~

Components typically required:

- Spring Cloud Config Server.
- Compatible Config Monitor integration.
- Spring Cloud Bus on Config Server.
- Configured message broker.
- Config Clients needing refresh also connected to the Bus.
- Webhook configured on the Git provider or configuration management system.

The monitor endpoint is typically `/monitor` on Config Server. Payload format, mapping changed files to application names, and event routing depend on the webhook provider, version, and monitor configuration. Check Spring Cloud Config Monitor documentation rather than assuming all JSON webhooks share the same format.

### 8.1. Monitor Is Not a Polling Mechanism

Config Monitor receives notifications from webhooks; it does not continuously poll Git by default. If a webhook fails to arrive, is invalid, or Config Server cannot publish the event, clients may continue using old configuration.

Include an independent verification step after the update pipeline: inspect configuration revision/version, call health checks, or verify loaded values on instances.

### 8.2. Do Not Send Secrets in Webhooks

Webhooks should only provide information needed to identify which configuration changed. Do not include passwords, tokens, or secret contents in payloads without explicit requirements and strong protection mechanisms. Each client should retrieve data through Config Client/secret integrations with its own permissions.

## 9. Consistency Limits in Distributed Environments

### 9.1. No Cluster-Wide Atomic Refresh

When an event is published, instances may receive and process it at different times. For a period of time:

- Instance A already uses the new configuration.
- Instance B still uses the old configuration.
- Instance C is currently refreshing or recreating targets.
- Instance D is offline and has not received the event yet.

This is **eventual consistency**. Spring Cloud Bus does not provide a distributed transaction guaranteeing every instance switches configuration at the exact same instant.

If the business cannot tolerate two configuration versions running concurrently, use a coordinated rollout strategy, traffic draining, or restart/blue-green deployment instead of relying purely on bus refresh.

### 9.2. Event Delivery Does Not Mean Refresh Succeeded

You can distinguish these milestones:

1. Event published by sender.
2. Broker receives and stores/forwards event.
3. Instance receives event.
4. Instance begins refresh.
5. Instance successfully loads new configuration.
6. Beans are rebound or targets recreated.
7. Instance successfully serves requests using the new configuration.

A dashboard showing only that the message broker received the event does not prove steps 5–7 succeeded. You must observe from the instance side.

### 9.3. Offline Instances

If an instance is offline while an event is published, what happens when it comes back depends on the broker, consumer group/subscription, persistence, retention, and how the application subscribes to events. Do not assume every broker/binder retains a refresh event long enough for all offline nodes.

When an instance restarts, Config Client normally fetches the current configuration during startup per its configured mechanism. This is why startup verification and config revision tracking remain necessary even when using Bus.

### 9.4. Duplicate or Delayed Events

A distributed system can experience duplicate events, retries, or delayed processing. Refresh is generally designed as a repeatable operation, yet recreating resources still carries a cost.

- Avoid destruction callbacks that produce side effects unsafe to repeat.
- Ensure `close()` and new target initialization have clear error handling.
- Track event IDs, origins, and receive timestamps.
- Avoid triggering continuous refreshes for every tiny commit.
- Batch multiple changes into a single event publication when appropriate.

## 10. Controlled Configuration Change Management

### 10.1. Tagging Configuration with a Revision or Version

To verify instances have loaded the same configuration set, you can provide non-sensitive metadata such as:

~~~yaml
app:
  config:
    revision: "release-2026-11-18.3"
~~~

After refresh, each instance can expose its revision via a safe internal endpoint or metric. This shows which instances have updated, which are still old, and which failed.

Do not use hashes from which secrets could be inferred or log the entire configuration. A revision should only identify the configuration release, not contain secret contents.

### 10.2. Canary Before Cluster-Wide Refresh

A safer workflow for high-risk changes:

1. Update configuration at the source and assign a revision.
2. Select a canary instance or small group.
3. Refresh the canary.
4. Verify new values, health, error rates, and business behavior.
5. If satisfactory, broadcast refresh to the remaining group.
6. Verify revision and health on each instance.
7. If errors occur, halt rollout and execute a controlled configuration rollback.

Not every change needs a canary; simpler, well-tested changes can use a streamlined workflow. For timeouts, endpoints, credentials, or access policies, staged verification limits the blast radius.

### 10.3. Rollback Is Also a Configuration Change

When new configuration causes errors, rolling back the configuration source is not enough. Running instances may still retain the new values until they receive a refresh or restart. The rollback workflow needs to:

- Restore the previous revision at the source.
- Publish the appropriate refresh signal.
- Verify each instance has returned to the old revision.
- Verify resources were recreated and connections succeed.
- Monitor failed requests until the system stabilizes.

## 11. Configuration Types That Should Not Be Refreshed Casually

Some changes can be unsafe when altered directly at runtime:

| Configuration group | Risk | Strategy to consider |
| --- | --- | --- |
| HTTP client timeouts | Client may hold old constructor values | Refresh/recreate client or support dynamic configuration |
| Downstream endpoints | Old target must close, new target must connect | Canary, health probes, and rollback |
| Database URL/credentials | Current connection pool may not rebind safely | Pool replacement/drain or rolling restart |
| Thread/connection pool size | Changes can cause resource exhaustion or spikes | Bound limits, measure load, and roll out in batches |
| JVM flags, heap, GC | Cannot be changed via bean refresh | Restart with new startup configuration |
| Classpath/auto-configuration | Needs new dependencies or bean structure changes | Build and deploy new artifact |
| Secret rotation | Old client may still hold old credentials | Coordinate rotation, refresh, and verify access permissions |
| Feature flags | Can change business behavior immediately | Compatibility testing and phased user rollout |

HikariDataSource is an example commonly excluded from the default refreshable list in Spring Cloud. Do not treat `@RefreshScope` as a safe way to swap datasources; design a concrete pool lifecycle.

## 12. Testing Local Refresh and Distributed Refresh

### 12.1. Unit/Integration Tests for Local Refresh

A local test should verify:

- Environment receives new values.
- `EnvironmentChangeEvent` is published for changed keys when using the corresponding mechanism.
- `@ConfigurationProperties` beans update within their capabilities.
- Old `@RefreshScope` target is destroyed.
- New target is created on the next proxy access.
- Resource cleanup callbacks are invoked.

Example target logic test:

~~~java
@Test
void refreshRecreatesScopedTarget() {
    int oldId = partnerClient.id();

    assertThat(refreshScope.refresh("partnerClient")).isTrue();

    int newId = partnerClient.id();

    assertThat(newId).isNotEqualTo(oldId);
}
~~~

The test requires Spring Cloud Context, the `refresh` scope, and the bean injected via a scoped proxy. To prove destruction callbacks, use `created`/`destroyed` counters as shown in the Refresh Scope lifecycle lesson.

### 12.2. Integration Tests for Bus

Testing Bus requires at least two application instances and a real broker or suitable container/test environment.

Scenario:

1. Start two instances of the same service or two applications with distinct bus IDs.
2. Confirm both connected to the broker and have the initial configuration revision.
3. Update configuration in Config Server or test source.
4. Send bus refresh from one instance.
5. Wait for the event to reach the other instance.
6. Verify each instance loaded the new revision.
7. Confirm old targets closed and new targets are created upon access.
8. Test pausing an instance or disconnecting the broker to observe recovery capability.

Do not use fixed `Thread.sleep` as sole proof. Use polling with timeouts or synchronization conditions to wait until revisions/health reach expected values.

### 12.3. Testing Destination Scope

If using destination patterns, verify:

- Instances outside the scope do not refresh.
- All instances inside the scope receive the event.
- Unique IDs and service/profile mapping are correct.
- Events sent by the sender do not cause unintended duplicate processing.
- Patterns do not accidentally match another service.

### 12.4. Testing Failures and Rollback

Test at least:

| Scenario | What to verify |
| --- | --- |
| Config Server unreachable | Local refresh follows fail-fast/optional policy |
| Broker unavailable | Sender knows publish failed; instances are not assumed updated |
| Offline instance | Startup fetches latest config or compensating refresh plan exists |
| New target creation fails | Errors reflected in logs/health; instance not marked healthy just because event arrived |
| Slow close callback | Refresh duration is bounded and observable |
| Duplicate events | Cleanup and recreation do not leak resources |
| Bad revision | Rollout halts and rollback is verified |

## 13. Production Observability and Operations

Monitor signals across the pipeline, broker, and instances:

| Layer | Metrics/logs to observe |
| --- | --- |
| Config repository/Config Server | Revision, update timestamp, config fetch errors, requests by application/profile |
| Refresh trigger | Caller, destination, timestamp, HTTP outcome |
| Bus/broker | Publish/consume rates, queue lag, connections, retries, and delivery errors |
| Each instance | Current revision, events received, refresh duration, changed keys at a safe level |
| Beans/resources | Target creation/destruction, callback errors, connection pools, and client health |
| Application | Readiness, request error rate, p95/p99 latency, dependency failures |

Do not log entire configurations or secrets for debugging. Use revisions, source names, changed key counts, and correlation/event IDs for tracing.

### 13.1. Health Does Not Equal Configuration Synchronization

An instance can report health UP while still running an old revision if health checks do not inspect configuration. If revision synchronization is a business requirement, build a dedicated indicator and explicit readiness rules.

For example, an instance can be considered ready when:

- It has loaded at least the deployed target revision.
- Critical client targets initialized successfully.
- Required dependencies are reachable.
- No refresh is currently in progress.

Do not make readiness depend on an optional dependency if the application can still serve its core business functions.

### 13.2. Avoiding Refresh Storms

If multiple commits or webhooks fire consecutively, all instances may simultaneously destroy and recreate clients/pools. Consequences include:

- Config Server receives many concurrent requests.
- Broker experiences queue lag.
- Dependencies receive connection spikes.
- In-flight requests may encounter errors while targets/resources switch over.

Debounce or batch changes in the pipeline, rate-limit refreshes, roll out in batches, and apply jitter to verification/retry steps. Do not retry publishing infinitely when the broker is failing.

## 14. Security and Access Control

Refresh is an administrative operation impacting runtime behavior. Control both local and bus paths:

- Only authorized operators/pipelines may invoke `/actuator/refresh` or `/actuator/busrefresh`.
- Protect the Config Server Monitor endpoint and webhooks with secrets/signatures or platform authentication.
- Use dedicated broker credentials, least-privilege publish/consume permissions, and TLS.
- Separate bus destinations by environment so dev does not broadcast events to production.
- Do not put secrets in Bus events; events should only be signals.
- Audit who issued the command, target service/destination, and desired revision.
- Restrict permissions for rollback and cluster-wide refresh.
- Test endpoint and broker access permissions in the pipeline.

If multiple environments share a broker, isolate namespaces/vhosts/topics and credentials. Differing `spring.application.name` alone may not suffice to isolate events across environments.

## 15. Common Errors

| Symptom | Possible cause | How to resolve |
| --- | --- | --- |
| Calling `/actuator/refresh` changed only one replica | This is a local refresh | Use Bus or orchestrated rollout for remaining replicas |
| `/actuator/busrefresh` does not exist | Missing Bus starter, Actuator, or endpoint not exposed | Check dependencies and management configuration |
| Sender returned success, but other instances did not change | Wrong broker/binder or destination; instances not consuming | Check bus ID, broker connections, queue lag, and each node's logs |
| Event received, yet values stayed old | Config Client did not load new source or Config Server still serves old revision | Check Config Server, application/profile/label, and property sources |
| Some instances updated, others did not | Event did not arrive, instance offline, or local refresh failed | Track revisions per instance and run compensating refresh |
| Target refresh failed after receiving event | New configuration invalid or dependency unavailable | Check target initialization and health |
| Repeated refreshes slow the system down | Webhook/event storm or expensive callbacks | Debounce, rate-limit, and roll out in batches |
| Config Server Monitor does not publish events | Webhook wrong endpoint/payload or missing Bus integration | Check monitor dependency, webhook auth, and Config Server logs |
| Event went to wrong environment | Environments share bus destination | Isolate broker namespace/vhost/topic and credentials |
| Rolled back source, yet instances still use new config | Refresh not triggered or not verified on all instances | Publish rollback signal and verify revision on every node |

## 16. Distributed Refresh Deployment Workflow

A practical workflow for `orders-service` might look like this:

1. **Prepare:** check release train, Config Client, Bus binder, broker, endpoint security, and health checks.
2. **Update source:** commit new configuration and record the revision.
3. **Trigger:** have the pipeline invoke the Config Server Monitor webhook or call bus refresh with authorized credentials.
4. **Propagate:** Bus publishes the event to instances matching the destination.
5. **Local refresh:** each instance loads configuration, publishes internal events, rebinds, and refreshes eligible targets.
6. **Verify:** collect revision, health, target recreation, and request error rate per instance.
7. **Expand:** if the canary passes, proceed with remaining groups or complete rollout.
8. **Rollback:** on failure, restore the previous revision, publish a new refresh, and verify every node.

For breaking changes or strict synchronization needs, rolling deployment or blue-green deployment may be more appropriate than runtime refresh.

## 17. Applied Exercises

**Exercise 1 — Local or distributed?** A service has four replicas. An operator calls `POST /actuator/refresh` on one replica. Describe the configuration state of all four instances and propose a mechanism to update the remaining replicas.

**Exercise 2 — Bus flow.** Draw the flow from the Config Server Monitor webhook to the broker and three Config Clients. Mark which steps fetch configuration contents and which steps only emit signals.

**Exercise 3 — Configuring Bus.** Add the Bus AMQP or Kafka starter, configure the broker, and expose `busrefresh`. Confirm two instances have distinct bus IDs and receive events.

**Exercise 4 — Destinations.** Publish an event targeting one specific service. Prove that instances outside the destination do not refresh and instances within the destination receive the signal.

**Exercise 5 — Offline instance.** Shut down one replica before publishing an event, then start it again. Determine whether the broker retains events for offline consumers and why startup must fetch the latest revision.

**Exercise 6 — Event arrived, target failed.** Configure an invalid new endpoint, publish a bus refresh, and observe target creation. Design a health check so instances are not marked ready merely because the event was received.

**Exercise 7 — Canary and rollback.** Update Inventory's timeout or endpoint. Refresh one canary, measure error rate/latency, then roll out cluster-wide or roll back by revision.

**Exercise 8 — Security.** Verify permissions to invoke local refresh, bus refresh, Config Server Monitor, and broker publish/consume permissions. Prove an unauthorized workload cannot trigger a production refresh.

## 18. Key Takeaways and Reference Sources

- **Local refresh** only updates `Environment` and beans in the `ApplicationContext` handling the command.
- `EnvironmentChangeEvent` supports notifying changed keys and rebinding eligible configuration beans.
- `RefreshScope` evicts targets from cache; proxies stay in place and new targets are created on demand.
- **Spring Cloud Bus** propagates signals via a broker; each receiving instance must refresh locally.
- Bus events are not copies of an `ApplicationContext` and should not contain secrets or config payloads.
- **Config Server Monitor** can receive webhooks and combine with Bus to broadcast refresh signals; it does not poll Git by default.
- Distributed refresh provides eventual consistency; there is no cluster-wide atomic update.
- Offline instances, broker failures, duplicate events, or failed target initialization all require observability and recovery plans.
- Track revisions and health per instance; do not infer success solely from the sender's HTTP response.
- For changes not supporting refresh or requiring strict synchronization, consider rolling restart/blue-green deployment.

Official sources to cross-check against your project's Spring Boot/Spring Cloud versions:

1. [Spring Cloud Context – Refresh Scope and Context Refresh](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
2. [Spring Cloud Bus – Reference Guide](https://docs.spring.io/spring-cloud-bus/reference/)
3. [Spring Cloud Config – Client Side Usage and Config Data](https://docs.spring.io/spring-cloud-config/reference/client.html)
4. [Spring Cloud Config – Monitor](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/monitor.html)
5. [Spring Boot Actuator – Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
6. [Spring Cloud – Release trains and Spring Boot compatibility](https://spring.io/projects/spring-cloud/)
