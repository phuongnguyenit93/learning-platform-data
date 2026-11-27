# Testing and Verifying Paths, Headers, Bodies, and Status Codes

## 1. Goal: Proving a Request Actually Passed Through the Gateway

In the **Setup** stage of **SPRING_CLOUD_GATEWAY**, a successful application startup does not yet prove that routes work properly. You need to send real HTTP requests from a client, inspect the exact **path**, **headers**, **body**, and **status code**, and determine whether a response came from the gateway or from the microservice.

Spring Cloud Gateway uses **route predicates** to select a route, a **filter chain** to apply path/header transformations or security policies, and then forwards the request to the target service. This lesson sets up a small "echo" backend to observe what the service **actually receives**. This verification workflow is the baseline before adding discovery/load balancing, authentication, rate limiting, circuit breakers, retries, TLS, or metrics/tracing in a microservices architecture.

After this lesson, you will be able to verify on your own:

1. Did the request match the predicate and enter the right route?
2. Does the path after `StripPrefix` match the backend endpoint?
3. Do headers added or overwritten by the gateway reach the backend, and do response headers reach the client?
4. Does the request's JSON body reach the backend with intact data?
5. Are backend status codes forwarded to the client, and how do gateway-generated status codes differ?
6. When a test fails, should you inspect the client, gateway, or backend first?

> **Scope:** This example uses **Spring Cloud Gateway Server WebFlux** with the backend running directly on the development machine. Both applications use HTTP on `localhost` for ease of testing; in real deployments, configure TLS, authentication, header policies, and access observability appropriately.

## 2. Test Architecture and Expected Results

We run two applications as two separate processes/ports:

| Component | Test Address | Role |
| --- | --- | --- |
| Client | `curl` or HTTP client | Calls the gateway and reads results |
| Gateway WebFlux | `http://localhost:8080` | Matches route, strips path prefix, sets headers, forwards |
| Echo backend | `http://localhost:9091` | Returns received method/path/query/headers/body; generates configurable status |

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Spring Cloud Gateway :8080
    participant B as Echo service :9091
    C->>G: GET /api/echo/inspect/42?view=full
    Note over G: Predicate Path=/api/echo/** matches
    Note over G: StripPrefix=1 and SetRequestHeader
    G->>B: GET /echo/inspect/42?view=full
    B-->>G: 200 JSON containing received path and headers
    Note over G: AddResponseHeader
    G-->>C: 200 JSON and X-Gateway-Response
~~~

An example route transforms:

| Attribute | Client Sends to Gateway | Backend Receives |
| --- | --- | --- |
| Method | `GET` | `GET` |
| Path | `/api/echo/inspect/42` | `/echo/inspect/42` |
| Query | `view=full` | `view=full` |
| `X-Debug-Client` header | `manual-test` | `manual-test` |
| `X-Gateway-Marker` header | May be absent or spoofed by client | `edge-lab` overwritten by gateway |
| Body | None in GET example | None |
| `X-Gateway-Response` response header | Absent before calling | Added by gateway to response sent to client |

What needs to be compared is the **actual data recorded by the backend**, not just YAML config that "looks right."

## 3. Preparing Two Spring Boot Applications

This example assumes you have a JDK matching your Spring Boot / Spring Cloud versions, Maven (or Maven Wrapper), and `curl`. Choose a **Spring Cloud release train compatible with Spring Boot** and import the Spring Cloud BOM in the gateway project; avoid mixing arbitrary versions. Both applications should run independently to make the network boundary clear.

### 3.1. Echo Backend

Create a Spring Boot application with the `spring-boot-starter-webflux` dependency. This backend is solely for testing and needs no service registry, database, or extra security.

Backend `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: echo-service
server:
  port: 9091
~~~

Startup class `EchoApplication.java`:

~~~java
package demo.echo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EchoApplication {
    public static void main(String[] args) {
        SpringApplication.run(EchoApplication.class, args);
    }
}
~~~

Create a controller in the **same package** `demo.echo`:

~~~java
package demo.echo;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class EchoController {

    private Map<String, Object> describe(
            ServerHttpRequest request, String clientHeader, String marker) {

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("method", request.getMethod().name());
        result.put("path", request.getPath().value());
        result.put("query", request.getURI().getRawQuery());
        result.put("clientHeader", clientHeader);
        result.put("gatewayMarker", marker);
        return result;
    }

    @GetMapping("/echo/inspect/{id}")
    public Map<String, Object> inspect(
            @PathVariable String id,
            @RequestHeader(value = "X-Debug-Client", required = false)
                    String clientHeader,
            @RequestHeader(value = "X-Gateway-Marker", required = false)
                    String marker,
            ServerHttpRequest request) {

        Map<String, Object> result = describe(request, clientHeader, marker);
        result.put("id", id);
        return result;
    }

    @PostMapping("/echo/inspect")
    public Mono<Map<String, Object>> inspectBody(
            @RequestBody Mono<Map<String, Object>> body,
            @RequestHeader(value = "X-Debug-Client", required = false)
                    String clientHeader,
            @RequestHeader(value = "X-Gateway-Marker", required = false)
                    String marker,
            ServerHttpRequest request) {

        return body.map(payload -> {
            Map<String, Object> result =
                    describe(request, clientHeader, marker);
            result.put("body", payload);
            return result;
        });
    }

    @GetMapping("/echo/status/{code}")
    public ResponseEntity<String> status(@PathVariable int code) {
        return ResponseEntity.status(code)
                .header("X-Origin", "echo-service")
                .body("backend-status-" + code);
    }
}
~~~

This controller supports:

- `GET /echo/inspect/{id}`: returns JSON describing the received request.
- `POST /echo/inspect`: deserializes the JSON body into a `Map` and places it back in the JSON response to verify **data content**.
- `GET /echo/status/{code}`: intentionally returns the specified HTTP status code with `X-Origin: echo-service` to identify responses from the backend.

While the backend has no gateway in front of it yet, test calling it directly:

~~~bash
curl -i "http://localhost:9091/echo/inspect/42?view=full"
~~~

The backend is expected to return `200 OK` with JSON containing `"path":"/echo/inspect/42"` and `"id":"42"`; the unset `clientHeader` and `gatewayMarker` fields will be `null`. Verifying the backend independently helps distinguish target application errors from routing errors later on.

### 3.2. Spring Cloud Gateway Application

In the gateway project, use Spring Boot with Spring Cloud Gateway **Server WebFlux** and a compatible Spring Cloud BOM. In recent releases, the starter is typically:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
</dependency>
~~~

Earlier versions of Spring Cloud Gateway used the starter name `spring-cloud-starter-gateway`. Choose the dependency according to the documentation for the **exact version** you are using; do not add `spring-boot-starter-web` (Servlet MVC) to a WebFlux Gateway project.

Startup class:

~~~java
package demo.gateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GatewayApplication {
    public static void main(String[] args) {
        SpringApplication.run(GatewayApplication.class, args);
    }
}
~~~

With Spring Cloud Gateway Server WebFlux using the new configuration namespace, place the following in `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: gateway-lab
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: echo-route
              uri: http://localhost:9091
              predicates:
                - Path=/api/echo/**
              filters:
                - StripPrefix=1
                - SetRequestHeader=X-Gateway-Marker, edge-lab
                - AddResponseHeader=X-Gateway-Response, routed
~~~

> **Version differences:** Some WebFlux Gateway releases use `spring.cloud.gateway.routes` instead of `spring.cloud.gateway.server.webflux.routes`. On those versions, move the **entire `routes` list** under `spring.cloud.gateway.routes`; do not define both namespaces at the same time. If you configure the wrong namespace, the application may start without registering any routes — and tests will return 404.

Configuration meaning:

| Component | Behavior to Verify |
| --- | --- |
| `id: echo-route` | Route name for identification in config and logs |
| `uri: http://localhost:9091` | Static HTTP target for testing without service discovery yet |
| `Path=/api/echo/**` | Selects requests whose path begins with this pattern |
| `StripPrefix=1` | Strips the first segment (`api`), turning `/api/echo/inspect/42` into `/echo/inspect/42` |
| `SetRequestHeader` | Overwrites `X-Gateway-Marker` to `edge-lab` on the forwarded request, even if the client sent a different value |
| `AddResponseHeader` | Appends `X-Gateway-Response: routed` to the route's response |

No filter in this example is configured to modify the JSON body or alter the HTTP status returned by the backend.

### 3.3. Starting in the Right Order

Open **two terminals** in the two project directories. Start the backend first, test the endpoint directly on `9091`, and then start the gateway on `8080`:

~~~bash
# Terminal 1: inside the echo-service project
./mvnw spring-boot:run

# Terminal 2: inside the gateway-lab project
./mvnw spring-boot:run
~~~

If the project uses an installed Maven, run `mvn spring-boot:run`; on Windows you can use `mvnw.cmd spring-boot:run`. Each command must run inside the **matching project directory** containing its Maven configuration.

During initial testing, hold off on adding auth, rate limiter, retry, or circuit breaker filters that have not yet been explained, because they can block or alter outcomes before you verify the basic route.

## 4. Verifying Paths and Query Strings

Call the gateway:

~~~bash
curl -i "http://localhost:8080/api/echo/inspect/42?view=full" \
  -H "X-Debug-Client: manual-test"
~~~

An **illustrative** response (header order and JSON field order may differ):

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
X-Gateway-Response: routed

{"method":"GET","path":"/echo/inspect/42","query":"view=full","clientHeader":"manual-test","gatewayMarker":"edge-lab","id":"42"}
~~~

Verify three values in the body:

1. `path` is `/echo/inspect/42`, proving the gateway applied `StripPrefix=1` before calling the backend.
2. `query` remains `view=full`, proving the query string passed through the prefix transformation.
3. `id` is `42`, proving the backend endpoint matched and handled the rewritten path properly.

If the response shows `"path":"/api/echo/inspect/42"`, most likely the prefix-stripping filter was not loaded, a different route was selected, or the request was sent directly to a backend differing from the test setup. If the status code is `404`, determine whether it is **404 because the gateway found no route** or **404 because the backend has no endpoint** (see section 7).

## 5. Verifying Request Headers and Response Headers

In the GET command above, the client intentionally sent `X-Debug-Client: manual-test`; the gateway added/overwrote `X-Gateway-Marker: edge-lab`. Because the backend echoes both in JSON, you can verify that headers actually traversed both hops.

To prove `SetRequestHeader` **overwrites** client-supplied values, try:

~~~bash
curl -i "http://localhost:8080/api/echo/inspect/42" \
  -H "X-Gateway-Marker: forged-value" \
  -H "X-Debug-Client: from-client"
~~~

The backend result must show:

~~~json
{
  "method": "GET",
  "path": "/echo/inspect/42",
  "query": null,
  "clientHeader": "from-client",
  "gatewayMarker": "edge-lab",
  "id": "42"
}
~~~

At the same time, in the **response headers** of `curl -i`, look for:

~~~http
X-Gateway-Response: routed
~~~

Security implication: a header attached by the gateway for diagnostic purposes **does not automatically become proof of identity**. To trust user-identifying headers, you need real authentication, stripping of spoofed client values, protection of the gateway-to-backend channel, and restrictions preventing direct access to the backend.

Do not expect every client header to be forwarded verbatim. Proxies can handle hop-by-hop headers such as `Host`, `Connection`, `Content-Length`, and `Transfer-Encoding` per hop; furthermore, `Forwarded` and `X-Forwarded-*` behavior depends on reverse proxy architecture and trusted proxy lists.

## 6. Verifying Request Bodies with POST JSON

To test bodies, send JSON through the gateway to the `POST /echo/inspect` endpoint. Example in a Bash environment:

~~~bash
curl -i -X POST "http://localhost:8080/api/echo/inspect" \
  -H "Content-Type: application/json" \
  -H "X-Debug-Client: body-check" \
  --data-binary '{"orderId":"O-42","quantity":2,"paid":false}'
~~~

The `200 OK` response should carry a body like:

~~~json
{
  "method": "POST",
  "path": "/echo/inspect",
  "query": null,
  "clientHeader": "body-check",
  "gatewayMarker": "edge-lab",
  "body": {
    "orderId": "O-42",
    "quantity": 2,
    "paid": false
  }
}
~~~

Key verification steps:

- **Path:** the backend sees `/echo/inspect`, not `/api/echo/inspect`.
- **Method:** remains `POST`, not accidentally turned into `GET`.
- **Body:** includes all three fields `orderId`, `quantity`, and `paid` with the right data types (string, number, boolean).
- **Headers:** `Content-Type: application/json` lets the backend pick the JSON decoder; `X-Gateway-Marker` remains `edge-lab`.
- **Status and response header:** valid requests return `200` and include `X-Gateway-Response: routed`.

This example proves **data-equivalent JSON content**, not byte-for-byte identity of the raw payload. The backend deserialized JSON into a `Map` and re-serialized it to JSON, so whitespace or field order may differ. To prove byte-for-byte integrity, you would need a backend returning a raw body checksum or comparing raw bytes at both ends.

**Specific to Windows PowerShell:** use `curl.exe` to avoid Windows PowerShell 5.1's `curl` alias. For complex JSON payloads, save UTF-8 into `payload.json` and pass `--data-binary "@payload.json"`; use UTF-8 **without BOM** when comparing bytes or working with strict parsers.

### What If the Request Body Does Not Reach the Backend?

Compare against a **direct** POST to the backend:

~~~bash
curl -i -X POST "http://localhost:9091/echo/inspect" \
  -H "Content-Type: application/json" \
  --data-binary '{"orderId":"O-42","quantity":2,"paid":false}'
~~~

If calling directly succeeds while going through the gateway fails, check the route, body-modifying filters, request size limits, or any custom filter that reads `Flux<DataBuffer>` without passing the body back down the chain. In WebFlux, the body is a reactive stream; calling `block()` or `subscribe()` directly inside a gateway filter can cause lifecycle and performance bugs. In this lab, `StripPrefix` and `SetRequestHeader` do not read the body, so JSON forwards without any body-rewrite configuration.

## 7. Verifying Status Codes and Error Origins

The gateway can return errors directly at the edge (such as no matching route, rate limiting, or failed authentication), or forward errors intentionally returned by the backend. These two categories must be distinguished.

### 7.1. Backend Intentionally Returns a Non-200 Status

Call the status endpoint created earlier:

~~~bash
curl -i "http://localhost:8080/api/echo/status/418"
~~~

Expected result:

~~~http
HTTP/1.1 418
X-Origin: echo-service
X-Gateway-Response: routed

backend-status-418
~~~

HTTP status `418` here is a test code **intentionally produced by the backend**. The `X-Origin: echo-service` header and `backend-status-418` body signal that the response came from the backend through the gateway; `X-Gateway-Response: routed` was added by the gateway on the return path. You can try `/api/echo/status/404` or `/api/echo/status/503` to see the gateway forward 4xx/5xx status codes from the backend under the current configuration.

Call the same endpoint directly:

~~~bash
curl -i "http://localhost:9091/echo/status/418"
~~~

The direct response includes `X-Origin` but **lacks the `X-Gateway-Response` header** configured on the gateway, helping you compare the two paths.

### 7.2. Gateway Finds No Matching Route

Call a path outside the `Path=/api/echo/**` predicate:

~~~bash
curl -i "http://localhost:8080/api/other/inspect/42"
~~~

If no other route or handler exists, the gateway returns **404 Not Found**. The echo service never receives this request. The absence of `X-Gateway-Response: routed` is also a clue, because that filter belongs only to the `echo-route` route.

### 7.3. Route Matches, But Backend Has No Endpoint

Call a path that **matches the route** yet has no mapping on the backend:

~~~bash
curl -i "http://localhost:8080/api/echo/missing"
~~~

The gateway matches `Path=/api/echo/**`, strips the prefix to `/echo/missing`, and forwards it; the backend then returns **404** because no endpoint matches. The client sees 404 in both cases, but the root cause is completely different from scenario 7.2.

| Scenario | Route Matches? | Does Backend Receive HTTP Request? | Signals to Compare |
| --- | --- | --- | --- |
| `/api/other/inspect/42` | No, when only the example route exists | No | 404 at gateway; no backend request log |
| `/api/echo/missing` | Yes | Yes | Backend receives `/echo/missing` and returns 404 |
| `/api/echo/status/418` | Yes | Yes | Backend produces 418, `X-Origin`, and distinctive body |
| `/api/echo/inspect/42` | Yes | Yes | Backend returns 200 and JSON describing the request |

If you stop the backend to test connection failures, the gateway typically produces a 5xx error. **Do not assume a single fixed status code** across all versions and configs: the exact result depends on error handlers, timeouts, retries, circuit breakers, or fallbacks enabled. With the static URI in this lab, connection failures also differ from `lb://service-id` finding no instances (typically 503 by default with Gateway WebFlux LoadBalancer).

## 8. Smoke Test Matrix and How to Compare Results

Run the following checks **after** both applications are up. This table is a reference benchmark for you to compare against your actual results, not output measured automatically in this article.

| Test Case | Request Through Gateway | Main Expectation |
| --- | --- | --- |
| Route and path | `GET /api/echo/inspect/42?view=full` | 200, backend path `/echo/inspect/42`, query `view=full` |
| Client header | Above GET with `X-Debug-Client: manual-test` | Response JSON contains `clientHeader=manual-test` |
| Header overwrite | Above GET with `X-Gateway-Marker: forged-value` | Response JSON contains `gatewayMarker=edge-lab` |
| Response header | Any GET matching the route | Response contains `X-Gateway-Response: routed` |
| JSON body | `POST /api/echo/inspect` with valid JSON | 200 and echoed body preserves fields/types |
| Backend status | `GET /api/echo/status/418` | 418, `X-Origin: echo-service`, body `backend-status-418` |
| Unmatched route | `GET /api/other/inspect/42` | Typically 404, backend never receives request |
| Missing backend endpoint | `GET /api/echo/missing` | Typically 404 after the route matched |

Example quick status checks from a Bash terminal without printing full bodies:

~~~bash
curl -sS -o /dev/null -w 'GET inspect: %{http_code}\n' \
  "http://localhost:8080/api/echo/inspect/42"

curl -sS -o /dev/null -w 'Backend status: %{http_code}\n' \
  "http://localhost:8080/api/echo/status/418"

curl -sS -o /dev/null -w 'No route: %{http_code}\n' \
  "http://localhost:8080/api/other/inspect/42"
~~~

With the **right configuration**, the expected outputs are `200`, `418`, and `404` respectively. The `curl` exit code and the HTTP status code are **two different signals**: an HTTP 404 or 418 response can still leave `curl` exiting with code 0 if `--fail` is not passed. When automating smoke tests, check `%{http_code}` explicitly or use `--fail-with-body` if your curl version supports it.

To inspect full headers and connection flow, use `curl -v` or `curl -i`. For JSON bodies, verify JSON structure rather than relying on field order or line breaks.

## 9. Diagnosing Errors by Location

### Gateway Returns 404 for Every Request

Check whether the gateway application loaded **the right `routes` configuration namespace** for its version, whether port `8080` actually belongs to the gateway, and whether the `Path=/api/echo/**` predicate matches the client path. If the application has Actuator and the gateway endpoint is **secured for access**, inspect the exposed route info to confirm routes actually registered. Never open management endpoints publicly just for debugging.

### Gateway Returns 502/503/504 or Connection Errors

Call the backend directly on `9091` first. Check that the service is running, the `uri` URL is accurate, and `localhost` is not confused across environments. When the gateway runs inside a Docker container, `localhost:9091` refers to **the gateway container itself**, not the host machine or backend container. Use the service name/container network or an appropriate reachable address. Also check timeouts or circuit breakers if enabled.

### Backend Receives the Wrong Path

Print or echo the path **at the backend**. Cases where `/api/echo/inspect/42` is not rewritten to `/echo/inspect/42` usually relate to `StripPrefix` not being applied, a different route being selected, or another `RewritePath` filter altering the path before/after. Route predicates select routes from the incoming request before gateway filters run; do not confuse the predicate-matched path with the forwarded path.

### Missing or Wrong Headers

Compare headers on **both request and response**. `SetRequestHeader` modifies the request going to the backend; `AddResponseHeader` modifies the response returning to the client. These two filters operate in opposite directions. If a reverse proxy or load balancer sits in front, hop-by-hop header handling and `Forwarded`/`X-Forwarded-*` configuration also affect actual values.

### Empty Body or 400 Returned

Send the POST directly to the backend to verify the endpoint accepts `Content-Type: application/json` and valid JSON. If it fails only through the gateway, inspect body-reading/modifying filters, request size limits, client disconnect events, and `DataBuffer` handling. A `GlobalFilter` that subscribes to or consumes the request body without re-emitting it downstream can break forwarding.

### Status Differs from Backend

Check whether any response-status filter, security check, rate limiter, circuit breaker/fallback, timeout, or exception handler intervened. The gateway can return 401, 403, 429, or 5xx **before** the microservice ever receives the request; when the backend intentionally returns 4xx/5xx, the default route configuration usually forwards that code. Combine status, body, headers, backend access logs, and traces to pinpoint responsibility accurately.

## 10. From Lab to Multi-Service Gateway

This setup lesson uses `uri: http://localhost:9091` to isolate HTTP verification. In microservices, you can replace the URI with `lb://echo-service` and configure Spring Cloud LoadBalancer with an appropriate service discovery source. The same smoke test suite should still pass for paths, headers, bodies, and statuses, while introducing an instance-selection step and a new class of failures: wrong service ID, empty registry instances, or unhealthy selected instances.

As you add more Spring Cloud Gateway capabilities, maintain a similar test suite:

- **Authentication/authorization:** add tests for missing/invalid tokens and insufficient permissions; verify requests are blocked at the gateway or backend without leaking tokens to logs.
- **Rate limiting:** send bursts under the same key and verify 429 behavior per configuration; avoid relying on lucky bucket timing.
- **Circuit breakers, timeouts, retries:** use a fault/latency-injecting backend to verify status codes, fallbacks, and backend invocation counts; be especially careful retrying creation/write operations.
- **TLS:** verify clients connect over HTTPS with valid certificates and, if using HTTPS/mTLS to backends, verify the gateway → service hop as well.
- **Observability:** propagate trace IDs / correlation IDs, measure per-hop latency, and log route ID, selected target URL, and status; never log Authorization headers, cookies, or sensitive bodies.

**Lesson completion criterion:** You can prove with real requests and responses that `/api/echo/...` passes through the route and reaches the backend as `/echo/...`; headers and JSON bodies preserve the right content; status codes 200, 418, and 404 reflect distinct scenarios; and you know how to trace step-by-step when results diverge. This provides the empirical foundation for building a secure, observable, and operable API Gateway.
