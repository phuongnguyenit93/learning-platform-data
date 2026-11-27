# Trade-offs Between List Freshness, Availability, and Synchronization Cost

Service discovery helps consumers resolve instance addresses by service ID, but the instance list does not always reflect the latest state instantaneously. When an instance just registered, failed, changed status, or deregistered, the change must pass through the registry, response cache, client cache, and potentially the LoadBalancer cache before every consumer sees the result.

Discovery design must therefore balance three goals: list freshness, the ability to continue lookups when the registry or network experiences an outage (availability), and the cost to synchronize changes (synchronization cost). Optimizing one goal often affects the other two. This lesson analyzes how Eureka and Consul handle that balance, how to choose policies by request type, and how to measure update latency in Spring Cloud systems.

## 1. Three Goals to Balance

**List freshness** indicates how close the data a consumer is using is to the current registry state. If an instance was just removed from the pool but the consumer still sees the old record, that list is stale. If a new instance has registered but the consumer does not see it yet, the list does not reflect the new topology either.

**Discovery availability** indicates whether consumers can continue retrieving the instance list when the registry, leader, or network path to the registry encounters an issue. A client with a local cache can keep looking up from older data while the registry is temporarily unreachable. This preserves serving capability while accepting the risk of picking an instance whose state has changed.

**Synchronization cost** includes polling requests, heartbeats, replication, blocking queries, serialization/deserialization, cache updates, network bandwidth, and CPU. The more frequent the updates or the stronger the required confirmation, the more synchronization work the system must process.

| Goal | Strengthened by | Common trade-offs |
|---|---|---|
| High freshness | Frequent fetch/watch, short cache, strongly consistent reads | Increases requests, CPU, network, and latency when waiting for quorum |
| High availability | Using local cache, allowing stale reads, continuing to serve during registry outages | Consumers may receive outdated addresses |
| Low cost | Fewer polls, longer caching, batching changes, using delta/blocking queries | Changes propagate slower or consumers see stale data for longer |

No single configuration is optimal for every service. Payment APIs, catalog lookup services, background workers, and gateways may need different freshness budgets.

## 2. Freshness Is Not Synonymous with Consistency

Several concepts must be distinguished:

- **Freshness:** whether data is up to date relative to the most recent change.
- **Consistency:** whether reads on different nodes or consumers observe states that are mutually compatible.
- **Availability:** whether a lookup request receives a response under failure conditions.
- **Propagation delay:** the time from when a change is accepted at the registry until a consumer observes the change.
- **Cache age:** the time elapsed since the cache was last updated.

A consumer can receive a fast response consistent with its local cache, yet that cache is already stale compared to the registry. Conversely, a query to the leader may read the latest state, but must wait an extra round-trip or fail to respond when there is no quorum.

For service discovery, consistency does not always mean every consumer sees the exact same list at the exact same moment. Many systems accept eventual consistency: changes propagate gradually and replicas eventually converge when the system stabilizes.

## 3. CAP and Service Discovery in Practice

CAP describes the trade-off when a network partition occurs: a distributed system must choose between continuing to answer requests on every side and guaranteeing that reads do not return conflicting data. In operations, it is important to understand the concrete behavior of the registry and client rather than labeling an entire product as CP or AP.

Service discovery has a distinct characteristic: consumers can often use cached data to keep sending requests while the registry is unreachable. That serving capability comes from previously fetched data, not proof that the registry currently holds the latest state.

For example, when the network between a consumer and the registry breaks:

1. The consumer has already cached two instances of `inventory-service`.
2. One instance actually stops during the partition.
3. The consumer cannot refresh the list but still holds the old cache.
4. If the consumer continues using the cache, requests may still be sent to the stopped instance.
5. If the consumer refuses to use the cache and requires a fresh lookup, requests may fail immediately because the registry is unreachable.

This is an application-layer policy decision: continue serving with a potentially stale list, or halt lookups to avoid using unverified data.

## 4. Eventual Consistency and the Lifecycle of a Change

A registration change typically passes through multiple stages:

    Instance
       |
       | register / status change / deregister
       v
    Registry leader or local agent
       |
       | replicate / catalog update
       v
    Registry response or query result
       |
       | fetch / watch / DNS query
       v
    DiscoveryClient cache
       |
       | refresh / list supplier
       v
    Spring Cloud LoadBalancer
       |
       v
    Consumer selects instance

Each step can add latency. For instance, an instance has already deregistered at the registry, yet the consumer's Eureka client has not fetched the new delta; or the Consul Catalog has updated, yet the consumer is still using an old cached result.

Therefore, when measuring propagation delay, record at least two milestones: the timestamp when the registry accepts the change and the timestamp when the consumer first observes the change. If you need to evaluate actual routing, also record when the LoadBalancer stops picking the old instance.

## 5. Eureka: Local Cache and Delta Fetch

Eureka Client downloads the registry from Eureka Server and retains a local cache. Service lookups normally read from this cache instead of calling the server for every business request.

Common properties:

    eureka:
      client:
        registry-fetch-interval-seconds: 30
        disable-delta: false
        fetch-registry: true

`registry-fetch-interval-seconds` controls the fetch period. The default value is typically 30 seconds. `disable-delta=false` lets the client retrieve only changes since the previous fetch instead of downloading the entire registry on every update.

Deltas reduce data transfer volume when the number of changes is much smaller than the number of fetches. The client applies deltas and can fall back to fetching the full registry if a mismatch is detected during reconciliation.

This creates a trade-off:

- A shorter fetch interval helps consumers see changes sooner.
- A longer fetch interval reduces request load on Eureka Server but extends how long the cache can remain stale.
- Disabling deltas makes clients transfer more data, especially when the registry is large.
- The local cache lets consumers continue lookups when Eureka Server is temporarily unreachable, though the data may be stale.

Netflix documentation describes clients fetching deltas periodically and storing the registry locally; propagation time can take up to roughly two minutes under the documented configuration and scenarios. This is not a fixed SLA for all versions or topologies. Measure the deployed system itself.

## 6. Eureka and Serving Capability During Registry Outages

If Eureka Server becomes temporarily unreachable after a client has already downloaded the registry, the application typically still has cached data for lookups. This improves the ability to keep calling services during brief incidents, though consumers might not know which instances just stopped or were added.

If a client starts up for the first time while unable to reach the registry, it does not yet have a full cache. Some configurations can use a backup registry for initial startup; do not assume every application has fallback data.

Eureka Server also features self-preservation to curb mass eviction when heartbeats fall below expectations. During a network partition, the server may retain expired-lease instances instead of deleting them immediately. This mechanism prioritizes protecting the registry against accidental mass removal when the root cause may be a network issue.

In operations, monitor:

- Registry fetch success/failure and fetch duration.
- Delta fetch count and full reconciliation count.
- Latest cache age.
- Heartbeat renewals and self-preservation state.
- Instance count in the registry versus actual running instances.
- Failed requests caused by consumers selecting instances that are no longer active.

Do not disable self-preservation solely to evict stale instances faster. Weigh the risk of mistakenly removing many instances during a network partition.

## 7. Consul: HTTP API Consistency Modes

Consul stores registration and health state on its servers, using consensus to commit changes. Followers may take time to receive new state from the leader. Consequently, how a read request is handled affects freshness and read cost.

Consul provides three main consistency modes for supported HTTP API reads:

| Mode | Behavior | Trade-off |
|---|---|---|
| default | Uses the default mechanism; HTTP API usually provides strong reads in most cases | Fast under normal conditions; still has a rare window during leader changes |
| stale | Allows followers to serve reads | Scales read load and can respond without a leader, but data can be stale |
| consistent | Leader verifies with quorum that it is still leader before responding | Higher read reliability, at the cost of an extra round-trip and latency |

Consul's HTTP API uses the default consistency mode if the request specifies no other mode. Consul DNS uses stale mode by default for underlying discovery queries. Do not assume all Consul query paths share the same default behavior.

Consistency modes apply to read requests. Write operations do not pick a mode via query parameters; Consul handles writes through the cluster's consistent mechanism.

If an operation needs the newest data, some endpoints support the `consistent` query parameter. If potentially stale data is acceptable to increase read capacity and load distribution, an endpoint may support `stale`. Only use modes supported by that endpoint and verify the documentation for your running version.

Example querying the Health API requiring strong consistency:

    curl "http://consul:8500/v1/health/service/inventory-service?consistent"

Example allowing stale reads:

    curl "http://consul:8500/v1/health/service/inventory-service?stale"

Consistent reads require the leader to verify quorum, so they can increase latency and depend on quorum. Do not enable it on every request just to keep the list fresh; reserve it for operations that truly cannot tolerate stale reads.

In `stale` mode, data is typically close to the leader under normal conditions, but there is no strict upper bound on staleness. If a consumer cannot tolerate stale results, pick an appropriate consistency mode rather than assuming followers only lag by a fixed interval.

## 8. Consul DNS and HTTP API Are Not Identical

Consul DNS uses `stale` consistency mode by default when querying the underlying service discovery APIs. The goal is to let multiple servers serve reads and keep returning results when the cluster lacks a leader, at the risk of staler data.

Consul HTTP API uses `default` mode by default, which is strong in most cases. A client calling the HTTP API can choose a consistency mode per request if the endpoint supports it.

Therefore, two consumers querying the same service via DNS versus the HTTP API may observe different results for a period of time. This is not necessarily a registration bug; it can be a consequence of consistency mode, follower replication, or caching.

When stale DNS results need to be bounded, Consul provides advanced settings such as `dns_config.allow_stale` and `dns_config.max_stale`. Bounding staleness can shift more queries back to the leader when followers lag too far, increasing load while the cluster is already stressed. Apply this only after evaluating the impact and confirming that stale results are riskier than slower or failing queries.

## 9. Consul Blocking Queries and Long Polling

Blocking queries let consumers wait for changes instead of repeatedly polling on a fixed interval. Many Consul APIs return an `X-Consul-Index` header representing the resource state. The client sends the previously received index along with `wait` to ask Consul to hold the request until a change occurs or the timeout expires.

Example initial query:

    curl -i "http://consul:8500/v1/health/service/inventory-service"

The response may contain:

    X-Consul-Index: 12345

Subsequent query:

    curl -i "http://consul:8500/v1/health/service/inventory-service?index=12345&wait=5m"

The request can be held open until the relevant state changes or the `wait` duration expires. Reaching the timeout does not mean data changed; the client must read the index header again and continue the loop.

Blocking queries reduce wasted polling when the registry does not change. When a change occurs, the response can arrive sooner than a fixed polling period. Still, they have timeouts, require reconnect handling, and do not guarantee every consumer receives the change simultaneously.

Not all Consul endpoints support blocking queries. Check the specific endpoint's documentation before building a watcher.

## 10. Spring Cloud Consul Catalog Watch

Spring Cloud Consul includes Catalog Watch, which uses blocking Consul HTTP APIs to monitor service catalog changes. When new service data arrives, the watch can publish a Heartbeat Event so related discovery components update.

Current configuration properties:

    spring:
      cloud:
        consul:
          discovery:
            catalog-services-watch-delay: 1000
            catalog-services-watch-timeout: 2

`catalog-services-watch-delay` is the delay between watch invocations, in milliseconds; current documentation specifies a default of 1000. `catalog-services-watch-timeout` is the number of seconds to wait on a blocking query; the current configuration table specifies a default of 2 seconds.

These settings configure Spring Cloud Consul's watch, not a guarantee that every change reaches every consumer in exactly one second. Latency also depends on Consul processing time, network, event dispatch, caching, and the LoadBalancer.

When tuning these values:

- A lower delay can start the next watch cycle sooner, but increases coordination activity.
- A longer timeout lets blocking queries wait longer and reduces polling when the catalog rarely changes.
- The timeout must be compatible with HTTP client timeouts and reconnect policies.
- Avoid creating too many watchers for the same service if a shared watcher or cache suffices.

Verify the exact property names and behavior for your Spring Cloud Consul version; do not confuse Catalog Watch with Consul Config Watch.

## 11. Caching: Lowering Cost at the Expense of Data Age

Caching avoids querying the registry on every request. However, caching introduces a window during which consumer data can differ from the current registry.

Common cache layers:

- Eureka Server response cache.
- Eureka Client local registry cache.
- Consul agent/query cache, if configured.
- `DiscoveryClient` or adapter caches.
- Spring Cloud LoadBalancer `ServiceInstanceListSupplier` cache.
- DNS caches in the JVM, operating system, or resolver.

When multiple cache layers coexist, delays can stack. For example, Eureka client refreshes its registry every 30 seconds, and then LoadBalancer holds the list for an additional TTL. The moment requests stop choosing an old instance can be much later than when Eureka Server removed it.

Not every `DiscoveryClient` uses the same caching. Identify the exact implementation, cache layers, and refresh mechanisms in effect before modifying TTLs.

## 12. Setting a Freshness Budget by Business Need

A freshness budget is the maximum duration a system tolerates a consumer using stale discovery data for a given request type. This is a system design SLO, not a default commitment guaranteed by Eureka or Consul.

Illustrative examples:

| Workload type | Reference freshness budget | Rationale |
|---|---:|---|
| Internal catalog lookup | 30–60 seconds | A stale instance can be handled via retries |
| Read API with multiple replicas | 5–15 seconds | Shift traffic away from failed instances relatively quickly |
| Dispatching new jobs | 5–10 seconds | Avoid assigning jobs to workers that just left the pool |
| Maintenance state changes | 1–5 seconds if possible | Limit new requests to draining instances |
| Flows requiring strict data consistency | Governed by dedicated controls | Discovery does not replace transactions or a source of truth |

These numbers are only starting points for discussion. Measure propagation delay, request failure rates, and registry capacity to set appropriate thresholds.

The freshness budget must be measured from when the change is accepted at the registry until the consumer and LoadBalancer actually stop using old data. Measuring only registry update time is insufficient.

## 13. Choosing Fail-Open vs. Fail-Closed When the Registry Is Unreachable

When the registry is temporarily unreachable, consumers must decide whether to keep using cached data.

**Fail-open with cache**

- Continue using the most recent instance list.
- Improves serving availability during short registry incidents.
- Accepts the risk that the cache holds dead or traffic-drained instances.
- Better suited for read APIs with retries, timeouts, and multiple replicas.

**Fail-closed**

- Do not select an instance if the list cannot be verified as required.
- Reduces the risk of using stale addresses for sensitive operations.
- Can fail requests even while the target service is still running.
- Suitable for operations where choosing the wrong instance has severe consequences and clear error handling exists.

Do not apply a single policy to all services. A consumer calling a read API can rely on cache briefly; a component orchestrating sensitive actions may require fresher registry state or additional application-level verification.

Whether fail-open or fail-closed, requests still need timeouts, bounded retries, circuit breakers, and handling for cases where an instance disappears after selection.

## 14. The Cost of Frequent Synchronization

Shortening fetch intervals or raising consistency levels can make data fresher, but incurs costs:

| Synchronization method | Increased cost | Benefit |
|---|---|---|
| Frequent polling | More HTTP requests, CPU, and response parsing | Bounds wait time until the next poll |
| Full registry fetch | Large payloads, deserializing many instances | Re-synchronizes full state |
| Delta fetch | Processing and reconciling deltas; mismatch handling needed | Transfers less data when change rate is low |
| Blocking query | Holding open connections, managing timeouts/reconnects | Reduces polling when nothing changes |
| Consistent read | Leader round-trip / quorum verification | Reduces stale read risk on supported endpoints |
| Short cache TTL | More refreshes and lookups | Reduces age of stale data |
| Long cache TTL | Fewer queries | Extends how long stale data may be used |

With thousands of consumers, lowering the fetch interval from 30 seconds to 5 seconds can increase fetch frequency roughly sixfold. That is a simple frequency calculation; actual load also depends on delta size, instance count, compression, server count, and client distribution.

Do not reduce all intervals simultaneously. Measure each layer and change one parameter at a time.

## 15. Scenario-Based Decision Matrix

| Scenario | Priority | Approach |
|---|---|---|
| Consumers must keep operating during brief registry faults | Availability | Use latest cache, bounded timeouts, and retries |
| Instance under maintenance must stop receiving new requests | Freshness and routing safety | Mark out-of-service/maintenance, wait for propagation, and drain |
| Read-heavy Consul cluster needing query scaling | Read scalability | Consider stale mode or caching on appropriate endpoints |
| Consumer cannot tolerate stale reads on a critical query | Consistency | Use consistent mode if endpoint supports it; accept latency |
| Registry changes infrequently with many polling consumers | Synchronization cost | Delta fetch, blocking queries, or watches |
| Instances churn constantly due to autoscaling oscillation | Topology stability | Stabilization windows, batched rollouts, and curbing health flapping |
| Consumers still use old instances after registry updates | Cache freshness | Inspect every cache layer and LoadBalancer supplier |

## 16. Practical Eureka Configuration and Testing

Example client configuration keeping default fetch interval and deltas:

    eureka:
      client:
        fetch-registry: true
        registry-fetch-interval-seconds: 30
        disable-delta: false
        g-zip-content: true
      instance:
        lease-renewal-interval-in-seconds: 30
        lease-expiration-duration-in-seconds: 90

This configuration favors common operational defaults: local caching, periodic fetches, and deltas. Reduce `registry-fetch-interval-seconds` only after measuring propagation delay and server load.

When testing:

1. Register two instances of `inventory-service`.
2. Start the consumer and confirm the cache contains both instances.
3. Transition one instance to `OUT_OF_SERVICE` or deregister it.
4. Record when Eureka Server receives the change.
5. Record when the consumer sees the updated list.
6. Record when LoadBalancer stops picking that instance.
7. Repeat while Eureka Server is temporarily unreachable.
8. Compare failed request counts when the consumer uses cache versus registry recovery duration.

Do not draw conclusions from a single trial. Repeat with varying consumer and instance counts to observe load effects.

## 17. Practical Consul Configuration and Testing

Spring Cloud Consul example:

    spring:
      cloud:
        consul:
          discovery:
            query-passing: true
            consistency-mode: default
            catalog-services-watch-delay: 1000
            catalog-services-watch-timeout: 2

`query-passing=true` instructs service health queries to return only passing instances. `consistency-mode` controls the consistency mode for health service requests according to the Spring Cloud Consul implementation and version in use. Catalog watch uses blocking queries to monitor catalog changes.

With the raw Consul HTTP API, you can compare modes:

    curl "http://consul:8500/v1/health/service/inventory-service"
    curl "http://consul:8500/v1/health/service/inventory-service?stale"
    curl "http://consul:8500/v1/health/service/inventory-service?consistent"

When testing, record the `X-Consul-Effective-Consistency` response header if the endpoint returns it to verify the actual mode used.

Do not set `consistent` mode for all queries just to obtain fresh data. Strong reads add overhead and depend on quorum. Nor should you enable `stale` mode everywhere if consumers cannot handle stale instances.

## 18. Measuring Propagation Delay and Cost

A benchmark should capture these milestones:

- T0: application calls register, deregister, or status change.
- T1: registry confirms the change.
- T2: response cache or follower reflects the change.
- T3: consumer `DiscoveryClient` observes the change.
- T4: LoadBalancer stops selecting the old instance or begins selecting the new one.
- T5: first real request follows the new topology.

Metrics:

    registry_write_latency = T1 - T0
    registry_replication_delay = T2 - T1
    consumer_discovery_delay = T3 - T1
    load_balancer_propagation_delay = T4 - T1
    end_to_end_topology_delay = T5 - T0

These are custom-instrumented benchmark metrics, not built-in default metric names in Eureka or Consul.

Also measure:

- Request rate to the registry.
- Average and p95 response sizes.
- Registry CPU, heap, GC, and network usage.
- Fetch, delta fetch, and full reconciliation counts.
- Open blocking query count and timeout rate.
- Consumer-side lookup latency and errors.
- Rate of requests routed to instances removed from the pool.
- Number of instances returned per query.

Test with different polling intervals, cache TTLs, and consistency modes. Keep topology, consumer count, and workload constant for fair comparison.

## 19. Troubleshooting Persistent Stale Data

When consumers still see old instances, check in order:

1. Has the registry accepted the deregistration or status change?
2. With Consul, are leader/followers converging and what consistency mode does the query use?
3. With Eureka, are client delta fetches succeeding or is it stuck on an old cache?
4. Is the registry-side response cache waiting to refresh?
5. Does `DiscoveryClient` or an adapter hold its own cache?
6. Does LoadBalancer have a `ServiceInstanceListSupplier` cache?
7. Does the consumer have a DNS cache or connection pool holding old addresses?
8. Is the instance being re-registered by an agent, orchestrator, or another process?

If the registry is already correct while the consumer is stale, do not repeatedly delete the registration. Focus on caching and refresh paths. If the registry itself is wrong, inspect replication, quorum, heartbeats, self-preservation, or the registration owner.

When the registry lacks quorum, understand how each mode responds. Consul consistent reads may fail to respond if quorum cannot be verified; stale reads may still reply from servers holding older data. The choice depends on whether consumers can tolerate stale data or must reject requests.

## 20. Design Principles

- Set freshness budgets based on the business impact of each service.
- Use caching to preserve serving capability during short registry faults, while monitoring cache age.
- Use deltas or blocking queries to lower polling cost when appropriate.
- Require consistent reads only for queries that truly cannot tolerate stale results.
- Distinguish between Consul DNS and HTTP API behaviors.
- Monitor Eureka self-preservation and full reconciliations.
- Inspect both `DiscoveryClient` caches and LoadBalancer caches.
- Use timeouts, bounded retries, and circuit breakers when an instance disappears after selection.
- Drain instances cleanly before deregistering and allow time for propagation.
- Do not treat the registry as a source of truth for transactions or business authorization.
- Measure end-to-end latency from registration change to live requests.
- Test network partitions, registry outages, leader elections, and stale caches before deployment.

## 21. Conclusion

List freshness, availability, and synchronization cost are related yet distinct objectives. Eureka uses local registry caching and delta fetches to cut lookup overhead while continuing to serve from cache during server interruptions. Consul offers consistency modes for the HTTP API—stale reads to boost read capacity and consistent reads at quorum cost—while blocking queries avoid unnecessary polling.

Do not choose a configuration solely out of a desire for an always-fresh list. Define your freshness budget, decide between fail-open and fail-closed when the registry fails, measure caching and propagation delay across all layers, and then balance polling, deltas, blocking queries, and consistency modes per service. Discovery only supplies routing metadata; applications still need to tolerate stale instances via timeouts, retries, circuit breakers, and proper error handling.

## References

- [Netflix Eureka — Understanding Client/Server Communication](https://github.com/Netflix/eureka/wiki/Understanding-eureka-client-server-communication)
- [Spring Cloud Netflix — Configuration Properties](https://docs.spring.io/spring-cloud-netflix/reference/configprops.html)
- [HashiCorp Consul — Consistency Modes](https://developer.hashicorp.com/consul/api-docs/features/consistency)
- [HashiCorp Consul — Blocking Queries](https://developer.hashicorp.com/consul/api-docs/features/blocking)
- [HashiCorp Consul — Agent Caching](https://developer.hashicorp.com/consul/api-docs/features/caching)
- [Spring Cloud Consul — Common Application Properties](https://docs.spring.io/spring-cloud-consul/reference/appendix.html)
- [Spring Cloud Consul — Service Discovery and Catalog Watch](https://docs.spring.io/spring-cloud-consul/reference/discovery.html)
- [Spring Cloud LoadBalancer — Caching](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
