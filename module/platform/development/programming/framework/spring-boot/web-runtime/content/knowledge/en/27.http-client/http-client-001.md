# Distinguishing the Request-Receiving Server from a Client Calling Another Service

## 1. Lesson Objectives

In Spring Boot, **the same process can act as both an HTTP server and an HTTP client**. The role is determined separately for each HTTP exchange:

- When a browser sends `GET /api/items/42` to Spring Boot, the browser is the client; Spring Boot is the **server receiving the request**.
- When Spring Boot code calls `GET http://catalog:8081/catalog/items/42`, Spring Boot becomes the **client sending the request**; catalog is the server on the second hop.
- When catalog returns a result, Spring Boot processes the data and **creates a new response** for the browser; there is no rule requiring the two responses to have the exact same status, headers, or body.

After this lesson, you will be able to:

1. Clearly distinguish **inbound** (coming into the application) from **outbound** (going out of the application), requests from responses, and the two client/server roles.
2. Explain Spring MVC controllers, embedded Tomcat, and HTTP clients such as `RestClient`, `WebClient`, `RestTemplate`, and JDK `HttpClient`.
3. Run a Java 17+/Spring Boot 3.3.5 lab with two processes on ports 8080 and 8081, demonstrating success, 404, timeout, and dependency-down outcomes.
4. Understand why `server.port` is not the outbound client's port, and why the server thread pool is different from an HTTP client connection pool.
5. Design timeouts, response error mapping, service authentication, observability, and retry limits.
6. Avoid confusing browser CORS with backend API calls, and avoid SSRF vulnerabilities from user-controlled destination URLs.

This lesson belongs to the **HTTP client** group of Spring Boot web-runtime. The hands-on section uses synchronous Spring MVC and `RestClient`; the end of the lesson compares this with reactive WebFlux.

## 2. One Business Flow, Two HTTP Exchanges

~~~text
       Exchange A: inbound            Exchange B: outbound
Browser                         Spring Boot Gateway                Catalog Service
  |                                    |                                   |
  | GET /api/items/42                  |                                   |
  | Host: localhost:8080               |                                   |
  |----------------------------------->|                                   |
  |                                    | GET /catalog/items/42             |
  |                                    | Host: localhost:8081              |
  |                                    |---------------------------------->|
  |                                    |                                   |
  |                                    | 200 JSON: item 42                 |
  |                                    |<----------------------------------|
  |                                    |                                   |
  | 200 JSON: item 42                  |                                   |
  |<-----------------------------------|                                   |
~~~

**Exchange A:** Spring Boot has a TCP/HTTP listener that receives the method, path, headers, query, and body and decides how to handle them. The result is response A sent back to the browser.

**Exchange B:** Inside the code handling A, the application decides to call another URL. The HTTP client library opens or reuses a connection to the downstream service, sends request B, and receives response B. This is an independent exchange in terms of network, HTTP method, headers, timeouts, and authentication.

The two hops can differ:

| Property | Exchange A (browser → gateway) | Exchange B (gateway → catalog) |
| --- | --- | --- |
| HTTP client | Browser | Spring Boot gateway |
| HTTP server | Spring Boot gateway | Catalog service |
| URL | `/api/items/42` | `/catalog/items/42` |
| Example host / port | `localhost:8080` | `localhost:8081` |
| Transport | May be HTTPS/HTTP2 | May independently be HTTP/1.1, HTTPS, or HTTP/2 |
| Credential | User cookie / token | Service credential or controlled delegation |
| Timeout | Decided by browser/proxy | Configured by gateway HTTP client |
| Error status | Chosen by gateway per public API | Returned by downstream or network exception |
| Log / metric | Server-side request | Client-side dependency call |

Key point: the gateway does not disappear when it calls a downstream service. It remains the **server of A** while simultaneously being the **client of B**. Do not assume "HTTP client" only means a JavaScript frontend or a mobile app.

## 3. View from the Spring Boot Web Runtime

~~~text
Inbound HTTP request
      |
      v
Listening socket :8080
      |
      v
Embedded Tomcat / Spring MVC DispatcherServlet
      |
      v
@RestController / @GetMapping / @PostMapping
      |
      v
Service, business rules, data mapping
      |
      +--> local computation
      |
      '--> RestClient / WebClient / HttpClient
                    |
                    v
         DNS + TCP/TLS + outbound HTTP request
                    |
                    v
          Remote HTTP server (:8081)
                    |
                    v
           Remote HTTP response
                    |
                    v
          Decode / validate / map error
                    |
                    v
         Controller returns ResponseEntity
                    |
                    v
          HTTP response from :8080
~~~

On the **server** side, annotations such as `@RestController`, `@GetMapping`, `@RequestParam`, `@PathVariable`, and `@RequestBody` declare how to handle **inbound** requests. `@RestController` combines controller functionality with response-body serialization; returned objects are typically converted into JSON by a message converter such as Jackson.

On the **client** side, `RestClient.get()`, `WebClient.post()`, or Java `HttpClient.send()` are used to **initiate requests to another server**. Your code chooses the destination, method, body, authentication, timeouts, and how to handle the response.

Server-side API example:

~~~java
@GetMapping("/api/items/{id}")
public ItemDto getItem(@PathVariable String id) {
    // Handling an inbound request.
    return service.loadItem(id);
}
~~~

Client-side API example, **just the snippet inside a method that already has RestClient**:

~~~java
ItemDto item = restClient.get()
        .uri("/catalog/items/{id}", id)
        .retrieve()
        .body(ItemDto.class);
~~~

`RestClient` has "Client" in its name because it sends requests. `@RestController` contains "Rest", but the annotation itself does not make outbound HTTP calls elsewhere.

## 4. server.port, baseUrl, and Ephemeral Ports Are Not the Same

Example configuration:

~~~properties
# Local port where the gateway LISTENS for requests.
server.port=8080

# Remote URL that the gateway's client CONNECTS to.
app.catalog.base-url=http://127.0.0.1:8081
~~~

- `server.port=8080`: embedded Tomcat receives inbound HTTP on 8080.
- `app.catalog.base-url`: an **application custom property**; Spring Boot does not provide this property out of the box. Code reads it to know where the downstream server is.
- Port `8081`: the remote HTTP server destination. It is not determined by `server.port`.
- When the gateway calls the downstream service, the OS can choose an **ephemeral source port** other than 8080 to open the TCP connection to `8081`. The source port number depends on the operating system and connection state.
- On Kubernetes, the `baseUrl` value is typically an internal service DNS + port; the browser might call a completely different public domain.

Changing `server.port` does not automatically update the outbound URL. Changing `app.catalog.base-url` does not open a new listener on the gateway. This is one of the most common basic confusions when first learning web runtime.

## 5. Why Must a Server Act as an HTTP Client?

Real-world patterns:

- **Backend for Frontend (BFF):** the frontend calls a single API; the backend calls catalog, pricing, and stock, then builds a UI-tailored DTO.
- **Service-to-service:** order-service calls inventory-service or payment-service.
- **Integration:** calling logistics, email providers, CRMs, or object storage APIs.
- **API aggregation:** fetching data from multiple sources, filtering, and combining it.
- **Authentication:** the application calls an identity provider to exchange tokens or fetch verification keys according to the appropriate flow.
- **Background job:** a scheduled task sends HTTP requests **without an inbound web request**.
- **Webhook workflow:** receiving a webhook as a server and then calling a downstream API as a client.

An application does not necessarily make HTTP calls to access a database; JDBC/R2DBC are different protocols. An app using a message broker might also not make outbound HTTP calls. Only when **it issues an HTTP request** does the HTTP client role appear on that hop.

## 6. Choosing the Right Java/Spring HTTP Client

| API | Style | When to use |
| --- | --- | --- |
| `RestClient` | Synchronous, fluent API | Imperative Spring MVC/services on Spring Framework 6.1+ |
| `RestTemplate` | Synchronous, template methods | Legacy projects already using it; maintenance/gradual migration |
| `WebClient` | Reactive, `Mono/Flux` publishers | Spring WebFlux or async/non-blocking pipelines |
| `java.net.http.HttpClient` | JDK 17, `send`/`sendAsync` | Core Java when avoiding Spring APIs |
| HTTP service interfaces | Java interface + annotations, backed by RestClient/WebClient | When modeling a clear typed client contract |

In Spring Boot 3.3, `RestClient.Builder` is auto-configured by Boot for non-reactive web applications when the classpath matches. Injecting the builder preserves converters and Boot-configured customizers; you can configure the base URL and request factory per dependency.

**RestClient is a synchronous API**: calling `retrieve().body(...)` makes the thread wait for a response or exception. **WebClient is a reactive API**: it returns `Mono`/`Flux`, and network I/O occurs when the pipeline is subscribed to. Do not call `block()` directly inside a WebFlux event-loop handler to turn a reactive API into a blocking one.

`RestTemplate` has not disappeared from Boot 3.3 projects; it is an older client but still commonly seen. Java 17's `HttpClient` is also not an HTTP server even though it uses "Client" in its class name.

## 7. Complete Lab: Spring Boot as Both Server and HTTP Client

We will run **two real processes** on the local machine:

- **Downstream catalog**: an HTTP server built with JDK 17, listening on `127.0.0.1:8081` and returning JSON.
- **Spring Boot gateway**: an MVC web server at `127.0.0.1:8080`, receiving inbound requests and using `RestClient` to call catalog on port 8081.

No Docker, database, or second Spring Boot project is required. The downstream HTTP server uses the JDK `jdk.httpserver` module to focus on observing the two HTTP roles.

### 7.1. Project Structure

~~~text
http-client-roles/
├── downstream/
│   └── CatalogStubServer.java
└── gateway/
    ├── pom.xml
    └── src/main/
        ├── java/com/example/gateway/
        │   ├── GatewayApplication.java
        │   ├── CatalogClient.java
        │   ├── GatewayController.java
        │   ├── ItemDto.java
        │   └── ErrorDto.java
        └── resources/
            └── application.properties
~~~

`downstream` and `gateway` are two separate processes. Only the `gateway` directory contains a Maven `pom.xml` and runs Spring Boot via Maven.

### 7.2. Downstream Server: CatalogStubServer.java

**File `downstream/CatalogStubServer.java`:**

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.Executors;

public class CatalogStubServer {

    public static void main(String[] args) throws IOException {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 8081), 0);

        server.createContext(
                "/catalog/items/", CatalogStubServer::handle);
        server.setExecutor(Executors.newFixedThreadPool(4));
        server.start();

        System.out.println(
                "CatalogStub listening on http://127.0.0.1:8081");
    }

    private static void handle(HttpExchange exchange) throws IOException {
        String path = exchange.getRequestURI().getPath();
        String id = path.substring("/catalog/items/".length());

        System.out.printf(
                "DOWNSTREAM %s %s%n",
                exchange.getRequestMethod(), path);

        int status;
        String json;

        if (!"GET".equals(exchange.getRequestMethod())) {
            status = 405;
            json = "{\"error\":\"METHOD_NOT_ALLOWED\"}";
            exchange.getResponseHeaders().set("Allow", "GET");
        } else if ("42".equals(id)) {
            status = 200;
            json = "{\"id\":\"42\",\"name\":\"Book\",\"price\":120}";
        } else if ("slow".equals(id)) {
            try {
                Thread.sleep(2500);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
            status = 200;
            json = "{\"id\":\"slow\",\"name\":\"Slow Book\",\"price\":130}";
        } else {
            status = 404;
            json = "{\"error\":\"ITEM_NOT_FOUND\"}";
        }

        byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "application/json; charset=UTF-8");
        exchange.sendResponseHeaders(status, bytes.length);

        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }
}
~~~

Points to observe:

1. `HttpServer.create(...)` and `start()` open an **HTTP listener on port 8081**; it is genuinely the downstream server.
2. `createContext` defines the server-side route `/catalog/items/`.
3. `id=42` returns JSON 200, `id=slow` intentionally delays 2.5 seconds, and other IDs return JSON 404.
4. The `DOWNSTREAM GET ...` log only appears when a request **reaches the downstream server**, whether the caller is a browser directly or the gateway.
5. The stub's thread pool of 4 handles inbound requests on port 8081; it is not the gateway's outbound client pool.
6. The stub server is for lab use only; it lacks production features such as TLS, authentication, or graceful shutdown.

Run in terminal A:

~~~bash
cd http-client-roles/downstream
javac --add-modules jdk.httpserver CatalogStubServer.java
java --add-modules jdk.httpserver CatalogStubServer
~~~

Expected stdout on server startup:

~~~text
CatalogStub listening on http://127.0.0.1:8081
~~~

Call the downstream server directly with curl from another terminal:

~~~bash
curl -i http://127.0.0.1:8081/catalog/items/42
curl -i http://127.0.0.1:8081/catalog/items/unknown
~~~

The first request normally returns 200 JSON `{"id":"42","name":"Book","price":120}`; the second returns 404. At this point, the Spring Boot gateway does not need to be running yet.

### 7.3. Gateway pom.xml

**File `gateway/pom.xml`:**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>http-client-roles-gateway</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter-web` provides MVC, embedded Tomcat, `spring-web` containing `RestClient`, and Jackson to serialize/deserialize JSON. `spring-boot-starter-webflux` is not needed for this synchronous lab.

### 7.4. application.properties

**File `gateway/src/main/resources/application.properties`:**

~~~properties
# INBOUND listener on Spring Boot.
server.address=127.0.0.1
server.port=8080

# OUTBOUND destination, a custom project property.
app.catalog.base-url=http://127.0.0.1:8081
~~~

Both addresses use loopback to avoid exposing the demo server to the network. In production/Kubernetes, appropriate network interfaces, DNS, Services, and egress policies are required. Do not copy `127.0.0.1` as-is into an environment where the downstream lives in another container/pod: `localhost` inside each container points to that container itself.

### 7.5. Spring Boot Main Class

**File `gateway/src/main/java/com/example/gateway/GatewayApplication.java`:**

~~~java
package com.example.gateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GatewayApplication {
    public static void main(String[] args) {
        SpringApplication.run(GatewayApplication.class, args);
    }
}
~~~

This class starts the Spring web application; opening the inbound listener is handled by Spring Boot and the embedded server, not because `main` calls RestClient.

### 7.6. DTOs: Java 17 Records

**File `gateway/src/main/java/com/example/gateway/ItemDto.java`:**

~~~java
package com.example.gateway;

public record ItemDto(String id, String name, int price) {
}
~~~

**File `gateway/src/main/java/com/example/gateway/ErrorDto.java`:**

~~~java
package com.example.gateway;

public record ErrorDto(String code, String message) {
}
~~~

Jackson can use records to convert JSON to Java and vice versa. The gateway's DTO can match or differ from the downstream schema; in the lab they match to keep the focus on HTTP roles.

### 7.7. CatalogClient — The Actual HTTP Client

**File `gateway/src/main/java/com/example/gateway/CatalogClient.java`:**

~~~java
package com.example.gateway;

import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class CatalogClient {

    private final RestClient restClient;

    public CatalogClient(
            RestClient.Builder builder,
            @Value("${app.catalog.base-url}") String baseUrl) {

        SimpleClientHttpRequestFactory factory =
                new SimpleClientHttpRequestFactory();

        factory.setConnectTimeout(Duration.ofMillis(800));
        factory.setReadTimeout(Duration.ofMillis(1200));

        this.restClient = builder
                .baseUrl(baseUrl)
                .requestFactory(factory)
                .build();
    }

    public ItemDto fetch(String id) {
        return restClient.get()
                .uri("/catalog/items/{id}", id)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .body(ItemDto.class);
    }
}
~~~

Detailed explanation:

- `@Service` marks a business component that can be injected by a controller; it does not open a new HTTP listener.
- Spring Boot 3.3 provides `RestClient.Builder` for MVC applications when the right dependency is present. Using the injected builder preserves Boot's shared configurations; `baseUrl` identifies the remote service.
- `SimpleClientHttpRequestFactory` is backed by JDK `HttpURLConnection`, suitable for a simple synchronous example. It is **not a built-in Apache HTTP connection pool**. When production requires connection pooling, choose an appropriate request factory/client implementation and measure the pool.
- `connectTimeout` of 800 ms bounds waiting for connection establishment; `readTimeout` of 1200 ms bounds reading data from the socket. Read timeout is **not necessarily** a total deadline from invocation start to response completion.
- `.get()` and `.uri("/catalog/items/{id}", id)` build an independent outbound GET request; URI templates handle path variables instead of concatenating URL strings from arbitrary input.
- `.accept(MediaType.APPLICATION_JSON)` sends the `Accept: application/json` header **to the downstream service**, without altering the browser's inbound request.
- `retrieve().body(ItemDto.class)` executes the exchange and parses JSON into a Java record; this line is **blocking/synchronous** in RestClient.
- By default, 4xx/5xx responses throw a `RestClientResponseException` or subclass; connect/read failures can result in `ResourceAccessException`.

In this lab, the destination URL comes from trusted config, not directly from a browser `url` parameter. This is also the simplest way to mitigate SSRF risk.

### 7.8. GatewayController — Receiving Inbound Requests and Choosing the Public Response

**File `gateway/src/main/java/com/example/gateway/GatewayController.java`:**

~~~java
package com.example.gateway;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

@RestController
@RequestMapping("/api/items")
public class GatewayController {

    private final CatalogClient catalogClient;

    public GatewayController(CatalogClient catalogClient) {
        this.catalogClient = catalogClient;
    }

    @GetMapping("/{id}")
    public ResponseEntity<?> one(@PathVariable String id) {
        if (!id.matches("[A-Za-z0-9-]{1,30}")) {
            return ResponseEntity.badRequest()
                    .body(new ErrorDto("INVALID_ID", "ID is invalid"));
        }

        try {
            ItemDto item = catalogClient.fetch(id);

            if (item == null) {
                return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                        .body(new ErrorDto(
                                "EMPTY_UPSTREAM_BODY",
                                "Catalog returned an empty body"));
            }

            return ResponseEntity.ok(item);

        } catch (HttpClientErrorException.NotFound ex) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                    .body(new ErrorDto(
                            "ITEM_NOT_FOUND", "No matching item"));

        } catch (RestClientResponseException ex) {
            return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                    .body(new ErrorDto(
                            "CATALOG_HTTP_ERROR",
                            "Catalog service returned an error"));

        } catch (ResourceAccessException ex) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body(new ErrorDto(
                            "CATALOG_UNAVAILABLE",
                            "Catalog service cannot be reached in time"));

        } catch (RestClientException ex) {
            return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                    .body(new ErrorDto(
                            "CATALOG_CLIENT_ERROR",
                            "Cannot process catalog response"));
        }
    }
}
~~~

The controller demonstrates a clear API boundary:

1. `@GetMapping("/{id}")` **receives the inbound request** on the gateway. The public route is `GET /api/items/{id}`.
2. The ID check performs validation before creating an outbound request.
3. `catalogClient.fetch(id)` makes the gateway act as an **HTTP client** of catalog-service.
4. Downstream returns 200 + valid JSON schema → gateway returns 200 + `ItemDto` serialized by the gateway itself.
5. Downstream returns 404 → `RestClient` throws `HttpClientErrorException.NotFound` → gateway decides to return 404 with an `ErrorDto` different from the downstream body.
6. Downstream returns another HTTP error → gateway chooses 502 in the lab; production needs to distinguish business errors, rate limits, auth failures, and domain policies.
7. Network/connect/read failure → `ResourceAccessException` → gateway chooses 503 **as a demo policy**. Do not treat this as a status Spring automatically uses for all timeouts; many gateways choose 504 if timeouts are classified explicitly.
8. Never return raw stack traces, internal hostnames, raw upstream bodies, or service credentials to the browser.

**Catch order:** the 404 subclass must come before the general `RestClientResponseException`; `ResourceAccessException` must come before the general `RestClientException`.

## 8. Running and Observing Both Exchanges

### 8.1. Terminal A — Downstream

~~~bash
cd http-client-roles/downstream
javac --add-modules jdk.httpserver CatalogStubServer.java
java --add-modules jdk.httpserver CatalogStubServer
~~~

Make sure this process stays running on `127.0.0.1:8081`.

### 8.2. Terminal B — Spring Boot Gateway

~~~bash
cd http-client-roles/gateway
mvn spring-boot:run
~~~

Tomcat will listen on `127.0.0.1:8080`. Use JDK 17+ and Maven 3.9+; avoid port conflicts. In PowerShell, similar commands apply, while browser/curl access the URL the same way.

### 8.3. Terminal C — Calling the Gateway

~~~bash
curl -i http://127.0.0.1:8080/api/items/42
~~~

Expected response structure:

~~~http
HTTP/1.1 200
Content-Type: application/json

{"id":"42","name":"Book","price":120}
~~~

This is representative output, not byte-for-byte; the `Date` header, header order, content length, and formatting may differ. In **terminal A**, the log adds:

~~~text
DOWNSTREAM GET /catalog/items/42
~~~

This proves the gateway **initiated a new HTTP request** to catalog. From the browser/curl you only called `:8080`, yet the backend service actually received HTTP on `:8081`.

### 8.4. Testing 404

~~~bash
curl -i http://127.0.0.1:8080/api/items/unknown
~~~

Downstream returns:

~~~json
{"error":"ITEM_NOT_FOUND"}
~~~

The gateway returns a **different** body according to its own contract:

~~~json
{"code":"ITEM_NOT_FOUND","message":"No matching item"}
~~~

Both responses having status 404 is the **result of mapping policy inside the gateway**, not because response B automatically becomes response A. The gateway can choose a different status if business semantics require it.

### 8.5. Testing Slow Downstream

~~~bash
curl -i http://127.0.0.1:8080/api/items/slow
~~~

CatalogStub sleeps for 2.5 seconds, while RestClient has a `readTimeout` of 1.2 seconds. Under lab conditions, the gateway typically encounters `ResourceAccessException` and returns 503 with:

~~~json
{"code":"CATALOG_UNAVAILABLE","message":"Catalog service cannot be reached in time"}
~~~

Exact timing and exception details can vary with OS, scheduling, and connection conditions. The downstream may log a write error after the gateway has stopped waiting. **A client-side timeout does not mean the remote server canceled all work.**

### 8.6. Testing Dependency Down

Stop terminal A with `Ctrl+C` while keeping the gateway running, then call again:

~~~bash
curl -i http://127.0.0.1:8080/api/items/42
~~~

The gateway still **receives inbound requests** but cannot connect downstream; in the lab it usually returns 503. This shows a web server application that is alive while an HTTP dependency is unavailable. Restarting catalog allows requests to succeed again without restarting the gateway.

### 8.7. Packaging the Gateway

In the `gateway` directory, after stopping the Maven instance if needed:

~~~bash
mvn clean package
java -jar target/http-client-roles-gateway-0.0.1-SNAPSHOT.jar
~~~

The executable JAR contains only the gateway. The downstream JDK HttpServer still needs to run separately on port 8081.

## 9. Downstream Response Is Not Automatically the Gateway Response

When calling a remote API, there are at least three outcomes:

1. **Valid HTTP response**: downstream returns status, headers, and body; the gateway can transform DTOs or choose a response.
2. **HTTP error response**: downstream returns 4xx/5xx; `RestClient.retrieve()` normally throws an exception, which the gateway must catch/transform.
3. **No HTTP response**: DNS failure, TLS handshake, TCP refused, read timeout, reset; the gateway must handle exceptions at the client/network layer.

For example, upstream returns 401 because the **gateway's service token** expired. That does not automatically mean the user is not logged into the gateway. If the gateway forwards 401 verbatim, the frontend might wrongly log the user out. Distinguish **downstream authorization failure** from **inbound caller authorization**.

| Downstream case | Gateway can return | Reason |
| --- | --- | --- |
| 200 valid JSON | 200 public DTO | Success per contract |
| 201 Created | 201 when the public API actually creates a resource | May rewrite `Location` to public URL |
| 204 No Content | 204/empty | Do not force-parse an empty body into a required object |
| 400 | 400 or 502 depending on error source | Could be invalid caller input or gateway-built bad request |
| 401/403 | 502/503 or appropriate domain code | Must distinguish service credential vs user auth |
| 404 | 404 if domain item truly does not exist | Lab intentionally maps to public 404 |
| 409 | 409 when a real business conflict occurs | Not always treated as a network failure |
| 429 | Backoff/rate limit, 429 or 503 per contract | Avoid creating a retry storm |
| 5xx | 502/503 per policy | Service failure observability needed |
| Connect/read timeout | 503/504 depending on classification | No complete upstream response |
| Invalid JSON/schema | 502/integration error | Validate and version contracts |

Never copy a raw response body containing stack traces or internal database details out to the browser. A gateway is responsible for keeping a **stable public contract**, even when downstream services change.

## 10. HTTP Body: Reading Inbound Differs from Sending Outbound

Server controller:

~~~java
@PostMapping("/api/orders")
public ResponseEntity<?> create(@RequestBody OrderRequest request) {
    // @RequestBody reads inbound JSON into a Java object.
    return ...;
}
~~~

HTTP client:

~~~java
OrderResult result = restClient.post()
        .uri("/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .body(new OrderRequest("42", 2))
        .retrieve()
        .body(OrderResult.class);
~~~

These are **two illustrative snippets that do not run standalone**: `OrderRequest`, `OrderResult`, `restClient`, imports, and enclosing class/methods must be defined. Key differences:

- `@RequestBody` on a controller: reads the **inbound request body**.
- `RestClient.body(...)`: creates the **outbound request body**.
- `RestClient.retrieve().body(Class)`: reads the **outbound response body**.
- `ResponseEntity` in a controller: creates the **inbound response** sent back to the caller.

The `Content-Type` header describes the media type of the message body being sent; `Accept` states what content type the client wants to receive. The two exchanges have separate headers and do not need to match.

## 11. Headers, Cookies, and Tokens Are Not Forwarded Automatically

A browser might send:

~~~http
GET /api/items/42 HTTP/1.1
Host: api.example.com
Cookie: SESSION=...
Authorization: Bearer <user-token>
X-Request-Id: req-123
~~~

The gateway calls downstream:

~~~http
GET /catalog/items/42 HTTP/1.1
Host: catalog.internal:8081
Authorization: Bearer <service-token>
X-Request-Id: req-123
Accept: application/json
~~~

The headers above are architectural examples, not lab logs. Forwarding a correlation ID or token must be decided explicitly in code/config.

**Do not copy unconditionally:**

- `Host`: must be the actual upstream host.
- `Cookie`: browser sessions may not belong to the downstream service; forwarding leaks credentials.
- `Authorization`: user tokens have specific audience/scope; if delegation is needed, follow a designed auth flow.
- `Content-Length`: must match the actual body bytes of the outbound message.
- `Connection` and hop-by-hop headers: must not be blindly forwarded.
- `Set-Cookie`: downstream cookies generally should not be emitted straight to public browsers.
- `Location`: upstream redirects may point to internal hostnames.
- `X-Forwarded-*`: must follow a trusted proxy chain, never trusting spoofed client values.
- `Content-Encoding`: if the gateway decoded/transformed the body, do not keep the header from the old representation.

For distributed tracing, propagating standard headers such as `traceparent` requires proper instrumentation and trust/PII policies; **you do not need to copy every header** to achieve correlation.

## 12. CORS Does Not Prevent RestClient from Calling Downstream

CORS is a **browser** mechanism used to control whether JavaScript at origin A can read a response from origin B. A server-side HTTP client like `RestClient` does not run inside a browser and therefore **is not subject to browser CORS checks**.

Example:

~~~text
Browser JS from http://localhost:5173
  -> http://localhost:8080/api/items/42
  -> may need CORS config on gateway

Spring Boot RestClient at localhost:8080
  -> http://localhost:8081/catalog/items/42
  -> does not need catalog to emit Access-Control-Allow-Origin
     just for server-side Java to read the response
~~~

Do not configure `@CrossOrigin("*")` on every service just because the gateway cannot call it. When an error occurs in RestClient, check DNS, network, URL, TLS, auth, status, timeout, or response format. CORS **does not replace authentication or firewalls**: curl or a backend client can call an API that browser JavaScript is blocked from reading by policy.

## 13. Inbound Thread Pool and Outbound Connection Pool Are Different

With synchronous Spring MVC/RestClient:

~~~text
Tomcat request worker
  -> GatewayController
  -> CatalogClient.fetch
  -> wait for outbound connect / response / timeout
  -> map ItemDto or error
  -> send inbound response
~~~

If 20 requests wait concurrently on a slow catalog service, many Tomcat workers can be held while waiting. However, the Tomcat worker count and outbound TCP connection count **are not the same setting**.

**Hypothetical** example with a pooled HTTP client:

~~~text
Tomcat request threads max = 20
Outbound client max connections to catalog = 5

20 inbound calls need catalog
  -> 5 leased outbound connections
  -> 15 pending/acquire timeout if all connections are busy
~~~

This model explains contention; it is **not the lab's setup**. The lab uses `SimpleClientHttpRequestFactory`/URLConnection, which does not have an Apache HttpClient pool with max=5. To use a pool, choose an HTTP client implementation that supports pooling and configure it properly.

Consider:

- Inbound Tomcat thread pool, accept queue, and connection timeout.
- Outbound connection pooling, connection acquisition time, DNS/TLS, and socket timeouts.
- Downstream server worker threads/event loops and database pool.
- Fan-out: one inbound request can trigger multiple outbound calls.
- Retries: if every failure retries multiple times, downstream load can surge.
- Memory/CPU, connection churn, and ephemeral port exhaustion.

Do not increase `server.tomcat.threads.max` to "fix" an outbound read timeout, and do not increase client pools unboundedly when the downstream lacks capacity.

### 13.1. Little’s Law for Viewing Concurrency

\[
L = \lambda W
\]

If the outbound arrival rate is steady around 50 calls/second and average call duration is 0.2 seconds, the average number of in-flight calls is roughly 10. This is a mathematical example, **not** the exact thread count to configure. Queue time, retries, and p99 can make the active/pending count higher; make sure to apply consistent measurement boundaries.

## 14. Timeouts Have Multiple Layers

~~~text
Browser client deadline
       |
Reverse proxy timeout
       |
Spring Boot inbound handler
       |
Outbound HTTP client connect/read/response timeout
       |
Downstream server queue + business + DB timeout
~~~

**A successful connection** is not yet **a successful response**:

- **Connect timeout**: bounds a TCP connection establishment phase according to client semantics.
- **Read/response timeout**: bounds waiting for data/response per client implementation; many implementations use a read inactivity timeout rather than a total deadline.
- **Overall deadline**: the time budget for the whole business operation, accounting for queueing, retries, parsing/transformation, and replying.
- **Server idle/connection timeout**: resource management for inbound sockets, not an outbound dependency timeout.
- **Proxy timeout**: reverse proxies have their own budgets and may close the connection before the gateway finishes.

In the lab, `readTimeout=1200ms` is intentionally lower than the stub's `Thread.sleep(2500)` to demonstrate failure. In production, set timeouts based on SLOs and the caller's remaining budget; avoid retries that exceed the deadline. A timeout does not guarantee that work already received by the remote server is canceled.

## 15. WebFlux WebClient: Still Two HTTP Roles

If the server is written with Spring WebFlux, request-handling endpoints typically return `Mono/Flux`, and the reactive client is typically `WebClient`. The two roles remain independent.

Bean configuration **for a separate WebFlux project**:

~~~java
package com.example.reactive;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class OutboundConfig {
    @Bean
    WebClient catalogWebClient(
            WebClient.Builder builder,
            @Value("${app.catalog.base-url}") String url) {
        return builder.baseUrl(url).build();
    }
}
~~~

Reactive controller:

~~~java
package com.example.reactive;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/items")
public class ReactiveGatewayController {
    private final WebClient catalogWebClient;

    public ReactiveGatewayController(WebClient catalogWebClient) {
        this.catalogWebClient = catalogWebClient;
    }

    @GetMapping("/{id}")
    public Mono<ItemDto> one(@PathVariable String id) {
        return catalogWebClient.get()
                .uri("/catalog/items/{id}", id)
                .retrieve()
                .bodyToMono(ItemDto.class);
    }
}
~~~

These two snippets are **separate configuration/handler examples**, not a standalone project: they require `spring-boot-starter-webflux`, the `ItemDto` record in the same package, a main app class, and the base URL property. Do not place a reactive controller with the same route into the MVC lab project.

`Mono<ItemDto>` is a publisher; the WebFlux runtime subscribes to it to perform outbound HTTP and then write the inbound response. `retrieve()` emits an error signal for error status codes; real projects need `onStatus`/`onErrorResume` and appropriate timeouts. **Never call `.block()` inside a WebFlux event-loop handler**, as it blocks the thread, negates reactive benefits, or is rejected by Reactor.

You can use `WebClient` inside an MVC application for outbound calls; simply having `WebClient` on the classpath does not turn MVC into WebFlux. When both `starter-web` and `starter-webflux` are present, Spring Boot 3.3 normally prefers MVC when auto-detecting the web application type.

### 15.1. Java 17 HttpClient

JDK 17 includes `java.net.http.HttpClient` with synchronous `send` and asynchronous `sendAsync`:

~~~java
// Snippet inside a method throwing Exception; requires imports
// java.net.URI and java.net.http.HttpClient/HttpRequest/HttpResponse.
HttpClient client = HttpClient.newHttpClient();
HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("http://127.0.0.1:8081/catalog/items/42"))
        .GET()
        .build();
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString());
System.out.println(response.statusCode());
System.out.println(response.body());
~~~

This is a **non-standalone snippet**, not a complete class. It demonstrates that an HTTP client does not have to be a Spring-specific API; a Java process can still send requests to another service.

## 16. Retries, Idempotency, and Circuit Breakers

When a downstream fails or times out, retries may be considered, but **never retry blindly**:

- Read-only GET requests may be eligible for bounded retries on transient failures, though they still consume capacity and can have side effects if poorly designed.
- A POST that creates an order or payment may already have been executed downstream before the gateway timed out. Retrying can create **duplicate orders or transactions**.
- You need a retry budget, exponential backoff/jitter, overall deadline, max attempts, and `Retry-After` awareness where appropriate.
- **Idempotency keys** or downstream deduplication mechanisms are vital for write operations.
- A **circuit breaker** can temporarily short-circuit calls to a failing dependency; a **bulkhead** limits concurrent calls to protect the gateway.

The lab does not include Spring Cloud CircuitBreaker/Resilience4j, so there are no built-in retries or circuit breakers. Apply them only when business semantics allow and metrics are in place.

## 17. Authentication Between Caller and Downstream

A user logged into the gateway does not necessarily have credentials valid for the catalog or payment service. Common patterns:

1. **Service identity:** the gateway uses a service account/OAuth client credentials or mTLS to call the downstream service.
2. **Token delegation:** sending a token representing the user issued with the proper audience/scope when the service needs user-level access control.
3. **Gateway authorization:** the gateway authenticates the user and calls internal services with scoped permissions; downstream should still enforce network/service identity controls.
4. **Unauthenticated**: acceptable in a loopback lab, never the production default.

**Do not forward a user bearer token directly to every downstream service.** A token whose audience is the gateway may be invalid at catalog, and spreading it increases exposure risk. Client credentials must be rotated, kept out of logs, narrowly scoped, and sent over proper HTTPS/mTLS.

TLS between the browser and gateway does not automatically secure the gateway–downstream hop; they are two separate connections. If backend traffic requires encryption, use HTTPS to the downstream and verify certificates/hostnames. Never use trust-all SSL in production.

## 18. Preventing SSRF When Designing Outbound URLs

Anti-pattern:

~~~java
@GetMapping("/fetch")
public String fetch(@RequestParam String url) {
    // UNSAFE: the caller chooses the host the server connects to.
    return RestClient.create()
            .get().uri(url).retrieve().body(String.class);
}
~~~

This is **intentionally insecure sample code** and must not be shipped to production. An attacker can force the gateway to call cloud metadata endpoints, private IPs, localhost admin APIs, or addresses beyond the browser's network reach — **Server-Side Request Forgery (SSRF)**.

Mitigations:

- Use a fixed `baseUrl` from server config; only accept validated resource IDs/path segments with URI templates.
- If calling arbitrary URLs is truly required, enforce a strict scheme/host/port allowlist, defend against DNS rebinding, redirects, and private/link-local IP ranges per your threat model.
- Network egress policies blocking unnecessary destinations.
- Limit request/response sizes, redirects, timeouts, protocols, and content types.
- Never let users control outbound `Authorization`, `Host`, or proxy settings.

In the lab, `app.catalog.base-url` is configured server-side and `id` only allows letters, digits, and hyphens — a simple example of enforcing this boundary.

## 19. Tracing and Metrics: Observing Both Server and Client

A distributed trace for a request crossing two services may look like:

~~~text
Trace ID: trace-abc
  SERVER span: GET /api/items/{id}                (gateway)
    CLIENT span: GET /catalog/items/{id}          (gateway)
      SERVER span: GET /catalog/items/{id}        (catalog)
~~~

In practice, this requires configuring Micrometer Observation/Tracing, an exporter, trace context propagation (e.g., W3C `traceparent`), and sampling; the current lab only logs downstream requests and **does not automatically produce distributed traces**.

Measure separately:

| Category | Key metrics/logs |
| --- | --- |
| Inbound server | Requests/s, 2xx/4xx/5xx statuses, p95/p99, active threads/connections |
| Outbound client | Dependency/URI template, status, timeout, latency, retry count |
| Connection pool | Active, idle, pending acquisitions, failures |
| Downstream | Queue time, DB query latency, 429/5xx, saturation |
| Tracing | Trace ID, client/server spans, context propagation |
| Reliability | Circuit breaker state, fallback rate, timeouts, errors |

Never log raw `Authorization` headers, session cookies, private keys, PII, or full sensitive request/response bodies. Avoid high-cardinality full URLs with user IDs as metric labels when route templates can be used.

## 20. Common Mistakes

| Symptom | Confusion/Cause | Fix |
| --- | --- | --- |
| Spring Boot runs on 8080 but cannot reach 8081 | Downstream is not running or URL is wrong | Call `curl :8081` directly, check process/network |
| Changed `server.port` but remote client still calls old URL | Listener differs from destination | Update `app.catalog.base-url` |
| Controller returns 200 but catalog has no log | Code did not actually call the client or hit a cache | Check service path and downstream logs |
| Gateway returns 503 when catalog stops | Outbound connect refused/timeout | Log client exception, distinguish from server listener |
| Downstream returns 404 but public JSON differs | Gateway maps/transforms response | Intended behavior per contract |
| JSON decode fails on upstream 200 | Incorrect schema/media type | Check DTO/version, map integration errors |
| Browser reports CORS error while RestClient still works | CORS applies to browsers, not Java HTTP clients | Check CORS on gateway inbound |
| Spring Security login succeeds on gateway but downstream returns 401 | Missing/wrong service credentials | Use proper service identity/delegation |
| High timeout even though server threads are idle | Outbound pool/network/remote is slow | Measure client latency, pool, DNS/TLS, upstream |
| Tomcat workers exhausted | Too many blocking calls | Limit concurrency, timeouts, pool, bulkhead |
| WebFlux stalls/hangs | Blocking `RestClient`/`block()` on event loop | Keep reactive WebClient or offload carefully |
| API returns internal host in Location | Forwarding raw upstream headers | Rewrite public URL, filter hop-by-hop headers |
| Retries create duplicate orders | Missing idempotency key | Add deduplication and retry policy |
| TLS handshake fails | Wrong certificate/hostname/truststore | Provide proper CA/SAN, never disable verification |
| Client URL comes from query parameter | SSRF | Fixed destination and egress policy |
| 200 from health endpoint while downstream calls return 503 | Gateway is up, dependency is down | Measure readiness/dependency health independently |

### 7-Step Debugging Workflow

1. **Inbound:** Are URL/method correct, which listener port, which controller route?
2. **Outbound:** Which method calls RestClient/WebClient, what are the actual base URL and path?
3. **Network:** Do DNS, TCP, TLS, and firewall/proxy/egress allow the connection?
4. **Downstream:** What are the actual status, headers, content type, and JSON schema?
5. **Mapping:** Which exception does the gateway catch, and what status/body does it return?
6. **Timeout/concurrency:** Server threads, client pool, queueing, read/response timeouts, retry budgets?
7. **Tracing:** Are correlation/trace context and metrics present on both hops, or only server access logs?

Do not see a gateway 500 and immediately assume embedded Tomcat is broken; the failure may lie in the outbound HTTP call, JSON decoding, or the downstream service.

## 21. Exercises and Answers

**Q1.** The browser calls `:8080/api/items/42` and the gateway calls `:8081/catalog/items/42`. Who is client and who is server on each hop?

**Q2.** Why does having `@RestController` not mean the application is making HTTP client calls?

**Q3.** How does `@RequestBody` in a controller differ from `RestClient.post().body(...)`?

**Q4.** When catalog returns 401 because a service token expired, should the gateway forward 401 to the browser by default?

**Q5.** Why can CORS block JavaScript calling the gateway while not blocking RestClient calling catalog?

**Q6.** If catalog processes a POST successfully but the response is lost, what is the risk of retrying the POST?

**Q7.** A WebFlux application uses `RestClient.retrieve().body()` inside an event-loop handler. What is the problem?

**Q8.** There are 100 inbound requests/s and each request calls three downstream services. Why can outbound RPS exceed inbound RPS?

**Q9.** Does changing `server.port` from 8080 to 9090 change RestClient's target address `127.0.0.1:8081`?

**Q10.** Why is letting users supply a raw `url` for the gateway to fetch a risky design?

**Q11.** Spring Boot returns 503 when catalog stops running, yet the application still starts cleanly. What does this prove?

**Q12.** Is forwarding inbound client tokens/cookies verbatim to downstream services always valid?

**Reference answers:**

1. Hop A: browser is client, gateway is server. Hop B: gateway is client, catalog is server.
2. A controller only declares inbound request handlers; issuing outbound HTTP requires invoking a client API in code or via an appropriate framework integration.
3. `@RequestBody` reads the inbound request body; `RestClient.body(...)` sends the outbound request body.
4. Not by default; it may be an internal workload authentication failure and should be mapped appropriately.
5. CORS is enforced by browsers on cross-origin scripts; backend HTTP clients are not subject to browser CORS enforcement.
6. It can create duplicate orders/payments; an idempotency key and retry policy are required.
7. Blocking the event loop causes latency/saturation; compose reactive WebClient instead.
8. Fan-out: 100 inbound × 3 = 300 outbound calls/s (before retries/cache).
9. No, the listener port and remote destination are independent.
10. SSRF into internal IPs/hosts or metadata endpoints; requires an allowlist/fixed destination.
11. The inbound server can stay healthy while an outbound dependency fails; both must be monitored.
12. No; credentials have separate audiences/scopes/domains and require proper service identity/delegation design.

## 22. Implementation Checklist

- [ ] Clearly define the public inbound API and each outbound dependency contract.
- [ ] Configure base URLs per environment, independent of `server.port` or user-provided URLs.
- [ ] Explicitly specify method/path/query/body/`Content-Type`/`Accept` and validate input.
- [ ] Choose sync RestClient or reactive WebClient matching the stack; never block the WebFlux event loop.
- [ ] Set connect/read/response/overall deadlines aligned with SLOs and proxy timeouts.
- [ ] Manage outbound connection pools, concurrency, bulkheads, and retry budgets.
- [ ] Never retry write operations without idempotency/duplicate protection.
- [ ] Map 4xx/5xx, timeouts, connect failures, and malformed JSON to public errors per contract.
- [ ] Never unconditionally copy user auth tokens, cookies, `Host`, hop-by-hop headers, or `Location`.
- [ ] Verify TLS/trust on every hop, control service identity, and enforce network egress rules.
- [ ] Prevent SSRF and avoid logging secrets/sensitive data.
- [ ] Collect metrics/traces for both the inbound server and outbound HTTP clients.
- [ ] Test success, 404, 429/5xx, slow responses, dependency down, timeouts, and invalid schemas.
- [ ] Limit body sizes/streaming and handle cleanup when requests are canceled.

## 23. References

- Spring Boot 3.3 — Calling REST Services / RestClient and WebClient: https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html
- Spring Boot 3.3 — RestClientAutoConfiguration: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/client/RestClientAutoConfiguration.html
- Spring Framework — REST Clients, RestClient and WebClient: https://docs.spring.io/spring-framework/reference/integration/rest-clients.html
- Spring Framework — Spring MVC @ResponseBody / @RestController: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responsebody.html
- Spring Framework 6.1 — SimpleClientHttpRequestFactory timeout API: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/http/client/SimpleClientHttpRequestFactory.html
- Spring Boot 3.3 — Detecting Web Application Type (MVC vs WebFlux): https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- JDK 17 — HttpServer: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html
- JDK 17 — HttpClient: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- RFC 9110 — HTTP Semantics: https://www.rfc-editor.org/rfc/rfc9110
- W3C Trace Context — traceparent: https://www.w3.org/TR/trace-context/
