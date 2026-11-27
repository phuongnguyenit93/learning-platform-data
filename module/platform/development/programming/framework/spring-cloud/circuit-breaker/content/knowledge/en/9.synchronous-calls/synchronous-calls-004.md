# Passing Parameters and Mapping Results Without Creating Per-Request IDs

When protecting synchronous calls with Spring Cloud CircuitBreaker and Resilience4j, each Circuit Breaker needs a stable ID representing the dependent service or protected operation. Per-request parameters such as product ID, warehouse code, order ID, or user ID are passed into the service call inside the supplier. Values that vary per request should not be concatenated into the Circuit Breaker ID.

This organization allows calls to the same service to share a single `CLOSED`, `OPEN`, or `HALF_OPEN` state and the same sliding window. The application can still pass full parameters, receive the response, map the response to a domain model, and handle per-request fallbacks. This is an essential technique when implementing synchronous Circuit Breakers to prevent cascading failures without fragmenting observability metrics.

## 1. Distinguishing Circuit Breaker IDs from Request Parameters

A Circuit Breaker ID identifies a group of calls that share the same protection policy. For example, an ordering application might use stable IDs such as:

| Circuit Breaker ID | Protected Scope |
|---|---|
| **inventory-read** | Reading stock quantities from the Inventory service |
| **inventory-reserve** | Sending stock reservation requests to the Inventory service |
| **catalog-product** | Fetching product details from the Catalog service |
| **payment-authorize** | Requesting payment authorization from the Payment service |

Per-request parameters are input data for that operation, for example:

- **sku:** the product code to look up.
- **warehouseCode:** the warehouse code to check.
- **orderId:** the order ID being processed.
- **quantity:** the quantity to reserve.
- **traceId:** a correlation identifier for tracing logs of one request across services.

Calls can use the **inventory-read** ID while passing different parameter pairs such as (SKU-001, HN-01) or (SKU-002, HCM-02). Both calls still go through the same Circuit Breaker because they depend on the same inventory read operation and need to be protected under the same policy.

Avoid creating IDs like **inventory-read-SKU-001**, **inventory-read-SKU-002**, or **inventory-read-order-12345**. Creating a separate Circuit Breaker for each product or order splits state and sliding windows. Each instance receives only a tiny fraction of traffic, making it difficult to reach the minimum sample size for failure-rate evaluation; metrics also explode in cardinality based on business data.

## 2. Passing Parameters Through the Synchronous Call Supplier

Spring Cloud CircuitBreaker's blocking API lets you pass a supplier containing the operation to protect. The supplier is executed when the Circuit Breaker permits the call. The lambda can capture the current method's input variables:

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
class InventoryGateway {

    private static final String INVENTORY_READ = "inventory-read";

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final InventoryClient inventoryClient;

    InventoryGateway(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            InventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    InventoryResponse getInventory(String sku, String warehouseCode) {
        return circuitBreakerFactory.create(INVENTORY_READ).run(
            () -> inventoryClient.getInventory(sku, warehouseCode),
            error -> InventoryResponse.unavailable(sku, warehouseCode)
        );
    }
}
~~~

In this example:

1. **INVENTORY_READ** is the fixed Circuit Breaker ID.
2. **sku** and **warehouseCode** are parameters specific to the current request.
3. The supplier invokes the client with those exact parameters.
4. If the Circuit Breaker is `OPEN`, the supplier is not executed and the fallback function is called.
5. The fallback response can carry information about the SKU and warehouse so the calling layer can handle it according to business logic.

Each invocation of **getInventory** can create a new lambda capturing different SKU and warehouse values. This does not create a new Circuit Breaker. The factory receives the same **inventory-read** ID, so the calls continue sharing the state and configuration of the same breaker.

If the client takes multiple parameters, pass them through a clear client method signature. There is no need to concatenate them into an ID string, nor to store parameters in a global variable for the Circuit Breaker to access. The supplier already captures the values needed for that execution.

## 3. Using a Stable ID to Share a Single Sliding Window

A Circuit Breaker relies on the outcomes of previous calls to decide state transitions. When the ID stays stable per dependency or operation, calls of the same kind contribute to the same evaluation window.

Suppose **inventory-read** has the following configuration:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory-read:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 3
~~~

If the first ten inventory read calls are made with various SKUs and warehouses, they are still recorded in the same **inventory-read** instance. Once the minimum sample threshold is met, the Circuit Breaker can evaluate the failure rate across the shared result set. If the failure rate reaches the threshold, subsequent inventory read calls are rejected during the `OPEN` period regardless of which SKU a request asks for.

This is the desired behavior when an incident affects the Inventory service or its shared network path. If a single SKU causes a business error because it does not exist, handle it as an appropriate business outcome rather than treating it as a health failure of the entire service.

If two dependent operations have different characteristics—such as reading stock and reserving stock—use two separate stable IDs. Both may call the same Inventory service, yet differ in endpoint, SLA, traffic volume, and error semantics. An ID should represent the scope the application wants to measure and protect.

## 4. Mapping Responses to a Domain Model

A dependent service often returns its own DTO or response structure. The application layer can map that response into a domain model so upstream components do not depend on external API shapes.

For example, Inventory returns **InventoryResponse**, while ordering logic uses **StockAvailability**:

~~~java
record InventoryResponse(
    String sku,
    String warehouseCode,
    int availableQuantity,
    String sourceStatus
) {}

record StockAvailability(
    String productCode,
    String warehouse,
    int quantityAvailable,
    boolean available
) {}

class InventoryMapper {

    StockAvailability toDomain(InventoryResponse response) {
        return new StockAvailability(
            response.sku(),
            response.warehouseCode(),
            response.availableQuantity(),
            response.availableQuantity() > 0
        );
    }
}
~~~

There are two common places to perform mapping. Choosing where depends on whether mapping errors should count as failures of the protected call.

### Mapping Inside the Supplier

If an invalid or unmappable response is considered a contract failure of the dependent service, mapping can be done directly inside the supplier:

~~~java
StockAvailability getAvailability(String sku, String warehouseCode) {
    return circuitBreakerFactory.create(INVENTORY_READ).run(
        () -> inventoryMapper.toDomain(
            inventoryClient.getInventory(sku, warehouseCode)
        ),
        error -> StockAvailabilityUnavailable.forItem(sku, warehouseCode)
    );
}
~~~

In this case, the supplier succeeds only if both the client call and the mapping step succeed. Exceptions thrown during mapping can also be recorded by the Circuit Breaker as failures of the protected execution. This approach fits when mapping errors indicate that the dependent service's response violated the contract expected by the application.

### Mapping After the Supplier Completes

If you want the Circuit Breaker to measure only the outcome of calling the dependent service, retrieve the response first and map it outside:

~~~java
StockAvailability getAvailability(String sku, String warehouseCode) {
    InventoryResponse response =
        circuitBreakerFactory.create(INVENTORY_READ).run(
            () -> inventoryClient.getInventory(sku, warehouseCode),
            error -> {
                throw new InventoryUnavailableException(
                    sku, warehouseCode, error
                );
            }
        );

    return inventoryMapper.toDomain(response);
}
~~~

Here, the Circuit Breaker protects the client call. If mapping fails after the client returned successfully, the mapping exception is not counted toward this Circuit Breaker's outcomes. This fits when mapping errors represent local application issues, such as a mapper bug or an invalid internal transformation rule.

If a malformed response indicates the dependent service returned corrupt data, mapping or contract validation can be placed inside the supplier so those errors count toward protection outcomes. Decide the exact measurement boundary intentionally rather than arbitrarily placing all processing inside or outside the supplier.

## 5. Mapping Fallbacks to the Same Result Type

With the synchronous API, the supplier and fallback must return compatible result types. If the supplier returns **InventoryResponse**, the fallback must also return **InventoryResponse** or throw an appropriate exception. If the supplier returns **StockAvailability**, the fallback must return **StockAvailability**.

Example using a cache as fallback data:

~~~java
InventoryResponse getInventory(
        String sku,
        String warehouseCode) {

    return circuitBreakerFactory.create(INVENTORY_READ).run(
        () -> inventoryClient.getInventory(sku, warehouseCode),
        error -> inventoryCache.find(sku, warehouseCode)
            .orElseThrow(() ->
                new InventoryUnavailableException(
                    sku, warehouseCode, error
                )
            )
    );
}
~~~

The cache is queried with the exact parameters of the current request. The Circuit Breaker ID remains **inventory-read**. If the cache holds an entry, the cached response is returned with the same type as the client response. If not, the fallback throws a business exception so upper layers can translate it into an appropriate response.

Do not return an empty DTO or a quantity of zero if it could be misinterpreted as the warehouse genuinely being out of stock. Fallback data should convey the unavailable status, cache timestamp, or data source if the business requires distinguishing them. For example, **unavailable** differs from **availableQuantity = 0**: the former means inventory could not be determined, whereas the latter means the warehouse was confirmed to have zero stock.

The fallback receives the failure cause via the **error** parameter. You can distinguish Circuit Breaker rejections, timeouts, and client errors to log or pick an appropriate fallback source:

~~~java
error -> {
    if (error instanceof CallNotPermittedException) {
        log.warn("Inventory is protected by Circuit Breaker, sku={}", sku);
    } else {
        log.warn("Failed to fetch inventory, sku={}", sku, error);
    }

    return inventoryCache.find(sku, warehouseCode)
        .orElseThrow(() ->
            new InventoryUnavailableException(sku, warehouseCode, error)
        );
}
~~~

Do not treat every error as an `OPEN` state. **CallNotPermittedException** indicates the call was rejected by the breaker; timeouts and client errors are distinct conditions that should be differentiated during monitoring.

## 6. Keeping Correlation IDs Separate from Circuit Breaker IDs

In distributed systems, a single request often traverses multiple services. A **traceId** or **correlationId** links logs belonging to the same request, while a Circuit Breaker ID identifies the protected group of calls. The two identifiers serve different purposes.

| Identifier | Lifecycle | Purpose |
|---|---|---|
| Circuit Breaker ID | Stable per dependency or operation | State, sliding window, configuration, and metrics |
| traceId / correlationId | Varies per request or trace | Log correlation and execution tracing |
| orderId | Per order | Business data and order lookup |
| sku | Per product | Query parameter for inventory or Catalog |

For example, a request with **traceId = 7f3a...** calls Inventory with **sku = SKU-001**. Logs can record all three pieces of information:

~~~java
log.info(
    "Calling Circuit Breaker {}, traceId={}, sku={}",
    INVENTORY_READ,
    traceId,
    sku
);
~~~

Circuit Breaker metrics remain tied solely to the stable ID **inventory-read**. Do not turn `traceId`, `orderId`, or SKU into instance names or metric tags. Placing high-cardinality changing values into tags causes monitoring systems to create massive numbers of time series, increasing memory and storage overhead.

In applications using tracing or logging context, `traceId` can be populated automatically into MDC or trace spans. Request tracing should rely on that mechanism, while the Circuit Breaker ID remains dedicated to aggregating dependency health.

## 7. Validating Inputs Before Calling the Service

Input validation errors usually do not reflect the health of a dependent service. If the SKU is blank or the quantity is invalid, validate before invoking the Circuit Breaker:

~~~java
StockAvailability reserveStock(
        String sku,
        String warehouseCode,
        int quantity) {

    if (sku == null || sku.isBlank()) {
        throw new IllegalArgumentException("sku must not be blank");
    }
    if (warehouseCode == null || warehouseCode.isBlank()) {
        throw new IllegalArgumentException(
            "warehouseCode must not be blank"
        );
    }
    if (quantity <= 0) {
        throw new IllegalArgumentException(
            "quantity must be greater than 0"
        );
    }

    InventoryResponse response =
        circuitBreakerFactory.create("inventory-reserve").run(
            () -> inventoryClient.reserve(
                sku,
                warehouseCode,
                quantity
            ),
            error -> {
                throw new InventoryUnavailableException(
                    sku, warehouseCode, error
                );
            }
        );

    return inventoryMapper.toDomain(response);
}
~~~

In this example, parameter validation runs before the supplier. Therefore, invalid input never triggers a call to Inventory and does not raise the Circuit Breaker's failure rate. When inputs are valid, the supplier forwards those values to the client.

If the dependent service returns a business error such as "insufficient stock", classify it according to the API contract. Business errors can be returned as valid responses or dedicated exceptions. Avoid letting normal business errors inflate the failure rate if the Circuit Breaker policy is meant to reflect infrastructure failures or dependency availability. Resilience4j allows configuring which exception types are recorded or ignored; configure this according to the client's semantics.

## 8. Do Not Create Dynamic IDs in Loops or Per Record

A common mistake is creating a Circuit Breaker inside a loop using a name concatenated from data:

~~~java
// Avoid: creating a separate Circuit Breaker identifier per SKU.
for (String sku : skuList) {
    String breakerId = "inventory-" + sku;
    circuitBreakerFactory.create(breakerId).run(
        () -> inventoryClient.getInventory(sku),
        error -> InventoryResponse.unavailable(sku, "DEFAULT")
    );
}
~~~

This causes the number of instances to grow with the number of SKUs. If the system has hundreds of thousands of SKUs, the factory and registry can retain a huge number of Circuit Breakers. Each instance has its own sliding window, yet traffic per SKU may be too low to reach **minimumNumberOfCalls**. Consequently, the protection mechanism lacks sufficient data to assess the overall health of Inventory.

The proper approach is to keep a single ID for the inventory read operation:

~~~java
for (String sku : skuList) {
    circuitBreakerFactory.create(INVENTORY_READ).run(
        () -> inventoryClient.getInventory(sku),
        error -> InventoryResponse.unavailable(sku, "DEFAULT")
    );
}
~~~

Each supplier still holds the SKU specific to that iteration, while all calls share the **inventory-read** ID. If you need per-tenant or per-product rate limiting, use a properly designed rate limiter or quota mechanism; do not turn the Circuit Breaker into a registry keyed by business entities.

## 9. Choosing ID Scope by Service and Operation

A stable ID does not necessarily have to represent an entire service host. Choose the scope based on the unit the application wants to monitor and protect.

For example, the same Inventory service may expose two endpoints:

- Inventory reads typically carry high traffic and require low latency.
- Stock reservations mutate data state and have different SLAs and retry policies.

You can define two IDs, **inventory-read** and **inventory-reserve**, to isolate state and metrics. However, do not split so granularly that every SKU, warehouse, user, or order gets its own ID.

When choosing an ID, ask yourself:

1. Do these calls target the same dependency or operation?
2. Should they share the same failure threshold, timeout, and sliding window?
3. When one group of calls fails, should the other group be blocked too?
4. Is the number of IDs fixed and manageable?

If two operations require different protection policies, separate their stable IDs. If they differ only in input parameters while sharing the same dependency and behavior, keep a shared ID.

## 10. Practice Scenario

An order service receives inventory check requests containing **sku**, **warehouseCode**, and **orderId**. A synchronous client calls the Inventory service. The application needs to protect all inventory read calls with the **inventory-read** Circuit Breaker.

Suppose three requests arrive:

| Request | SKU | Warehouse | Order |
|---|---|---|---|
| A | SKU-001 | HN-01 | ORD-1001 |
| B | SKU-002 | HCM-02 | ORD-1002 |
| C | SKU-003 | HN-01 | ORD-1003 |

All three requests invoke:

~~~java
circuitBreakerFactory.create("inventory-read").run(
    () -> inventoryClient.getInventory(sku, warehouseCode),
    error -> inventoryCache.find(sku, warehouseCode)
        .orElseThrow(() ->
            new InventoryUnavailableException(sku, warehouseCode, error)
        )
);
~~~

There is only one Circuit Breaker ID, **inventory-read**. Each supplier captures the SKU and warehouse values for its respective request. **orderId** can be recorded in logs or trace context for traceability, but it does not participate in forming the Circuit Breaker name.

If request A succeeds, request B fails due to a timeout, and request C succeeds, the outcomes are recorded into the same instance according to the configured policy. Once enough samples accumulate, the Circuit Breaker evaluates the failure rate across all inventory read calls. If it transitions to `OPEN`, subsequent requests are rejected before the client is called; the fallback uses the cache or throws a business exception according to policy.

While practicing, make sure you can identify:

- Which ID is the stable identifier for the protected operation.
- Which parameters are passed into each request's supplier.
- Which response is mapped to the domain model and whether mapping sits inside or outside the supplier.
- Whether the fallback returns the same data type or which exception it throws.
- Where `traceId` and `orderId` are logged without increasing the number of Circuit Breaker instances.
- Which outcomes are recorded into the shared sliding window.

## Conclusion

For synchronous calls, use a stable Circuit Breaker ID for each dependent service or protected operation. Pass request-varying parameters inside the supplier, keep `traceId` and business identifiers for logging/tracing, and map responses at the position matching the failure scope you want to measure. This allows calls to the same dependency to share a sliding window and state, avoids creating dynamic per-request instances, and still preserves per-request inputs, fallbacks, and domain models.
