# Making Service-Name Calls with retrieve and exchange

In a microservices system, an application generally should not hardcode the address `http://10.0.1.25:8080` of a specific instance. With **Spring Cloud LoadBalancer**, a `RestClient` configured with `@LoadBalanced` can call URLs like **`http://inventory-service/api/items/42`**. The host portion `inventory-service` is interpreted as a **service ID**; LoadBalancer looks up the matching `ServiceInstance` set, selects one instance, and sends the HTTP request to that instance's actual host/port.

This lesson belongs to the **RestClient** chapter in the **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING** module. The focus is on making calls by **service name**, using **`retrieve()`** for convenient response handling, and using **`exchange()`** when finer-grained control over the HTTP response is needed. The examples also show relationships with discovery, health checks, timeouts, retries, and observability, helping make inter-service communication reliable and error diagnosis accurate.

> `RestClient` is a **synchronous (blocking)** HTTP client in Spring Framework 6.1 and later. It has a fluent API similar to `WebClient` but is not a reactive client. Use `WebClient` if the requirement is truly a non-blocking processing pipeline.

## 1. Request flow: where are service-ID URLs handled?

When a service calls:

~~~java
restClient.get()
    .uri("http://inventory-service/api/items/{id}", "42")
    .retrieve()
    .body(ItemDto.class);
~~~

Overview of the flow:

~~~mermaid
sequenceDiagram
    autonumber
    participant C as order-service
    participant R as @LoadBalanced RestClient
    participant LB as Spring Cloud LoadBalancer
    participant S as ServiceInstanceListSupplier
    participant I as inventory-service instance

    C->>R: GET http://inventory-service/api/items/42
    R->>LB: Select instance for inventory-service
    LB->>S: Fetch ServiceInstance list
    S-->>LB: [inventory-a, inventory-b]
    LB-->>R: inventory-b (host:port)
    R->>I: GET /api/items/42
    I-->>R: HTTP status, headers, body
    R-->>C: DTO / ResponseEntity / exception
~~~

`RestClient` does not automatically look up instances via discovery just because a URL looks like a service name. You need a **`RestClient.Builder` bean annotated with `@LoadBalanced`**, compatible Spring Cloud LoadBalancer dependencies, and an instance-list source.

Three stages must be distinguished:

1. **Service ID resolution**: from `inventory-service` to the candidate list.
2. **Instance selection**: Round Robin or another policy selects one `ServiceInstance`.
3. **HTTP execution**: the client sends the request and receives an HTTP response or a connection/timeout error.

If no instance can be selected, the request never reaches the backend. This error differs from HTTP `404` or `503` returned by the target server.

## 2. Project prerequisites

The examples use Java 17+, a Spring Boot version supporting Spring Framework 6.1+ (such as Spring Boot 3.2+), and a **compatible Spring Cloud release train**. Let the project's BOM/dependency management select versions rather than arbitrarily mixing incompatible ones.

**Gradle (Groovy DSL):**

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
}
~~~

**Maven:**

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>
</dependencies>
~~~

`spring-boot-starter-web` provides MVC and common synchronous HTTP components; `spring-cloud-starter-loadbalancer` provides client-side load-balancing integration. Both dependency snippets show only what is needed for this lesson and do not replace the project's overall build and version-management configuration.

In real environments, the instance list usually comes from Eureka, Consul, Kubernetes, or a configured discovery source. To run a small lab **without a registry**, you can use `SimpleDiscoveryClient` with a static list.

## 3. Configuring two instances under the same service ID

Suppose two instances `inventory-a` and `inventory-b` serve the same API:

| Instance | Actual address | Logical service ID |
|---|---|---|
| inventory-a | `http://localhost:18081` | `inventory-service` |
| inventory-b | `http://localhost:18082` | `inventory-service` |

Configuration in the caller's `application.yml`:

~~~yaml
server:
  port: 18090

spring:
  application:
    name: order-service
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:18081
              - uri: http://localhost:18082
~~~

`SimpleDiscoveryClient` is a static instance source intended for small environments or demos. In production, dynamic discovery is more suitable when instances are deployed, removed, or scaled frequently.

A sample backend for the two processes:

~~~java
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

record ItemDto(String id, String name, int stock) {}

@RestController
@RequestMapping("/api/items")
class InventoryController {

    @Value("${instance.id:inventory-unknown}")
    private String instanceId;

    @GetMapping("/{id}")
    ResponseEntity<?> find(@PathVariable String id) {
        if ("missing".equals(id)) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Map.of("code", "ITEM_NOT_FOUND"));
        }

        if ("busy".equals(id)) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(Map.of("code", "INVENTORY_BUSY"));
        }

        return ResponseEntity.ok()
            .header("X-Instance-Id", instanceId)
            .body(new ItemDto(id, "Notebook", 7));
    }
}
~~~

Run two copies from the same Spring Boot application:

~~~bash
java -jar inventory-service.jar --server.port=18081 --instance.id=inventory-a
java -jar inventory-service.jar --server.port=18082 --instance.id=inventory-b
~~~

These commands assume you have built a Spring Boot artifact containing the sample controller and an `@SpringBootApplication` entry point. The filename `inventory-service.jar` is illustrative, not a pre-built artifact produced by this lesson.

Test the backends directly before testing LoadBalancer:

~~~bash
curl -i http://localhost:18081/api/items/42
curl -i http://localhost:18082/api/items/missing
~~~

Expect the first call to return HTTP `200` with header `X-Instance-Id: inventory-a`, and the second to return `404`.

## 4. Creating a @LoadBalanced RestClient.Builder properly

In the caller application, declare the builder bean:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class InventoryHttpConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }

    @Bean
    RestClient inventoryRestClient(
            @org.springframework.beans.factory.annotation.Qualifier(
                "loadBalancedRestClientBuilder"
            ) RestClient.Builder builder) {
        return builder.build();
    }
}
~~~

Spring Cloud integrates LoadBalancer components into the **builder bean** annotated with `@LoadBalanced`. When `builder.build()` is called, the created `RestClient` carries that configuration. The discovery dependency supplies the instance set, while the LoadBalancer algorithm chooses the target.

You can shorten the `@Qualifier` import in a real project:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;

// Inside @Bean inventoryRestClient:
RestClient inventoryRestClient(
        @Qualifier("loadBalancedRestClientBuilder")
        RestClient.Builder builder) {
    return builder.build();
}
~~~

The second snippet only illustrates the shorter syntax **replacing the corresponding method declaration above**, not an additional bean to register twice.

### Mistake: using RestClient.create() and expecting it to load balance automatically

~~~java
// Does not automatically use Spring Cloud LoadBalancer:
RestClient plain = RestClient.create();

plain.get()
    .uri("http://inventory-service/api/items/42")
    .retrieve()
    .body(String.class);
~~~

Calling `RestClient.create()` directly does not receive the interceptor/load-balancing configuration from the `@LoadBalanced RestClient.Builder` bean. Therefore, the host `inventory-service` will be handed to ordinary DNS and fail name resolution unless the environment has dedicated DNS or routing.

**Rule:** for service-ID URLs using Spring Cloud LoadBalancer, build clients from a **Spring-managed builder annotated with `@LoadBalanced`**. For external Internet URLs or endpoints that must be called directly via DNS, use a plain RestClient to avoid confusing hostnames with service IDs.

## 5. retrieve(): the standard operation for reading a body

`retrieve()` fits when the application needs the body mapped to a Java object by Spring's HTTP message converters:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
class InventoryGateway {

    private final RestClient restClient;

    InventoryGateway(RestClient inventoryRestClient) {
        this.restClient = inventoryRestClient;
    }

    ItemDto getItem(String id) {
        return restClient.get()
            .uri("http://inventory-service/api/items/{id}", id)
            .retrieve()
            .body(ItemDto.class);
    }
}
~~~

In the example, `ItemDto` is a data type in the caller with a matching JSON shape, such as `record ItemDto(String id, String name, int stock) {}`. Java code in the backend and caller can define DTOs in separate modules; sharing source files is not required.

Steps:

1. `get()` selects the HTTP GET method.
2. `uri("http://inventory-service/...", id)` constructs the URI; the hostname is the service ID.
3. LoadBalancer selects an instance; the HTTP request is sent to that instance.
4. `retrieve()` creates a `ResponseSpec` and applies default status handling.
5. `body(ItemDto.class)` decodes the JSON response into the DTO.

**Synchronous characteristic:** calling `body(...)` blocks the caller thread until a result or error arrives. Calling multiple services sequentially in a web request means total latency accumulates across those blocking calls.

### URI templates avoid manual string concatenation

Instead of:

~~~java
// Avoid building paths manually with unencoded input:
String url = "http://inventory-service/api/items/" + id;
~~~

Use:

~~~java
ItemDto item = restClient.get()
    .uri("http://inventory-service/api/items/{id}", id)
    .retrieve()
    .body(ItemDto.class);
~~~

You can use the URI builder for query parameters:

~~~java
List<ItemDto> items = restClient.get()
    .uri(uriBuilder -> uriBuilder
        .scheme("http")
        .host("inventory-service")
        .path("/api/items")
        .queryParam("category", "paper")
        .queryParam("limit", 20)
        .build())
    .retrieve()
    .body(new org.springframework.core.ParameterizedTypeReference<List<ItemDto>>() {});
~~~

This illustration returns a JSON array matching `List<ItemDto>`; the earlier sample backend only declared a single-item endpoint, so running the list example requires adding a matching `GET /api/items` endpoint. `ParameterizedTypeReference` preserves generic type info for the converter.

Do not hardcode `localhost:18081` in the client when the goal is to verify selection by service name.

## 6. retrieve().toEntity(): when status and headers are needed

When you only need the body, `body(ItemDto.class)` is usually enough. If business logic needs the HTTP status and headers from the instance, use `toEntity(...)`:

~~~java
import org.springframework.http.ResponseEntity;

ResponseEntity<ItemDto> entity = restClient.get()
    .uri("http://inventory-service/api/items/{id}", "42")
    .retrieve()
    .toEntity(ItemDto.class);

int status = entity.getStatusCode().value();
String chosenInstance =
    entity.getHeaders().getFirst("X-Instance-Id");
ItemDto item = entity.getBody();
~~~

This is how you observe which instance actually returned the response in the lab. The `X-Instance-Id` header is custom-created by the backend; Spring Cloud LoadBalancer **does not automatically attach** it to every response.

Notes:

- `toEntity(...)` is still governed by `retrieve()`'s default status handler; unhandled HTTP 4xx/5xx responses will throw an exception rather than returning a successful `ResponseEntity`.
- Responses with `204 No Content` or an empty body can cause `entity.getBody()` to be `null`.
- If only status and headers are needed without a body, you can use `retrieve().toBodilessEntity()`.

### When request headers need to be added

~~~java
ItemDto item = restClient.get()
    .uri("http://inventory-service/api/items/{id}", id)
    .header("X-Correlation-Id", correlationId)
    .accept(org.springframework.http.MediaType.APPLICATION_JSON)
    .retrieve()
    .body(ItemDto.class);
~~~

A correlation ID helps link logs between caller and backend. Never place authentication tokens, personal data, or sensitive info into URL queries or logs indiscriminately.

## 7. How does retrieve() handle HTTP 4xx/5xx by default?

With `retrieve()`, HTTP `4xx` and `5xx` statuses not handled by a custom handler **by default throw exceptions** belonging to `RestClientResponseException` (or its subclasses), rather than returning a DTO like 2xx statuses.

Example when the backend returns `404`:

~~~java
try {
    ItemDto item = restClient.get()
        .uri("http://inventory-service/api/items/missing")
        .retrieve()
        .body(ItemDto.class);
} catch (org.springframework.web.client.RestClientResponseException ex) {
    int status = ex.getStatusCode().value();
    String responseBody = ex.getResponseBodyAsString();
    // Classify 404, 429, 500, 503 according to business contract.
}
~~~

`RestClientResponseException` represents **an actual HTTP error response received**. Do not use this catch block to wrap no-instance errors, DNS errors, or connect timeouts.

Example classifying errors with `onStatus(...)`:

~~~java
ItemDto item = restClient.get()
    .uri("http://inventory-service/api/items/{id}", id)
    .retrieve()
    .onStatus(
        status -> status.value() == 404,
        (request, response) -> {
            throw new ItemNotFoundException(id);
        }
    )
    .onStatus(
        org.springframework.http.HttpStatusCode::is5xxServerError,
        (request, response) -> {
            throw new InventoryUnavailableException(
                "inventory-service returned " +
                response.getStatusCode().value());
        }
    )
    .body(ItemDto.class);
~~~

`ItemNotFoundException` and `InventoryUnavailableException` are **application-defined business exceptions**. The `onStatus(...)` handler receives the request and HTTP response; it can inspect headers/body to decide the error, while avoiding placing sensitive payloads into exceptions or logs.

Do not turn every `404` into “service unavailable”: `404` usually means the resource does not exist, whereas `503` indicates serving availability is temporarily degraded. Final classification depends on the API contract.

## 8. exchange(): lower-level response control

`exchange(...)` gives the caller direct access to `ClientHttpRequest` and `ClientHttpResponse` inside a callback. This is useful when you need to inspect the status before deciding how to read the body, handle multiple response shapes, or extract specific headers without `retrieve()`'s status-handler mechanism throwing automatically.

Example inspection response carrying the raw status, header, and body:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;

import org.springframework.web.client.RestClient;

record RawInventoryResult(
    int httpStatus,
    String instanceId,
    String rawBody
) {}

RawInventoryResult inspect(RestClient restClient, String id) {
    return restClient.get()
        .uri("http://inventory-service/api/items/{id}", id)
        .exchange((request, response) -> {
            int code = response.getStatusCode().value();
            String instanceId =
                response.getHeaders().getFirst("X-Instance-Id");

            // Only suitable for small responses in a lab.
            String body = new String(
                response.getBody().readAllBytes(),
                StandardCharsets.UTF_8
            );

            return new RawInventoryResult(code, instanceId, body);
        });
}
~~~

When calling `inspect(..., "42")`, the object may contain `httpStatus=200` and the item JSON. With `"missing"`, it may contain `httpStatus=404` and raw body `{"code":"ITEM_NOT_FOUND"}` **without automatically throwing an exception from `retrieve()`'s status handler**.

**Core difference: `exchange()` does not apply the status handlers used by `retrieve()`.** If an HTTP response has an error status, the `exchange()` callback must decide whether to return data, throw an exception, or execute a fallback.

The `exchange()` callback is invoked after the request has been sent and a response is present. A failure occurring **before receiving an HTTP response**, such as failing to select an instance or failing to connect, still fails the call; `exchange()` does not turn those failures into a synthetic response.

### Only use readAllBytes for small, trusted responses

The example reads the entire body into memory for easy observation. For large responses, streaming, file downloads, or unbounded payloads, use a bounded parser/streaming strategy. Never log raw bodies containing sensitive data.

## 9. exchange(): deciding 404, 503, and success responses by contract

Another example using `exchange()` to map HTTP statuses according to application choice:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Optional;

import org.springframework.http.HttpStatusCode;

Optional<String> getRawItem(RestClient restClient, String id) {
    return restClient.get()
        .uri("http://inventory-service/api/items/{id}", id)
        .exchange((request, response) -> {
            HttpStatusCode status = response.getStatusCode();

            if (status.value() == 404) {
                return Optional.empty();
            }

            if (!status.is2xxSuccessful()) {
                throw new InventoryUnavailableException(
                    "HTTP " + status.value() +
                    " from inventory-service");
            }

            String json = new String(
                response.getBody().readAllBytes(),
                StandardCharsets.UTF_8
            );
            return Optional.of(json);
        });
}
~~~

In this approach:

- `404` becomes `Optional.empty()`, fitting when “not found” is a valid outcome.
- `5xx` and non-2xx statuses other than 404 are converted into a custom exception.
- `2xx` is returned as raw JSON so the example focuses on status handling; if a DTO is needed, use an appropriate converter or JSON mapper.
- If `204 No Content` is valid, handle an empty body explicitly rather than assuming JSON is always present.

Not every API should return `Optional.empty()` for 404. For some APIs, 404 signals misconfigured routes, wrong paths, or missing endpoints. The callback's decision must match the agreed contract between both services.

## 10. Comparing retrieve and exchange

| Criterion | `retrieve()` | `exchange(...)` |
|---|---|---|
| Abstraction level | High, convenient with DTOs | Low, direct access to request/response |
| Reading JSON body | `body(MyDto.class)` | Read/convert body manually in callback |
| Reading status/headers | `toEntity(...)` or `toBodilessEntity()` | `response.getStatusCode()`, `response.getHeaders()` |
| Default HTTP 4xx/5xx | Throws exception via default status handler | Callback handles it; `retrieve()` default status handlers do not apply |
| Customizing HTTP errors | `onStatus(...)` | `if`/`switch` inside callback |
| No instance selected | Fails before HTTP response arrives | Also fails before response callback runs |
| Complexity | Low for standard APIs | Higher; status/body must be handled carefully |
| Best suited for | CRUD, DTOs, clear HTTP contracts | Special responses, status branching, raw body/headers |

Both methods **use the same LoadBalancer mechanism** when called on the same integrated `RestClient`. `retrieve()` and `exchange()` differ in **response handling**, not the instance-selection algorithm.

### Selection guidelines

- Use **`retrieve()`** in most cases when reading JSON DTOs, plus `onStatus(...)` when custom error handling is needed.
- Use **`retrieve().toEntity(...)`** when you need status/headers of a successful response.
- Use **`exchange(...)`** when you must branch across multiple statuses, read different body shapes per status, or work closer to the HTTP transport.
- Do not use `exchange()` merely to bypass 4xx/5xx exception handling: omitting error branches can easily make the application interpret HTTP 503 as success.

## 11. Distinguishing pre-HTTP errors from server errors

When calling by service ID, not every failure produces a `ClientHttpResponse`:

~~~mermaid
flowchart TD
    A["RestClient calls inventory-service"] --> B{"Did LoadBalancer select an instance?"}
    B -->|No| C["No server: handle selection error"]
    B -->|Yes| D{"Connected and received HTTP response?"}
    D -->|No| E["Network error / timeout / TLS"]
    D -->|Yes| F{"HTTP status?"}
    F -->|2xx| G["Decode body or handle response"]
    F -->|4xx| H["Contract / resource / permission error"]
    F -->|5xx| I["Server or dependency error"]
~~~

Common failures:

| Error | Is there an HTTP response from `inventory-service`? | How to handle |
|---|---|---|
| No instances for service ID | No | Check service name, discovery, and supplier |
| Connection refused or connect timeout | No | Check running instances, port, network |
| Read/response timeout | Complete response may not have arrived | Check load, deadlines, connection pool |
| HTTP `404` | Yes | Verify resource/path and contract |
| HTTP `429` | Yes | Check rate limits and retry policy if safe |
| HTTP `503` | Yes from backend or gateway if actually received | Investigate overload, health, and dependencies |
| JSON deserialization error | Possibly after receiving 2xx status | Check schema, media type, and converter |

In some integrations/versions, missing `ServiceInstance` cases may raise an exception such as `IllegalStateException`. Exact exception types can vary by client, retry setup, and Spring Cloud version. Do not assume every error is a `RestClientResponseException`; that type represents cases where an HTTP response with an error status was received.

A gateway or caller itself may also synthesize HTTP `503` when no instance is found, so you must distinguish **the HTTP response sent back to the caller** from **an HTTP response from `inventory-service`**.

## 12. Timeouts for LoadBalanced RestClient

Configure timeouts at the HTTP client layer. Lab example using `SimpleClientHttpRequestFactory`:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class InventoryTimeoutConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        SimpleClientHttpRequestFactory factory =
            new SimpleClientHttpRequestFactory();

        factory.setConnectTimeout(2000);  // 2 seconds
        factory.setReadTimeout(3000);     // 3 seconds

        return RestClient.builder().requestFactory(factory);
    }
}
~~~

This is an **alternative** to the `loadBalancedRestClientBuilder` bean in section 4; do not register two beans of the same name concurrently in one context. In high-load systems, pick an HTTP request factory with connection pooling and dedicated timeout settings suited to your library versions.

Distinguish clearly:

- **Connect timeout** bounds connection establishment time per the transport used.
- **Read timeout** bounds data-reading wait time per the HTTP request factory.
- **Overall deadline** of a business operation may span discovery, instance selection, connection, reading the body, and multiple retries; setting only those two timeouts does not guarantee a hard overall deadline.

If backend B is temporarily slow, `RestClient` still holds the caller thread while waiting. Setting timeouts too long can exhaust threads; setting them too short can trigger false errors on normal network paths. Tune according to SLOs and observed latency distributions.

## 13. Retries: not every error should be retried

When a request fails, retries can help if an instance just died before discovery refreshed or a transient connection error occurred. However, retries add load and can repeat side effects.

Guidelines:

1. Cap **total attempts**, total duration, and backoff; add jitter when needed to avoid synchronized retry storms.
2. Do not blindly retry all HTTP `4xx` responses; `404` rarely becomes `200` just by repeating the call.
3. For HTTP `429` or `503`, check the API contract, `Retry-After` guidance if present, and time budget.
4. For write operations such as inventory deduction, order creation, or payments, require **idempotency** or an idempotency key before retrying.
5. Do not assume retries pick a different instance automatically. Spring Cloud LoadBalancer has separate retry integrations depending on version; verify the policy and actual selection outcomes.
6. Avoid stacked retries across RestClient, LoadBalancer, gateway, and service mesh, as attempt counts can multiply.

Simple illustration: 100 requests/second, each retried up to three times **total** on failure, can generate around 300 attempts/second if most calls continue failing. If the root cause is backend overload, uncontrolled retries make the outage worse.

**Neither `exchange()` nor `retrieve()` automatically enables or guarantees retries.** Retry policy belongs to client/integration configuration and resilience libraries explicitly configured by the application.

## 14. Observing the selected instance and response

To verify which instance received a request, the lab uses the `X-Instance-Id` header returned by the backend. You can call repeatedly:

~~~bash
for i in $(seq 1 8); do
  curl -i http://localhost:18090/demo/item/42
done
~~~

The caller can expose a test controller:

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
class DemoController {

    private final RestClient restClient;

    DemoController(RestClient inventoryRestClient) {
        this.restClient = inventoryRestClient;
    }

    @GetMapping("/demo/item/{id}")
    ResponseEntity<ItemDto> item(@PathVariable String id) {
        return restClient.get()
            .uri("http://inventory-service/api/items/{id}", id)
            .retrieve()
            .toEntity(ItemDto.class);
    }
}
~~~

Because the controller returns the backend's `ResponseEntity`, the backend's `X-Instance-Id` header can be observed on the caller's response in the lab. In production, do not blindly mirror all backend headers onto public APIs, as this can leak infrastructure details or break contracts.

With Round Robin and a stable instance list, repeated calls usually show both `inventory-a` and `inventory-b`; exact selection ratios also depend on caller concurrency, health/discovery states, and retry configuration.

Recommended fields/metrics to log and measure:

| Field or metric | Purpose |
|---|---|
| `serviceId` | Identify the logical target service |
| Selected instance | Identify target host/port when troubleshooting errors |
| `traceId` / `correlationId` | Correlate logs between caller and backend |
| HTTP method and operation | Classify calls without excessive cardinality |
| HTTP status from backend | Distinguish 4xx/5xx responses received |
| Exception class/cause | Recognize pre-HTTP errors |
| Connect/read latency | Pinpoint timeouts and bottlenecks |
| Retry attempts | Measure attempt counts and load amplification |
| Supplier/discovery instance count | Check whether candidates were available |

You can combine Spring Boot/Micrometer observability with hooks such as `LoadBalancerLifecycle` to observe instance selection and call completion times. Do not assume a LoadBalancer metric automatically captures internal server processing time.

## 15. Testing retrieve and exchange across different responses

With the sample backend returning `200`, `404`, and `503`, verify the table below:

| Request | With `retrieve()` without `onStatus` | With `exchange()` returning `RawInventoryResult` |
|---|---|---|
| `GET /api/items/42` | `ItemDto` object | `httpStatus=200`, JSON body |
| `GET /api/items/missing` | HTTP 404 exception | `httpStatus=404`, error body |
| `GET /api/items/busy` | HTTP 503 exception | `httpStatus=503`, error body |
| Backend returns 204 | `body(...)` may be `null` | `httpStatus=204`, empty body |
| No instance in discovery | Target-selection failure before HTTP | Failure before callback is invoked |
| Instance stops after selection | Connection/timeout exception | Failure before response arrives |
| Invalid JSON schema | Decode error converting DTO | Raw body may still be returned if callback does not decode |

Note that `GET /api/items/busy` is a scenario path of the lab backend: calling `/api/items/{id}` with `id=busy`. For HTTP `204`, the backend would need an added branch returning `204` if you want to run it; the table presents **behaviors to verify**, not a claim that the sample backend already includes that branch.

### Common pitfalls checklist

- Creating `RestClient.create()` or `RestClient.builder()` manually instead of using the `@LoadBalanced` builder, causing service IDs to be resolved directly via DNS.
- Service ID in the URI not matching discovery; e.g., calling `inventory` when `inventory-service` is registered.
- Calling the right service ID while all instances are filtered out by health checks, zone rules, or filters.
- Confusing `toEntity()` with `exchange()`: `toEntity` still uses `retrieve()`'s status handlers.
- Assuming `exchange()` automatically throws exceptions on HTTP `404` or `503`.
- Using `onStatus` to catch “no instance selected” errors; no HTTP response exists yet at that stage.
- Reading the body inside `exchange()` without bounding size or checking status.
- Setting overly long timeouts or unbounded retries, tying up blocking threads.
- Passing internal headers or raw error bodies straight to public APIs without checking for sensitive data.
- Testing with only one instance, failing to prove selection by service ID.

## 16. Conclusion and operating principles

- **`@LoadBalanced RestClient.Builder`** is the link that turns the URI host into a service ID and lets Spring Cloud LoadBalancer select a `ServiceInstance`.
- **`retrieve()`** is the standard way to obtain DTOs, headers, and success statuses; it handles HTTP 4xx/5xx via default status handlers or `onStatus` declared by the application.
- **`exchange()`** gives direct control over the HTTP response in a callback and does not apply `retrieve()`'s status handlers; the application must intentionally handle status, body, and errors.
- **No instance selected, connection failure, and HTTP error status are separate stages**. Distinguish them to configure discovery, health checks, timeouts, retries, and observability accurately.
- **RestClient is blocking**; factor in worker threads and deadlines when chaining multiple service calls. If a non-blocking reactive pipeline is required, use WebClient rather than inserting `block()` arbitrarily onto a reactive event loop.

Key point to remember: `retrieve()` and `exchange()` **do not decide the load-balancing algorithm**. They determine how the application handles the response after Spring Cloud LoadBalancer has selected an instance and the HTTP client has attempted the call. Reliable inter-service communication requires coordinating service discovery, instance filtering, health checks, deadlines, bounded retries, and clear observability.
