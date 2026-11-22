# Adding a Correlation ID to Java Logging — Hands-on Project

## 1. Objectives and Completion Criteria

When multiple HTTP requests run concurrently on the same Java service, their logs can interleave:

```text
INFO  OrderController - request received
INFO  OrderService    - checking order
WARN  InventoryClient - remote timeout
INFO  OrderController - request completed
```

It is unclear which request the timeout belongs to. A **Correlation ID** is an identifier used to link events within the same processing flow:

```text
INFO  [cid=req-A11] OrderController - request received
INFO  [cid=req-A11] OrderService    - checking order
WARN  [cid=req-A11] InventoryClient - remote timeout
INFO  [cid=req-A11] OrderController - request completed
```

This is a **Hands-on Project: Adding a Correlation ID**, not just an explanation of `MDC.put`. After completing it, learners should be able to:

1. Define the scope of a correlation ID: a single HTTP request, a distributed workflow, or a batch.
2. Safely generate a new ID when no trusted input is present; never use a user ID, token, or session cookie as the ID.
3. Verify the inbound header source and validate syntax/length to prevent spoofing and log injection.
4. Store a consistent ID in the Servlet request; attach it to the logging context on each thread/dispatch.
5. Include the ID in SLF4J/Logback output, the `X-Correlation-ID` response header, and allowed outbound HTTP calls.
6. Clean up/restore the MDC in `finally` so request B does not mistakenly carry request A's ID.
7. Handle async/executors and understand why Servlet async dispatch does not automatically cover every background thread.
8. Distinguish `correlation_id` from OpenTelemetry `trace_id`/`span_id` and W3C `traceparent`.
9. Write unit/integration tests verifying requests, errors, security boundaries, outgoing headers, concurrency, context cleanup, and log queryability.
10. Apply data limits, access controls, retention, and observability when the pipeline drops records.

**Deliverable:** a standalone Java 17 program with deterministic stdout to understand the logic, followed by Spring Boot 3.x integration files, a test controller, propagation, `TaskDecorator`, and a QA checklist. The Spring snippets require a classpath/framework; they are not standalone `javac` files.

## 2. What Is a Correlation ID, and How Does It Differ from Other IDs?

| Identifier | Meaning | Creator / Consumer |
| --- | --- | --- |
| `correlation_id` | Links logs of the same logical workflow | Entry service/gateway and participating services |
| `request_id` | Identifies a specific HTTP request | Edge/API gateway/application |
| `trace_id` | Identifies a distributed trace | OpenTelemetry/Micrometer Tracing/tracer |
| `span_id` | Identifies a span within a trace | Tracer/SDK |
| `business_id` | Order, transaction, job | Domain model; carries privacy risks |
| `idempotency_key` | Controls duplicate retries/side effects | API/business persistence contract |

Some systems set `correlation_id=request_id` at the entry point and forward the same ID across the service chain. Others use a single correlation ID for a workflow that spans a message queue. There is no single mandatory Java standard for the format or lifetime of this custom header: **you must clearly define the contract and when it ends**.

**Do not use a correlation ID for authentication or authorization.** Knowing or guessing an ID does not mean a client has permission to read the corresponding data. The ID also **does not replace** an idempotency key in payments or event deduplication.

### 2.1. Correlation ID and W3C `traceparent`

W3C Trace Context example:

```http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
```

`traceparent` contains a version, trace ID (32 hex digits), parent ID (16 hex digits), and trace flags. It differs from a custom header:

```http
X-Correlation-ID: 00b4374c-95b9-4575-821e-86184ac6470d
```

If the application already uses OpenTelemetry or Micrometer Tracing, let **the instrumentation inject/extract W3C context automatically**. Do not write code that converts an arbitrary string from `X-Correlation-ID` into an active trace ID. You may keep both fields in logs when there is a clear use case; it is not always mandatory to create a separate ID if the trace ID already meets your needs.

## 3. Target Processing Flow

```text
Public Client
     |
     v
Trusted Ingress/Gateway
  - strip/overwrite inbound X-Correlation-ID per policy
  - verify service-to-service trust boundary
     |
     v
Java Servlet Service A
  [CorrelationIdFilter]
     |
     +-- choose ID: validated trusted incoming OR new UUID
     +-- save request attribute = ID
     +-- put MDC["correlation_id"] = ID for current dispatch
     +-- response.setHeader("X-Correlation-ID", ID)
     |
     v
Controller -> Service -> Repository (logs share the same cid)
     |
     +-- HTTP client to allowlisted Service B
           Header: X-Correlation-ID = ID
                 |
                 v
          Service B (validate + trust + reuse ID)
     |
     +-- async task: capture/restore context if task uses worker thread
     |
  finally: restore previous MDC key; prevent context leakage
```

Three boundaries to test:

- **Security boundary:** headers sent by an Internet client are untrusted input. Matching a regex does not mean they are trustworthy.
- **Thread boundary:** MDC is thread-local in common logging implementations. Thread pools and callbacks do not automatically inherit context safely.
- **Transport boundary:** an ID appearing in app logs does not prove the outbound service, Collector, or backend recorded it; you must test the actual path and log query.

### 3.1. Lab ID Format Contract

Illustrative conventions:
- Header `X-Correlation-ID`.
- MDC key/structured field `correlation_id`.
- Inbound is accepted only when there is **exactly one value** and it comes from a verified gateway that strips external headers.
- Regex `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`: 1–64 ASCII characters, no whitespace or control characters.
- If missing, invalid, or untrusted, generate `UUID.randomUUID().toString()`.
- Do not log raw rejected headers; do not concatenate unvalidated values into log messages.
- For async Servlet redispatch, **do not generate a second ID** if the request attribute already holds a valid ID.

The regex is an example policy, not a mandatory standard for every environment. If your gateway uses a different format, update the ingress, services, and tests together under a versioned contract.

## 4. Run the Standalone Java 17 Demo Before Spring Integration

Start with a **JDK-only** example using `java.util.logging` (JUL) and `ThreadLocal` to simulate a scoped logging context. **This is not SLF4J MDC**. The program receives three simulated requests:

- A trusted upstream sends a valid `edge-101` → accepted.
- An untrusted client sends `spoof-999` → ignored, generating `gen-202`.
- A trusted upstream sends a string containing a newline → rejected, generating `gen-303`.

For deterministic stdout, the demo uses a fake generator with fixed values. Production must use an appropriate random generator.

Save `CorrelationIdLab.java`:

```java
import java.net.URI;
import java.net.http.HttpRequest;
import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class CorrelationIdLab {
    private static final String HEADER = "X-Correlation-ID";
    private static final ThreadLocal<String> CURRENT = new ThreadLocal<>();

    private static boolean valid(String value) {
        return value != null
                && value.matches("[A-Za-z0-9][A-Za-z0-9._-]{0,63}");
    }

    private static String resolve(String inbound,
                                  boolean trustedGateway,
                                  Supplier<String> generator) {
        return trustedGateway && valid(inbound)
                ? inbound : generator.get();
    }

    private static final class Scope implements AutoCloseable {
        private final String previous;

        Scope(String id) {
            previous = CURRENT.get();
            CURRENT.set(id);
        }

        @Override
        public void close() {
            if (previous == null) {
                CURRENT.remove();
            } else {
                CURRENT.set(previous);
            }
        }
    }

    private static final class Capture extends Handler {
        private final List<String> lines = new ArrayList<>();

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                String id = CURRENT.get();
                lines.add(record.getLevel().getName()
                        + " cid=" + (id == null ? "none" : id)
                        + " " + record.getMessage());
            }
        }

        @Override public void flush() { }
        @Override public void close() { }

        List<String> lines() {
            return List.copyOf(lines);
        }
    }

    private static void handle(String name,
                               String headerValue,
                               boolean trustedGateway,
                               String generatedId,
                               Logger logger,
                               List<String> forwarded) {
        String id = resolve(headerValue, trustedGateway,
                () -> generatedId);

        try (Scope ignored = new Scope(id)) {
            logger.info("event=request.accepted name=" + name);

            HttpRequest outgoing = HttpRequest.newBuilder(
                    URI.create("https://inventory.internal.example/stock"))
                    .header(HEADER, CURRENT.get())
                    .GET()
                    .build();

            String sent = outgoing.headers()
                    .firstValue(HEADER)
                    .orElse("none");
            forwarded.add("request=" + name + " cid=" + sent);
            logger.info("event=downstream.prepared name=" + name);
        }

        if (CURRENT.get() != null) {
            throw new IllegalStateException("CONTEXT_LEAK");
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("lab.correlation");
        Capture capture = new Capture();
        capture.setLevel(Level.ALL);
        logger.setLevel(Level.INFO);
        logger.setUseParentHandlers(false);
        logger.addHandler(capture);

        try {
            List<String> forwarded = new ArrayList<>();
            handle("first", "edge-101", true,
                    "gen-101", logger, forwarded);
            handle("second", "spoof-999", false,
                    "gen-202", logger, forwarded);
            handle("third", "bad\nvalue", true,
                    "gen-303", logger, forwarded);

            for (String line : capture.lines()) {
                System.out.println(line);
            }
            for (String item : forwarded) {
                System.out.println("outbound " + item);
            }
            System.out.println("after_requests cid="
                    + (CURRENT.get() == null ? "none" : CURRENT.get()));
        } finally {
            logger.removeHandler(capture);
            capture.close();
        }
    }
}
```

Compile and run:

```bash
javac --release 17 CorrelationIdLab.java
java CorrelationIdLab
```

Exact stdout:

```text
INFO cid=edge-101 event=request.accepted name=first
INFO cid=edge-101 event=downstream.prepared name=first
INFO cid=gen-202 event=request.accepted name=second
INFO cid=gen-202 event=downstream.prepared name=second
INFO cid=gen-303 event=request.accepted name=third
INFO cid=gen-303 event=downstream.prepared name=third
outbound request=first cid=edge-101
outbound request=second cid=gen-202
outbound request=third cid=gen-303
after_requests cid=none
```

**Explanation:**
- `resolve` keeps the incoming header only when both trust and valid syntax are satisfied.
- `HttpRequest.newBuilder` only prepares the outbound request and headers; `HttpClient.send` is not called, so **no network request is sent**.
- The custom JUL `Handler` prints the CID from `ThreadLocal` when receiving a log record and disables parent handlers, so there are no timestamps or duplicate output from the default JUL console handler.
- `Scope.close()` restores the previous value or removes it, so the next request on the same thread does not carry the old ID.
- A header containing a newline is rejected by the regex before being placed into `HttpRequest`/headers.
- The fixed generator is for testing only, not production ID generation. In practice, use `UUID.randomUUID()` and avoid tokens or user information.
- There is no trace SDK, collector, or backend delivery guarantee in this demo.

## 5. Starting the Spring Boot 3.x Project

A Spring Boot 3.x **Servlet Spring MVC** project uses Java 17, `spring-boot-starter-web`, and SLF4J/Logback. Spring Boot 3 uses `jakarta.servlet`; Spring Boot 2 uses `javax.servlet`—do not mix the two APIs.

Suggested structure:

```text
src/main/java/com/example/correlation/
  DemoApplication.java
  CorrelationIdFilter.java
  CorrelationIdConfig.java
  ProbeController.java
  CorrelatedExecutorConfig.java
src/main/resources/
  application.properties
```

For a Maven project that already has a Spring Boot parent/BOM, web dependency:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
```

This is a **fragment inside `pom.xml`**, not a complete POM: the parent/BOM, version, and build config still need to be provided by the project. The default Spring Boot starter typically includes SLF4J and Logback; verify the actual provider and do not add multiple conflicting SLF4J implementations.

Bootstrap application `DemoApplication.java`:

```java
package com.example.correlation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

If using Spring WebFlux/Reactor, **do not use this Servlet filter**; WebFlux requires a `WebFilter` and reactive context propagation, and you cannot copy the `ThreadLocal` mechanism as-is.

## 6. Writing CorrelationIdFilter with One ID per Logical Request

The filter needs to store the ID in a Servlet request attribute across dispatches, bind a scoped MDC key, and return the ID in the response. File `CorrelationIdFilter.java`:

```java
package com.example.correlation;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.Collections;
import java.util.List;
import java.util.UUID;
import java.util.regex.Pattern;
import org.slf4j.MDC;
import org.springframework.web.filter.OncePerRequestFilter;

public final class CorrelationIdFilter extends OncePerRequestFilter {
    public static final String HEADER = "X-Correlation-ID";
    public static final String MDC_KEY = "correlation_id";
    private static final String ATTRIBUTE =
            CorrelationIdFilter.class.getName() + ".requestId";
    private static final Pattern VALID =
            Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,63}");

    private final boolean trustInbound;

    public CorrelationIdFilter(boolean trustInbound) {
        this.trustInbound = trustInbound;
    }

    private static boolean valid(String raw) {
        return raw != null && VALID.matcher(raw).matches();
    }

    private static String incoming(HttpServletRequest request) {
        List<String> values = Collections.list(request.getHeaders(HEADER));
        return values.size() == 1 ? values.get(0) : null;
    }

    @Override
    protected boolean shouldNotFilterAsyncDispatch() {
        return false;
    }

    @Override
    protected boolean shouldNotFilterErrorDispatch() {
        return false;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        Object saved = request.getAttribute(ATTRIBUTE);
        String id = saved instanceof String value && valid(value)
                ? value : null;

        if (id == null) {
            String candidate = incoming(request);
            id = trustInbound && valid(candidate)
                    ? candidate : UUID.randomUUID().toString();
            request.setAttribute(ATTRIBUTE, id);
        }

        response.setHeader(HEADER, id);
        String previous = MDC.get(MDC_KEY);

        try (MDC.MDCCloseable ignored =
                     MDC.putCloseable(MDC_KEY, id)) {
            chain.doFilter(request, response);
        } finally {
            if (previous == null) {
                MDC.remove(MDC_KEY);
            } else {
                MDC.put(MDC_KEY, previous);
            }
        }
    }
}
```

Key points:

- A `request attribute` keeps the ID stable across dispatches within the same Servlet request, while the container preserves the attribute. Do not generate a new ID every time the filter is re-entered.
- `Collections.list(request.getHeaders(...))` checks the number of header values. Duplicate headers with the same name must not have one picked arbitrarily; a proxy may also fold them into a comma-separated string, which the regex rejects as well.
- `trustInbound=false` is the safe default for public-facing applications. Only enable `true` when the ingress strips/overwrites client headers, the backend receives traffic from a verified upstream, and direct-bypass paths are blocked.
- `MDC.putCloseable` sets the key for the current scope, and `finally` restores the previous value. Do not call `MDC.clear()` indiscriminately in a filter because it can wipe trace/span metadata or context belonging to another middleware.
- `OncePerRequestFilter` guarantees once per **request dispatch**, not a single invocation for the entire lifecycle when `ASYNC` or `ERROR` dispatches occur.
- Error dispatches nested inside `REQUEST` have a separate `doFilterNestedErrorDispatch` mechanism; this sample class does not customize that hook. You must test on a real container if you need correlation in all error-handler logs.
- Setting the response header early ensures the client receives the ID; however, a response wrapper or error handler may reset headers. Test the exact behavior at response time, especially on HTTP 500.
- The class above is Spring Boot integration code, not a standalone JDK file.

### 6.1. Validation Does Not Create Trust

An attacker can send `X-Correlation-ID: trusted-admin-123` — syntactically valid, yet its identity is unverified. **Never treat this value as authentication or authorization**. The gateway must strip or replace untrusted headers, then authenticate upstream identity via network/mTLS/service mesh policy. The header can be used to look up events once it has crossed a safe boundary, never to make authorization decisions.

## 7. Registering the Filter for REQUEST, ASYNC, and ERROR

Do not put `@Component` on the filter above if you also use `FilterRegistrationBean`; register a single explicit instance.

File `CorrelationIdConfig.java`:

```java
package com.example.correlation;

import jakarta.servlet.DispatcherType;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.env.Environment;

@Configuration
public class CorrelationIdConfig {
    @Bean
    public FilterRegistrationBean<CorrelationIdFilter>
    correlationIdFilterRegistration(Environment environment) {

        boolean trusted = Boolean.TRUE.equals(environment.getProperty(
                "app.logging.trust-inbound-correlation-id",
                Boolean.class,
                false));

        FilterRegistrationBean<CorrelationIdFilter> registration =
                new FilterRegistrationBean<>();
        registration.setFilter(new CorrelationIdFilter(trusted));
        registration.setName("correlationIdFilter");
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 10);
        registration.setAsyncSupported(true);
        registration.setDispatcherTypes(
                DispatcherType.REQUEST,
                DispatcherType.ASYNC,
                DispatcherType.ERROR);
        return registration;
    }
}
```

Spring Servlet filter mappings must include the appropriate dispatcher types; merely overriding `shouldNotFilterAsyncDispatch()` is not enough for the filter to run on `ASYNC`. `setAsyncSupported(true)` lets the container allow async processing on the filter. `Ordered.HIGHEST_PRECEDENCE+10` is an illustrative choice; verify the actual order relative to Spring Security, tracing filters, request wrappers, and other custom middleware.

Having the filter run again on `ASYNC` dispatch **does not** replace propagation to arbitrary executor tasks. That is covered separately in section 11.

## 8. Configuring Logback to Print the Correlation ID

File `application.properties`:

```properties
server.port=8080

# Only set to true when the ingress actually strips/overwrites public headers.
app.logging.trust-inbound-correlation-id=false

# Pattern for Spring Boot + Logback.
logging.pattern.console=%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level [cid=%X{correlation_id:-none}] %logger{36} - %msg%n
logging.level.com.example.correlation=INFO
```

`%X{correlation_id:-none}` reads the MDC key; **the pattern does not generate an ID**. Logs outside HTTP (startup, scheduler, standalone tasks) may not have a correlation ID: displaying `none` is appropriate when no scope has been created.

If the application already uses Micrometer Tracing or OpenTelemetry, the logging config may already include `traceId`, `spanId`, or `trace_id`/`span_id`. Do not overwrite and lose those fields when customizing the console pattern. With a JSON encoder, verify that `correlation_id` is emitted as a queryable structured field rather than just part of the message text.

Log4j 2 also has a `ThreadContext`/`Map` pattern, but uses its own config file and syntax; do not paste Logback XML directly into Log4j 2.

## 9. Test Controller: Same ID in Response Header and Logs

File `ProbeController.java`:

```java
package com.example.correlation;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/demo")
public class ProbeController {
    private static final Logger LOG =
            LoggerFactory.getLogger(ProbeController.class);

    @GetMapping("/ping")
    public ResponseEntity<String> ping() {
        LOG.info("event=demo.ping outcome=SUCCESS");
        return ResponseEntity.ok("pong");
    }

    @GetMapping("/error")
    public ResponseEntity<String> error() {
        LOG.warn("event=demo.error.triggered");
        throw new IllegalStateException("synthetic_failure");
    }
}
```

`/error` is for lab testing only; do not deploy a route that intentionally throws errors publicly in production. Run the project via the included Maven Wrapper:

```bash
./mvnw spring-boot:run
```

You must have Maven/Wrapper and a valid POM; this is not a single-file `javac` run. Call:

```bash
curl --include http://127.0.0.1:8080/demo/ping
```

Example response:

```text
HTTP/1.1 200
X-Correlation-ID: 6a218a3e-4f6f-499d-a7f8-456c1a899655

pong
```

The UUID will **differ on each run**; other HTTP headers depend on the servlet container. Find the `event=demo.ping` log; the `cid` value in the log must match the response header of the **same request**.

Call next:

```bash
curl --include \
  -H "X-Correlation-ID: client-picked-id" \
  http://127.0.0.1:8080/demo/ping
```

With the trust flag `false`, the response **must not** keep `client-picked-id`. If switching trust to `true` in a backend environment with a real ingress, verify that the gateway strips public headers and only attaches valid values. Do not just flip the property to `true` to test on a public service.

For the `/demo/error` route, check the response header, the ID in the `WARN` log, the error handler, and the number of log records. An error response may be reset, so do not promise header preservation without testing the Servlet error lifecycle.

## 10. Sending the ID to a Downstream Service

Suppose service A calls Inventory Service B over HTTP. When calling an allowed internal host, add `X-Correlation-ID` from the scoped context to the outbound request.

With Spring Framework 6.1+/Spring Boot 3.2+, you can use a `RestClient` interceptor:

```java
// Snippet inside a @Configuration class importing RestClient, MDC, and @Bean.
@Bean
RestClient inventoryClient(RestClient.Builder builder) {
    return builder
        .baseUrl("https://inventory.internal.example")
        .requestInterceptor((request, body, execution) -> {
            String id = MDC.get("correlation_id");
            String host = request.getURI().getHost();

            if (id != null
                    && "inventory.internal.example"
                            .equalsIgnoreCase(host)) {
                request.getHeaders().set("X-Correlation-ID", id);
            }

            return execution.execute(request, body);
        })
        .build();
}
```

The host `inventory.internal.example` is an illustrative address, not a live backend. This code snippet requires Spring Web, SLF4J, and imports inside a configuration class. Do not send internal IDs and credentials to untrusted hosts; also verify redirect/proxy behavior and service discovery.

An HTTP client running on a worker thread without MDC may send a request **without the header** even if the upstream servlet thread had an ID. With WebClient/Reactor, use reactive context/instrumentation; do not arbitrarily copy `MDC.get` and assume it is always on the right thread.

The custom header helps correlate logs when service B receives and preserves a valid ID. **It does not automatically create a distributed trace**; W3C propagation/tracer must be configured independently.

## 11. Async and Thread Pools: Propagate Context and Clean Up

In many logging backends, MDC is a per-thread context. If request A invokes `@Async` on another thread, `MDC.get("correlation_id")` may be empty. If the previous worker did not clean up, it might even carry request B's ID.

### 11.1. TaskDecorator for a Specific Executor

File `CorrelatedExecutorConfig.java`:

```java
package com.example.correlation;

import java.util.Map;
import org.slf4j.MDC;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class CorrelatedExecutorConfig {
    @Bean("correlatedExecutor")
    public ThreadPoolTaskExecutor correlatedExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("correlated-");

        executor.setTaskDecorator(task -> {
            Map<String, String> captured = MDC.getCopyOfContextMap();
            return () -> {
                Map<String, String> previous = MDC.getCopyOfContextMap();
                try {
                    if (captured == null) {
                        MDC.clear();
                    } else {
                        MDC.setContextMap(captured);
                    }
                    task.run();
                } finally {
                    if (previous == null) {
                        MDC.clear();
                    } else {
                        MDC.setContextMap(previous);
                    }
                }
            };
        });

        return executor;
    }
}
```

In a Spring-managed bean lifecycle, the executor is initialized when the bean is created. If you instantiate an executor manually outside Spring, you must initialize and shut it down properly. `TaskDecorator` snapshots the MDC from the submitter and restores the previous map on the worker in `finally`.

**Important limitations:**
- Only tasks **submitted through this executor** receive the context. `CompletableFuture.runAsync(task)` without an explicit executor typically uses the common pool, which is not automatically wrapped.
- With `@Async("correlatedExecutor")`, async support must also be properly enabled; verify the actual executor used.
- `TaskDecorator` copies the MDC **map**, not an OpenTelemetry active span or Reactor Context. If you need trace continuity, use Micrometer Context Propagation/OpenTelemetry instrumentation and avoid copying ID text as if it were active tracing state.
- A snapshot can contain sensitive keys if someone previously placed them in MDC; only put approved metadata into MDC.
- `MDC.getCopyOfContextMap()` can return `null`, so the code must handle `null`.

### 11.2. CompletableFuture Example

```java
// Snippet in a service that has the correlatedExecutor bean and Logger log.
CompletableFuture<Void> work = CompletableFuture.runAsync(
        () -> log.info("event=inventory.refresh.started"),
        correlatedExecutor);
```

This is an integration snippet; the task receives the correlation ID only when `correlatedExecutor` is the bean configured with `TaskDecorator` and the task is submitted within an active MDC scope.

### 11.3. Servlet ASYNC Dispatch Is Not Every Async Task

`OncePerRequestFilter` can run on `DispatcherType.ASYNC` when registered. However, a controller `Callable`/`DeferredResult` or an application background job can run **between** dispatches on a different thread without passing through the filter. Never leave MDC on a request thread waiting until async completes; that thread may serve another request. Each thread/task needs its own scope and cleanup.

For Scheduled Jobs, Message Consumers, and Kafka/Rabbit workers, define an entry boundary to generate/select a new correlation ID or use a validated message header. `correlation_id` does not replace `message_id`, `idempotency_key`, or `retry_attempt`.

## 12. OpenTelemetry and Micrometer Tracing

With auto-instrumentation, a log may contain:

```text
correlation_id=6a218a3e-4f6f-499d-a7f8-456c1a899655
trace_id=4bf92f3577b34da6a3ce929d0e0e4736
span_id=00f067aa0ba902b7
```

Depending on the stack, Micrometer Tracing typically uses MDC keys `traceId` and `spanId`, while OpenTelemetry Java agent MDC instrumentation may use `trace_id` and `span_id`. Check the actual encoder: simply adding a pattern does not create a tracer or make spans appear.

A trace ID appearing in a log **does not guarantee the backend holds the trace**: head/tail sampling, exporter/Collector failures, retention, or the wrong environment can all prevent querying the trace. Log and trace correlation is a lookup capability when both pipelines are working, not a log storage guarantee.

Do not attach `correlation_id`, `request_id`, or `trace_id` to **metric labels** per request. These labels have high cardinality; for request latency/error metrics, use route template/status/method/service to compute p95/p99 and error rate.

## 13. Writing Unit Tests for the ID Policy

| Inbound | Trusted? | Expected |
| --- | --- | --- |
| No header | No | Generate new ID |
| Valid `edge-101` | Yes | Keep `edge-101` |
| Valid `client-picked` | No | Ignore, generate ID |
| Empty header | Yes | Generate ID |
| Header with newline/tab | Yes | Reject, do not log raw |
| 100-char header | Yes | Reject per 64-char limit |
| Header with comma/control character | Yes | Reject |
| Multiple headers with same name | Yes | Reject or explicit gateway policy |
| Valid ID across ASYNC dispatch | N/A | Keep ID from request attribute |
| Reused thread | N/A | Must not carry previous request's CID |
| Exception | N/A | MDC cleanup in `finally` |
| Outbound to non-allowlisted host | N/A | Do not forward header |

At the test boundary, distinguish request headers from the Internet from headers sent by a verified trusted service. Do not "mock `trusted = true`" and treat that as a complete security test; you also need integration tests at the real ingress.

### 13.1. MockMvc Example (Snippet Requiring Test Dependencies)

```java
@WebMvcTest(ProbeController.class)
@Import(CorrelationIdConfig.class)
class CorrelationIdWebTest {
    @Autowired MockMvc mvc;

    @Test
    void publicHeaderCannotSelectId() throws Exception {
        MvcResult result = mvc.perform(
                get("/demo/ping")
                    .header("X-Correlation-ID", "attacker-123"))
                .andExpect(status().isOk())
                .andReturn();

        String id = result.getResponse()
                .getHeader("X-Correlation-ID");

        assertNotNull(id);
        assertNotEquals("attacker-123", id);
        assertTrue(id.matches(
                "[A-Za-z0-9][A-Za-z0-9._-]{0,63}"));
    }
}
```

This is an **illustrative test class with imports omitted**, not a standalone JDK file. It requires `spring-boot-starter-test`, MockMvc, JUnit Jupiter, and test properties keeping `trustInbound=false`. If Spring Security is in the project, configure authentication accordingly.

MockMvc does not fully simulate proxy trust, networking, Servlet container error/async lifecycles, or multithreading. Real integration tests are required for production deployment.

## 14. E2E Tests: Same ID Across Console, Response, and Downstream

A practical test suite:

1. Call `/demo/ping` without a header. Assert the response has a valid new ID.
2. Capture the `demo.ping` log event; assert `correlation_id` matches that request's response header.
3. Send two consecutive requests on the same worker thread; assert the IDs differ and there is no leakage.
4. Send a spoofed inbound header from a public client; assert the service does not pick it when the trust flag is `false`.
5. Route through an ingress that strips/overwrites headers, with trust enabled for that environment: assert service A and service B share the same ID.
6. Trigger an HTTP 500 error: assert the error log/response ID belongs to the same logical request and is not regenerated on `ERROR` dispatch; note that the container may reset headers.
7. Use `Callable`/`DeferredResult` and a dedicated executor; assert worker logs have the CID when the executor is instrumented.
8. Submit another task to the same worker just used; assert it does not have the old CID.
9. Make an HTTP client call to a non-allowlisted host; assert the CID is not sent.
10. Test the JSON encoder and Collector/backend query by ID, not just console output.
11. Send a synthetic header containing a newline/secret; assert it does not appear in the message, MDC, or response.
12. Test fan-out/dual ingest: the same event must not be recorded twice due to root/child additivity or stdout + OTLP going to the same backend.

**A log having a CID does not prove the request is traced end-to-end.** You must verify each boundary and data pipeline.

## 15. Security and Privacy: Non-Negotiables

- **Spoofing:** clients can send syntactically valid IDs; enforce a trust boundary at the gateway and backend network.
- **Log injection:** reject control characters/newlines and overly long raw headers; use structured encoding, never concatenate untrusted data directly.
- **PII:** never use email, user ID, phone number, IP, session token, JWT, or order ID as the default CID.
- **Exfiltration:** never forward internal CIDs and baggage to unauthorized external hosts; check redirects.
- **Authentication:** never use a CID as authorization, a CSRF token, a session, or an idempotency key.
- **Retention:** even random CIDs link events together; control ACLs, retention periods, and exports.
- **Observability security:** logging pipelines can drop or delay records; never infer "no log seen means the action did not happen."
- **Cleanup:** a missing `finally` can misattribute user A's activity to user B's logs, creating privacy risks and misleading investigations.

If browser JavaScript needs to read the response header, CORS may need `Access-Control-Expose-Headers: X-Correlation-ID` on **allowed origins**. This only exposes header visibility to scripts, not authentication; do not open unnecessary wildcard or credential policies.

## 16. Common Anti-Patterns

**Mistake 1 — generating a UUID in each service without forwarding:** a request crosses three services and gets three different IDs; logs are hard to stitch together.

**Mistake 2 — trusting every inbound header:** an attacker can force someone else's ID, causing spoofing/false correlation.

**Mistake 3 — logging rejected headers raw:** newlines/secrets can cause log injection or data exposure.

**Mistake 4 — using a global static String:** concurrent requests and threads overwrite each other's IDs.

**Mistake 5 — forgetting MDC cleanup:** a thread pool worker retains the previous request's ID.

**Mistake 6 — calling `MDC.clear()` indiscriminately:** wipes `traceId`/`spanId` or context owned by another framework.

**Mistake 7 — setting the filter ASYNC flag without dispatcher mapping:** does not run on async redispatch as expected.

**Mistake 8 — applying `TaskDecorator` to an unused executor:** `CompletableFuture` still runs on the common pool and loses the CID.

**Mistake 9 — copying only trace ID text via MDC:** does not create a parent/child span relationship; use OTel Context Propagation.

**Mistake 10 — adding CID to metric labels:** every request creates a new time series, exploding cardinality and cost.

**Mistake 11 — attaching handlers/appenders on both root and child:** a single event may be emitted twice due to additivity.

**Mistake 12 — using CID as identity/idempotency:** provides no proof of authorization and does not prevent duplicate side effects.

**Mistake 13 — assuming response headers survive every 500:** error handlers/containers can reset the response; test it.

**Mistake 14 — checking console only:** logs may fail to pass through the shipper/OTLP/Collector or backend query.

**Mistake 15 — forwarding headers arbitrarily:** internal identifiers get sent to external domains outside the organization.

**Mistake 16 — treating an ID as audit proof:** auditing requires its own transaction, durability, and identity contract.

## 17. Operational Runbook When Support Receives a Correlation ID

When a user reports an error with `X-Correlation-ID`:
1. Identify the service, environment, endpoint, and time window.
2. Query the exact `correlation_id` in centralized logs, preferring the structured field.
3. Sort by source event timestamp and account for time zones/ingest delay.
4. Inspect request outcome, status, `error_type`, retry attempts, and service version.
5. Follow the ID to find downstream logs in trusted services.
6. If the log has a `trace_id`, open the trace (if sampled/stored) to inspect the critical path and dependency spans.
7. Use HTTP metrics/histograms to see whether the error is isolated or affects many requests.
8. Do not infer caller identity from the ID; open sensitive data only with proper authorization/need-to-know.
9. If no record is found, check log level/filters, MDC encoder, async propagation, sampling, queue/drops, and the Collector/backend.
10. After fixing, verify new events have the correct CID at both source and backend.

Do not share full logs or tokens in a ticket just because a CID is present. When extracting records, apply redaction and restrict access per policy.

## 18. Final Project Acceptance Checklist

- [ ] Define ID lifetime, header format, max length, and owner.
- [ ] Public ingress strips/overwrites untrusted headers; backend has no bypass path.
- [ ] Missing/invalid/untrusted inbound generates a new ID; no PII used.
- [ ] Request attribute stores one ID across supported dispatches.
- [ ] Filter sets MDC on entry and restores/removes it in `finally`.
- [ ] Logback/structured encoder actually emits `correlation_id`.
- [ ] HTTP response header contains the same ID on success and error per tested contract.
- [ ] Outbound client forwards only to allowlisted services.
- [ ] Async workers are configured with context propagation on the right executor.
- [ ] Thread reuse causes no leakage; concurrent tests do not mix IDs.
- [ ] OTel/Micrometer Tracing still handles `traceparent` and span hierarchy; trace ID is not manually altered.
- [ ] CID is not added to metric labels; CID is not used for auth/idempotency.
- [ ] Synthetic tokens/cookies/Authorization headers are not leaked in logs.
- [ ] Centralized pipeline has no duplicates, uses the right parser/schema, and is queryable by CID.
- [ ] Runbook exists for ID lookup and diagnosing dropped traces/logs.
- [ ] Monitoring includes metrics for logging failures and queue/backpressure if using a remote pipeline.

**Conclusion:** Adding a correlation ID properly means designing **trust boundary + ID lifecycle + scoped context + propagation + verification**, not just calling `UUID.randomUUID()` and inserting an ID into a log message. Once these steps are tested, a Java application can correlate logs per request/workflow, reduce confusion across threads/services, and improve production debugging while protecting user data.

## Official References

- [SLF4J MDC API: putCloseable, getCopyOfContextMap, setContextMap](https://www.slf4j.org/apidocs/org/slf4j/MDC.html).
- [SLF4J User Manual](https://www.slf4j.org/manual.html).
- [Logback MDC Manual](https://logback.qos.ch/manual/mdc.html).
- [Spring OncePerRequestFilter JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html).
- [Spring MVC Async Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html).
- [Spring ThreadPoolTaskExecutor/TaskDecorator](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html).
- [Spring Boot Tracing and Logging Correlation IDs](https://docs.spring.io/spring-boot/reference/actuator/tracing.html).
- [Spring Boot Logging](https://docs.spring.io/spring-boot/reference/features/logging.html).
- [OpenTelemetry Logs correlation](https://opentelemetry.io/docs/specs/otel/logs/).
- [OpenTelemetry Java MDC instrumentation](https://github.com/open-telemetry/opentelemetry-java-instrumentation/blob/main/docs/logger-mdc-instrumentation.md).
- [W3C Trace Context](https://www.w3.org/TR/trace-context/).
- [Oracle JDK 17 UUID](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/UUID.html).
- [Oracle JDK 17 HttpRequest.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html).
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).