# Attaching a Correlation ID to Logs

When a request passes through multiple layers in a Spring Boot application, logs are typically written by controllers, services, repositories, and outbound components. If each log line does not carry a shared identifier, operators have to search by timestamp, message content, or thread and can easily mix up concurrent requests. A correlation ID solves this problem by attaching an identifier across the processing lifecycle so that related log lines can be queried together.

In this practice exercise, we create or accept a correlation ID on incoming requests, place the value into MDC so the logger records it automatically, return the ID to the client, propagate the ID across HTTP calls, and ensure the context is cleared from the thread after processing. The lesson also distinguishes a correlation ID from a distributed tracing trace ID, because these two values have related purposes but do not completely replace each other.

## 1. What Is a Correlation ID?

A correlation ID is an identifier attached to a request or a workflow to link events emitted during processing. For example, a gateway receives an order request with `X-Correlation-ID: order-req-42`; Order Service, Inventory Service, and Payment Service can write this same ID into their logs. When investigating, operations teams search for `order-req-42` to inspect logs belonging to the same journey.

A correlation ID is typically propagated via:

- HTTP request and response headers.
- HTTP/gRPC calls between services.
- Message headers when publishing and consuming events.
- The logging framework's MDC within the current execution scope.
- Executor or asynchronous task contexts when work continues on another thread.

A correlation ID should remain stable across the journey being investigated. If every service generates a new ID on its own, logs can no longer be linked together. A trusted entry point such as an API gateway or the first service accepts a valid ID or generates a new one and forwards it.

## 2. Distinguishing Correlation ID from Trace ID

Both correlation ID and trace ID help locate related events, but they have different origins and scopes.

| Property | Correlation ID | Trace ID |
|---|---|---|
| Purpose | Group logs and events by request/job | Link spans into a distributed trace |
| Origin | Gateway, application, or calling system | Tracing SDK/bridge per trace context |
| Propagation | Application-defined header or message metadata | W3C Trace Context or corresponding propagator |
| Scope | Defined by system convention; can span multiple business steps | Defined by the trace lifecycle in the tracing system |
| Accompanying metadata | Usually a simple ID | Trace ID, span ID, trace flags, and span relationships |
| Observability capability | Find logs sharing the same ID | View span tree, parent-child relationships, duration, and error status |

If Micrometer Tracing is enabled, trace ID and span ID can usually be added to log correlation automatically. In a system with full distributed tracing, the trace ID can cover most log-linking needs for a single request. A separate correlation ID remains useful when you need to preserve a ticket/request code issued by a gateway, partner, or business system, or when you want to correlate logs in flows that do not yet have traces.

Avoid overriding `traceparent` or generating your own trace IDs to replace tracing instrumentation. Let Micrometer Tracing or OpenTelemetry manage the trace context; a dedicated correlation ID is purely supplementary metadata.

## 3. Putting the Correlation ID into MDC

MDC (Mapped Diagnostic Context) is a thread-scoped data map supported by logging frameworks such as Logback. When a correlation ID is placed in MDC, the log pattern can read this value and automatically include it on every log line without passing the ID parameter into every logger call.

For a Spring Boot application using Spring MVC and a servlet container, you can use `OncePerRequestFilter` to set up MDC at the start of the request and clean it up in `finally`.

The filter examples below use Spring MVC/Servlet and `jakarta.servlet` (Spring Boot 3 and later). If the application uses WebFlux, apply Reactor Context instead of registering a servlet filter.

### 3.1. Creating the Request Identification Filter

The example below uses the `X-Correlation-ID` header. An ID is accepted when it contains only letters, digits, dots, underscores, or hyphens and has a maximum length of 64 characters. If the header is absent or invalid, the application generates a new UUID. Restricting characters also prevents newlines and control characters from entering logs.

```java
package com.example.observability;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class CorrelationIdFilter extends OncePerRequestFilter {

    public static final String HEADER_NAME = "X-Correlation-ID";
    public static final String MDC_KEY = "correlationId";

    private static final Pattern VALID_ID =
            Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,63}");

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {

        String correlationId = resolve(request.getHeader(HEADER_NAME));
        MDC.put(MDC_KEY, correlationId);
        response.setHeader(HEADER_NAME, correlationId);

        try {
            filterChain.doFilter(request, response);
        } finally {
            // The servlet container reuses threads for subsequent requests.
            // Always remove the value to prevent the next request's logs from picking up the wrong ID.
            MDC.remove(MDC_KEY);
        }
    }

    private String resolve(String candidate) {
        if (candidate != null && VALID_ID.matcher(candidate).matches()) {
            return candidate;
        }
        return UUID.randomUUID().toString();
    }
}
```

The filter performs four steps in order:

1. Reads `X-Correlation-ID` from the request.
2. Validates the format and generates a UUID if needed.
3. Puts the ID into MDC and returns the ID in the response header.
4. Executes the rest of the filter chain and removes the MDC entry whether the request succeeds or throws an exception.

`OncePerRequestFilter` prevents the filter from running repeatedly by accident within a standard dispatch. For async dispatches or processing flows that continue on another thread, design explicit context propagation as shown in section 7; the original thread's MDC does not automatically follow the work.

### 3.2. Why Must MDC Be Cleaned Up in finally?

Servlet containers typically use a thread pool. A thread may handle request A and then be reused for request B. MDC relies on thread-local storage; if A's ID is not removed, B's logs can carry the wrong correlation ID. This is a context leak bug and can lead to misdirected investigations or information disclosure across requests.

Placing `MDC.remove` inside `finally` guarantees cleanup even when a controller or service throws an exception. Never clean up only on the success branch, and do not leave MDC populated by setting a default value for the entire thread.

## 4. Configuring the Log Pattern

Once the filter writes the ID to MDC, configure Logback to print the `correlationId` value on every log line. Example in `application.yml`:

```yaml
logging:
  pattern:
    console: "%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level [corr=%X{correlationId:-}] [trace=%X{traceId:-} span=%X{spanId:-}] %logger{36} - %msg%n"
```

The `%X{...}` expressions read values from MDC. If tracing is not enabled in the application, `traceId` and `spanId` may be empty; the correlation ID still works independently. If Micrometer Tracing is configured, the trace keys are typically populated into MDC by the bridge according to the logging configuration of the version in use.

Example logs after calling an endpoint:

```text
2026-11-22T14:30:00.123+07:00 INFO  [corr=order-req-42] [trace=4bf92f3577b34da6a3ce929d0e0e4736 span=00f067aa0ba902b7] OrderController - Creating order
2026-11-22T14:30:00.145+07:00 INFO  [corr=order-req-42] [trace=4bf92f3577b34da6a3ce929d0e0e4736 span=00f067aa0ba902b7] OrderService - Reserving inventory
```

If using JSON logging, emit `correlationId` as a separate field instead of only concatenating it into the message. Structured fields allow the logging system to query accurately and avoid string parsing.

If the client is browser JavaScript and needs to read the response header, configure CORS to expose `X-Correlation-ID` to allowed origins. Otherwise, the browser may receive the response without allowing JavaScript to access this header.

## 5. Propagating the Correlation ID Across HTTP Calls

The filter only sets MDC inside the service receiving the request. When that service calls another service, it must forward the correlation ID on the outbound request. With Spring Boot and Spring Framework supporting `RestClient`, you can add a `ClientHttpRequestInterceptor` to the Spring Boot-injected builder.

`RestClient` was introduced in Spring Framework 6.1 (supported in Spring Boot 3.2 and later). For older versions, use `RestTemplate` and the corresponding interceptor.

```java
package com.example.observability;

import org.slf4j.MDC;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
public class HttpClientConfiguration {

    @Bean
    RestClient inventoryRestClient(RestClient.Builder builder) {
        return builder
                .baseUrl("http://localhost:8081")
                .requestInterceptor((request, body, execution) -> {
                    String correlationId = MDC.get(CorrelationIdFilter.MDC_KEY);
                    if (correlationId != null) {
                        request.getHeaders().set(
                                CorrelationIdFilter.HEADER_NAME, correlationId);
                    }
                    return execution.execute(request, body);
                })
                .build();
    }
}
```

Using the Spring Boot-configured builder preserves the customizers and instrumentation registered by the framework. Avoid arbitrarily creating clients with `RestClient.create()` if you need to retain the application's automatic observability configuration. The interceptor above only propagates the custom correlation ID; trace context such as `traceparent` continues to be handled by Micrometer Tracing/HTTP instrumentation.

At the target service, `CorrelationIdFilter` reads the header again and puts the same ID into MDC. Thus, logs in both the calling service and receiving service share the same correlation ID. In a real environment, `baseUrl` should be externalized via configuration and service discovery.

When calling the configured client, the application uses it just like a normal `RestClient`:

```java
InventoryResponse reserve(ReservationRequest request) {
    return inventoryRestClient.post()
            .uri("/inventory/reservations")
            .body(request)
            .retrieve()
            .body(InventoryResponse.class);
}
```

If using `RestTemplate`, a similar `ClientHttpRequestInterceptor` can be applied. With `WebClient` or Spring WebFlux, do not rely directly on MDC/ThreadLocal because a reactive pipeline can switch threads; see section 7.

## 6. Propagating the Correlation ID Across a Message Broker

For asynchronous workflows, the producer must write the correlation ID into a message header. The consumer reads the header, puts the ID into MDC within its processing scope, and removes it upon completion.

Example at the Spring Messaging level:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.messaging.Message;

public class BillingConsumer {

    private static final Logger log = LoggerFactory.getLogger(BillingConsumer.class);
    private final BillingService billingService;

    public BillingConsumer(BillingService billingService) {
        this.billingService = billingService;
    }

    public void handle(Message<OrderCreated> message) {
        Object value = message.getHeaders().get(CorrelationIdFilter.HEADER_NAME);
        String correlationId = value instanceof String id ? id : null;

        if (correlationId == null || !correlationId.matches(
                "[A-Za-z0-9][A-Za-z0-9._-]{0,63}")) {
            correlationId = java.util.UUID.randomUUID().toString();
        }

        MDC.put(CorrelationIdFilter.MDC_KEY, correlationId);
        try {
            log.info("Processing order-created event");
            billingService.process(message.getPayload());
        } finally {
            MDC.remove(CorrelationIdFilter.MDC_KEY);
        }
    }
}
```

This is an illustrative example for a consumer using Spring Messaging; header-reading APIs may differ between Spring Kafka, AMQP, or specific broker clients. On the producer side, set the same header on the message before publishing. Both sides must agree on the header name and validation rules.

Example creating a message on the producer:

```java
import org.slf4j.MDC;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

String correlationId = MDC.get(CorrelationIdFilter.MDC_KEY);
Message<OrderCreated> message = MessageBuilder.withPayload(event)
        .setHeader(CorrelationIdFilter.HEADER_NAME, correlationId)
        .build();
messagePublisher.publish(message);
```

In production code, only add the header when `correlationId` is non-`null`, or ensure the producer always runs inside an initialized context. `OrderCreated` and `messagePublisher` represent the application's event type and broker adapter.

A correlation ID makes it possible to group producer and consumer logs even when they run at different times. If a message is retried, redelivered, or moved to a dead-letter queue, keeping the original ID helps trace back to the origin. You can add a separate `deliveryAttempt` or message ID to distinguish each delivery attempt; do not change the correlation ID on each retry.

For distributed tracing over messaging, trace context needs to be injected/extracted using its own propagator. Correlation ID does not replace standard tracing headers.

## 7. Context in Asynchronous Tasks

MDC does not automatically propagate from the calling thread to worker threads. When using `@Async`, `ExecutorService`, or a thread pool, you must copy the context into the task and restore thread state after execution.

### 7.1. Using TaskDecorator for a Spring Task Executor

`TaskDecorator` lets you wrap a `Runnable` before the executor runs it. Example:

This decorator propagates MDC values such as `correlationId`. It does not replace Micrometer Tracing's span context propagation; for distributed tracing, enable the corresponding context propagation mechanism of your stack.

```java
import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

import java.util.Map;

public class MdcTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable task) {
        Map<String, String> callerContext = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> workerPreviousContext = MDC.getCopyOfContextMap();
            try {
                if (callerContext == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(callerContext);
                }
                task.run();
            } finally {
                if (workerPreviousContext == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(workerPreviousContext);
                }
            }
        };
    }
}
```

Attach the decorator to the executor actually used by the application:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncConfiguration {

    @Bean("applicationTaskExecutor")
    ThreadPoolTaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("application-");
        executor.setTaskDecorator(new MdcTaskDecorator());
        return executor;
    }
}
```

`MdcTaskDecorator` in the previous example is the class that copies and restores MDC. The executor bean above has its lifecycle managed by Spring; there is no need to call `initialize()` manually. Explicitly specify the executor when using `@Async`:

```java
@Async("applicationTaskExecutor")
public void sendOrderNotification(String orderId) {
    log.info("Sending notification for order {}", orderId);
}
```

If the application uses multiple executors, attach the decorator to every relevant executor. Do not assume the configuration above automatically applies to thread pools created by other libraries. For long-lived tasks, only propagate necessary keys and do not copy sensitive data into the context.

### 7.2. Spring WebFlux and Reactor

In WebFlux, a single request can hop across multiple threads within the same reactive pipeline. Since MDC relies on ThreadLocal, setting MDC in a servlet filter is insufficient to guarantee correlation end-to-end. Use Reactor Context together with the Micrometer Context Propagation mechanism supported in your Spring Boot/Micrometer version; only bridge into MDC at the appropriate logging boundary. Do not call `MDC.put` in one operator and assume the value still exists in an operator running on another thread.

## 8. Testing the Correlation ID

Testing should verify ID generation, preservation of valid IDs, propagation to other services, and context cleanup.

### 8.1. Calling an Endpoint with a Client-Sent ID

Suppose the application has the endpoint `GET /api/orders`. Send a request:

```bash
curl -i -H "X-Correlation-ID: order-req-42" \
  http://localhost:8080/api/orders
```

Expected results:

- The response has the header `X-Correlation-ID: order-req-42`.
- Every log line emitted during the request has `corr=order-req-42`.
- If the service calls another service, the outbound request carries the same header.
- Logs in the receiving service also display `corr=order-req-42`.

### 8.2. Calling a Request Without an ID

```bash
curl -i http://localhost:8080/api/orders
```

The response must include a new UUID in `X-Correlation-ID`. Log lines for that request use the same UUID. Calling it again will yield a different ID.

### 8.3. Sending an Invalid ID

Try a value containing spaces, control characters, or exceeding the length limit. The filter must generate a new ID (or return an error according to the chosen API policy), and must not write the raw invalid value to logs. Do not echo unvalidated headers back to the client.

### 8.4. Testing with MockMvc

Example verifying that the ID is preserved and returned:

```java
mockMvc.perform(get("/api/orders")
        .header(CorrelationIdFilter.HEADER_NAME, "order-req-42"))
    .andExpect(status().isOk())
    .andExpect(header().string(
        CorrelationIdFilter.HEADER_NAME, "order-req-42"));
```

Add tests for missing headers and malformed headers. For tests running on the same thread, you can assert that `MDC.get(CorrelationIdFilter.MDC_KEY)` is `null` after the request finishes to catch context leaks. Outbound tests should verify whether the request sent by the client to a mock service carries the expected header.

## 9. Querying Logs by Correlation ID

When logs are emitted as plain text, you can search for the ID string using a log search tool or CLI commands. With JSON logging, querying by the exact field is more efficient.

Example logical query in a log backend:

```text
correlationId = "order-req-42"
```

A typical investigation workflow is:

1. Find all logs matching the correlation ID.
2. Sort by timestamp and group by `service.name`.
3. Locate the first log reporting an error or abnormal latency.
4. If a trace ID is present, open the corresponding trace to inspect spans and dependencies.
5. Cross-reference request ID, message ID, or business ID when identifying specific business steps.

Correlation IDs help locate logs; traces help understand relationships and timing between operations. Combining both types of data speeds up investigation.

## 10. Common Issues and Troubleshooting

| Symptom | Possible Causes | How to Check / Fix |
|---|---|---|
| Logs have no correlation ID | Filter not registered, wrong filter order, or log pattern missing `%X` | Check filter chain, MDC key, and Logback configuration |
| Each service has a different ID | Outbound client does not forward header or target service does not read header | Check interceptor and inbound filter |
| Next request's logs carry previous request's ID | MDC not cleared in `finally` | Clear MDC on all exit paths and test thread reuse |
| Controller has ID but `@Async` does not | MDC does not propagate across thread pools automatically | Attach `TaskDecorator` to the executor in use |
| WebFlux intermittently has/lacks ID | ThreadLocal/MDC does not fit reactive context | Use Reactor Context and Micrometer Context Propagation |
| Trace ID exists but correlation ID is missing | Dedicated filter not installed or ID not added to pattern | Decide if a separate ID is needed; if so, add filter and propagation |
| Correlation ID exists but trace cannot be found | Tracing not enabled, sampling dropped trace, or trace propagation failed | Check trace exporter, sampling, and `traceparent` |
| Logs contain very long ID or strange characters | Inbound header not validated | Enforce length limits, character allowlist, and regenerate when invalid |
| Log search returns too many results | Client reuses a single ID across unrelated requests | Enforce per-request scope uniqueness and gateway ID generation rules |

## 11. Security and Operational Principles

Correlation IDs are often sent via client-controlled headers, so they must not be treated as trusted data. Validate length, characters, and format; restrict IDs to prevent log injection or log flooding. If the system requires UUID format, validate strictly against UUID format. If you must preserve partner-supplied IDs, apply an appropriate allowlist rule and optionally record a separate internal ID when an external ID is invalid.

Do not put the correlation ID into metric tags. Each request typically has a distinct ID; using it as a tag creates cardinality roughly equal to the number of requests and sharply increases metrics cost. Correlation IDs belong in logs and may appear in trace attributes when justified, but privacy and retention must be considered.

Do not use correlation IDs for authentication, authorization, or proving a request was processed. The ID is purely a lookup key. Access control must rely on authentication/authorization mechanisms; duplicate-submission protection must use an idempotency key or appropriate business mechanism.

In a multi-service system, standardize the header name, ID generation rules, format limits, and forwarding responsibilities. The gateway should serve as the inbound normalization point; internal services must preserve valid IDs throughout the same journey. If a request initiates a workflow lasting hours or days, consider using a dedicated workflow ID/business correlation key instead of keeping a single request ID for the entire business lifecycle.

## 12. Practice Completion Checklist

- [ ] Requests with a valid `X-Correlation-ID` keep the ID intact.
- [ ] Requests missing an ID or carrying an invalid ID get a newly generated ID per policy.
- [ ] Responses return the correlation ID to help clients with lookup.
- [ ] MDC is populated before request-handling code writes logs.
- [ ] Log pattern displays the correlation ID on all relevant lines.
- [ ] MDC is always cleared in `finally` after the request.
- [ ] HTTP clients propagate the ID to downstream services.
- [ ] Message producers/consumers preserve the ID across message headers if messaging is used.
- [ ] Asynchronous executors propagate and restore MDC properly.
- [ ] WebFlux uses Reactor Context/Micrometer Context Propagation instead of assuming ThreadLocal.
- [ ] Trace ID/span ID remain managed by tracing instrumentation.
- [ ] Correlation ID is never added to metric tags or used for security purposes.

Once the steps above are working, a single correlation ID can guide operators from gateway logs to downstream service logs and related asynchronous tasks. When distributed tracing is enabled, trace ID and span ID add timing structure and relationships between operations; the correlation ID continues serving as a stable lookup key following system conventions.
