# Managing Tenants Without Creating Unbounded Instances

In a multi-tenant application, many customers may call the same dependent service such as Catalog, Inventory, or Payment. Each tenant has its own data and access permissions, yet not every tenant needs its own Circuit Breaker. If you append the tenant ID to the Circuit Breaker name for every request, the instance count can grow with the number of tenants without a clear bound. As a result, the registry, sliding windows, metrics, and memory grow continuously, while each instance receives too few samples to evaluate dependency health.

Proper design starts by distinguishing **tenant identity** from **Circuit Breaker ID**. Tenant identity identifies the customer and data scope; Circuit Breaker ID identifies the dependency or operation that shares a failure domain and protection policy. When multiple tenants share a backend, a stable breaker per operation accurately reflects backend health. When the backend is genuinely divided into independent failure domains, a finite number of breakers per shard or deployment region can be used.

## 1. Tenant ID and Circuit Breaker ID serve two purposes

Tenant ID varies by the customer or organization sending the request. Circuit Breaker ID should remain stable by the dependency or operation the application wants to protect.

| Identifier | Example | Purpose |
|---|---|---|
| Tenant ID | **tenant-4821** | Identifies customer, access permissions, and data scope |
| Circuit Breaker ID | **catalog-read** | Shares state and sliding window for Catalog read calls |
| Operation | **reserve-stock** | Describes the protected operation |
| Backend shard | **inventory-eu-1** | Identifies an independent failure domain if infrastructure is genuinely partitioned |
| Trace ID | A unique code per request or trace | Links logs and spans of a single execution |

A product read request may carry tenant ID **tenant-4821**, SKU **SKU-001**, and its own trace ID. If all tenants call the same Catalog cluster, the call still uses Circuit Breaker ID **catalog-read**. The tenant and SKU parameters go into the call's supplier; they do not need to be concatenated into the breaker name.

Do not use names like **catalog-tenant-4821**, **catalog-tenant-4822**, or **inventory-order-90001** per request. Each new name can create an additional instance and statistics window. This naming fragments outcomes, increases metric cardinality, and can leave the registry holding many unused states.

## 2. Why you should not create one Circuit Breaker per tenant

Suppose a SaaS platform has 50,000 tenants all calling one Catalog cluster. If each tenant had its own Circuit Breaker, the application could create up to 50,000 instances for just a single operation.

That approach causes several issues:

- **Increased memory and management overhead:** each instance holds its own configuration, state, sliding window, and supporting structures.
- **Sample fragmentation:** a low-traffic tenant may never reach **minimumNumberOfCalls**, leaving the breaker without enough data to evaluate.
- **High metric cardinality:** each breaker name can become a new metric group or time series.
- **Operational difficulty:** dashboards and alerts must handle tens of thousands of constantly changing states.
- **Abuse risk:** if instance names are derived from request data, a flood of tenants or spoofed values can force the application to allocate unbounded state.
- **Poor reflection of shared backend failures:** if Catalog fails for all tenants, per-tenant instances may open at different times or fail to open because each instance has too few samples.

A Circuit Breaker is meant to protect a dependency from calls when the dependency degrades. If multiple tenants depend on the same backend, observing shared outcomes detects failures earlier and prevents cascading load.

## 3. Using a stable Circuit Breaker when the backend is shared

When all tenants call the same service or cluster sharing a failure domain, use one Circuit Breaker for each operation that needs protection.

Example application reading Catalog for multiple tenants:

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
class CatalogGateway {

    private static final String CATALOG_READ = "catalog-read";

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final CatalogClient catalogClient;
    private final ProductCache productCache;

    CatalogGateway(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            CatalogClient catalogClient,
            ProductCache productCache) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.catalogClient = catalogClient;
        this.productCache = productCache;
    }

    Product getProduct(
            TenantId tenantId,
            String sku) {
        return circuitBreakerFactory.create(CATALOG_READ).run(
            () -> catalogClient.getProduct(tenantId, sku),
            error -> productCache.find(tenantId, sku)
                .orElseThrow(() ->
                    new CatalogUnavailableException(tenantId, sku, error)
                )
        );
    }
}
~~~

All tenants use the fixed name **catalog-read**. The supplier still passes the tenant ID and SKU to the client so the backend enforces authorization and queries the right data. The fallback queries the cache by both tenant ID and SKU to avoid returning another customer's data.

If Catalog fails cluster-wide, error outcomes from multiple tenants contribute together to the **catalog-read** sliding window. Once the threshold is reached, the breaker transitions to OPEN and blocks new calls to the dependency. This is the appropriate behavior when an outage genuinely affects the shared backend.

Ensure the tenant ID comes from a trusted authentication context, such as a verified principal or security context. Never trust an arbitrary client-supplied header to access another tenant's data. A Circuit Breaker does not replace authentication, authorization, or data isolation mechanisms.

## 4. Configuring one instance for a shared operation

The instance name in Resilience4j must match the ID passed to the factory:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      catalog-read:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 100
        minimumNumberOfCalls: 30
        failureRateThreshold: 50
        slowCallDurationThreshold: 800ms
        slowCallRateThreshold: 60
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 5
~~~

This configuration creates a shared window for the Catalog read operation. The values in this example are illustrative only; tune them to traffic volume, normal latency, and backend capacity.

If the application has multiple distinct operations, you can use one stable instance per operation:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      catalog-read:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 100
        minimumNumberOfCalls: 30
        failureRateThreshold: 50
        waitDurationInOpenState: 15s

      catalog-search:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 60
        minimumNumberOfCalls: 20
        failureRateThreshold: 40
        waitDurationInOpenState: 20s

      inventory-reserve:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 30
        minimumNumberOfCalls: 15
        failureRateThreshold: 40
        waitDurationInOpenState: 20s
~~~

The IDs above are finite and operation-oriented. They do not grow as tenants or requests grow. Reading products, searching, and reserving stock may require different policies because their SLAs and error semantics differ; splitting by operation preserves meaningful evaluation scope.

Do not split a Circuit Breaker merely to have a separate chart per tenant. If you need error rates per tenant, use logs, traces, or metrics with controlled cardinality; do not turn every tenant into an independent state machine when the backend remains a shared failure domain.

## 5. When should you split by shard or region?

In some cases, tenants do not share a single backend. For example, a platform routes tenants to independent Inventory clusters by region or shard. If one shard fails, the other shards continue operating normally. In that situation, a single shared Circuit Breaker for all of Inventory could open too broadly and block requests heading to healthy backends.

You can create a finite number of instances corresponding to actual failure domains:

| Backend failure domain | Circuit Breaker ID |
|---|---|
| Inventory shard EU-1 | **inventory-eu-1** |
| Inventory shard AP-1 | **inventory-ap-1** |
| Inventory shard US-1 | **inventory-us-1** |

The instance count is bounded by the number of deployed shards, not the number of tenants. A tenant is mapped to a shard by a router or service discovery; the application then selects the corresponding Circuit Breaker.

Example using an enum to constrain the set of valid names:

~~~java
enum InventoryShard {
    EU_1("inventory-eu-1"),
    AP_1("inventory-ap-1"),
    US_1("inventory-us-1");

    private final String breakerId;

    InventoryShard(String breakerId) {
        this.breakerId = breakerId;
    }

    String breakerId() {
        return breakerId;
    }
}
~~~

The service receives the shard determined by the resolver from tenant routing:

~~~java
@Service
class ShardedInventoryGateway {

    private final CircuitBreakerFactory<?, ?> factory;
    private final InventoryRouter inventoryRouter;
    private final InventoryClient inventoryClient;

    ShardedInventoryGateway(
            CircuitBreakerFactory<?, ?> factory,
            InventoryRouter inventoryRouter,
            InventoryClient inventoryClient) {
        this.factory = factory;
        this.inventoryRouter = inventoryRouter;
        this.inventoryClient = inventoryClient;
    }

    Stock getStock(TenantId tenantId, String sku) {
        InventoryShard shard = inventoryRouter.resolve(tenantId);

        return factory.create(shard.breakerId()).run(
            () -> inventoryClient.getStock(shard, tenantId, sku),
            error -> Stock.unavailable(sku)
        );
    }
}
~~~

In this example, **InventoryRouter** only returns a value from the defined enum. The Circuit Breaker ID is never taken directly from the raw tenant ID string. When adding a new shard, the development team adds a controlled identifier value and its corresponding configuration.

Only split by shard when shards genuinely have independent failure modes. If multiple shards still depend on the same database, DNS, network gateway, or shared service, consider adding a protection layer for the shared dependency. Over-splitting can hide failures of a shared component across separate windows.

## 6. Do not use tenant tier as a failure domain if the backend is still shared

Another pattern is grouping tenants into tiers such as Free, Standard, and Enterprise. Teams may want to apply different quotas or concurrency limits per service tier. However, do not default to creating separate Circuit Breakers per tier.

If every tier still calls the same Catalog cluster, Catalog failures affect everyone. Splitting breakers by tier leaves each window receiving only a fraction of the traffic and causes them to open at different times. One group could keep sending requests to a failing backend simply because its own breaker has not accumulated enough samples.

Separate responsibilities clearly:

- Circuit Breaker monitors the health of a dependency or failure domain.
- Rate limiter or quota controls usage per tenant or service tier.
- Bulkhead limits concurrent resources so one workload group does not exhaust processing capacity.
- Authorization and tenant routing control access permissions and where data lives.

If service tiers are genuinely served by physically isolated backend clusters, then separate per-cluster breakers can be used. Base the decision on deployment architecture and blast radius, not merely on a tenant's commercial label.

## 7. Controlling noisy-neighbor tenants with quotas and Bulkheads

One tenant may generate heavy traffic or send many slow requests, impacting other tenants. A shared Circuit Breaker detects backend degradation, but does not provide per-tenant resource fairness. To limit individual customer usage, use dedicated quota or rate-limiting mechanisms.

A Bulkhead can limit concurrent tasks to a dependency or resource group. In a multi-tenant system, you can design finite pools or limits by service tier, shard, or workload. Do not create an unbounded thread pool or Bulkhead per tenant.

Example division of responsibilities:

| Mechanism | Scope | Goal |
|---|---|---|
| Circuit Breaker **catalog-read** | Shared Catalog dependency | Stop calling a failing backend |
| Rate limit | Tenant or API key | Limit request rate per customer |
| Bulkhead | Finite operation or resource group | Limit concurrent executions |
| Queue limit | Worker pool or shard | Prevent unbounded queue growth |
| Tenant authorization | Requests and data | Prevent cross-tenant access |

Per-tenant rate limiting may need to store separate state, but that mechanism must have clear capacity bounds, TTLs, and cleanup policies. Do not repurpose the Circuit Breaker registry as a per-tenant quota store. The two mechanisms have different goals and lifecycles.

## 8. Fallbacks and caches must preserve tenant boundaries

Sharing a Circuit Breaker does not mean sharing fallback data. When Catalog is unavailable, the fallback must still look up data for the right tenant.

Example cache key that includes the tenant ID:

~~~java
Optional<Product> find(TenantId tenantId, String sku) {
    return cache.get(
        tenantId.value() + ":product:" + sku,
        Product.class
    );
}
~~~

If only SKU is used as the key while tenants have different catalogs, pricing, or visibility permissions, the fallback could return another tenant's data. That is a severe data isolation bug.

Fallbacks must follow these rules:

- Tenant ID is authenticated before querying the cache.
- Cache keys include the tenant ID or equivalent tenant namespace.
- Fallback data respects tenant access permissions.
- Cache retention aligns with business rules and stale-data policies.
- If no valid data exists, return an unavailable error instead of fabricating business results.

The Circuit Breaker protects the call path to the dependency; it does not by itself guarantee that caches, data, or fallbacks respect tenant isolation.

## 9. Keeping metrics at finite cardinality

Metrics are a major reason to avoid dynamic Circuit Breaker names. Many monitoring systems create time series based on instance names and tags. If every tenant ID becomes a breaker name or tag, the number of time series can multiply by the number of tenants and operations.

Use bounded-cardinality dimensions:

- Circuit Breaker name by dependency or operation.
- Shard or region if the number of shards is finite.
- Call outcome: success, failure, ignored, not permitted.
- Error type normalized into a finite set of values.
- Environment or deployment version when comparisons are needed.

Tenant ID can be useful in logs or traces for investigating specific requests. However, do not put tenant ID, user ID, order ID, SKU, or trace ID into high-cardinality metric tags. If per-tenant statistics are required, use an analytics system or bounded aggregation tables with appropriate sampling and retention policies.

Example log that keeps both the breaker ID and tenant ID:

~~~java
log.warn(
    "Circuit Breaker {} rejected request for tenant={}, sku={}",
    "catalog-read",
    tenantId.value(),
    sku
);
~~~

On dashboards, metrics remain grouped by **catalog-read**; logs or traces allow locating a specific tenant during an incident. This separation keeps operational metrics stable while still supporting investigation.

## 10. When dedicated Circuit Breakers are genuinely needed for specific tenants

Some systems have large enterprise customers deployed on dedicated backends or special isolation requirements. In such cases, dedicated breakers may make sense, provided these conditions are met:

1. The number of tenants granted dedicated breakers is finite and managed through provisioning.
2. Each tenant corresponds to an independent failure domain or has genuinely different protection policies.
3. Instance names are built from a controlled allowlist of identifiers, not arbitrary request input.
4. There is a cap on total instances and active count monitoring.
5. There is a clear lifecycle process when a tenant is decommissioned.
6. There is a plan for handling state when instances are evicted and recreated.
7. Metrics and dashboards do not produce cardinality beyond storage capacity.

Do not simply add an unbounded cache to hold per-tenant Circuit Breakers and treat it as safe. If eviction is used, understand that evicting an instance also discards its OPEN state and sliding window. When the instance is recreated, the breaker can start fresh in its initial state and send requests to a failing dependency. Eviction is therefore a protection-semantics decision, not merely a memory optimization.

If dynamic instance management is unavoidable, cap the count, control creation privileges, define expiration rules, and handle state removal explicitly. Prefer pre-provisioning for a finite set of tenants rather than auto-creating instances for every tenant seen in traffic.

## 11. Testing multi-tenant designs

The test suite should verify both data isolation and the sharing scope of Circuit Breaker state.

| Test | Condition | Expected verification |
|---|---|---|
| Multiple tenants sharing a backend | Tenant A and B call Catalog | Both use the **catalog-read** ID |
| Varying tenant IDs | Send requests from many different tenants | Circuit Breaker instance count does not grow with tenants |
| Shared backend failing | Requests from multiple tenants receive technical errors | Same sliding window reflects backend health |
| Circuit Breaker OPEN | Call from another tenant while shared breaker is OPEN | No further requests sent to the backend |
| Fallback | Two tenants have the same SKU but different data | Cache returns the right tenant's data |
| Independent shards | Tenant A on EU shard, tenant B on AP shard | Each shard uses its respective finite breaker ID |
| Noisy-neighbor tenant | One tenant exceeds quota | That tenant is throttled without creating a new breaker |
| Metrics | Generate traffic for many tenants | Cardinality does not grow with tenant ID |
| Deactivated tenant | Tenant is no longer authorized | Authorization blocks request; no need to create or keep a new breaker |

Use integration tests with a real Circuit Breaker to verify state and actual calls reaching the client. Mocking the factory only verifies that the service passes the right ID and arguments; it does not prove the registry avoids unintended instances or actually shares state.

An important test is sending requests with different tenant IDs targeting the same backend, then verifying all use the same breaker ID. Next, induce enough errors to open the circuit and confirm requests from another tenant are also rejected when they share the failure domain. This intentional sharing behavior must be clearly documented in operational contracts.

## 12. Practical scenario

A SaaS platform has 20,000 tenants. All tenants share a Catalog cluster, while Inventory is deployed across three independent regional shards.

Selected design:

- Catalog uses one Circuit Breaker **catalog-read** for all tenants.
- Inventory uses three finite Circuit Breakers: **inventory-eu-1**, **inventory-ap-1**, and **inventory-us-1**.
- Tenant ID is used for authentication, routing, cache keys, and tracing.
- Quotas are managed separately per tenant.
- Bulkheads limit concurrent load of operations.
- Circuit Breaker metrics only use finite-cardinality instance names, shards, and outcome types.

When Catalog experiences an outage, **catalog-read** records failures from shared traffic and transitions to OPEN per its threshold. Requests from all tenants are protected by the same breaker. When Inventory shard EU-1 fails, only **inventory-eu-1** changes state; tenants routed to AP-1 or US-1 continue using their respective shard breakers.

If one tenant generates excessive traffic, quotas throttle that tenant. The Circuit Breaker still reflects backend condition rather than one tenant's usage. The Catalog fallback uses a cache key containing both tenant ID and SKU to preserve data isolation.

After deployment, verify:

1. The Catalog instance count stays at one regardless of how many tenants send traffic.
2. The Inventory instance count does not exceed the number of provisioned shards.
3. Circuit Breaker IDs never contain tenant IDs or request IDs.
4. Caches and fallbacks always preserve tenant namespaces.
5. Quotas and Bulkheads control noisy neighbors independently of Circuit Breakers.
6. Metrics maintain finite cardinality while logs/traces still allow per-tenant request investigation.

## Conclusion

Safe multi-tenant management requires separating tenant identity from Circuit Breaker ID. When multiple tenants share a backend, use stable Circuit Breakers by dependency or operation to share state and sliding windows. Only split breakers by shard or region when they represent independent failure domains and a finite number of partitions. Use quotas, rate limits, and Bulkheads to control per-tenant load; keep tenant IDs in authentication, cache keys, and tracing, while avoiding putting them into instance names or high-cardinality metric tags.
