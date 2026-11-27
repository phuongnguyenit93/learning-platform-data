# Periodic Polling, Change Tracking, and Instance List Caching

In microservices, the list of instances for a service changes over time. New instances may be created as load increases; old instances may be stopped, replaced, or moved to another machine. Consumers must keep discovery information up to date to avoid calling stale addresses and to utilize newly joined instances.

In Spring Cloud, DiscoveryClient provides a way to query instances by service ID. However, a single call to getInstances() only answers which instances the discovery client knows about at that query moment. To track changes over time, a system needs an update strategy: periodic polling, receiving change signals from the registry if supported by the platform, or combining both. Caching reduces query volume and latency, yet introduces the risk of stale data.

This article focuses on how to organize polling cycles, detect changes, and manage instance list caches in Spring Cloud Service Discovery.

## 1. Why must the instance list be updated?

Suppose order-service calls inventory-service. At startup, the consumer discovers two instances:

~~~text
inventory-service
  10.0.2.15:8081
  10.0.2.16:8081
~~~

Later, the platform deploys a third instance and stops the second instance:

~~~text
inventory-service
  10.0.2.15:8081
  10.0.3.21:8081
~~~

If the consumer continues using the initial list, it may miss the new instance and send requests to an address that has stopped serving. Common consequences include:

- Requests fail because the old address no longer accepts connections.
- Load is distributed unevenly because the consumer is unaware of the new instance.
- Consumers at different points in time see different lists.
- A change has been recorded by the registry yet has not reached the consumer's or load balancer's cache.

Therefore, discovery is not merely a one-time lookup operation. Applications need a way to refresh data and bound how long stale data is allowed to persist.

## 2. Periodic polling

Polling is how a consumer or discovery component periodically asks the registry for the current list of service instances. On each query, the client retrieves the new result and either updates its cache or compares it against the previous result.

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant D as DiscoveryClient
    participant R as Service Registry
    loop Periodic interval
        C->>D: getInstances(inventory-service)
        D->>R: Read instance list (if needed)
        R-->>D: Current list
        D-->>C: ServiceInstance list
        C->>C: Compare and update snapshot
    end
~~~

The interval can be configured based on operational needs. Short intervals detect changes faster, yet increase query frequency and processing overhead. Long intervals reduce registry load, yet mean consumers may continue using stale data longer.

### Polling can occur at multiple layers

Not every application request queries the registry. Depending on the registry and Spring Cloud integration, updates may happen across multiple layers:

| Layer | Update mechanism | Purpose |
|---|---|---|
| Registry client | Periodically syncs or fetches lists from the registry | Maintains discovery data on the application side |
| Consumer application | Calls DiscoveryClient on a schedule or as needed | Observes lists, builds snapshots, or executes custom logic |
| Load balancer | Fetches instance lists from a supplier and may cache them | Selects an instance for requests |
| Gateway or proxy | Syncs targets or queries the registry per integration mechanism | Routes requests on the server side |

For instance, a registry client may refresh its list from the server in the background and supply local data to DiscoveryClient. When a consumer calls getInstances(), that call may read from a local cache rather than making a new network query to the registry. Understand how your chosen implementation works before assuming every API call hits the registry.

### Choosing a polling interval

When picking an interval, consider:

- **Staleness tolerance window:** how long can the system afford before a new instance is seen or a stopped instance is removed from the list?
- **Scale:** how many consumers exist, and how many service IDs does each consumer track?
- **Query cost:** can the registry sustain the read rate and response payload volume?
- **Rate of change:** do instances churn continuously or only during deployment windows?
- **Resilience:** when the registry becomes temporarily unreachable, how long must the consumer continue using the latest snapshot?

If many consumers share the same fixed interval, they may all query simultaneously. You can add jitter (a small random offset) to spread out query times and avoid synchronized load spikes.

fixedDelay and fixedRate also behave differently. fixedDelay measures the wait interval after the previous execution completes; fixedRate schedules executions at a fixed cadence. For query tasks that can block or take time, control overlapping runs, timeouts, and thread pool sizing.

## 3. Tracking changes by comparing snapshots

A snapshot is a point-in-time capture of the instance list. When a new query result arrives, the consumer compares the new snapshot against the previous snapshot to detect:

- **Added instances:** present in the new list but absent from the old list.
- **Removed instances:** present in the old list but no longer in the new list.
- **Instances with changed attributes:** the same instance whose host, port, scheme, or metadata changed.
- **No change:** the two snapshots are equivalent across the attributes the application cares about.

~~~mermaid
flowchart TD
    A["Receive new list"] --> B["Normalize and sort"]
    B --> C["Compare with previous snapshot"]
    C --> D{"Any changes?"}
    D -->|"No"| E["Keep current snapshot"]
    D -->|"Yes"| F["Compute added, removed, updated instances"]
    F --> G["Publish new snapshot"]
    G --> H["Log / emit metrics / process further"]
~~~

To compare accurately, choose stable instance-identifying attributes. You can use the instance ID if the registry supplies one reliably; otherwise, use the URI combined with relevant metadata. Do not compare only the instance count: two lists may both contain two elements even though both addresses changed.

Metadata should also be included in the comparison if it influences routing or instance selection. For instance, a change in zone or version may matter even when host and port remain unchanged. Conversely, there is no need to flag changes in metadata that have no effect on consumer logic.

### Example comparing two lists

Previous list:

~~~text
10.0.2.15:8081
10.0.2.16:8081
~~~

New list:

~~~text
10.0.2.15:8081
10.0.3.21:8081
~~~

Comparison result:

| Change type | Instance |
|---|---|
| Unchanged | 10.0.2.15:8081 |
| Removed | 10.0.2.16:8081 |
| Added | 10.0.3.21:8081 |

Diffing helps observe topology and drive additional logic. However, if the goal is solely sending requests, do not build a custom instance selector from this snapshot when Spring Cloud LoadBalancer already handles that responsibility.

## 4. Example of polling with DiscoveryClient in Spring

For applications that need to observe changes for a specific service, you can create a scheduled task. The following example retrieves URIs and metadata of inventory-service instances, normalizes them into a list of signatures, and compares against the previous snapshot.

~~~java
@Configuration
@EnableScheduling
public class DiscoverySchedulingConfiguration {
}
~~~

~~~java
@Component
public class InventoryDiscoveryMonitor {

    private static final Logger log =
        LoggerFactory.getLogger(InventoryDiscoveryMonitor.class);

    private final DiscoveryClient discoveryClient;

    private final AtomicReference<List<String>> snapshot =
        new AtomicReference<>(Collections.emptyList());

    public InventoryDiscoveryMonitor(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    @Scheduled(fixedDelayString =
        "${discovery.inventory.refresh-delay-ms:10000}")
    public synchronized void refresh() {
        try {
            List<String> current = discoveryClient
                .getInstances("inventory-service")
                .stream()
                .map(instance ->
                    instance.getUri() + "|" +
                    new TreeMap<>(instance.getMetadata()))
                .sorted()
                .collect(Collectors.toList());

            List<String> next =
                Collections.unmodifiableList(current);
            List<String> previous = snapshot.get();

            if (!previous.equals(next)) {
                log.info(
                    "inventory-service discovery changed: {} -> {}",
                    previous,
                    next
                );
                snapshot.set(next);
            }
        } catch (RuntimeException ex) {
            log.warn("Cannot refresh inventory-service discovery", ex);
        }
    }
}
~~~

This is an illustrative example for observing changes, not a custom load balancer. Required imports include DiscoveryClient, Component, Configuration, EnableScheduling, Scheduled, Logger, LoggerFactory, AtomicReference, Collections, List, TreeMap, and Collectors.

Points to note:

- @EnableScheduling enables scheduled task execution in the application.
- fixedDelayString reads the wait interval from configuration, defaulting here to 10,000 milliseconds after the previous execution completes.
- URI and metadata are normalized into a signature for comparison. TreeMap keeps metadata key order deterministic when building strings.
- The snapshot is replaced only when the new list differs from the previous list.
- When a query throws an error, the example preserves the latest snapshot and logs a warning. Do not wipe the cache just because a single refresh failed.

In real applications, rate-limit change logs to avoid excessive logging during continuous topology churn. You can emit metrics for instance count, refresh failure count, and timestamp of the latest successful refresh. If you must distinguish "the service genuinely has zero instances" from "the registry is failing", use additional health signals or error states provided by the registry implementation. The generic discovery API may return an empty list without enough context to distinguish all causes.

## 5. Event-driven updates or watches

Polling is not the only option. Some registries provide watch, event, long polling, or subscription mechanisms so consumers learn when data changes. When supported, consumers can update sooner without continuously sending full queries.

Examples of approaches:

- Consul provides watches and blocking queries to monitor changes in the catalog or related data.
- Eureka clients typically maintain a client-side registry copy and refresh that copy on a configured interval.
- Some platforms or service meshes push endpoint change events to proxies or sidecars.

These mechanisms are features of specific registries or integrations. Spring Cloud's DiscoveryClient provides a service and instance lookup abstraction, yet does not guarantee a uniform change-event API across all registries. If an application requires watches, verify the capabilities and API of the implementation in use.

### Combining watches with reconciliation polling

Watches help detect changes quickly, yet connections can drop, events can be missed, or a consumer may restart while the registry is changing. Therefore, a resilient implementation pattern is:

1. Fetch a full initial snapshot when the consumer starts up.
2. Register a watch or subscription if the registry supports it.
3. Upon receiving a signal, refresh the relevant data or fetch a new snapshot.
4. Periodically run a reconciliation query to fix drift if any events were missed.
5. When a watch connection drops, reconnect with backoff and fetch a fresh snapshot before resuming event processing.

Events can be treated as a signal to trigger a refresh. Snapshots from the discovery source should still be validated before being published for other consumers to use.

## 6. Instance list caching

Caching holds discovery results in memory or an intermediate store to avoid repeated queries. Caches may reside in the registry client, consumer application, Spring Cloud LoadBalancer's ServiceInstanceListSupplier, gateway, or proxy.

Benefits of caching:

- Reduces registry read frequency and network traffic.
- Reduces latency when retrieving instance lists.
- Allows consumers to keep operating for a window when the registry is temporarily unreachable.
- Eliminates redundant work when consecutive requests need the same list.

In return, caching introduces update lag. If an instance stops while the cache still holds its old address, requests may continue routing to that instance. If the cache lacks a newly added instance, load may not be distributed to the new instance.

### TTL and refresh timing

TTL (time to live) is how long a cache entry is considered valid. Once TTL expires, the cache must be refreshed before or during the next read, depending on the implementation strategy.

| TTL | Benefit | Risk |
|---|---|---|
| Short | Sees changes faster | Increases query count and cache processing overhead |
| Long | Lowers registry load, increases reuse of existing data | Lists may stay stale longer |
| Unlimited | Minimal queries | May retain invalid addresses indefinitely if no other update mechanism exists |

There is no single TTL right for every system. Choose based on staleness tolerance, instance churn rate, and query cost. TTLs across cache layers should be evaluated together: registry client caches, load balancer caches, and custom application caches can stack update delays.

### Last-known-good snapshot caching

When a refresh fails due to a timeout or temporary registry unavailability, wiping the snapshot immediately can strip the application of all routing information. One option is retaining the latest successful snapshot for a bounded period while flagging the data as stale.

This strategy typically involves:

1. Publishing a new snapshot only after the query completes and the data is validated.
2. On refresh failure, keeping the last valid snapshot instead of replacing it with unverified data.
3. Recording the timestamp of the last successful refresh and the snapshot's age.
4. Setting a maximum age limit for stale data; once exceeded, alerting or switching to a safe fallback policy.
5. Continuing refresh attempts with backoff to avoid flooding an impaired registry.

Do not hold stale data indefinitely. An old address may have been reassigned to a different process or may no longer route to the original provider. Using last-known-good must be paired with timeouts, request error handling, and explicit time bounds.

### Avoiding unnecessary extra cache layers

Spring Cloud LoadBalancer has a supplier mechanism and can integrate caching to store instance lists for selection. The registry client may also cache data already. If the application introduces another independent cache without understanding those two layers, the system ends up with multiple snapshots refreshing at different times.

Before adding a custom cache, determine:

- Does the registry client already refresh data automatically?
- Which supplier does the load balancer use and where does it cache?
- What purpose does the new cache serve: observation, reporting, specialized routing, or load reduction?
- Are the TTLs and invalidation mechanisms across cache layers compatible?

For ordinary request sending, use Spring Cloud LoadBalancer's integration for instance selection. The self-managed cache in the example above is solely for topology monitoring. If you genuinely need custom routing logic, ensure caching stays updated and handles errors consistently with the remaining discovery layers.

## 7. Handling errors during polling and refresh

Discovery refreshes can encounter several failure modes:

| Scenario | Symptom | Handling approach |
|---|---|---|
| Registry unreachable | Timeouts or exceptions when querying | Retain the latest valid snapshot within bounds; retry with backoff |
| Service has no instances | Returned list is empty | Check provider, service ID, and registration status; do not assume a registry fault |
| Instance just stopped | Old snapshot still holds the address | Refresh list, set request timeouts, and exclude failing targets per appropriate mechanism |
| New instance not visible yet | Snapshot lacks the new address | Check registration, refresh, and cache intervals at each layer |
| Watch disconnected | No new events arriving | Reconnect, fetch a full snapshot, and continue reconciliation polling |
| Overlapping refreshes | Older result may overwrite newer result | Use a single update thread or synchronization/snapshot versioning |

### Retries and backoff

If the registry is overloaded or disconnected, having all consumers continuously retry on the same short interval can worsen the outage. Exponential backoff progressively lengthens wait times between attempts; jitter spreads retry timestamps across consumers.

Illustrative wait sequence:

~~~text
Attempt 1: 1 second
Attempt 2: 2 seconds
Attempt 3: 4 seconds
Attempt 4: 8 seconds
...
~~~

In practice, cap the maximum backoff and optionally reset the cycle after a successful refresh. Never retry indefinitely at high frequency. For discovery read tasks, retries need an overall timeout so resources are not held too long.

### Distinguishing empty results from query errors

An empty list can be a legitimate result if a service has no instances yet or all instances were removed. It can also be a sign of a misconfigured service ID or an implementation's behavior during a registry fault. Never automatically overwrite a healthy snapshot with an empty list unless you know what the registry result means.

Observe registry status, connection errors, last successful refresh timestamps, and instance counts as well. If the adapter distinguishes query errors from empty results, use that signal to decide whether to publish a new snapshot or retain prior data.

## 8. Operations and observing discovery quality

To know whether caching and polling work properly, monitor several metrics:

| Metric | Meaning |
|---|---|
| Refresh success/failure | Counts of successful and failed updates |
| Refresh duration | Time taken to complete one query |
| Last successful refresh | Timestamp of the most recent valid snapshot |
| Snapshot age | Age of the data currently in use |
| Instance count | Number of instances discovered per service ID |
| Added/removed/updated count | Number of instances changed between two snapshots |
| Watch reconnect count | Number of times a watch connection had to be re-established |

Logs should record the service ID, instance count, refresh outcome, and error reason; avoid logging sensitive data or connection details that could be abused. For systems with many services, use metrics with controlled labels to avoid excessive cardinality.

A useful alert is when snapshot age exceeds an operational threshold. This catches consumers that are still running yet can no longer update their discovery list. You should also alert when a critical service has zero instances for an extended period, after ruling out intentional scale-to-zero events.

## 9. Design principles

- Query only the service IDs the application genuinely needs to track, if the full catalog is not required.
- Pick refresh intervals based on staleness tolerance and registry load.
- Add jitter to polling or retries when multiple consumers exist to prevent thundering-herd queries.
- Compare instance identities and critical metadata, not merely instance counts.
- Publish new snapshots atomically after processing completes.
- Retain last-known-good with strict bounds when refreshes fail; track data age and never use stale data indefinitely.
- Understand built-in caching in the registry client and Spring Cloud LoadBalancer before adding custom caches.
- When using watches/events, retain full-snapshot fetches and reconciliation polling to recover from missed events.
- Let Spring Cloud LoadBalancer handle instance selection for normal requests; keep monitoring caches strictly for observability or explicitly designed logic.

Periodic polling, watches, and caching are three complementary mechanisms. Polling reconciles state on a schedule; watches shorten change-detection latency when supported by the registry; caching reduces load and speeds up reads while requiring TTLs and stale-data bounds. Combining these mechanisms properly helps consumers keep pace with instance lifecycles and lowers the risk of routing to stale addresses in Spring Cloud Service Discovery.
