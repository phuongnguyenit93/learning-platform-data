# Declaring Circuit Breaker Names and Per-Route Scope

In Spring Cloud Gateway, the **CircuitBreaker** filter protects calls from the Gateway to downstream services. Each route has a **route ID** to identify the routing rule, whereas the CircuitBreaker filter takes a **name** to select the Circuit Breaker instance to execute. These two names serve different purposes: the route ID identifies the route configuration, while the Circuit Breaker name identifies the state, policy, and sliding window shared by calls passing through that breaker.

Proper naming determines the Gateway's protection scope. If multiple routes use the same Circuit Breaker name, they can share the CLOSED, OPEN, and HALF_OPEN states and the same statistical window. If each route needs its own policy or failure scope, assign a separate breaker name and configure Resilience4j under that exact name. Names should remain stable per dependent service or operation, not vary per request.

## 1. Distinguishing Route ID and Circuit Breaker Name

A route in the Gateway typically has an ID, a target URI, predicates, and filters. For example, the **catalog-read-route** receives requests with path /catalog/** and forwards them to the Catalog service.

The CircuitBreaker filter inside the route has a **name** attribute, for example **catalogReadBreaker**. This is the ID Spring Cloud CircuitBreaker uses to retrieve or create the corresponding breaker.

| Attribute | Example | Role |
|---|---|---|
| Route ID | catalog-read-route | Identifies the route in Gateway configuration and observability data |
| Predicate | Path=/catalog/** | Determines which requests match the route |
| Target URI | lb://CATALOG-SERVICE | The service or URI to which the Gateway forwards requests |
| Circuit Breaker name | catalogReadBreaker | Selects the Circuit Breaker instance and Resilience4j policy |
| Fallback URI | forward:/fallback/catalog | Internal path invoked when the filter triggers a fallback |

The Route ID does not automatically become the Circuit Breaker name. You must explicitly declare **name** in the filter. Similarly, the instance name in Resilience4j configuration must match the Circuit Breaker name used by the route.

## 2. Declaring a CircuitBreaker Filter for a Route

The following example declares a route for reading Catalog data:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-read-route
          uri: lb://CATALOG-SERVICE
          predicates:
            - Path=/catalog/**
          filters:
            - name: CircuitBreaker
              args:
                name: catalogReadBreaker
                fallbackUri: forward:/fallback/catalog
~~~

When a request matches /catalog/**, the Gateway forwards the request to **CATALOG-SERVICE** via service discovery/load balancer. The CircuitBreaker filter protects calls to that service using the instance named **catalogReadBreaker**.

Two points to verify:

- **id: catalog-read-route** is the route name; it does not configure the Circuit Breaker's state or sliding window.
- **args.name: catalogReadBreaker** is the breaker name; this is the name that must be used under **resilience4j.circuitbreaker.instances**.

**fallbackUri** in the example uses the **forward:** scheme to forward internally to a handler inside the Gateway application itself. The fallback path should be separate from business route predicates so fallback requests are not routed back to the failing service.

Route property structure may differ across Spring Cloud Gateway generations and WebFlux or MVC server packaging. Use the proper property prefix for the Gateway version in your project; the semantics of route ID, filter name, and instance scope still must be kept distinct.

## 3. Configuring Resilience4j by Circuit Breaker Name

Once the route uses the name **catalogReadBreaker**, declare an instance of the same name in Resilience4j configuration:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      catalogReadBreaker:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 3
~~~

Meaning of the properties:

- **slidingWindowType: COUNT_BASED**: evaluates based on the number of call outcomes.
- **slidingWindowSize: 20**: window stores up to the 20 most recent outcomes.
- **minimumNumberOfCalls: 10**: requires at least 10 recorded calls before evaluating the rate.
- **failureRateThreshold: 50**: a failure rate reaching 50% can transition the breaker to OPEN once enough samples exist.
- **waitDurationInOpenState: 15s**: wait duration in OPEN before allowing recovery checks.
- **permittedNumberOfCallsInHalfOpenState: 3**: limits the number of probe calls in HALF_OPEN.

If the route declares **name: catalogReadBreaker** while properties only define **instances.catalog**, the specific configuration for **catalogReadBreaker** will not be bound to the instance requested by the route. Keep names consistent between the filter and Resilience4j configuration, including letter casing.

## 4. Using a Separate Circuit Breaker Per Route

When routes call different services or require different protection policies, assign a distinct breaker name for each scope. For example, the Gateway has a Catalog read route and an Inventory check route:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-read-route
          uri: lb://CATALOG-SERVICE
          predicates:
            - Path=/catalog/**
          filters:
            - name: CircuitBreaker
              args:
                name: catalogReadBreaker
                fallbackUri: forward:/fallback/catalog

        - id: inventory-check-route
          uri: lb://INVENTORY-SERVICE
          predicates:
            - Path=/inventory/**
          filters:
            - name: CircuitBreaker
              args:
                name: inventoryCheckBreaker
                fallbackUri: forward:/fallback/inventory
~~~

Declare two independent instances:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      catalogReadBreaker:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 15s

      inventoryCheckBreaker:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 30
        minimumNumberOfCalls: 15
        failureRateThreshold: 40
        waitDurationInOpenState: 20s
~~~

With this organization:

- Catalog failures are recorded in **catalogReadBreaker**.
- Inventory failures are recorded in **inventoryCheckBreaker**.
- The two breakers have separate states and sliding windows.
- Thresholds and OPEN durations can be tuned to the characteristics of each dependency.

If Catalog transitions to OPEN, the Inventory route can continue operating according to the state of **inventoryCheckBreaker**. This is the benefit of separating protection scope per dependency or operation.

## 5. Multiple Routes Sharing One Circuit Breaker Name

Each route does not strictly have to have its own breaker. Two routes can share a name when they genuinely need to share protection policy and state.

For example, a Catalog service called via two paths:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-public-route
          uri: lb://CATALOG-SERVICE
          predicates:
            - Path=/public/catalog/**
          filters:
            - name: CircuitBreaker
              args:
                name: catalogSharedBreaker
                fallbackUri: forward:/fallback/catalog

        - id: catalog-internal-route
          uri: lb://CATALOG-SERVICE
          predicates:
            - Path=/internal/catalog/**
          filters:
            - name: CircuitBreaker
              args:
                name: catalogSharedBreaker
                fallbackUri: forward:/fallback/catalog
~~~

Both routes use **catalogSharedBreaker**. Because they share the instance name, protected calls share state and evaluation data of the same Circuit Breaker. If failures from one request group cause the breaker to transition to OPEN, calls from the other route can also be rejected.

Sharing is appropriate when:

- Both routes call the same dependency and have equivalent failure characteristics.
- They need the same timeouts, failure thresholds, and OPEN duration.
- You want to aggregate traffic from both routes into the same sliding window.
- When the dependency degrades, you want to stop both call paths from adding further load.

Do not share a name merely because two routes belong to the same Gateway. If the public and internal routes have different SLAs, backends, or error policies, a shared breaker can cause one route's failures to disrupt the other route. Choose scope based on the dependency and operational behavior the team wants to protect.

## 6. Impact of Shared Scope on the Sliding Window

A Circuit Breaker evaluates outcomes received by its instance. When two routes share a name, outcomes from both routes can enter the same sliding window.

Suppose **catalogSharedBreaker** uses a COUNT_BASED window of 20 samples and a minimum of 10 calls. Over a period, the public route produces 6 outcomes and the internal route produces 4 outcomes. When those outcomes are recorded in the same instance, the breaker has all 10 samples needed to begin evaluating the failure rate.

Conversely, if split into **catalogPublicBreaker** and **catalogInternalBreaker**, each instance has its own window. This enables detecting incidents per flow, but each instance needs enough traffic to evaluate. If a route receives few requests, it may take longer to reach the minimum sample count.

| Naming approach | Sliding window scope | Consequence |
|---|---|---|
| Same name for multiple routes | One shared window | Aggregates failures and traffic; one route can affect another |
| Separate name per route | Independent windows | Isolates incidents per route; each instance needs sufficient samples |
| Separate name per operation | Window per operation type | Suitable when operations have different SLAs or error semantics |

When choosing scope, consider both backend capacity and monitoring goals. If a backend is shared yet operations have very different characteristics, you can separate Circuit Breakers by operation. If multiple routes are merely aliases for the same operation, sharing a name is usually easier to operate.

## 7. Declaring a Separate Fallback for Each Route

Each route can specify a **fallbackUri** suited to the response payload it needs to return. For example:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-read-route
          uri: lb://CATALOG-SERVICE
          predicates:
            - Path=/catalog/**
          filters:
            - name: CircuitBreaker
              args:
                name: catalogReadBreaker
                fallbackUri: forward:/fallback/catalog

        - id: inventory-check-route
          uri: lb://INVENTORY-SERVICE
          predicates:
            - Path=/inventory/**
          filters:
            - name: CircuitBreaker
              args:
                name: inventoryCheckBreaker
                fallbackUri: forward:/fallback/inventory
~~~

The Gateway can handle both fallbacks with a controller:

~~~java
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class GatewayFallbackController {

    @RequestMapping("/fallback/catalog")
    ResponseEntity<Map<String, String>> catalogFallback() {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
            .body(Map.of(
                "code", "CATALOG_UNAVAILABLE",
                "message", "Catalog is currently unable to serve the request"
            ));
    }

    @RequestMapping("/fallback/inventory")
    ResponseEntity<Map<String, String>> inventoryFallback() {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
            .body(Map.of(
                "code", "INVENTORY_UNAVAILABLE",
                "message", "Inventory is currently unable to serve the request"
            ));
    }
}
~~~

The Fallback URI uses **forward:** so the Gateway forwards internally to the controller. The controller returns an HTTP status code and payload matching the API contract. In practice, fallback responses should preserve a consistent error structure and may include a correlation ID or error code so clients know they can retry later.

Do not configure a fallback that matches the protected business route predicate if that causes the request to re-enter the same route and create a loop. A fallback also should not call back into the failing backend via another path without its own protection mechanism.

## 8. Distinguishing Route ID, Circuit Breaker Name, and Fallback URI in Operations

When investigating incidents, record all three identifiers:

- **Route ID:** indicates which Gateway route the request matched.
- **Circuit Breaker name:** indicates which breaker allowed or rejected the call.
- **Fallback URI:** indicates which handler was used to generate the fallback response.

Example of logging route ID and breaker name alongside trace ID:

~~~java
log.warn(
    "Gateway route={} circuitBreaker={} traceId={} falling back",
    routeId,
    circuitBreakerName,
    traceId
);
~~~

Do not embed trace IDs, user IDs, order IDs, or URLs with dynamic parameters into the Circuit Breaker name. Breaker names must be finite and stable. Putting per-request data into the name can spawn many instances and metric groups, fragmenting sliding windows and inflating monitoring cardinality.

With Micrometer/Actuator and an appropriate registry, Circuit Breaker metrics can be grouped by instance name. When the dashboard shows **catalogSharedBreaker** in the OPEN state, cross-check route IDs to identify which routes share that instance. Recording both names speeds up impact scoping.

## 9. Naming Conventions for Multi-Route Systems

A Circuit Breaker name should describe the protected dependency or operation. A simple convention is dependency + operation + Breaker.

For example:

| Dependency | Operation | Circuit Breaker name |
|---|---|---|
| Catalog | Read product | catalogReadBreaker |
| Catalog | Search | catalogSearchBreaker |
| Inventory | Check stock | inventoryCheckBreaker |
| Inventory | Reserve stock | inventoryReserveBreaker |
| Payment | Authorize payment | paymentAuthorizeBreaker |

When deciding whether to split or share a name, answer:

1. Do the routes call the same backend and the same operation?
2. Do they need the same failure threshold, sliding window, and OPEN duration?
3. Should failures on one route stop the remaining routes from calling the backend?
4. Does each route have enough traffic to be evaluated independently?
5. Does the dashboard need to track incidents by dependency or per route?

If the answers indicate the routes should share state, share the name. If you need isolated failure handling and separate policies, give them different names. Keep route IDs distinct so each route remains individually observable even when multiple routes share one breaker.

## 10. Common Configuration Mistakes

1. **Confusing route ID with Circuit Breaker name.** The route has a valid ID, but the filter name does not match Resilience4j properties; check args.name and instances.<name>.
2. **Naming Circuit Breakers per request.** Instance counts grow uncontrollably and sliding windows are fragmented; use stable names by dependency or operation.
3. **Sharing a name across different backends.** Failures in one dependency can push the shared breaker to OPEN and affect the remaining routes.
4. **Splitting names too finely.** Each route gets too little traffic to reach minimumNumberOfCalls; failure rate evaluation becomes slow or under-sampled.
5. **Forgetting to configure the corresponding instance.** The filter uses catalogReadBreaker while properties only declare instances.catalog; the intended configuration is not mapped to the right ID.
6. **Fallback URI matching the business route again.** Fallback requests can loop back to the failing backend or re-enter filters; use a dedicated internal path.
7. **Not tracking both route ID and Circuit Breaker name.** Having only one name on dashboards makes it hard to tell which routes are affected when multiple routes share a breaker.
8. **Using a property prefix for the wrong Gateway version.** Cross-check the release train and server variant documentation before deploying route YAML.

## 11. Practical Scenario

A Gateway has three routes:

- /catalog/** calls the Catalog service to read product details.
- /catalog/search/** calls the same Catalog service to search.
- /inventory/** calls the Inventory service to check stock.

The development team decides that the two Catalog routes share a single breaker because they target the same backend and need the same protection policy. Inventory uses a separate breaker.

Configuration:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-read-route
          uri: lb://CATALOG-SERVICE
          predicates:
            - Path=/catalog/**
          filters:
            - name: CircuitBreaker
              args:
                name: catalogSharedBreaker
                fallbackUri: forward:/fallback/catalog

        - id: catalog-search-route
          uri: lb://CATALOG-SERVICE
          predicates:
            - Path=/catalog/search/**
          filters:
            - name: CircuitBreaker
              args:
                name: catalogSharedBreaker
                fallbackUri: forward:/fallback/catalog

        - id: inventory-check-route
          uri: lb://INVENTORY-SERVICE
          predicates:
            - Path=/inventory/**
          filters:
            - name: CircuitBreaker
              args:
                name: inventoryCheckBreaker
                fallbackUri: forward:/fallback/inventory
~~~

Pay attention to predicate ordering and path specificity when designing routes so search requests match the intended route. In the example, both Catalog routes use **catalogSharedBreaker**, so failures from either reads or searches can contribute to the shared sliding window. The Inventory route uses **inventoryCheckBreaker**, so its state is independent.

When the Catalog Circuit Breaker transitions to OPEN, both Catalog routes can fall back. The Inventory route continues to be evaluated by its own breaker. If search operations exhibit significantly different latency or failure rates compared to product reads, operations can split them into **catalogSearchBreaker** and **catalogReadBreaker** after weighing traffic volume and isolation goals.

After deployment, verify:

1. Each request matches the expected route ID.
2. The filter uses the right Circuit Breaker name.
3. The instance name in Resilience4j matches the filter name.
4. Routes sharing a name actually share state and metrics.
5. The Fallback URI forwards to a separate handler and does not loop back to the business route.
6. Dashboards display status by Circuit Breaker name and logs still identify the route ID.

## Conclusion

In Spring Cloud Gateway, the **route ID** identifies the routing rule while the **CircuitBreaker name** determines the instance and protected state scope. Multiple routes using the same name share the Circuit Breaker and sliding window; separate names isolate state, policy, and metrics. Choose stable names by dependency or operation, declare the same name in Resilience4j properties, use a dedicated fallback URI, and record both route ID and Circuit Breaker name for smooth operations.
