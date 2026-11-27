# Building a Dependent Service with Success, Error, and Slow Response Modes

When practicing with a circuit breaker, you need a dependent service whose output you can control in order to reproduce the scenarios that the calling application must handle. This hands-on practice builds a simulated inventory service with Spring Boot that supports three modes: returning successful data, returning an HTTP 503 error, and responding successfully after a configurable delay.

The simulated service acts as an upstream/downstream dependency with deterministic behavior. A Spring Cloud CircuitBreaker application can call it to observe normal outcomes, failure rate, and slow call rate, and then test fallback behavior when the circuit is OPEN. We will run the simulator separately on port 8081 so that simulated state is not mixed with the calling application.

## Objectives and Practice Diagram

After completing this practice, you can:

- Start a standalone HTTP service that simulates an inventory service.
- Select success, error, or slow response mode via a query parameter.
- Adjust latency to test the slow call threshold and timeout.
- Send repeated requests to generate enough samples for the sliding window.
- Use the same endpoint as the target of a circuit breaker in another application.

~~~mermaid
flowchart LR
    A[Spring Cloud Application] -->|HTTP request| B[Simulated Inventory Service :8081]
    B --> C{mode}
    C -->|success| D[HTTP 200 and inventory data]
    C -->|error| E[HTTP 503 and error code]
    C -->|slow| F[Bounded wait then HTTP 200]
    D --> A
    E --> A
    F --> A
~~~

Within the scope of this exercise, the simulated service only produces predictable responses. It does not access a database and does not represent real inventory logic.

## 1. Create a Spring Boot Application for the Simulated Service

Create a separate Spring Boot application, for example named `inventory-simulator`. Use Java 17 or later and Spring Boot 3. Add the Web dependency to create REST endpoints:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
        <optional>true</optional>
    </dependency>
</dependencies>
~~~

If the project already uses the Spring Boot parent or BOM, let dependency management manage the versions. Actuator is optional and only needed if you want to check the simulator's health endpoint.

Configure the application to run on port 8081:

~~~yaml
spring:
  application:
    name: inventory-simulator

server:
  port: 8081

management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Keep the simulator port different from the calling application's port, for example having the caller run on 8080. When the two applications are independent, you can stop or restart the simulator without losing the caller's circuit breaker configuration.

## 2. Declare the Response Models

Create two records to represent the simulated success and error results:

~~~java
package com.example.inventorysimulator.api;

public record InventoryResponse(
        String sku,
        Integer available,
        String status,
        String mode,
        long delayMs,
        String message
) {
}
~~~

~~~java
package com.example.inventorysimulator.api;

public record ApiError(
        String code,
        String message,
        String mode
) {
}
~~~

The success response includes a simulated available quantity. The error response has a stable error code so the caller or tests can identify it. The `mode` and `delayMs` fields help confirm that the simulator executed the expected scenario.

## 3. Create an Endpoint with Three Modes

Create the following controller. The endpoint uses `success` mode by default; the other two modes are selected via the `mode` query parameter.

~~~java
package com.example.inventorysimulator.api;

import java.util.Locale;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/inventory")
public class InventorySimulationController {

    private static final long MAX_DELAY_MS = 10_000L;

    @GetMapping("/{sku}")
    public ResponseEntity<?> find(
            @PathVariable String sku,
            @RequestParam(defaultValue = "success") String mode,
            @RequestParam(defaultValue = "1500") long delayMs) {

        String selectedMode = mode.toLowerCase(Locale.ROOT);

        return switch (selectedMode) {
            case "success" -> ResponseEntity.ok(
                    new InventoryResponse(
                            sku, 12, "AVAILABLE", selectedMode, 0,
                            "Simulated inventory response"
                    )
            );

            case "error" -> ResponseEntity
                    .status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body(new ApiError(
                            "INVENTORY_SIMULATED_FAILURE",
                            "Inventory dependency is temporarily unavailable",
                            selectedMode
                    ));

            case "slow" -> slowResponse(sku, delayMs);

            default -> ResponseEntity.badRequest().body(
                    new ApiError(
                            "INVALID_SIMULATION_MODE",
                            "mode must be success, error or slow",
                            selectedMode
                    )
            );
        };
    }

    private ResponseEntity<?> slowResponse(String sku, long requestedDelayMs) {
        long boundedDelayMs = Math.max(
                0L,
                Math.min(requestedDelayMs, MAX_DELAY_MS)
        );

        try {
            Thread.sleep(boundedDelayMs);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();

            return ResponseEntity
                    .status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body(new ApiError(
                            "SIMULATION_INTERRUPTED",
                            "The simulated delay was interrupted",
                            "slow"
                    ));
        }

        return ResponseEntity.ok(
                new InventoryResponse(
                        sku, 12, "AVAILABLE", "slow", boundedDelayMs,
                        "Successful response after simulated delay"
                )
        );
    }
}
~~~

Key points to note:

- `success` returns HTTP 200 and simulated inventory data.
- `error` returns HTTP 503 with the code `INVENTORY_SIMULATED_FAILURE`. This is a valid HTTP response; an HTTP client like RestClient typically turns 5xx responses into an exception when using `retrieve()`.
- `slow` waits for `delayMs` and then still returns HTTP 200. Because the final outcome succeeds, this isolates slow calls from failures.
- The delay is capped at a maximum of 10 seconds to prevent a request from accidentally holding a thread for too long.
- When the thread is interrupted, the controller restores the interrupt flag and returns a controlled error.

Using `Thread.sleep` here is only intended to simulate a slow service in a practice environment. Do not use this approach to introduce artificial latency in production endpoints. Real services should use client-side timeouts, resource limits, and observe the actual root causes of latency.

## 4. Start and Test the Simulator

Run the Spring Boot application from the simulator project directory. After it starts, send the following requests in order:

**Success:**

~~~bash
curl -i "http://localhost:8081/inventory/SKU-100?mode=success"
~~~

The expected result is HTTP 200 and JSON similar to:

~~~json
{
  "sku": "SKU-100",
  "available": 12,
  "status": "AVAILABLE",
  "mode": "success",
  "delayMs": 0,
  "message": "Simulated inventory response"
}
~~~

**Dependency error:**

~~~bash
curl -i "http://localhost:8081/inventory/SKU-100?mode=error"
~~~

The expected result is HTTP 503 and a body containing the code `INVENTORY_SIMULATED_FAILURE`. If the caller uses an HTTP client that turns 5xx into an exception, the circuit breaker can record this outcome as a failure according to its exception classification configuration.

**Slow but successful response:**

~~~bash
curl -i "http://localhost:8081/inventory/SKU-100?mode=slow&delayMs=1800"
~~~

The expected result is HTTP 200 after about 1.8 seconds. If the circuit breaker's `slowCallDurationThreshold` is lower than 1.8 seconds and the caller's timeout is longer than this delay, the call is recorded as a slow call rather than a failure.

**Invalid mode:**

~~~bash
curl -i "http://localhost:8081/inventory/SKU-100?mode=unknown"
~~~

The expected result is HTTP 400. Do not use 400 as a dependency failure signal in this practice; it is a simulation parameter error caused by an invalid value sent by the caller.

On Windows PowerShell, you can explicitly invoke `curl.exe` to avoid PowerShell's `curl` alias. On Linux or macOS, use `curl` as shown in the examples.

## 5. Connect the Simulator to the CircuitBreaker Application

In the calling application, create an HTTP client pointing to the simulator. The following example uses `RestClient` from Spring Framework 6.1 or later:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
public class InventoryHttpConfiguration {

    @Bean
    RestClient inventoryRestClient(RestClient.Builder builder) {
        return builder
                .baseUrl("http://localhost:8081")
                .build();
    }
}
~~~

Create a service that calls the simulator through the Spring Cloud CircuitBreaker factory:

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class InventoryQueryService {

    private final RestClient restClient;
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;

    public InventoryQueryService(
            RestClient inventoryRestClient,
            CircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.restClient = inventoryRestClient;
        this.circuitBreakerFactory = circuitBreakerFactory;
    }

    public InventoryResponse find(
            String sku,
            String mode,
            long delayMs) {

        return circuitBreakerFactory.create("inventoryProbe").run(
                () -> restClient.get()
                        .uri(uriBuilder -> uriBuilder
                                .path("/inventory/{sku}")
                                .queryParam("mode", mode)
                                .queryParam("delayMs", delayMs)
                                .build(sku))
                        .retrieve()
                        .body(InventoryResponse.class),
                error -> new InventoryResponse(
                        sku,
                        null,
                        "UNAVAILABLE",
                        mode,
                        0,
                        error.getClass().getSimpleName()
                )
        );
    }
}
~~~

The caller needs the Spring Cloud CircuitBreaker dependency with a compatible Resilience4j backend. The `InventoryResponse` and `CircuitBreakerFactory` types in the example belong to the calling application; you can share the DTO via a contract module if the project architecture permits.

When the simulator returns 503, `RestClient.retrieve()` throws an exception for the 5xx response and the fallback is invoked. When the simulator returns 200 after a long delay, the supplier still completes successfully, but the circuit breaker can mark the call as slow. When the circuit is OPEN, new calls are rejected before reaching the simulator and the fallback returns a degraded result.

## 6. Configure the Circuit Breaker to Observe Both Errors and Slow Calls

In the calling application, declare an instance matching the name `inventoryProbe`:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventoryProbe:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 50
        slowCallDurationThreshold: 800ms
        slowCallRateThreshold: 50
        waitDurationInOpenState: 5s
        permittedNumberOfCallsInHalfOpenState: 2
~~~

With this configuration:

- At least 5 samples are required before evaluating rates.
- Calls taking longer than 800 ms are counted as slow calls.
- If the slow call rate reaches 50%, the circuit can open even if all calls return HTTP 200.
- If the failure rate reaches 50%, the circuit can also open due to errors.
- After 5 seconds in OPEN, the circuit can allow probe calls in HALF_OPEN.

Do not set the HTTP client timeout shorter than 800 ms while testing slow success. If the caller times out at 500 ms, a 1.8-second call becomes a timeout error before it can complete successfully, and the test will no longer isolate the slow call rate.

Timeout and slow call threshold serve different purposes. A timeout limits how long you wait; a slow call threshold classifies calls by duration after the call completes. Test each mechanism separately.

## 7. Practice Three Circuit Breaker Scenarios

Each scenario should use a fresh circuit breaker or restart the caller so that the sliding window and OPEN state from the previous run do not affect the results.

| Scenario | Request to simulator | Expected result on caller |
|---|---|---|
| Normal | `mode=success` | HTTP 200, response has `available=12`, breaker records success. |
| Fast error | `mode=error` | Simulator returns 503, RestClient throws exception, breaker records failure and fallback runs. |
| Slow but successful | `mode=slow&delayMs=1800` | Simulator returns 200 after delay, breaker records slow call but failure count does not increase. |
| Circuit OPEN | Send any mode after enough error/slow samples | Caller fails fast, simulator receives no new requests, fallback runs. |
| Recovery | After OPEN duration, send `mode=success` | Breaker tests in HALF_OPEN and can return to CLOSED if enough probe calls succeed. |

**Exercise A — Verify the success path**

1. Start the caller and simulator.
2. Send a request with `mode=success`.
3. Verify the 200 response and inventory data.
4. Observe the successful call count of `inventoryProbe`.

**Exercise B — Generate a failure rate**

1. Use a fresh breaker with a window of 10 and minimumNumberOfCalls 5.
2. Send at least 5 requests with `mode=error`.
3. Verify that each simulator response is 503.
4. Verify that the caller triggers the fallback and the failure rate increases.
5. Once the condition is met, send another request and verify that the OPEN circuit fails fast.

**Exercise C — Generate an independent slow call rate**

1. Use a fresh breaker to avoid leftover state from Exercise B.
2. Set `slowCallDurationThreshold=800ms` and the caller timeout longer than 1.8 seconds.
3. Send at least 5 requests with `mode=slow&delayMs=1800`.
4. Verify that each response is HTTP 200.
5. Verify that the slow call rate increases while the failure rate remains 0.
6. When the slow call rate reaches the threshold, verify that the circuit breaker can open.

**Exercise D — Verify OPEN and HALF_OPEN states**

1. After the breaker is OPEN, send another request and observe the fast response time.
2. Check the simulator logs to verify that the rejected request did not reach the dependent service.
3. Wait for `waitDurationInOpenState` to elapse.
4. Send a success request to test a probe call.
5. Verify that the circuit returns to CLOSED after the probe calls succeed.

## 8. Diagnosing Unexpected Results

| Symptom | Possible cause | How to check |
|---|---|---|
| Error mode does not increase failure rate | HTTP client does not convert status 503 into an exception or the exception is ignored. | Check the exception in the supplier and the classification configuration. |
| Slow mode does not increase slow call rate | Slow threshold is higher than the delay, or the caller measures duration at a different layer. | Compare actual delay with `slowCallDurationThreshold`. |
| Slow mode becomes a failure | Client timeout is shorter than the simulator delay. | Increase the timeout in the slow-success test or reduce the delay. |
| Circuit does not OPEN | Not enough `minimumNumberOfCalls`, rate has not reached threshold, or breaker ID mismatch. | Check sample count, metrics, and instance name. |
| Requests still reach simulator when breaker is thought to be OPEN | Caller is using a different ID or a separate call path that bypasses the breaker. | Check the factory name, logs, and call path. |
| Requests are rejected right from the start | Breaker is still OPEN from a previous scenario. | Create a fresh instance or restart the caller. |
| Unstable slow responses | Test machine is overloaded or delay is too close to threshold. | Use a larger gap between delay and threshold. |

If using `RestClient`, remember that 4xx/5xx responses from `retrieve()` typically throw exceptions. If you use a different HTTP client or handle responses with an API that does not automatically throw exceptions, you must explicitly convert the chosen statuses into errors so the circuit breaker can record them.

## 9. Limitations of the Simulated Service

The simulator uses `Thread.sleep` to hold the request thread during the simulated delay. This is a simple way to create slow responses in synchronous exercises, but it does not accurately model all types of network or distributed system latency.

For deeper testing, you can replace it with WireMock, MockWebServer, or a dedicated test service that can control:

- Delay before sending response headers.
- Delay between elements of a response stream.
- Abrupt connection termination.
- Returning different HTTP status codes.
- Probabilistic error rates.
- Limiting concurrent requests.

Do not expose simulated error modes to production or the public internet. Keep the simulator inside the development/test network, cap the delay, and do not include sensitive data in responses.

## Completion Checklist

- [ ] Simulator starts independently on port 8081.
- [ ] `mode=success` returns HTTP 200 and inventory data.
- [ ] `mode=error` returns HTTP 503 with a stable error code.
- [ ] `mode=slow` returns HTTP 200 after a bounded delay.
- [ ] Invalid `mode` returns HTTP 400.
- [ ] Caller invokes simulator through a circuit breaker with a stable ID.
- [ ] 503 errors are recorded as failures and trigger fallback.
- [ ] Slow successes increase slow call rate without increasing failure rate.
- [ ] When breaker is OPEN, new requests are rejected before reaching the simulator.
- [ ] After OPEN duration, HALF_OPEN can test recovery with successful responses.

A dependent service with success, error, and slow response modes creates a repeatable test environment for Spring Cloud CircuitBreaker. By separating the simulator from the caller, bounding the latency, and verifying both HTTP responses and circuit breaker metrics, you can observe dependency errors, latency degradation, and recovery independently without waiting for a real external system to fail.
