# Observe a call across two services with correlated traces and logs

## 1. What problem does this lab solve?

Suppose a user asks: “Why did this inventory check fail?”. A log line in the order service does not say whether the inventory service received the request yet. If both services handle many requests concurrently, matching logs solely by timestamp or product ID is very error-prone.

In this lab, one request traverses two independent Java processes:

```text
curl
  |
  | GET /orders/P100
  v
order-service :8081
  |
  | GET /inventory/P100 + trace context
  v
inventory-service :8082

Both services:
  - write logs in their own process
  - send spans to Zipkin :9411
```

Required outcomes:

1. The business response traverses both services properly.
2. Request-processing logs on both sides carry the same traceId.
3. Each operation has an appropriate spanId; do not force both services to share one span.
4. Zipkin shows the relationship among the incoming request span on A, the outgoing HTTP span from A, and the incoming request span on B.
5. From a log line, find the matching trace; from the trace, know which service's logs to inspect next.

Zipkin receives span data to assemble traces. Application log lines remain in the terminal or log files; this lab does not configure centralized log aggregation. The link between the two forms of evidence here is traceId and spanId.

The project uses Java 21, Gradle 8.5, Spring Boot 3.3.x, and Micrometer Tracing with Brave and Zipkin. This is a standalone lab project; the code snippets below are complete enough to build and run both applications.

## 2. Concepts to distinguish

| Concept | Meaning in this lab |
| --- | --- |
| Trace | The entire chain of work associated with one request |
| Span | One operation with start/end timestamps, e.g. receiving HTTP or calling HTTP |
| traceId | Shared identifier to find spans and logs belonging to the same trace |
| spanId | Identifier of a specific span |
| parentId | Parent span identifier, establishing causal relationships |
| Propagation | Passing trace context across process boundaries |
| MDC | Key–value context used by the logging system to enrich log lines with identifiers |
| Export | Sending span data from the application to a collector such as Zipkin |

Two logs sharing a traceId do not necessarily share a spanId. For example, logs inside controller A belong to A's incoming request span; logs inside controller B belong to B's incoming request span.

Placing a span in scope lets the tracer and logging bridge attach context to log lines emitted within that scope. See [Micrometer Tracing API](https://docs.micrometer.io/tracing/reference/api.html).

Keep two paths distinct:

- **Business path:** A calls B on port 8082 and passes context headers.
- **Observability path:** A and B send spans to Zipkin on port 9411.

Zipkin does not sit between A and B to forward business requests. Successfully sending spans to Zipkin also does not prove context headers between A and B are working.

## 3. Prepare and create the project

Prepare JDK 21, Gradle 8.5 to generate the wrapper initially, Docker to run Zipkin, and free ports 8081, 8082, and 9411.

Create the structure:

```text
tracing-two-services/
├── settings.gradle
├── build.gradle
├── order-service/
│   └── src/main/
│       ├── java/com/example/order/
│       │   ├── OrderApplication.java
│       │   └── OrderController.java
│       └── resources/application.yml
├── inventory-service/
│   └── src/main/
│       ├── java/com/example/inventory/
│       │   ├── InventoryApplication.java
│       │   └── InventoryController.java
│       └── resources/application.yml
└── tools/
    └── TraceEvidenceCheck.java
```

The two service directories do not need separate `build.gradle` files in the sample because shared configuration lives in the root `subprojects` block.

### 3.1. settings.gradle

```groovy
rootProject.name = 'tracing-two-services'
include 'order-service', 'inventory-service'
```

### 3.2. build.gradle

The sample pins Spring Boot 3.3.0 within the 3.3.x line. The BOM shipped with the plugin manages library versions, including observability dependencies.

```groovy
plugins {
    id 'org.springframework.boot' version '3.3.0' apply false
}

subprojects {
    apply plugin: 'java'
    apply plugin: 'org.springframework.boot'

    group = 'com.example'
    version = '1.0.0'

    java {
        toolchain {
            languageVersion = JavaLanguageVersion.of(21)
        }
    }

    repositories {
        mavenCentral()
    }

    dependencies {
        implementation platform(
                org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
        implementation 'org.springframework.boot:spring-boot-starter-web'
        implementation 'org.springframework.boot:spring-boot-starter-actuator'
        implementation 'io.micrometer:micrometer-tracing-bridge-brave'
        implementation 'io.zipkin.reporter2:zipkin-reporter-brave'
    }
}
```

Different roles of the dependencies:

- Web starter provides Spring MVC and the embedded web server.
- Actuator provides auto-configuration for observability infrastructure.
- `micrometer-tracing-bridge-brave` bridges Micrometer's tracing API to Brave.
- `zipkin-reporter-brave` handles reporting spans to Zipkin.

This Brave–Zipkin combination is supported by Spring Boot in [Tracing — OpenZipkin Brave With Zipkin](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html#actuator.micrometer-tracing.tracer-implementations.brave-zipkin).

Do not add Spring Cloud Sleuth to this Spring Boot 3 sample. Also do not mix in an OpenTelemetry bridge when the lab already selects Brave as the tracer.

## 4. Write the order service

### 4.1. OrderApplication.java

File `order-service/src/main/java/com/example/order/OrderApplication.java`:

```java
package com.example.order;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
```

### 4.2. OrderController.java

File `order-service/src/main/java/com/example/order/OrderController.java`:

```java
package com.example.order;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;

@RestController
public class OrderController {
    private static final Logger log =
            LoggerFactory.getLogger(OrderController.class);

    private final RestClient inventory;

    public OrderController(
            RestClient.Builder builder,
            @Value("${inventory.base-url}") String inventoryBaseUrl) {
        SimpleClientHttpRequestFactory requestFactory =
                new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(2000);
        requestFactory.setReadTimeout(3000);

        this.inventory = builder
                .baseUrl(inventoryBaseUrl)
                .requestFactory(requestFactory)
                .build();
    }

    @GetMapping("/orders/{productId}")
    public OrderView order(@PathVariable("productId") String productId) {
        log.info("order.start productId={}", productId);

        try {
            InventoryView result = inventory.get()
                    .uri("/inventory/{productId}", productId)
                    .retrieve()
                    .body(InventoryView.class);

            if (result == null) {
                throw new IllegalStateException("Inventory response is empty");
            }

            log.info("order.done productId={} available={}",
                    productId, result.available());
            return new OrderView(productId, result.available());
        } catch (RestClientResponseException exception) {
            log.error("order.inventory_error productId={} downstreamStatus={}",
                    productId, exception.getStatusCode().value());
            throw exception;
        }
    }

    public record InventoryView(String productId, boolean available) {
    }

    public record OrderView(String productId, boolean available) {
    }
}
```

Points to observe:

- `RestClient.Builder` is injected by Spring Boot, then configured with base URL and request factory.
- The URI uses the template `/inventory/{productId}`; trace headers are never manually concatenated as strings.
- Two logs `order.start` and `order.done` wrap the synchronous call to inventory.
- Connect limit is 2,000 ms and read limit is 3,000 ms; this is not a single overall deadline across all steps.
- When B returns an HTTP error status, A logs `downstreamStatus` and rethrows the exception. The sample has no custom error-mapping layer yet.

An important prerequisite for automatic context propagation is using the Spring Boot–configured builder. Creating a client via `RestClient.create(...)` or a raw builder outside this mechanism can lose required observability configuration. See [Propagating Traces](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html#actuator.micrometer-tracing.propagating-traces).

Choosing the request factory in the example still goes through the injected builder. It does not replace it with a completely detached RestClient.

## 5. Write the inventory service

### 5.1. InventoryApplication.java

File `inventory-service/src/main/java/com/example/inventory/InventoryApplication.java`:

```java
package com.example.inventory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InventoryApplication {
    public static void main(String[] args) {
        SpringApplication.run(InventoryApplication.class, args);
    }
}
```

### 5.2. InventoryController.java

File `inventory-service/src/main/java/com/example/inventory/InventoryController.java`:

```java
package com.example.inventory;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class InventoryController {
    private static final Logger log =
            LoggerFactory.getLogger(InventoryController.class);

    @GetMapping("/inventory/{productId}")
    public InventoryView inventory(@PathVariable("productId") String productId) {
        if ("FAIL".equals(productId)) {
            log.warn("inventory.failure productId={}", productId);
            throw new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE,
                    "Inventory failure for tracing exercise");
        }

        boolean available = !"P-OUT".equals(productId);
        log.info("inventory.check productId={} available={}",
                productId, available);
        return new InventoryView(productId, available);
    }

    public record InventoryView(String productId, boolean available) {
    }
}
```

Three product IDs create three intentional scenarios:

| productId | Outcome at B | Purpose |
| --- | --- | --- |
| P100 | HTTP 200, available=true | Observe the happy path |
| P-OUT | HTTP 200, available=false | Distinguish a negative business outcome from an HTTP error |
| FAIL | HTTP 503 | Observe the error path across two services |

These are fixed rules for the lab, not a real inventory lookup. B does not manually read an arbitrary header and write it as traceId; tracing infrastructure accepts context according to the configured propagation standard.

## 6. Configure tracing and logging on both sides

### 6.1. order-service/application.yml

File `order-service/src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: order-service
  jmx:
    enabled: false

server:
  address: 127.0.0.1
  port: 8081

management:
  endpoints:
    enabled-by-default: false
    web:
      exposure:
        include: health
  endpoint:
    health:
      enabled: true
      show-details: never
  tracing:
    sampling:
      probability: 1.0
    propagation:
      type: w3c
    brave:
      span-joining-supported: false
  zipkin:
    tracing:
      endpoint: http://127.0.0.1:9411/api/v2/spans

logging:
  file:
    name: logs/order-service.log
  pattern:
    console: "%d{HH:mm:ss.SSS} %-5level [app=${spring.application.name} trace=%X{traceId:-} span=%X{spanId:-}] %logger{24} - %msg%n"
    file: "%d{HH:mm:ss.SSS} %-5level [app=${spring.application.name} trace=%X{traceId:-} span=%X{spanId:-}] %logger{24} - %msg%n"

inventory:
  base-url: http://127.0.0.1:8082
```

### 6.2. inventory-service/application.yml

File `inventory-service/src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: inventory-service
  jmx:
    enabled: false

server:
  address: 127.0.0.1
  port: 8082

management:
  endpoints:
    enabled-by-default: false
    web:
      exposure:
        include: health
  endpoint:
    health:
      enabled: true
      show-details: never
  tracing:
    sampling:
      probability: 1.0
    propagation:
      type: w3c
    brave:
      span-joining-supported: false
  zipkin:
    tracing:
      endpoint: http://127.0.0.1:9411/api/v2/spans

logging:
  file:
    name: logs/inventory-service.log
  pattern:
    console: "%d{HH:mm:ss.SSS} %-5level [app=${spring.application.name} trace=%X{traceId:-} span=%X{spanId:-}] %logger{24} - %msg%n"
    file: "%d{HH:mm:ss.SSS} %-5level [app=${spring.application.name} trace=%X{traceId:-} span=%X{spanId:-}] %logger{24} - %msg%n"
```

### 6.3. Why are these settings needed?

Two distinct `spring.application.name` values identify each service in logs and the backend. Ports 8081 and 8082 allow concurrent execution on one machine. Different log file paths avoid two processes writing to the same file.

Both sides use W3C propagation. `span-joining-supported: false` selects the model that does not share span IDs between client-side and server-side spans. Sampling policy and span collector endpoint are declared explicitly for easy lab observation. Look up keys in [Common Application Properties — tracing and Zipkin](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html).

Sampling probability 1.0 serves a low-volume lab experiment. It is not a default configuration to copy verbatim to high-traffic systems. When incoming context arrives from upstream, sampling decisions may also be inherited from that context; do not use probability 1.0 to assume every trace definitely reached the backend.

The log pattern contains three fields: app, trace, and span. `%X{traceId:-}` and `%X{spanId:-}` read MDC; they do not generate IDs themselves. When there is no active span, these fields can be blank. Thus, startup logs having no traceId is normal.

Actuator HTTP endpoints expose only health for process checks. Sending traces to Zipkin does not require exposing all Actuator endpoints or publishing an endpoint named traces.

The `127.0.0.1` addresses apply when both JVMs run directly on the same host. When moving them into containers, target hostnames and networking must be redesigned; localhost inside a container does not point to the Zipkin container or the other service.

## 7. Start up in the right order

Run commands from the `tracing-two-services` root.

### 7.1. Run Zipkin

In one terminal:

```powershell
docker run --rm --name tracing-lab-zipkin -p 127.0.0.1:9411:9411 openzipkin/zipkin
```

The command keeps Zipkin in the foreground so startup status is visible. Wait for the server to become ready. You can open [local Zipkin](http://127.0.0.1:9411/zipkin/) to view the UI.

Basic Docker usage and trace lookup features are introduced in the [OpenZipkin project](https://github.com/openzipkin/zipkin). The sample uses default in-memory storage for practice; do not treat traces in this container as durable storage.

### 7.2. Generate the wrapper and package both JARs

In another terminal, use the prepared Gradle 8.5:

```powershell
gradle wrapper --gradle-version 8.5
.\gradlew.bat :order-service:bootJar :inventory-service:bootJar
```

The first run downloads plugins and dependencies if not cached yet. The two resulting JARs:

```text
order-service/build/libs/order-service-1.0.0.jar
inventory-service/build/libs/inventory-service-1.0.0.jar
```

### 7.3. Start B then start A

Open two terminals, both at the project root.

Terminal B:

```powershell
java -jar inventory-service/build/libs/inventory-service-1.0.0.jar
```

Terminal A:

```powershell
java -jar order-service/build/libs/order-service-1.0.0.jar
```

Wait for both applications to finish starting. Corresponding log files sit at `logs/order-service.log` and `logs/inventory-service.log` under root because that is the working directory of both Java commands.

Check health if needed:

```powershell
curl.exe -i http://127.0.0.1:8081/actuator/health
curl.exe -i http://127.0.0.1:8082/actuator/health
```

Health requests can also generate observability data. Therefore search later by the business request's traceId rather than relying on total trace counts displayed.

On Linux/macOS, use `curl` and `./gradlew` instead of `curl.exe` and `.\gradlew.bat`.

## 8. Send a request and read logs by context

Call A, do not call B directly in the first step:

```powershell
curl.exe -i http://127.0.0.1:8081/orders/P100
```

Expect HTTP 200 and equivalent JSON:

```json
{
  "productId": "P100",
  "available": true
}
```

Each new request carrying no prior context typically starts a new trace. Copy the traceId from the `order.start` log line, then search for it in both files.

The condensed log example below illustrates the shape; timestamps and span IDs are example values, not fixed stdout:

```text
12:00:00.000 INFO [app=order-service trace=11111111111111111111111111111111 span=aaaaaaaaaaaaaaaa] OrderController - order.start productId=P100
12:00:00.005 INFO [app=inventory-service trace=11111111111111111111111111111111 span=bbbbbbbbbbbbbbbb] InventoryController - inventory.check productId=P100 available=true
12:00:00.010 INFO [app=order-service trace=11111111111111111111111111111111 span=aaaaaaaaaaaaaaaa] OrderController - order.done productId=P100 available=true
```

How to read it:

- All three lines share the same traceId, so they can be queried as a group.
- Both lines from A share the same spanId because the code runs inside A's request-handling span.
- B's line has a different spanId because it represents work in another service.
- Product ID helps clarify the scenario; traceId itself is the correlation key for a specific call when multiple requests exist for the same product.

A's HTTP client span is created by observability instrumentation around the RestClient call. It need not emit a separate business log line in the sample.

In a multi-host system, log timestamps across hosts can drift due to clock skew. Use span parent–child relationships to understand the flow; do not rely solely on sorting log lines by timestamp.

## 9. Verify the W3C header and locate the exact trace

The `traceparent` header carries fields formatted as:

```text
version-trace-id-parent-id-trace-flags
```

For version 00, trace-id has 32 hex characters and parent-id has 16 hex characters; neither ID may be all zeros. When A calls B, the outgoing parent-id represents the sender's span for that hop. The format is specified in [W3C Trace Context](https://www.w3.org/TR/trace-context/#traceparent-header).

Do not take the spanId from A's controller log and assume that is the parent-id B receives. Between them sits A's HTTP client span.

### One call with a known traceId

For easy manual correlation in the lab, send the following request exactly once:

```powershell
curl.exe -i -H "traceparent: 00-11111111111111111111111111111111-2222222222222222-01" http://127.0.0.1:8081/orders/P100
```

When the valid context is accepted, the traceId to look for in both service logs is:

```text
11111111111111111111111111111111
```

`2222222222222222` acts as a simulated parent span from the caller. The lab does not send that span to Zipkin, so the backend may not find a record for that external parent. That is not evidence of lost spans for A or B.

A fixed header is only for a single controlled check. Do not reuse the same traceId across multiple independent requests because they could be merged into one trace. Normal calls in section 8 let the tracer generate fresh context naturally.

Search logs with PowerShell:

```powershell
Select-String -Path logs/order-service.log,logs/inventory-service.log -SimpleMatch '11111111111111111111111111111111'
```

If the two services show two different traceIds, inspect the HTTP builder, propagation format, and header presence at the A–B boundary before adjusting logging patterns.

TraceId is a correlation identifier, not authentication material or proof that the caller was authorized.

## 10. Read the trace in Zipkin and return to logs

After the request completes, wait for span export and refresh Zipkin. Search by the recorded traceId; button labels/filtering controls can vary across UI versions.

In the configured model, identify the main operations:

```text
Caller parent span: 2222222222222222 (simulated, unrecorded)
└── A: receive GET /orders/{productId}
    └── A: HTTP call to B
        └── B: receive GET /inventory/{productId}
```

This is a role diagram, not a promise that span names display verbatim as written above. Exact names and tags depend on instrumentation conventions.

You can also inspect trace data via the Zipkin API:

```powershell
$trace = Invoke-RestMethod -Uri 'http://127.0.0.1:9411/api/v2/trace/11111111111111111111111111111111'
$trace | Select-Object traceId,id,parentId,kind,@{Name='service';Expression={$_.localEndpoint.serviceName}}
```

The API is documented at [Zipkin API](https://zipkin.io/zipkin-api/). If spans have not been flushed to the backend yet, querying immediately may not return the trace yet; wait and check span reporter logs.

Read in order:

1. Find the server span for order-service.
2. Find the client span on A and match its parentId to A's server span id.
3. Find the server span for inventory-service and match its parentId to the client span.
4. Compare A/B server span ids with the spanIds in the corresponding controller logs.
5. Check duration, status, and error info for each hop.

If A's span is long while B's processing is short, you cannot conclude B caused all the latency. There is also time on A, connection establishment, data transfer, or queuing. Nested span durations overlap, so summing all durations double-counts time.

Having a trace ID in logs while Zipkin lacks data is a different investigation branch from A and B having two different traceIds. One involves export/sampling/storage; the other involves context propagation and extraction.

## 11. Automatically verify happy-path log evidence

The check below reads log files according to the configured pattern. It verifies that start/done lines in A and the check line in B share the same trace, both A lines share a span, and B has a different span from A.

File `tools/TraceEvidenceCheck.java`:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class TraceEvidenceCheck {
    private static final Pattern CONTEXT = Pattern.compile(
            "\\[app=([^ ]+) trace=([0-9a-f]{32}) span=([0-9a-f]{16})\\]");

    private record Evidence(String app, String traceId, String spanId) {
    }

    private static Evidence latest(
            Path file, String traceId, String message) throws Exception {
        List<String> lines = Files.readAllLines(file);
        for (int index = lines.size() - 1; index >= 0; index--) {
            String line = lines.get(index);
            Matcher match = CONTEXT.matcher(line);
            if (line.endsWith(" - " + message)
                    && match.find()
                    && traceId.equals(match.group(2))) {
                return new Evidence(
                        match.group(1), match.group(2), match.group(3));
            }
        }
        throw new IllegalStateException(
                "Missing evidence in " + file + " for " + message);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3 || !args[0].matches("[0-9a-f]{32}")
                || args[0].equals("00000000000000000000000000000000")) {
            throw new IllegalArgumentException(
                    "Arguments: nonzero-32-hex-trace-id order-log inventory-log");
        }

        String traceId = args[0];
        Evidence start = latest(
                Path.of(args[1]), traceId, "order.start productId=P100");
        Evidence done = latest(
                Path.of(args[1]), traceId,
                "order.done productId=P100 available=true");
        Evidence inventory = latest(
                Path.of(args[2]), traceId,
                "inventory.check productId=P100 available=true");

        boolean services = start.app().equals("order-service")
                && done.app().equals("order-service")
                && inventory.app().equals("inventory-service");
        boolean sameTrace = start.traceId().equals(done.traceId())
                && start.traceId().equals(inventory.traceId());
        boolean stableOrderSpan = start.spanId().equals(done.spanId());
        boolean differentSpans = !start.spanId().equals(inventory.spanId());
        boolean nonzeroSpans =
                !start.spanId().equals("0000000000000000")
                && !inventory.spanId().equals("0000000000000000");

        System.out.println("same-trace=" + sameTrace);
        System.out.println("order-span-stable=" + stableOrderSpan);
        System.out.println("different-service-spans=" + differentSpans);

        if (!(services && sameTrace && stableOrderSpan
                && differentSpans && nonzeroSpans)) {
            throw new IllegalStateException("Trace evidence mismatch");
        }
        System.out.println("evidence=PASS");
    }
}
```

This is a standalone Java program using the standard library, runnable on JDK 17 or newer. At the project root, after the call with the known traceId:

```powershell
javac -encoding UTF-8 -d tools tools/TraceEvidenceCheck.java
java -cp tools TraceEvidenceCheck 11111111111111111111111111111111 logs/order-service.log logs/inventory-service.log
```

When the data satisfies all conditions, exact stdout is:

```text
same-trace=true
order-span-stable=true
different-service-spans=true
evidence=PASS
```

If matching lines are not found, a spanId fails validation, or checked relationships fail, the program throws an exception and exits non-zero.

Limitations of this check:

- It proves correlation fields in logs conform to the lab contract.
- It does not prove spans were exported to Zipkin.
- It does not prove parentId relationships in backend data.
- It only selects lines for P100 and the defined log pattern.
- It does not prove the system prevents application code from spoofing log fields.

Therefore keep both log checks and backend trace checks. Do not consider printing the same ID string into two files as having implemented distributed tracing.

## 12. Observe error paths and distinguish business negatives

### 12.1. Negative business outcome with successful HTTP

```powershell
curl.exe -i http://127.0.0.1:8081/orders/P-OUT
```

Expect HTTP 200:

```json
{
  "productId": "P-OUT",
  "available": false
}
```

Logs still contain `order.done` and `inventory.check`. Out-of-stock in this convention is business data, not automatically an HTTP error.

### 12.2. B returns an HTTP error

```powershell
curl.exe -i http://127.0.0.1:8081/orders/FAIL
```

Without a custom exception handler in the sample, B returns 503, the RestClient call in A throws an exception, and the request to A typically ends with HTTP 500.

Find traceId from `order.start productId=FAIL`, then cross-check:

- B logs `inventory.failure productId=FAIL`.
- A logs `order.inventory_error productId=FAIL downstreamStatus=503`.
- There is no `order.done` log for that failed call.
- Spans reflect per-hop status; do not assume A's HTTP status must equal B's HTTP status.

Do not run the P100 checker from section 11 on a FAIL call's trace; that checker is specifically for the happy path.

### 12.3. B is down or connection fails

Stop only the inventory-service process and call A again. This is a connection/read error, different from receiving HTTP 503.

`RestClientResponseException` in the code catches only cases where an HTTP error response was received. Network errors can take a different exception type; do not necessarily expect an `order.inventory_error` log line with an HTTP status code.

When B never received the request, having no controller log in B is valid evidence. Inspect A's client span and connection error before concluding propagation is broken.

Restart B after the experiment; make a fresh request to confirm the happy path works again.

## 13. Diagnostic table when correlation behaves unexpectedly

| Symptom | Investigation branch |
| --- | --- |
| Both sides have different traceIds | HTTP builder, receiver-side instrumentation, propagation, headers stripped by proxy |
| Both sides share traceId but have different spanIds | Matches separate spans in the lab model; check parentId to confirm |
| A has traceId, B has empty trace/span | Check tracing on B, MDC, and where the log was emitted |
| Logs have IDs but Zipkin has no trace | Exporter, /api/v2/spans endpoint, sampling, flush timing, and backend |
| Zipkin has trace but no related logs | Log level, file path, log pattern, filters, and execution scope |
| Only A spans visible, no B spans | Did B actually receive the request, did B export, or did B start a different trace |
| Startup logs have empty trace/span | Normal when there is no active span |
| Context lost after offloading to executor or new thread | Thread context propagation mechanism; not just HTTP headers |

Do not generate a separate UUID in each service to act as traceId. Two different UUIDs do not link calls; copying the same UUID into MDC still does not build spans with parent–child relationships.

Do not put Authorization headers or entire payloads into logs to correlate calls. In this lab, traceId, spanId, service name, operation marker, and test productId are sufficient to trace calls.

When expanding to asynchronous processing, do not assume MDC or tracing context automatically follows every executor. You need context-propagation support and dedicated tests across that boundary.

## 14. Completion criteria and cleanup

The lab is complete when you have full evidence for a successful call:

- A receives P100 and calls B; the response has available=true.
- Both log files correlate with the same traceId.
- SpanIds in logs match the handling span at each service.
- The backend has the main spans in the same trace with proper parent–child relationships.
- The log evidence checker reports PASS.
- At least one B failure scenario was observed and distinguished from a connection error.

When finished, stop both JVMs with Ctrl+C in their respective terminals. Stop the lab container:

```powershell
docker stop tracing-lab-zipkin
```

Because the container was created with `--rm`, Docker removes the container once stopped. Save any needed evidence before stopping if you want to keep lab results.

What carries forward to production systems is how to follow a single call using IDs and span relationships, then use logs to understand decisions at each hop. Sampling rates, retention, logged fields, and observability access controls must be designed for the specific operating environment.
