# Logging Request Metadata

## Objectives

After this lesson, you will be able to:

- Explain the role of an interceptor in the lifecycle of a GraphQL request.
- Use WebGraphQlInterceptor to log metadata before and after GraphQL execution completes.
- Retrieve the request ID, operation name, and appropriate transport information.
- Measure processing duration using System.nanoTime().
- Distinguish GraphQL errors in the response from exceptions that terminate the pipeline abnormally.
- Pass the request ID into GraphQLContext so resolvers can log with the same correlation ID.
- Design structured logging with allowlists and redaction.
- Avoid logging query documents, variables, authorization headers, and sensitive data.
- Understand the limitations of interceptors and the relationship between logging, metrics, and tracing.
- Test logged metadata over HTTP or WebFlux transports.

## 1. Why Log Metadata for GraphQL?

A GraphQL endpoint typically receives multiple operation types on a single URL, such as Query, Mutation, and Subscription. Looking only at HTTP server access logs tells you which endpoint received a request and how long it took, but makes it hard to tell which operation was sent and how many errors GraphQL execution returned.

Logging metadata helps answer operational questions:

- Which operations are called most frequently?
- Which requests take a long time?
- Did a GraphQL response return field errors?
- Which request ID should be used to correlate with resolver or service logs?
- Did a failure occur during GraphQL execution or in the request-processing pipeline?

For example, two requests both call POST /graphql, yet one runs the GetBook operation while the other runs SearchBooks. Recording the operation name along with the request ID and duration enables clearer analysis without logging the full query content.

Metadata suitable for logging typically includes:

- Request ID provided by the server or transport.
- Operation name.
- Processing duration.
- Number of GraphQL errors.
- Outcome: completed, pipeline error, or cancelled.
- Selected allowlisted headers if genuinely needed.

Do not log the entire request body, variables, query document, or all HTTP headers by default. Those parts can contain tokens, personal information, business data, and sensitive values.

## 2. Where Does WebGraphQlInterceptor Sit?

Spring for GraphQL provides WebGraphQlInterceptor to intervene in requests/responses at the boundary between web transport and GraphQL.

The interceptor receives WebGraphQlRequest, then calls Chain to continue processing the request. The result is a WebGraphQlResponse publisher:

~~~java
public interface WebGraphQlInterceptor {

    Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain);
}
~~~

The flow can be visualized as:

~~~mermaid
flowchart TD
    A["HTTP / WebSocket transport"] --> B["WebGraphQlRequest"]
    B --> C["WebGraphQlInterceptor"]
    C --> D["chain.next(request)"]
    D --> E["GraphQL execution"]
    E --> F["WebGraphQlResponse"]
    F --> G["Interceptor observes response"]
    G --> H["Transport writes response"]
~~~

An interceptor is suited for recording shared metadata for a GraphQL request. It can observe the request before forwarding and the response after execution completes.

An interceptor does not replace HTTP access logs. A request that fails during HTTP parsing, authentication filtering, or routing before being converted into a WebGraphQlRequest may never reach the interceptor. Therefore, web server access logs and the GraphQL interceptor complement each other.

## 3. Reading Metadata from WebGraphQlRequest

WebGraphQlRequest provides information about the GraphQL request and transport. Useful values often include:

- getId(): request identifier.
- getOperationName(): operation name sent by the client, which may be absent.
- getUri(): request URI.
- getHeaders(): HTTP headers.
- getDocument() and getVariables(): operation content and variables.

For standard logging, only a small set of metadata is needed:

~~~java
String requestId = request.getId();

String operationName = request.getOperationName();
String operation = operationName != null
        ? operationName
        : "anonymous";
~~~

The operation name may not be specified by the client. In that case, log a fallback value such as anonymous.

Operation name is also client-supplied metadata. In production, restrict its length and strip control characters such as carriage return or newline before logging to avoid log injection. Parameterized logging prevents the string from being interpreted as a format string, but does not automatically strip control characters.

Do not log getDocument() or getVariables() directly in production logs. Query documents can contain inline literals; variables often contain emails, phone numbers, personal data, or business information. When operation analysis is needed, prefer operation name, persisted query ID, or a separately generated and controlled fingerprint.

## 4. Writing an Interceptor That Logs Requests and Responses

The example below logs request ID, operation name, processing duration, and GraphQL error count:

~~~java
import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
class GraphQlRequestLoggingInterceptor implements WebGraphQlInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(GraphQlRequestLoggingInterceptor.class);

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        long startedAt = System.nanoTime();
        String requestId = request.getId();

        String operationName = request.getOperationName();
        String operation = operationName != null
                ? operationName
                : "anonymous";

        log.info(
                "GraphQL request started requestId={} operation={}",
                requestId,
                operation
        );

        return chain.next(request)
                .doOnNext(response -> {
                    long durationMs = TimeUnit.NANOSECONDS.toMillis(
                            System.nanoTime() - startedAt
                    );

                    int errorCount = response.getErrors().size();

                    if (errorCount == 0) {
                        log.info(
                                "GraphQL request completed requestId={} operation={} durationMs={} errorCount={}",
                                requestId,
                                operation,
                                durationMs,
                                errorCount
                        );
                    }
                    else {
                        log.warn(
                                "GraphQL request completed with errors requestId={} operation={} durationMs={} errorCount={}",
                                requestId,
                                operation,
                                durationMs,
                                errorCount
                        );
                    }
                })
                .doOnError(exception -> {
                    long durationMs = TimeUnit.NANOSECONDS.toMillis(
                            System.nanoTime() - startedAt
                    );

                    log.warn(
                            "GraphQL request pipeline failed requestId={} operation={} durationMs={} exceptionType={}",
                            requestId,
                            operation,
                            durationMs,
                            exception.getClass().getSimpleName()
                    );
                })
                .doOnCancel(() ->
                        log.info(
                                "GraphQL request cancelled requestId={} operation={}",
                                requestId,
                                operation
                        )
                );
    }
}
~~~

Key points to note:

- Start time is captured using System.nanoTime(), suitable for measuring elapsed time.
- chain.next(request) continues the interceptor chain and GraphQL execution.
- doOnNext observes the response when the publisher emits a result.
- response.getErrors().size() counts GraphQL errors present in the response.
- doOnError observes exceptions causing the publisher to terminate with an error.
- doOnCancel records when a subscriber cancels waiting for the response.

The example avoids logging the exception message because messages can contain input data or internal details. When stack traces are needed for investigation, apply appropriate logging and redaction policies, and restrict access to logs.

## 5. GraphQL Errors Differ from Pipeline Exceptions

This is an important distinction when logging GraphQL.

A GraphQL operation can succeed at the pipeline level while the response still contains errors. For example:

- A resolver throws an exception and the exception is mapped to a GraphQL error.
- Access to a field is denied.
- A nullable field fails to load data.
- Part of the selection set fails while other fields still return data.

In these cases, GraphQL typically returns a WebGraphQlResponse containing an errors list. The publisher still completes normally, so doOnNext runs and doOnError does not.

Conversely, doOnError reflects an exception that causes the processing chain to terminate abnormally, such as an infrastructure failure or an exception in the pipeline before a normal response can be built.

| Case | Signal in Interceptor | How to Log |
| --- | --- | --- |
| Response has no GraphQL errors | doOnNext, errorCount = 0 | INFO |
| Response has one or more GraphQL errors | doOnNext, errorCount > 0 | WARN or level matching policy |
| Pipeline emits an exception | doOnError | ERROR/WARN depending on error type |
| Request is cancelled | doOnCancel | INFO or DEBUG |

Do not treat every response with errors as an HTTP transport failure. GraphQL can return partial data alongside errors. Logging should clearly show that the response contained GraphQL errors while the operation still executed and produced a response.

Also do not automatically log full error messages. Error messages can contain IDs, inputs, or internal information. You can log error counts, error classifications, or normalized error codes permitted for logging.

## 6. Measuring Duration Properly

Use System.nanoTime() to measure elapsed time:

~~~java
long startedAt = System.nanoTime();

// Execute work to measure

long elapsedNanos = System.nanoTime() - startedAt;
long durationMs = TimeUnit.NANOSECONDS.toMillis(elapsedNanos);
~~~

Do not use System.currentTimeMillis() to compute elapsed time because the system clock can be adjusted. currentTimeMillis is suited for wall-clock timestamps; nanoTime is suited for measuring durations.

Inside an interceptor, the duration measured around chain.next(request) reflects the time from when the interceptor starts until the response is emitted. This is the total time of the pipeline inside the interceptor, not the isolated time of a single resolver or SQL query.

If deeper breakdown is needed, measure additionally at the service, repository, or via GraphQL instrumentation/Observation. Do not infer which resolver is slow solely from the total request duration.

## 7. Passing Request ID into GraphQLContext

A request ID is more useful when resolvers and services can use the same identifier in their logs.

WebGraphQlRequest allows customizing ExecutionInput before execution. You can put the request ID into GraphQLContext:

~~~java
String requestId = request.getId();

request.configureExecutionInput((input, builder) ->
        builder.graphQLContext(context ->
                context.put("requestId", requestId)
        ).build()
);
~~~

Then resolvers can receive the value using @ContextValue:

~~~java
import org.springframework.graphql.data.method.annotation.ContextValue;

@QueryMapping
public Book book(
        @Argument("id") UUID id,
        @ContextValue("requestId") String requestId) {

    log.debug(
            "Resolving book requestId={} bookId={}",
            requestId,
            id
    );

    return bookService.findById(id);
}
~~~

This way, logs in the interceptor and logs in the resolver can be correlated using the same request ID.

Pass only the necessary metadata. Do not put the entire WebGraphQlRequest, headers, or variables into GraphQLContext. GraphQLContext is execution-scoped; data placed here can be accessed by multiple resolvers within the same operation.

## 8. Client Correlation ID vs. Internal Request ID

Some systems send a correlation ID or trace ID header to link requests across gateways and multiple services.

Example header:

~~~http
X-Correlation-ID: 7f4b5c21-1f5a-4f2a-9f20-4d0e1c6f5a31
~~~

An allowlisted header can be read:

~~~java
String externalCorrelationId =
        request.getHeaders().getFirst("X-Correlation-ID");
~~~

However, client-sent values are not inherently trustworthy. When using them in logs:

- Validate format.
- Limit length.
- Strip control characters and newlines.
- Do not use them as an authentication mechanism.
- Fall back to a server-provided request ID.
- Do not allow arbitrary values to forge log entries or cause log injection.

A safe practice is using the internal request ID as the primary identifier, while storing the external correlation ID as a separate metadata field after validation.

If the system already uses distributed tracing, prefer the trace ID managed by the tracing infrastructure. Avoid inventing multiple redundant IDs without a clear convention.

## 9. Selecting Metadata Permitted for Logging

Logging should use an allowlist instead of capturing all headers and trying to strip sensitive ones.

Examples of fields that can be useful if permitted by system policy:

| Metadata | Notes |
| --- | --- |
| Request ID | Prefer internal, unique identifier |
| Operation name | May be anonymous if client did not name it |
| Duration | Record explicit unit, e.g., milliseconds |
| GraphQL error count | No need to log full messages |
| HTTP method | Useful when breaking down by transport |
| Content-Type | Log only when diagnosing transport issues |
| User-Agent | Can contain long strings or untrusted data |
| Correlation ID | Validate and limit length before logging |

Avoid recording the following values in standard logs:

- Authorization and Proxy-Authorization.
- Cookie and Set-Cookie.
- Access tokens, refresh tokens, or API keys.
- Full GraphQL variables.
- Query documents containing inline literals.
- Passwords, OTPs, payment details, and personal data.
- Full response data.

If debugging a specific request is necessary, use a time-limited, access-controlled logging mechanism with redaction per security policy. Do not enable broad logging of sensitive payloads in production.

## 10. Structured Logging

Structured logging allows log systems to filter and aggregate by fields rather than parsing free-form message strings.

Example of a structured log event:

~~~json
{
    "event": "graphql.request.completed",
    "requestId": "req-7f2a",
    "operation": "GetBook",
    "durationMs": 34,
    "errorCount": 0
}
~~~

Fields should have consistent names across services:

- event: event type.
- requestId: request identifier.
- operation: GraphQL operation name.
- durationMs: execution duration.
- errorCount: number of GraphQL errors.
- outcome: completed, completed_with_errors, pipeline_failed, or cancelled.

Do not cram all metadata into a single string. When using a JSON encoder or structured logging framework, pass individual fields so the log system can index and query them.

Avoid placing high-cardinality IDs into metric labels. Request IDs belong in logs and traces, but are generally unsuitable as metric tags because they can create an enormous number of time series.

## 11. Logging Errors Without Leaking Data

A GraphQL error may contain a message intended for the client. That message is not necessarily appropriate to write verbatim into logs.

For example, do not log by default:

~~~java
response.getErrors().forEach(error ->
        log.warn("GraphQL error: {}", error.getMessage())
);
~~~

Instead, you can log the error count and normalized error categories:

~~~java
int errorCount = response.getErrors().size();

log.warn(
        "GraphQL response contains errors requestId={} operation={} errorCount={}",
        requestId,
        operation,
        errorCount
);
~~~

If more information is needed, define stable error codes in extensions per application convention and log only permitted codes. Avoid logging stack traces for routine validation errors; reserve stack traces for system errors requiring investigation.

Never use a client-supplied message as a format string. Always use the logging framework's placeholders and pass values as arguments.

## 12. Logging in Reactive Pipelines and MDC

WebGraphQlInterceptor returns a Mono, so callbacks may run on a different thread from the initial one when the pipeline switches schedulers.

SLF4J's MDC is typically ThreadLocal-based. If you manually set MDC at the start of the interceptor and clear it in a synchronous finally block, the value may no longer be present when callbacks run on another thread. Conversely, MDC entries may linger on a reused thread if not cleaned up properly.

There are two approaches:

- Pass the request ID directly as a structured logging field in each log statement.
- If automatic MDC or tracing context is required, configure context propagation compatible with Reactor and your application's observability stack.

Example of passing directly:

~~~java
log.info(
        "GraphQL resolver completed requestId={} field={}",
        requestId,
        "Book.author"
);
~~~

Do not rely on ad-hoc ThreadLocal to carry principal, tenant, or request ID across reactive boundaries. Use GraphQLContext, Reactor Context, or an explicitly configured context propagation mechanism.

## 13. Registering the Interceptor

You can register WebGraphQlInterceptor through WebGraphQlConfigurer:

~~~java
import java.util.List;

import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.server.WebGraphQlConfigurer;
import org.springframework.graphql.server.WebGraphQlInterceptor;

@Configuration
class GraphQlWebConfiguration implements WebGraphQlConfigurer {

    private final GraphQlRequestLoggingInterceptor loggingInterceptor;

    GraphQlWebConfiguration(
            GraphQlRequestLoggingInterceptor loggingInterceptor) {
        this.loggingInterceptor = loggingInterceptor;
    }

    @Override
    public void configureInterceptors(
            List<WebGraphQlInterceptor> interceptors) {

        interceptors.add(loggingInterceptor);
    }
}
~~~

This registration enables the interceptor to participate in the web GraphQL processing chain. In a Spring Boot application, you can organize interceptors as Spring beans and wire them via the application's web GraphQL configuration.

When multiple interceptors are present, understand that each interceptor can modify requests, add context, or observe responses. A logging interceptor should stick to observing and logging; avoid altering variables or response data beyond its purpose.

## 14. A Logging Interceptor Does Not Replace Metrics and Tracing

Logging, metrics, and tracing answer different questions.

| Tool | Primary Question | Example |
| --- | --- | --- |
| Logging | What happened to a specific request? | Request ID, operation name, error count |
| Metrics | What are the load and performance trends? | Request rate, latency histogram, error rate |
| Tracing | Which services/spans did the request traverse? | Trace ID, GraphQL span, database span |

Do not create separate metrics per request ID or arbitrary operation name due to potential cardinality explosion. For metrics, prefer bounded label sets such as operation category, transport, and outcome.

If Spring Boot Actuator and Micrometer are already configured, leverage existing observation and tracing support. A logging interceptor can add business metadata or request-specific fields, but should not build a parallel timing system inconsistent with metrics.

## 15. Testing Logging Metadata

To verify that the interceptor is actually invoked, tests must pass through the web GraphQL transport. A test calling ExecutionGraphQlService directly may bypass WebGraphQlInterceptor.

You can use HttpGraphQlTester or WebGraphQlTester depending on your application's transport, combined with a test appender to capture logs.

Example operation used in testing:

~~~graphql
query GetBook {
    book(id: "book-42") {
        id
        title
    }
}
~~~

Things to verify:

1. The request is sent through the HTTP or WebFlux transport.
2. The start log includes request ID and operation name.
3. The completion log includes duration and error count.
4. Responses containing GraphQL errors are still recorded via the response branch.
5. Pipeline exceptions are recorded via the error branch.
6. Request cancellation is handled if supported by the test harness.
7. Variables, Authorization, and Cookies do not appear in logs.
8. The request ID in resolver logs matches the request ID in the interceptor if propagated into GraphQLContext.

Include a test for an unnamed operation to verify the anonymous fallback. Also verify that overly long correlation ID headers or headers with invalid characters are ignored or normalized according to application policy.

## 16. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| No logs from interceptor | Request did not reach WebGraphQlInterceptor or interceptor is not registered | Check transport and WebGraphQlConfigurer |
| Only request is logged, no duration | Response publisher is not observed | Use doOnNext and measure elapsed time |
| GraphQL response has errors but doOnError does not run | GraphQL errors reside in a normal response | Inspect response.getErrors() |
| All errors logged as transport failures | Conflating GraphQL errors and pipeline exceptions | Separate doOnNext from doOnError |
| Request ID differs between interceptor and resolver | ID not passed into GraphQLContext or using a different ID | Use the same key and request ID source |
| MDC is lost when switching threads | MDC relies on ThreadLocal in a reactive pipeline | Pass fields directly or configure context propagation |
| Logs contain tokens or personal data | Logging full headers, document, or variables | Use allowlists, redaction, and test logs |
| Logs forged via headers | Trusting client-sent correlation ID without validation | Validate format, length, and control characters |
| Excessive logging increases cost | Logging every field and payload at INFO | Select essential events, use DEBUG selectively |
| Metrics cardinality explodes | Using request ID as a metric tag | Put request ID in logs/traces, keep metric labels bounded |

## 17. Workflow for Implementing Metadata Logging

When adding logging for a GraphQL endpoint, follow this sequence:

1. **Choose the observation point.** Use WebGraphQlInterceptor for metadata at the web GraphQL boundary.
2. **Select allowed log fields.** Start with request ID, operation name, duration, and error count.
3. **Log request start.** Capture metadata before calling chain.next(request).
4. **Measure duration.** Use System.nanoTime() to calculate elapsed duration.
5. **Observe responses.** Record error count from WebGraphQlResponse.getErrors().
6. **Separate pipeline errors.** Use doOnError for exceptions that terminate the publisher abnormally.
7. **Propagate correlation.** Put request ID into GraphQLContext if resolvers need to log the same ID.
8. **Protect data.** Do not log variables, document, Authorization, or Cookie.
9. **Check reactive context.** Do not rely on MDC/ThreadLocal without configured propagation.
10. **Test via transport.** Use HttpGraphQlTester or WebGraphQlTester and verify log contents as well.

## 18. Summary

WebGraphQlInterceptor is an appropriate place to log metadata for a GraphQL request before and after it passes through GraphQL execution. Useful fields typically include request ID, operation name, duration, error count, and outcome. Use System.nanoTime() to measure time, observe responses with doOnNext, and separate pipeline exceptions with doOnError.

GraphQL errors normally reside inside WebGraphQlResponse and do not necessarily cause the publisher to emit an error. Therefore, distinguish responses containing errors from pipeline exceptions. You can pass the request ID into GraphQLContext so resolvers log consistently using @ContextValue. Use structured logging, allowlists, and redaction; never log query documents, variables, authorization headers, or cookies in standard logs. Combining interceptors with access logs, metrics, and tracing provides system observability while keeping request data safe.
