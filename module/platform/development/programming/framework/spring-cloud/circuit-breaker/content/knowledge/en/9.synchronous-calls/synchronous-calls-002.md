# Placing Circuit Breaker Boundaries Around the Right Remote Operation

## Lesson Objectives

In a Spring Cloud application, a business method often does several things: validating input, reading local data, calling another service, transforming results, and saving changes. A circuit breaker needs to track the health of a specific remote dependency. If placed around the entire business method, local errors can also be miscounted as failures of the dependent service.

The right boundary usually sits where the application performs a remote I/O operation. For example, an inventory read call gets its own breaker, and a pricing call gets its own breaker. Each breaker monitors the exact dependency it protects and records only the outcomes of that operation.

After this lesson, you can:

- Identify the proper boundary of a synchronous call that needs a circuit breaker.
- Use `CircuitBreakerFactory` to wrap a remote operation in a `Supplier`.
- Choose distinct IDs for dependencies or operations with different operational characteristics.
- Separate remote service failures from input validation errors and local business processing.
- Design meaningful fallbacks that do not mask business errors.
- Verify behavior when the breaker is in `CLOSED`, `OPEN`, and `HALF_OPEN`.

## 1. What Is a Circuit Breaker Boundary?

Suppose `order-service` handles an order creation request. A simple flow might consist of:

1. Validating the product code and quantity.
2. Reading inventory availability from `inventory-service`.
3. Fetching the price from `pricing-service`.
4. Calculating the total amount and applying discount rules.
5. Saving the order.

In this flow, step 2 and step 3 are two remote operations against two different dependencies. Circuit breakers should be placed at each of those call boundaries:

    Client
      |
      v
    order-service
      |
      +-- validate request (local)
      |
      +-- [breaker: inventory-read] --> inventory-service
      |
      +-- [breaker: pricing-quote] --> pricing-service
      |
      +-- calculate total (local)
      |
      +-- save order (database)

Each breaker tracks one outbound call operation. When `inventory-service` fails, the `inventory-read` breaker can open. The `pricing-quote` call is still evaluated independently. This prevents failures in one dependency from skewing statistics or mistakenly blocking another dependency.

An appropriate circuit breaker boundary has three characteristics:

- **A clear dependency:** the protected operation calls a specific remote service or resource.
- **Observable outcomes:** success, failure, or slow response of the operation meaningfully reflects the dependency's health.
- **A suitable recovery policy:** when the breaker rejects a call, the application knows whether it can use a cache, return an undetermined status, or propagate the error to the caller.

A circuit breaker is not a wrapper around every line of code in a method. It is a mechanism that protects calls to a dependency.

## 2. Why Not Wrap the Entire Business Method?

The following example places a breaker around the whole order creation workflow:

    public OrderResult createOrder(CreateOrderRequest request) {
        return circuitBreakerFactory.create("inventory").run(
            () -> {
                validate(request);
                Product product = productRepository.findById(request.productId())
                    .orElseThrow();
                InventoryResponse stock = inventoryClient.get()
                    .uri("/inventory/{sku}", request.sku())
                    .retrieve()
                    .body(InventoryResponse.class);
                BigDecimal total = calculateTotal(product, stock, request);
                orderRepository.save(Order.from(request, total));
                return OrderResult.created(total);
            },
            error -> OrderResult.unavailable()
        );
    }

This approach can cause several problems:

- If `validate` throws an error due to invalid input, the `inventory` breaker may still record a failure even though `inventory-service` was never called.
- If the local database fails, the `inventory` breaker may open for the wrong reason.
- If a business calculation throws an exception, the fallback may hide a logic bug.
- If saving the order partially executes before throwing an error, the fallback may return a generic result while the data state actually requires explicit handling.
- When `pricing-service` is also inside the lambda, pricing failures can be recorded against the `inventory` breaker.

Those errors do not reflect the health of `inventory-service`. They render circuit breaker statistics meaningless and can cause the system to reject calls to a healthy dependency.

Keep business orchestration outside the breaker. Only wrap the remote operation inside the `Supplier` executed by the circuit breaker.

## 3. Using CircuitBreakerFactory to Wrap a Synchronous Call

Spring Cloud CircuitBreaker provides `CircuitBreakerFactory` to create breakers by ID. The `run` method accepts a `Supplier` that executes the primary call and a fallback function that accepts a `Throwable`:

    import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
    import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
    import org.springframework.stereotype.Service;
    import org.springframework.web.client.RestClient;

    @Service
    public class InventoryGateway {

        private final RestClient inventoryClient;
        private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;

        public InventoryGateway(
                RestClient inventoryClient,
                CircuitBreakerFactory<?, ?> circuitBreakerFactory) {
            this.inventoryClient = inventoryClient;
            this.circuitBreakerFactory = circuitBreakerFactory;
        }

        public InventoryResponse find(String sku) {
            CircuitBreaker breaker = circuitBreakerFactory.create("inventory-read");

            return breaker.run(
                () -> inventoryClient.get()
                    .uri("/inventory/{sku}", sku)
                    .retrieve()
                    .body(InventoryResponse.class),
                error -> InventoryResponse.unknown(sku)
            );
        }
    }

Here, the `Supplier` performs only one operation: sending an HTTP GET to `inventory-service` and reading the response. Creating the breaker with the ID `inventory-read` ties state, configuration, and metrics to the inventory read call.

`InventoryResponse.unknown(sku)` is an illustrative application-defined method. It must clearly represent that the system has not been able to determine stock availability. Do not use a default value such as `quantity = 0` if that causes the business layer to mistakenly assume the product is definitely out of stock.

In a real application, `RestClient` should be configured with an appropriate base URL, connect timeout, and response timeout. Those settings belong to the HTTP client. The circuit breaker evaluates call outcomes and can reject subsequent calls when the dependency shows signs of failure; it does not replace network timeouts on its own.

## 4. Keeping Local Processing Outside the Supplier

A clean structure is to place remote calls inside a gateway or adapter. The business layer calls the gateway like a normal dependency:

    @Service
    public class OrderService {

        private final InventoryGateway inventoryGateway;
        private final PricingGateway pricingGateway;
        private final OrderRepository orderRepository;

        public OrderService(
                InventoryGateway inventoryGateway,
                PricingGateway pricingGateway,
                OrderRepository orderRepository) {
            this.inventoryGateway = inventoryGateway;
            this.pricingGateway = pricingGateway;
            this.orderRepository = orderRepository;
        }

        public OrderResult createOrder(CreateOrderRequest request) {
            validate(request);

            InventoryResponse stock = inventoryGateway.find(request.sku());
            PricingResponse price = pricingGateway.quote(request.sku());

            Order order = calculateOrder(request, stock, price);
            orderRepository.save(order);

            return OrderResult.from(order);
        }
    }

In this structure:

- `OrderService` is responsible for workflow orchestration and business rules.
- `InventoryGateway` is responsible for calling `inventory-service` and protecting that exact call.
- `PricingGateway` is responsible for calling `pricing-service` with its own breaker.
- The repository is responsible for database operations.

If `validate`, `calculateOrder`, or `orderRepository.save` fails, the error is handled according to that component's policy. The `inventory` breaker only receives outcomes from the `inventory-service` call.

Not every project needs a separate gateway class per endpoint. You can use an adapter with multiple methods, provided each wrapped `Supplier` contains only the remote operation being protected and the breaker ID is chosen clearly.

## 5. Choosing IDs by Dependency and Operation

The ID is the breaker identifier used by the factory. This name is typically linked to configuration and observability data. Choosing stable IDs helps track the exact operation across deployments.

Examples:

| Call | Suggested ID | Reason |
| --- | --- | --- |
| Read inventory | inventory-read | Tracks inventory read operations separately. |
| Reserve stock | inventory-reserve | May have different timeouts, load, and error policies from reads. |
| Fetch price | pricing-quote | Independent `pricing-service` dependency. |
| Look up customer profile | customer-profile | Tracks the `customer-service` dependency. |

Avoid using a single generic ID like `remote-call` for all dependencies. Otherwise, one failing service can trip the breaker and block calls to other services as well.

Also avoid creating IDs containing variable data such as SKU, `orderId`, `userId`, or `requestId`. If every request creates a new breaker, the number of instances grows unboundedly, each breaker has too few samples, and the sliding window lacks sufficient data for evaluation. IDs should reflect an operation or group of operations with stable operational characteristics.

If two operations call the same service but have very different characteristics—such as a fast read versus a long-running report export—you can use two separate IDs. If multiple operations share the same operational target and need a shared policy, consider `groupName` when supported by the factory and configuration. Even when sharing a group configuration, the ID still keeps breaker state isolated per operation.

## 6. Protecting Each Dependency in a Multi-Call Flow

Suppose `order-service` needs both inventory and pricing. The two calls must have separate breakers:

    @Service
    public class OrderDependencies {

        private final RestClient inventoryClient;
        private final RestClient pricingClient;
        private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;

        public OrderDependencies(
                RestClient inventoryClient,
                RestClient pricingClient,
                CircuitBreakerFactory<?, ?> circuitBreakerFactory) {
            this.inventoryClient = inventoryClient;
            this.pricingClient = pricingClient;
            this.circuitBreakerFactory = circuitBreakerFactory;
        }

        public InventoryResponse inventory(String sku) {
            return circuitBreakerFactory.create("inventory-read").run(
                () -> inventoryClient.get()
                    .uri("/inventory/{sku}", sku)
                    .retrieve()
                    .body(InventoryResponse.class),
                error -> InventoryResponse.unknown(sku)
            );
        }

        public PricingResponse pricing(String sku) {
            return circuitBreakerFactory.create("pricing-quote").run(
                () -> pricingClient.get()
                    .uri("/prices/{sku}", sku)
                    .retrieve()
                    .body(PricingResponse.class),
                error -> PricingResponse.unavailable(sku)
            );
        }
    }

When inventory fails, the `inventory-read` breaker can transition to `OPEN`. Pricing calls still pass through the `pricing-quote` breaker and are evaluated with their own metrics. Conversely, pricing errors do not trip the inventory breaker.

If the business flow requires both results to create an order, the orchestration layer must decide what to do when a gateway returns a degraded state. For example, if reliable pricing is unavailable, it can halt order creation and ask the caller to retry. If stock is unknown, it can save the order in a pending-verification state. These decisions belong to the business layer and should not be hidden inside a breaker fallback.

## 7. Classifying Errors Before Letting the Breaker Record Them

Not every exception indicates an unhealthy dependency. For example:

- Connection errors or timeouts may reflect that the remote service is unavailable.
- HTTP 5xx errors usually indicate processing failures in the dependent service.
- HTTP 4xx errors may be business outcomes or invalid inputs, not necessarily service health failures.
- Input validation errors in `order-service` should not count as `inventory-service` failures if they occur before any network call.

Resilience4j allows configuring recorded and ignored exceptions via `recordExceptions` and `ignoreExceptions`. Illustrative example:

    resilience4j:
      circuitbreaker:
        instances:
          inventory-read:
            recordExceptions:
              - org.springframework.web.client.ResourceAccessException
              - org.springframework.web.client.HttpServerErrorException
            ignoreExceptions:
              - org.springframework.web.client.HttpClientErrorException

This configuration is only an example of classification. Verify the actual exception classes thrown by the HTTP client in use and the API's business policy. Some 4xx errors such as 429 may indicate overload or rate limiting from the dependency and need separate handling; do not blindly ignore all 4xx responses.

`recordExceptions` must also be reviewed alongside `ignoreExceptions` and Resilience4j's defaults. The goal is for the breaker to record failures indicating the dependency cannot serve calls, while not opening due to business errors or local programming bugs.

Fallback invocation and failure recording are two separate decisions. The `run` fallback function can be invoked when the `Supplier` fails or when the breaker rejects the call. Whether an exception counts toward the failure rate is determined by the breaker's configuration. Do not assume that an error handled by a fallback was necessarily recorded as a circuit breaker failure.

## 8. Designing Fallbacks Around Data Semantics

A fallback runs when the primary operation cannot return a result normally. A good fallback should answer: what data can the business layer proceed with without making wrong decisions?

Some options:

| Dependency Type | Potentially Suitable Fallback | What to Control |
| --- | --- | --- |
| Inventory lookup | Return `UNKNOWN` status or valid cached data. | Do not claim in-stock or out-of-stock without reliable data. |
| Price lookup | Return price-unavailable status or ask to retry. | Do not use a zero price or stale price if business rules disallow it. |
| Optional profile | Use cache or omit optional fields. | Apply only when the data is not required for the core decision. |
| Authentication service | Usually propagate the error to reject the action. | Never grant access simply because the auth service is unavailable. |

Example fallback distinguishing an open breaker from infrastructure errors:

    private InventoryResponse inventoryFallback(String sku, Throwable error) {
        if (error instanceof CallNotPermittedException) {
            return InventoryResponse.unavailable(sku);
        }

        if (error instanceof ResourceAccessException) {
            return InventoryResponse.unknown(sku);
        }

        throw new InventoryLookupException(
            "Cannot determine inventory for " + sku,
            error
        );
    }

`CallNotPermittedException` signals that the breaker is `OPEN` or not permitting trial calls at that moment. `ResourceAccessException` typically occurs when there is a network resource access issue. `InventoryLookupException` is an application-defined exception. Other error types are propagated so the calling layer can decide how to handle them.

A fallback must be fast, resource-bounded, and never call back into the failing dependency. If the fallback uses a cache, check data age and business rules. If the fallback itself fails, propagate the error clearly rather than hiding it.

## 9. Breaker State and Its Impact on the Right Call

For the `inventory-read` breaker:

- **CLOSED:** The `Supplier` sends requests to `inventory-service`. Success, failure, or slow outcomes update statistics as configured.
- **OPEN:** The `Supplier` is not executed. Calls fail fast and the fallback function can return a degraded state.
- **HALF_OPEN:** Only a limited number of trial calls are permitted to reach `inventory-service`. Their outcomes determine whether the breaker closes or reopens.

If `inventory-read` transitions to `OPEN`, operations protected by the `inventory-read` ID are affected. The `pricing-quote` breaker maintains its own independent state. This is a key reason to set clear boundaries and choose dependency-specific IDs.

Breaker state typically resides in memory per application instance. If `order-service` runs across multiple pods, each pod can have its own statistics and state. Do not assume that a breaker opening on one pod automatically opens the breaker on all pods simultaneously.

## 10. Timeouts and Supplier Execution Duration

A circuit breaker can mark slow calls based on `slowCallDurationThreshold`, but marking a call as slow does not automatically cancel the network operation. For synchronous calls, configure timeouts on the HTTP client:

- Connect timeout bounds connection establishment time.
- Response or read timeout bounds waiting for response data according to the client's capabilities.
- The circuit breaker uses `slowCallDurationThreshold` and `slowCallRateThreshold` to evaluate slow calls within the statistical window.

Set timeouts aligned with the time budget of the client request to `order-service`. If the HTTP client timeout is too long, processing threads may be held for a long time before the `Supplier` finishes and the breaker gets a chance to record the outcome.

Do not use a circuit breaker as a substitute for timeouts. Nor should you set a dependency timeout much longer than the upstream caller can wait. For synchronous tasks, whether an in-flight call can be canceled depends on the HTTP client and how it implements timeouts.

## 11. Verifying Boundaries with Failure Scenarios

You can verify the design with controlled test scenarios:

| Scenario | Expected Observation |
| --- | --- |
| Request missing SKU and validation fails | The `inventory-read` breaker records no call because the `Supplier` never ran. |
| `inventory-service` returns success | The `inventory-read` breaker records a success. |
| `inventory-service` loses connectivity | The call fails; fallback or error is handled per policy. |
| `inventory-service` responds slower than threshold | A slow call is recorded; the breaker may open if the rate exceeds threshold. |
| `pricing-service` returns errors | The `pricing-quote` breaker records pricing outcomes; `inventory-read` is unaffected. |
| `order-service` database fails on save | The persistence error is handled in the repository/business layer, not misattributed to inventory. |
| `inventory-read` breaker is `OPEN` | The `Supplier` calling inventory is not executed; fallback is invoked. |
| Dependency recovers in `HALF_OPEN` | Only permitted trial calls run; their outcomes determine the next state. |

During testing, inspect breaker state, permitted calls, rejected calls, failure rate, slow call rate, and response time. If the breaker opens when only validation or database errors occurred, review the `Supplier` scope and exception classification.

## 12. Lab Exercise: Separating Inventory and Pricing Boundaries

Build an `order-service` with two synchronous gateways:

1. `InventoryGateway.find(sku)` calls `inventory-service` inside the `inventory-read` breaker.
2. `PricingGateway.quote(sku)` calls `pricing-service` inside the `pricing-quote` breaker.
3. `OrderService.validate(request)` runs before both gateways and stays outside the breakers.
4. `OrderService.calculateOrder(...)` processes results outside the breakers.
5. `OrderRepository.save(...)` persists the order outside both breakers.

Then test these scenarios:

- Make `inventory-service` stop responding and confirm the `inventory-read` breaker opens after sufficient samples.
- While `inventory-read` is `OPEN`, invoke `pricing-quote` and confirm the `pricing` breaker continues operating independently.
- Send an invalid request and confirm the `inventory` breaker records no failure since no call was executed.
- Force a database error during order save and confirm the error does not open either the `inventory` or `pricing` breaker.
- Restore `inventory-service` and observe trial calls in `HALF_OPEN`.
- Verify that the fallback returns `UNKNOWN` or `UNAVAILABLE` matching the application contract.

Upon completion, you should be able to point to the exact line performing remote I/O, the `Supplier` protected by each breaker, the ID bound to each dependency, and which errors must not affect the failure rate. Clear boundaries allow the circuit breaker to produce reliable metrics and contain incidents to the specific dependency having trouble.
