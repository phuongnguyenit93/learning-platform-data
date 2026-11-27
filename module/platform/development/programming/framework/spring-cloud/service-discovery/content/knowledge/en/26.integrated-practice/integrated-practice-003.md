# Measuring the Time from New Registration to Caller Visibility

A new instance may be accepted by the registry before the consumer sees it immediately. The registry must record the registration and potentially replicate it to other nodes/agents; the consumer's DiscoveryClient updates via fetch intervals, watches, or queries; and LoadBalancer may also keep the instance list in a cache. Therefore, the moment a provider reports registration complete is not the moment the caller can select the new instance.

This practice measures the time from when the registry acknowledges a new registration until the consumer sees the exact instance ID, and then additionally measures when a request via Spring Cloud LoadBalancer actually reaches that instance. The procedure applies to Eureka, Consul, and ZooKeeper.

## Objectives

After this practice, learners can create a new registration with a unique instance ID, record the registry acknowledgment timestamp, measure when the health check becomes passing if applicable, measure when DiscoveryClient returns the new instance, measure when LoadBalancer can invoke the new instance, separate the latency layers, and report median, p95, p99, along with margins of error.

You need one registry, one provider capable of spawning new instances, and one consumer using that registry's discovery client. You can run locally or with Docker Compose. If components run on multiple hosts, synchronize clocks before comparing timestamps.

## Timing Model and Measurement Milestones

| Milestone | Meaning | Where Recorded |
|---|---|---|
| T_req | Start sending registration request | Registrar/test harness |
| T_ack | Registry confirms receipt of registration | Registrar or registry API response |
| T_pass | Health check turns passing, if applicable | Consul/registry health API |
| T_seen | Consumer's DiscoveryClient first returns the exact instance ID | Consumer process |
| T_route | Request via LoadBalancer is first handled by the exact new instance ID | Provider response + consumer |
| T_done | Measurement ends or times out | Test harness |

Key intervals:

- Registration request latency = T_ack - T_req.
- Health readiness delay = T_pass - T_ack.
- Discovery propagation latency = T_seen - T_ack.
- End-to-end visibility latency = T_seen - T_req.
- Load-balanced reachability latency = T_route - T_ack.
- Latency from discovery to route = T_route - T_seen.

If the registry has no health check, omit T_pass. If the sole goal is determining when the consumer sees the instance, T_seen is the primary endpoint; T_route is an additional measurement.

Do not use process start time or ApplicationReadyEvent as T_ack. An application can start up before registration is sent. Also do not use the moment the dashboard displays the service as T_seen: the dashboard and the consumer may read data from different nodes/caches.

### Distinguishing "Seeing the Instance" from "Reaching the Instance"

DiscoveryClient returning the instance means the caller has seen the record through its discovery API. A successful LoadBalanced request to the new instance means LoadBalancer has selected that instance, the advertised address is reachable, and the provider handled the request.

A service may have multiple old and new instances. The first request to the service might be handled by an old instance; you cannot use that first success as T_route. The provider must return its instance ID so the consumer can confirm the response came from the new instance.

## Experiment Architecture

Use a new provider instance with a unique ID, for example inventory-node-run-001. The provider exposes an endpoint returning its current instance ID. The consumer has two ways to observe:

1. Call DiscoveryClient.getInstances(serviceId) to inspect the instance list.
2. Make an HTTP call using a @LoadBalanced RestClient to see whether LoadBalancer selects the new instance yet.

Measurement flow:

    Test harness records T_req
        -> Send registration command
        -> Registry acknowledges, record T_ack
        -> (Consul) wait for check passing, record T_pass
        -> Consumer polls DiscoveryClient
        -> First time expectedInstanceId is seen, record T_seen
        -> Consumer calls via LoadBalancer
        -> Provider returns instance ID
        -> First time the new ID is received, record T_route

If you want to accurately measure the caller's cache, the DiscoveryClient and RestClient logic must run inside the exact consumer process under evaluation. A separate test harness with its own DiscoveryClient only measures the harness's cache, not proving that the production consumer has seen the instance.

## Environment Preparation

### Provider Configuration

The provider needs a stable service ID and a distinct instance ID for each run. Set the instance ID via an environment variable so each run creates a fresh registration without colliding with old records.

Example configuration:

    spring:
      application:
        name: inventory-service
    server:
      port: 8080
    app:
      instance-id: ${INSTANCE_ID:inventory-node-run-001}

The provider should return its instance ID in the response body or header. Example controller using an environment property:

    @RestController
    class InstanceInfoController {
        private final Environment environment;

        InstanceInfoController(Environment environment) {
            this.environment = environment;
        }

        @GetMapping("/internal/instance-id")
        String instanceId() {
            return environment.getProperty("app.instance-id");
        }
    }

This endpoint is for lab/test environments only. In production, do not expose internal metadata or instance identifiers without a clear operational reason.

If using Eureka, set a unique instance ID in Eureka configuration or ensure registration produces a non-colliding instance ID. If using Consul, each instance's service ID must be distinct. With ZooKeeper, each ephemeral node/service instance needs a separate identifier.

### Consumer Configuration

The consumer needs the appropriate discovery starter and registry endpoint for the environment. Eureka example:

    spring:
      application:
        name: order-service
      cloud:
        discovery:
          enabled: true
    eureka:
      client:
        register-with-eureka: true
        fetch-registry: true
        service-url:
          defaultZone: http://eureka-server:8761/eureka/

Consul example:

    spring:
      application:
        name: order-service
      cloud:
        consul:
          host: consul-agent
          port: 8500
          discovery:
            enabled: true
            register: true

ZooKeeper example:

    spring:
      application:
        name: order-service
      cloud:
        zookeeper:
          connect-string: zk-1:2181,zk-2:2181,zk-3:2181
          discovery:
            enabled: true
            register: true

The configurations above only illustrate connectivity. The consumer must use the exact starters and properties of the active release train. In Docker Compose, use service DNS names and container ports; do not use localhost to call a registry in another container.

The consumer needs the corresponding provider discovery starter and Spring Cloud LoadBalancer if you want to use service ID URIs via a @LoadBalanced client. Manage versions using a Spring Cloud BOM compatible with Spring Boot. RestClient is only suitable for Spring Framework/Spring Cloud versions that support this integration; in older codebases, you can use a @LoadBalanced RestTemplate and keep the same T_seen/T_route measurement approach.

## Recording Registration Events

Create a unique run ID for each trial, e.g., run-001. Record these fields:

| Field | Example | Purpose |
|---|---|---|
| runId | run-001 | Correlate logs of a single measurement run |
| serviceId | inventory-service | Service ID being looked up |
| instanceId | inventory-node-run-001 | Identify the exact new registration |
| registry | consul | Provider under test |
| t_req_utc | 2026-11-24T10:00:00.120Z | Timestamp when registration began |
| t_ack_utc | 2026-11-24T10:00:00.180Z | Timestamp when registry acknowledged |
| t_pass_utc | 2026-11-24T10:00:00.540Z | Timestamp when health check became passing |
| t_seen_utc | 2026-11-24T10:00:01.020Z | First time consumer saw the instance |
| t_route_utc | 2026-11-24T10:00:01.240Z | First time consumer routed to the exact instance |

T_req and T_ack should be recorded where the registration is executed. With a synchronous registration API, T_ack is when a successful response is received from the registry/agent. If the provider registers via lifecycle hooks, capture the client's registration success log/event or observe the record via the registry API; do not infer T_ack from container start time.

With Consul, the Agent API may accept a service registration before the health check becomes passing. Therefore, T_ack and T_pass must be recorded separately. If the consumer only queries passing instances, T_seen normally cannot precede T_pass.

With Eureka, the registry can accept a registration before consumers fetch the registry next. Seeing the instance on the dashboard does not prove every Eureka client has updated its local registry.

With ZooKeeper, record when znode/ephemeral node creation is acknowledged and when the consumer receives the watch event or sees the node via the discovery API. If the consumer has not yet established a watch/session, the initial wait time may differ from subsequent updates.

## Clocks and Measurement Error

### Measuring Within the Same JVM

If T_ack and T_seen are measured in the same process, use System.nanoTime() to compute duration. This is a monotonic clock and will not jump when NTP adjusts the wall clock.

Example polling DiscoveryClient inside the consumer:

    long startedNanos = System.nanoTime();
    long deadlineNanos = startedNanos + TimeUnit.SECONDS.toNanos(60);
    long pollIntervalMillis = 100;

    while (System.nanoTime() < deadlineNanos) {
        List<ServiceInstance> instances =
            discoveryClient.getInstances("inventory-service");

        boolean found = instances.stream()
            .anyMatch(instance ->
                expectedInstanceId.equals(instance.getInstanceId()));

        if (found) {
            long elapsedNanos = System.nanoTime() - startedNanos;
            long elapsedMillis =
                TimeUnit.NANOSECONDS.toMillis(elapsedNanos);

            log.info("runId={} instanceId={} event=DISCOVERY_SEEN elapsedMs={}",
                runId, expectedInstanceId, elapsedMillis);
            break;
        }

        Thread.sleep(pollIntervalMillis);
    }

This snippet assumes DiscoveryClient, expectedInstanceId, and runId are already injected. For this duration to truly equal T_seen - T_ack, startedNanos must be recorded immediately after the same process receives registration acknowledgment. If T_ack comes from another process, do not directly compare two nanoTime values.

If the consumer only receives the T_ack timestamp via a message/event, you can store an Instant to correlate logs; never transfer a System.nanoTime value from the registrar process to the consumer process.

### Measuring Across Processes or Hosts

Use UTC timestamps like Instant.now() on each component and synchronize clocks via NTP/chrony or the platform's time synchronization mechanism. Record the sync status and estimated clock offset before the experiment.

System.nanoTime() is only for calculating durations within the same JVM/process. Never subtract nanoTime values from two different containers or machines.

If the maximum clock skew is 20 ms, cross-host result reports must state a minimum clock error of ±20 ms, in addition to polling and scheduling error. If clock offset is uncontrolled, do not draw millisecond-precision conclusions.

### Error Due to Polling Interval

If the consumer polls every 100 ms, the instance may have appeared right after the last failed poll and before the first successful poll. The true T_seen lies within the interval:

    last_not_seen < T_seen <= first_seen

Thus, the first_seen measurement has a polling error of up to approximately one poll interval, plus scheduler delay and DiscoveryClient call duration. Record both the last miss timestamp and the first hit timestamp to report an interval rather than a single number.

Polling too aggressively increases load on the discovery client/registry and can distort the measurement itself. Start with 100-250 ms in the lab, then test 500 ms or 1 second to see if results change significantly.

## Observing from DiscoveryClient

The consumer must check for the exact instance ID, not just whether the list is non-empty. For example:

    List<ServiceInstance> instances =
        discoveryClient.getInstances("inventory-service");

    for (ServiceInstance instance : instances) {
        log.info(
            "serviceId={} instanceId={} host={} port={} uri={} metadata={}",
            instance.getServiceId(),
            instance.getInstanceId(),
            instance.getHost(),
            instance.getPort(),
            instance.getUri(),
            instance.getMetadata()
        );
    }

Some providers may not return an instance ID via ServiceInstance or may represent the ID inside metadata. In that case, choose a stable, unique identifier such as an instance-id metadata field or the host/port pair in the lab. Do not use the generic service name to identify a new instance.

Log the instance list on every poll, or at least log the list at the last miss and the first hit. This helps catch cases where the consumer already sees the service ID but does not yet see the exact new instance ID.

Do not rely solely on the registry dashboard. The dashboard usually reads data at the server/catalog level; DiscoveryClient returns data according to the cache, watch, or query that the consumer itself uses.

## Measuring the Real Call Path via Spring Cloud LoadBalancer

DiscoveryClient may see an instance before the LoadBalancer cache is updated. To measure T_route, create a RestClient with LoadBalancer integration:

    @Configuration
    class ClientConfiguration {
        @Bean
        @LoadBalanced
        RestClient.Builder loadBalancedRestClientBuilder() {
            return RestClient.builder();
        }
    }

The consumer calls the endpoint returning the instance ID:

    String instanceId = restClient.get()
        .uri("http://inventory-service/internal/instance-id")
        .retrieve()
        .body(String.class);

Repeat bounded GET calls until the response contains expectedInstanceId. Record that timestamp as T_route. The endpoint must be a safe read operation; never use a data-mutating POST just to probe an instance.

If the service has multiple instances, the first call may hit an old instance. Keep calling at the poll interval until the response matches the new instance ID or the deadline expires. Record separately:

- T_first_service_response: first time calling the service succeeds with any instance.
- T_route: first time a response comes from the new instance.
- Number of requests required before LoadBalancer selects the new instance.

If LoadBalancer uses round-robin and there are N instances, the number of calls until the new instance is chosen depends on selection order and any errors encountered. This is a route selection metric, not pure discovery latency.

## Layer-by-Layer Experiments

### Experiment A: Measuring Registry Acknowledge

1. Start the registry and consumer.
2. Ensure the test service ID does not yet have the upcoming instance ID.
3. Generate a new instance ID for the current run.
4. Record T_req right before sending the registration.
5. Record T_ack right after the acknowledgment response from the registry/agent.
6. Read the registry API to confirm the exact instance ID exists.
7. Save registration latency = T_ack - T_req.

If registration is handled by Spring Cloud auto-registration, enable controlled logging for the provider client and identify the log/event corresponding to the successful response. Do not use the Started application log timestamp as T_ack.

### Experiment B: Measuring Health Readiness

With Consul, after T_ack is recorded, query the Agent API or Health API until the instance's check turns passing. Record T_pass.

    health_ready_delay = T_pass - T_ack

If a check stays critical due to a wrong path/port/auth, the discovery measurement will be skewed or the consumer will filter that instance out completely. Record the check failure reason and do not treat that time as cache propagation.

With Eureka, record the instance status and check whether the consumer filters by status/health metadata. With ZooKeeper, if there is no equivalent health check, skip the T_pass milestone or record an application-specific health signal.

### Experiment C: Measuring Consumer Discovery Visibility

1. Start the probe inside the consumer process.
2. Record T_ack or send an event containing T_ack to the probe.
3. Poll DiscoveryClient by service ID.
4. Mark seen only when the exact expectedInstanceId is found.
5. Record T_seen and last_not_seen.
6. Compute T_seen - T_ack along with the polling margin of error.

Do not create a separate DiscoveryClient solely for measurement if your goal is to understand the real consumer's cache. Inject the exact bean used by the business call flow.

### Experiment D: Measuring LoadBalancer Reachability

1. Start making GET calls via the @LoadBalanced RestClient.
2. Read the instance ID from the response.
3. Record T_first_service_response when any instance responds successfully.
4. Record T_route when the response comes from expectedInstanceId.
5. Compute T_route - T_ack and T_route - T_seen.
6. If T_seen has already occurred but T_route takes longer, investigate LoadBalancer cache, instance selection, advertised address, or connectivity to the instance.

If requests never reach the new instance, check the LoadBalancer cache and service instance list supplier. DiscoveryClient may have updated while the supplier/cache still holds the stale list.

## Cache and Propagation Layers to Distinguish

A new registration can pass through multiple layers before the caller sees it:

| Layer | What to Verify | Latency Indicator |
|---|---|---|
| Provider registration client | When was the request sent and accepted? | T_req to T_ack |
| Registry node/agent | Has the record appeared where the consumer queries? | T_ack to registry visible |
| Registry replication | Have other peers/servers received the data? | Difference across nodes/agents |
| DiscoveryClient | Has the client received the new data via fetch/watch/query? | Registry visible to T_seen |
| Discovery cache | Is a local cache still holding the old list? | T_seen varies with cache refresh |
| LoadBalancer supplier/cache | Has the instance list LoadBalancer selects from updated? | T_seen to T_route |
| Network/provider | Is the selected instance reachable? | T_route extended by timeout/connect failure |

Do not collapse everything into a single registry latency metric. If possible, record an additional timestamp when the registry API returns the instance and when the consumer's DiscoveryClient sees it. The gap between those two milestones helps isolate the propagation/cache portion.

## Registry-Specific Differences to Observe

### Eureka

Eureka Client registers the instance with Eureka Server; consumers typically fetch the registry periodically and keep a local registry/cache. Thus, a registration can be accepted by the server before the consumer's next fetch.

Check relevant properties:

- eureka.client.register-with-eureka: whether the provider sends registration.
- eureka.client.fetch-registry: whether the consumer downloads the registry.
- eureka.client.registry-fetch-interval-seconds: client registry fetch period.
- eureka.client.service-url.defaultZone: server/peer the client uses.
- Instance status and instance ID in the registry.

Default values and specific behavior depend on the Spring Cloud Netflix/Eureka Client version. Do not assume all consumers fetch at the same time or from the same node. If using a Eureka cluster, check registration replication and which server the consumer reads from.

The Eureka dashboard showing an instance does not mean the consumer's local cache has received it. Measure T_seen from DiscoveryClient inside the consumer process. If the server accepts the registration immediately but T_seen grows with the fetch interval, the fetch interval may be the primary delay.

### Consul

Consul service registration is usually sent to a local agent. The agent can accept a registration before the health check is passing or before the catalog/consumer query sees a qualifying instance.

Record separately:

- T_ack: local agent/API acknowledges registration.
- T_pass: check transitions to passing.
- T_seen: consumer discovery client sees the instance according to the health query in use.

If the consumer only requests passing instances, T_seen depends on T_pass as well. Check ACLs, datacenter, namespace, partition, query filters, and the Consul agent/server address the consumer accesses.

If there are multiple agents or servers, do not assume local agent results and server catalog query results always appear simultaneously. Document the exact API used to retrieve data and the node/agent being observed.

### ZooKeeper

ZooKeeper discovery typically stores service information in znodes, often using ephemeral nodes for session-bound instances. Consumers can use watches to receive changes or read data via the discovery client.

Measure:

- T_ack: znode/registration creation operation is acknowledged.
- T_seen: consumer receives the watch event or DiscoveryClient returns the instance.
- Reconnect/session recovery time if the consumer disconnects while registration occurs.

Watches can be re-registered after session expiration; measuring only the first time after consumer startup differs from updates on an established watch. Clearly note whether the consumer is cold-start or warm-watch.

## Designing an Experiment Matrix

| Group | Consumer State | Registration | Objective |
|---|---|---|---|
| Cold consumer | Consumer just started, cache/watch unstable | Create new instance | Measure initialization cost and initial fetch/watch |
| Warm consumer | Consumer operating steadily | Create new instance | Measure normal propagation |
| Registry peer | Consumer queries via another peer/server | Create new instance | Measure replication and read path |
| Health delayed | Check intentionally slow or not yet passing | Create new instance | Separate health readiness from discovery |
| LB cache | Discovery sees instance but LB cache is still warm | Create new instance | Measure delay to actual routing |
| Consumer reconnect | Consumer disconnects then reconnects | Create instance during reconnect | Measure watch/cache recovery |

Each run requires a new instance ID and a new run ID. Clean up old registrations afterward so previous runs do not skew measurements.

Execute at least several dozen runs to obtain reliable medians and p95 values rather than a single sample. If you need a meaningful p99, increase runs to hundreds or thousands; p99 from a tiny sample set is unstable.

## Results Log Table

Record one row per run, e.g., CSV:

    run_id,registry,consumer_mode,instance_id,t_req_ms,t_ack_ms,t_pass_ms,t_seen_ms,t_route_ms,poll_ms,clock_error_ms
    run-001,eureka,warm,inventory-node-001,1000,1040,,31800,32050,100,2
    run-002,consul,warm,inventory-node-002,2000,2030,2180,2290,2410,100,2
    run-003,zookeeper,warm,inventory-node-003,3000,3040,,3120,3290,100,2

The numbers above are illustrative data only, not benchmarks or defaults of any registry. An empty value for T_pass means the provider does not use a health check or that milestone does not apply.

You can compute duration columns:

    registration_ms = t_ack_ms - t_req_ms
    health_delay_ms = t_pass_ms - t_ack_ms
    discovery_ms = t_seen_ms - t_ack_ms
    end_to_end_visibility_ms = t_seen_ms - t_req_ms
    loadbalanced_reachability_ms = t_route_ms - t_ack_ms
    route_after_discovery_ms = t_route_ms - t_seen_ms

If using UTC wall-clock across multiple hosts, only compute durations after verifying clock offset and recording the margin of error. When possible, compute primary durations inside the same process using a monotonic clock and use UTC only for log correlation.

## Analyzing Results

Compute at least:

- min: fastest run, for reference only.
- median/p50: typical experience.
- p95: most runs complete within this threshold.
- p99: tail of the distribution, requires sufficient samples.
- max: slowest run and outlier errors.
- Count of timeouts or cases where the instance was not seen before the deadline.

| Observation | Potential Area to Investigate |
|---|---|
| Large T_ack | Registry API, network, auth, or slow provider registration client |
| Large T_pass - T_ack | Health check interval, endpoint readiness, timeouts, or dependency not ready |
| Registry sees it but large T_seen | Replication, fetch interval, watch, discovery cache, or consumer reading another node |
| Fast T_seen but large T_route | LoadBalancer cache/supplier, instance selection, stale address, or provider connectivity |
| Dashboard sees it but consumer does not | Dashboard and consumer using different sources/nodes/caches |
| Results vary sharply between cold and warm | Client initialization, initial fetch, watch registration, or cache warm-up |
| T_route occasionally very long despite stable T_seen | LoadBalancer selecting old instance, retries, timeouts, or request distribution |

Do not draw conclusions from a single run. Compare under identical configurations, registry topology, poll interval, and consumer code path.

## Controlling Confounding Variables

Keep the following factors constant:

- Same Spring Boot, Spring Cloud, and registry versions across comparisons.
- Same number of registry nodes/agents and same datacenter/namespace.
- Same polling, cache TTL, fetch interval, and health check configuration.
- Same network path and background load level.
- Do not run multiple registration tests concurrently against the same service ID.
- Use distinct instance IDs and verify there are no stale records.
- Do not allow HTTP client retries to distort call counts or T_route timing.
- Explicitly note whether the consumer has a warm cache/watch or just started.
- Synchronize clocks if logs span multiple hosts.

When measuring baseline propagation, you can temporarily disable or shorten caches in a lab environment to understand each layer. Afterward, re-run with production configuration. Never disable caches in production just to make metrics look better; caching is part of the system behavior under evaluation.

## Practice Completion Criteria

The practice meets requirements when it includes:

1. A new service instance with a unique ID.
2. T_req and T_ack timestamps with clearly documented recording sources.
3. T_pass if the registry has health checks.
4. T_seen measured from DiscoveryClient in the actual consumer process.
5. T_route verified by the instance ID returned from the provider.
6. Clock error and poll interval documented in the report.
7. Multiple runs with p50/p95 results; p99 if sample size is sufficient.
8. Explanation of which layer contributes the largest latency.
9. Comparison between cold/warm or at least two different cache/fetch configurations.
10. Documented registry/client configuration so others can reproduce the measurement.

## Self-Assessment Questions

1. Why is T_ack not equivalent to T_seen?
2. Why is the dashboard showing an instance insufficient proof that the consumer has seen it?
3. For Consul, why must T_pass be measured separately?
4. Why can T_seen be smaller than T_route?
5. With a 100 ms polling interval, how is the error margin of T_seen interpreted?
6. Why must you not subtract System.nanoTime() values from two different processes?
7. When Eureka fetches the registry periodically, which property directly affects when the consumer updates?
8. If the consumer sees the instance but requests still go to an old instance, which layer should be checked?
9. Why must the instance ID be unique per run?
10. Why should p95 be reported instead of only reporting the single fastest run?

## Conclusion

The latency from registration to caller visibility is the sum of registry acceptance and replication time, health readiness, discovery fetch/watch/cache, and LoadBalancer cache. Measure T_ack, T_pass, T_seen, and T_route separately; use a unique instance ID to confirm the exact record, and measure durations with a monotonic clock inside the same process or use UTC with clock synchronization across hosts. By isolating these milestones, operations teams can pinpoint whether latency resides in the registry, health check, discovery client, or load balancer rather than staring at the dashboard and guessing.
