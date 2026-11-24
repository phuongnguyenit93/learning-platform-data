# Correlating Logs with traceId, spanId, and MDC

When an operation crosses multiple services, a log line saying "processing failed" only tells you what just happened in one place. To find the full path of that operation, you need a shared identifier. To know which processing step along that path a log line belongs to, you also need an identifier for the step. In a Spring Boot application with Micrometer Tracing, `traceId` and `spanId` provide these two links; MDC lets the logging system include them on every line without passing two extra parameters through every method.

This lesson uses Spring Boot 3.3.x, Java 21, SLF4J 2, and Logback. The focus is understanding context at log time, reading the right IDs, and preserving context across thread switches. The standalone MDC experiment also works on Java 17 or later.

## 1. Understanding the Components Before Configuring

| Component | Meaning | Question It Helps Answer |
| --- | --- | --- |
| Trace | Path of a tracked operation, potentially across multiple services | Which steps belong to the same execution? |
| `traceId` | Identifier of a trace | Which logs do I need to search to reconstruct that path? |
| Span | A measured unit of work within a trace, possibly with parent-child relationships | Which specific step is executing? |
| `spanId` | Identifier of a span | Which span does this log line belong to? |
| Trace context | Information the tracing library uses to identify the current trace/span and pass relationships between steps | Where will the next unit of work attach? |
| MDC (Mapped Diagnostic Context) | A set of key-value pairs for logging; with Logback, data is bound to the current thread | When logging here, what diagnostic data is available to print alongside it? |

Spans in the same trace share a `traceId`; each span has its own `spanId` within that trace. See [OpenTelemetry trace and span concepts](https://opentelemetry.io/docs/concepts/signals/traces/).

Common pitfall: MDC is only a place from which the logging system reads data. Putting a string under key `traceId` does not create a real trace. Likewise, putting `spanId` does not start a measurement, record parent-child relationships, or send spans to a trace storage system.

A business identifier such as `orderId`, or an application-defined request ID such as `requestId`, also does not automatically become `traceId`. They can be logged additionally for searching along different axes.

### Reading an Example

Suppose the orders service receives a request, then calls the inventory service. These are illustrative logs; IDs are chosen for readability:

```text
service=orders    trace=0123456789abcdef0123456789abcdef span=1111111111111111 received
service=orders    trace=0123456789abcdef0123456789abcdef span=2222222222222222 checking-stock
service=inventory trace=0123456789abcdef0123456789abcdef span=3333333333333333 stock-found
service=orders    trace=0123456789abcdef0123456789abcdef span=1111111111111111 completed
```

All four lines share `traceId`, so they can be searched by one execution. Different `spanId` values show different steps. The last line returns to the initial span because the execution scope of the inventory-call step has ended. Do not infer parent-child relationships merely by looking at the numeric values of IDs; that relationship lives in span data.

## 2. Why Does the Logger Know the Current Trace?

A typical synchronous processing flow has these steps:

```text
Receive HTTP request
  → library extracts incoming context or starts a new trace
  → sets current span within an execution scope
  → tracing integration puts matching traceId/spanId into MDC
  → logger creates log event
  → Logback pattern reads MDC and prints the IDs
  → close scope: restores previous context
```

"Scope" is the execution interval during which a span is considered current. Starting a span and placing a span in scope are two related yet distinct operations. Having created a span does not mean every subsequent log belongs to that span.

Micrometer provides `Tracer.SpanInScope` to manage scope. Closing a child span's scope restores the parent context; when the entire request finishes, the library must clear or restore the corresponding context. Refer to [Micrometer span and scope management API](https://docs.micrometer.io/tracing/reference/api.html).

With Logback, MDC is not a shared map for the entire application. Two threads can use the same `traceId` key while holding different values. However, a thread in a thread pool gets reused for many sequential tasks. If code puts data into MDC without restoring it properly, later tasks can mistakenly pick up data from an earlier task. [Logback MDC documentation](https://logback.qos.ch/manual/mdc.html) explains thread-bound mechanics and why child threads do not automatically inherit a copy of a parent thread's MDC.

Three tasks must be distinguished:

- **Log correlation:** putting IDs into logs for searching.
- **Context propagation:** carrying context across network calls or thread switches so downstream steps continue the right trace.
- **Trace export:** sending span data to Zipkin or a trace collection system.

Succeeding at one does not prove the other two work.

## 3. Observing Directly in Spring Boot 3.3.x

### 3.1. Preparing a Practice Application

In a standalone Spring Boot 3.3.x project that already has Gradle Wrapper, Java 21, and Spring Boot dependency management, add the following dependencies. This is an addition to `build.gradle`, not a complete build file:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-brave'
    implementation 'io.zipkin.reporter2:zipkin-reporter-brave'
}
```

The example picks Brave as the tracing library and Zipkin as the span receiver. Use one appropriate bridge and let Spring Boot manage compatible versions. Starter Actuator alone does not supply all tracing libraries for this example. Do not add Spring Cloud Sleuth just to get IDs in a Boot 3 application.

Practice configuration in `src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: log-correlation-demo

management:
  tracing:
    sampling:
      probability: 1.0
  zipkin:
    tracing:
      endpoint: http://localhost:9411/api/v2/spans

logging:
  include-application-name: false
  pattern:
    correlation: "[${spring.application.name:},%X{traceId:-},%X{spanId:-}] "
```

Run Zipkin at the address above if you want to view the span tree. `probability: 1.0` serves observation in the lab; sampling choices for real systems depend on traffic and operational needs. You do not need to expose an extra Actuator endpoint for MDC to appear.

Spring Boot 3.3 integrates these IDs into the default log pattern when using Micrometer Tracing. `logging.pattern.correlation` customizes the displayed portion; the trailing space separates it from the logger portion that follows. Related dependencies and properties are described in [Spring Boot 3.3 tracing documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html).

### 3.2. Creating a Child Span and Following Before-During-After Logs

Use the complete application class below in the practice project, at `src/main/java/demo/LogCorrelationApplication.java`:

```java
package demo;

import java.util.Map;

import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class LogCorrelationApplication {
    private static final Logger log =
            LoggerFactory.getLogger(LogCorrelationApplication.class);

    private final Tracer tracer;

    public LogCorrelationApplication(Tracer tracer) {
        this.tracer = tracer;
    }

    public static void main(String[] args) {
        SpringApplication.run(LogCorrelationApplication.class, args);
    }

    @GetMapping("/demo/log-correlation")
    public Map<String, String> demonstrate() {
        log.info("received");

        Span child = tracer.nextSpan().name("prepare-result").start();
        try (Tracer.SpanInScope scope = tracer.withSpan(child)) {
            log.info("preparing");
        } catch (RuntimeException ex) {
            child.error(ex);
            throw ex;
        } finally {
            child.end();
        }

        log.info("completed");
        Span current = tracer.currentSpan();
        if (current == null) {
            return Map.of("traceId", "none", "spanId", "none");
        }
        return Map.of(
                "traceId", current.context().traceId(),
                "spanId", current.context().spanId());
    }
}
```

Start with `./gradlew bootRun` on Linux/macOS or `.\gradlew.bat bootRun` in PowerShell. From another terminal window, call:

```bash
curl http://localhost:8080/demo/log-correlation
```

On Windows, you can use `curl.exe` to invoke the curl binary directly.

When HTTP server tracing is active, the three application messages have this relationship:

```text
received   → trace T, span P
preparing  → trace T, span C
completed  → trace T, span P
```

This describes the relationship, not fixed stdout: IDs, timestamps, threads, and startup lines vary per run. The returned JSON contains the IDs of the current HTTP span at the end of the method. Returning IDs only serves observation in this example.

In the code:

1. HTTP instrumentation sets the parent span before entering the controller.
2. `nextSpan()` uses the current context to create a child span; `start()` starts that span.
3. `withSpan(child)` makes the child span current inside the `try` block.
4. Closing `SpanInScope` restores the parent span before the `completed` line.
5. `child.end()` finishes the span created by this code. Do not end the library-managed HTTP span.

Placing a log outside the child span's scope and expecting it to have the child span's `spanId` is a mistake about execution scope. You should also never call `MDC.put("traceId", ...)` or `MDC.put("spanId", ...)` manually to "fix" the example: doing so can make logs display IDs that differ from the real tracer.

### 3.3. Understanding Log Pattern Syntax

In Logback, `%X{traceId}` reads the `traceId` key from the log event's MDC. `%X{traceId:-}` supplies an empty fallback if the key is missing; `%X{traceId:-none}` uses `none` when missing.

Patterns only read existing values; they do not generate IDs. If an application uses a custom `logback-spring.xml` whose console/file pattern lacks the correlation portion or `%X{...}`, changing the property above may not affect that pattern. Inspect the appender that actually receives events. For example, a pattern element inside a custom Logback config might be:

```xml
<pattern>%d{HH:mm:ss.SSS} [%thread] %-5level trace=%X{traceId:-none} span=%X{spanId:-none} %logger{36} - %msg%n</pattern>
```

This is only the `pattern` element inside an encoder, not a complete Logback config file. When outputting JSON logs, configure an MDC-aware encoder to emit dedicated fields; a text console pattern does not automatically turn into JSON configuration.

## 4. Standalone MDC Experiment: Displayed Data Is Not a Real Trace

The following experiment intentionally populates fixed ID strings to isolate MDC mechanics. It does not use Micrometer, creates no real spans, and makes no HTTP calls. In an application with tracing, let the tracing integration manage these two keys as in section 3.

Prepare a practice directory containing `MdcDemo.java` and a `lib/` folder holding three compatible JARs: `slf4j-api`, `logback-classic`, `logback-core`. One set used for the experiment is SLF4J `2.0.13` and Logback Classic/Core `1.5.6`; this is a version set for reproducing the example, not a directive to pick the newest version. Place only one logging library set in `lib/`.

The program configures Logback right in code to omit timestamps and produce deterministic output:

```java
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.LoggerContext;
import ch.qos.logback.classic.encoder.PatternLayoutEncoder;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.ConsoleAppender;

public class MdcDemo {
    private static final Logger log = LoggerFactory.getLogger(MdcDemo.class);

    public static void main(String[] args) throws Exception {
        configureLogging();
        MDC.clear();
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            MDC.put("traceId", "0123456789abcdef0123456789abcdef");
            MDC.put("spanId", "1111111111111111");
            log.info("parent");

            String previousSpan = MDC.get("spanId");
            try {
                MDC.put("spanId", "2222222222222222");
                log.info("child");
            } finally {
                MDC.put("spanId", previousSpan);
            }
            log.info("parent-again");

            pool.submit(() -> log.info("worker-without-copy")).get();

            Map<String, String> captured = MDC.getCopyOfContextMap();
            pool.submit(() -> {
                Map<String, String> previous = MDC.getCopyOfContextMap();
                try {
                    restore(captured);
                    log.info("worker-with-copy");
                } finally {
                    restore(previous);
                }
            }).get();

            pool.submit(() -> log.info("worker-after-cleanup")).get();
        } finally {
            MDC.clear();
            pool.shutdown();
        }
        log.info("outside");
    }

    private static void restore(Map<String, String> values) {
        if (values == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(values);
        }
    }

    private static void configureLogging() {
        LoggerContext context = (LoggerContext) LoggerFactory.getILoggerFactory();
        context.reset();

        PatternLayoutEncoder encoder = new PatternLayoutEncoder();
        encoder.setContext(context);
        encoder.setPattern("%msg trace=%X{traceId:-none} span=%X{spanId:-none}%n");
        encoder.start();

        ConsoleAppender<ILoggingEvent> appender = new ConsoleAppender<>();
        appender.setContext(context);
        appender.setEncoder(encoder);
        appender.start();

        ch.qos.logback.classic.Logger root =
                context.getLogger(Logger.ROOT_LOGGER_NAME);
        root.setLevel(Level.INFO);
        root.addAppender(appender);
    }
}
```

Compile and run from the directory containing the file. On PowerShell/Windows:

```powershell
javac --release 17 -encoding UTF-8 -cp "lib/*" MdcDemo.java
java -cp ".;lib/*" MdcDemo
```

On Linux/macOS, the compile command is the same; the run command uses `:` to separate classpath entries:

```bash
java -cp ".:lib/*" MdcDemo
```

Program output:

```text
parent trace=0123456789abcdef0123456789abcdef span=1111111111111111
child trace=0123456789abcdef0123456789abcdef span=2222222222222222
parent-again trace=0123456789abcdef0123456789abcdef span=1111111111111111
worker-without-copy trace=none span=none
worker-with-copy trace=0123456789abcdef0123456789abcdef span=1111111111111111
worker-after-cleanup trace=none span=none
outside trace=none span=none
```

Note four points from the output:

- `child` only changed the `spanId` key in MDC; `parent-again` shows the previous value was restored.
- `worker-without-copy` lacks both keys even though the submitting thread had them.
- `worker-with-copy` sees the snapshot captured before task submission.
- `worker-after-cleanup` runs on the same executor thread yet does not retain the previous task's IDs.

The `.get()` calls make the experiment wait for each task to finish so output ordering stays deterministic. The MDC copying code here only verifies carrying logging data to another thread. It does not transfer tracer context, does not create span relationships, and does not guarantee HTTP calls inside that thread join the right trace.

`configureLogging()` resets logger configuration solely so the experiment has deterministic output. Do not copy this reset into a running Spring Boot application.

## 5. When Using @Async, Executors, or Reactor

### 5.1. Propagating Context Across Thread Switches

Switching to another thread is a boundary that must be handled. For instance, `CompletableFuture.runAsync(...)` without an executor argument uses the default thread pool; do not assume it receives the HTTP request's context.

In Spring Framework 6.1, `ContextPropagatingTaskDecorator` supports capturing and restoring context through accessors registered in Micrometer Context Propagation. You can attach it to an application-managed executor. This is a configuration class added to the Spring Boot project from section 3:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class TraceTaskConfiguration {
    @Bean("traceExecutor")
    public ThreadPoolTaskExecutor traceExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("trace-demo-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        return executor;
    }
}
```

Spring manages initialization and shutdown of this executor bean. Submit tasks to this `traceExecutor` bean while the source context is still active; the decorator captures context at submission time and restores it during execution. With Spring Boot-configured HTTP observations, this is how observation context is preserved across an executor. See [Spring 6.1 ContextPropagatingTaskDecorator API](https://docs.spring.io/spring-framework/docs/6.1.16/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html).

If using `@Async("traceExecutor")`, enable `@EnableAsync` and invoke through the Spring proxy, typically from another bean. A self-invocation like `this.sendAsync()` bypasses the default proxy, so it does not prove the code runs asynchronously or uses the configured executor.

The decorator does not automatically know about every arbitrary `ThreadLocal` variable and MDC key. Which context gets propagated depends on registered `ThreadLocalAccessor` instances. For custom business keys, configure an appropriate accessor or dedicated propagation mechanism. Do not infer that having `traceId` means every MDC key is copied as well.

Micrometer clearly describes capturing values, setting them in scope, and restoring previous values when the scope closes in [Context Propagation usage examples](https://docs.micrometer.io/context-propagation/reference/usage.html). Capturing context inside the target thread after the source context has already been lost will not recover the source information.

Beyond checking IDs, distinguish:

- **Continuing current context:** code on the target thread may still log the same `spanId` if it does not open another span.
- **Creating a separate measured step:** create a child span/observation within an appropriate scope; then `traceId` is preserved and `spanId` changes.

Renaming threads, using `@Async`, or using virtual threads does not automatically create a child span.

### 5.2. In Reactive Processing Flows

With Reactor, a processing chain can switch threads multiple times. Do not call `MDC.put(...)` while assembling a `Mono` and assume every downstream operator reads that data. Reactor context and execution time differ from keeping data on one thread.

In Spring Boot 3.3, you can enable automatic context propagation for Reactor:

```yaml
spring:
  reactor:
    context-propagation: auto
```

This configuration supports restoring integrated `ThreadLocal` values from the reactive context. It does not replace a tracing bridge, instrumentation, or registering accessors for custom data. Check logs right inside the executing operators, especially around `publishOn`, `subscribeOn`, and custom boundaries. Refer to [Spring Boot 3.3 context propagation section](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

## 6. Adding Business Data to MDC Without Breaking Traces

Suppose you need to attach an order ID to logs during a synchronous block. Use a dedicated key such as `orderId`, save the previous value, and restore it in `finally`. The snippet below is a method to place in a service class that already has a `log` field and imports `org.slf4j.MDC`:

```java
public void processOrder(String orderId) {
    String previousOrderId = MDC.get("orderId");
    try {
        MDC.put("orderId", orderId);
        log.info("processing-order");
    } finally {
        if (previousOrderId == null) {
            MDC.remove("orderId");
        } else {
            MDC.put("orderId", previousOrderId);
        }
    }
}
```

To see this key, the log pattern needs `%X{orderId:-}`, or the JSON encoder must output the corresponding field. A key in MDC also does not automatically become a span attribute.

You can use `MDC.putCloseable(...)` to automatically remove the key when leaving the `try` block. However, that closeable removes the key rather than restoring an overwritten previous value. For nested scopes using the same key, saving and restoring as above matches the requirement properly. See [SLF4J MDC API](https://www.slf4j.org/apidocs/org/slf4j/MDC.html).

Practical principles:

- Manage only keys owned by your code snippet; avoid `MDC.clear()` at the end of a service method because it erases `traceId`, `spanId`, and caller-layer data too.
- Do not overwrite the two tracing keys with `requestId`, a new UUID, or a business ID. When adding a custom request ID, use a separate key name.
- A local MDC key is not automatically propagated over the network. Extra data needing cross-service propagation can use a configured baggage mechanism; clearly define which fields are propagated and which are logged.
- Keep logged data small and diagnostics-focused; never put passwords or tokens into MDC.
- Never use `traceId` or `orderId` as metric tags whose cardinality grows per request. Looking up individual executions is the job of logs/traces.

## 7. Correlating Logs Across Services

Merely printing two fields with the same name is not enough to link traces across the network. The calling service must inject context into the outbound request, and the receiving service must extract it using a compatible format.

One common format is W3C Trace Context, using the `traceparent` header structured with version, trace ID, parent ID, and trace flags. MDC is local data for logging; it is not an HTTP header. Do not take `MDC.get("traceId")` and treat that string as an entire `traceparent`. Format details are in the [W3C Trace Context specification](https://www.w3.org/TR/trace-context/).

In Spring Boot, create HTTP clients through Boot-configured builders such as `RestClient.Builder`, `RestTemplateBuilder`, or `WebClient.Builder` to receive observation and context propagation integration. When constructing clients outside that configuration path, verify the corresponding instrumentation yourself.

You can verify along this path:

1. Find the request's `traceId` in service A.
2. Verify the A → B call uses a tracing-integrated client.
3. Verify B extracts the incoming context properly.
4. Compare `traceId` in A's and B's logs, then check the span tree in the tracing system.

Services in the same trace normally have different spans. Do not expect A's `spanId` to equal B's `spanId`. When clocks drift across machines, timestamp ordering of logs alone is also insufficient to prove causality; inspect the spans and their relationships.

## 8. Symptom-Based Diagnostics

| Symptom | What to Check | Appropriate Fix |
| --- | --- | --- |
| Startup logs lack IDs | Was there an active span yet? | Accept empty fields when no traced work is running; do not generate fake IDs just to fill blanks |
| Controller logs lack IDs | Bridge, tracing config, HTTP instrumentation, and actual appender pattern | Confirm current span via `tracer.currentSpan()`, then check MDC and display pattern |
| Tracer has a span yet console prints no IDs | Does the console/file pattern or JSON encoder read the right keys? | Fix the display config of the actual log writer |
| IDs disappear only after switching to an executor | Does the actual executor propagate context? | Attach context propagation and submit work through the right executor |
| New task carries the old task's IDs | Is data on the reused thread restored? | Clean up in `finally` and verify exception paths too |
| Logs in A and B have different `traceId` values | Did the network call inject and extract compatible context? | Check client, headers, intermediate proxies, and propagation configuration |
| Logs have IDs yet trace search finds nothing | Sampling decision, exporter, target endpoint, collector, retention window | Inspect the trace export flow separately; do not conclude MDC is broken solely from missing traces |
| One request changes `spanId` across lines | Are there child steps or nested scopes? | Compare against the span tree; this may be expected behavior |
| After child span block, logs still use child ID | Was the scope closed on the right thread? | Use automatic scope management and keep scope closing distinct from ending the span |

A trace not selected for recording/export can still carry context and IDs for log correlation. Conversely, changing log levels does not decide which spans get exported. To verify the entire path, inspect both logging configuration and tracing configuration plus the span receiver.

If an application puts logs into a queue itself and only reads MDC on the consumer thread, context may already have changed. Capture the relevant data when the log event is created or use an asynchronous logging mechanism that preserves event context; do not read the consumer thread's MDC to guess the producer thread's context.

## 9. Practice Exercises to Test Your Explanation Skills

### Exercise 1: Identifying Scope

Run the Spring Boot example twice, calling the endpoint once per independent request without passing external context. In each call, locate the three messages `received`, `preparing`, `completed`.

What you should be able to explain: the three lines in a single call share a trace; the line inside the child span has a different span ID; afterward it returns to the HTTP span. Two independent requests normally produce different traces. Do not treat one run's specific IDs as a fixed answer.

### Exercise 2: Exposing a Thread-Reuse Bug

In a copy of the `MdcDemo` experiment, remove `restore(previous)` from the `finally` block of the MDC-copying task. Keep the executor single-threaded.

Predict before running: `worker-after-cleanup` will still see the two copied IDs because the same thread was not cleaned up. Restore `finally` and confirm that line returns to `trace=none span=none`.

### Exercise 3: Separating Display Bugs from Context Bugs

In the practice Spring Boot project, keep tracing intact and replace the correlation pattern with a string containing no `%X`. Observe the logs, then inspect the JSON returned by the endpoint.

Key takeaway: not printing IDs in the log pattern does not mean the current span was lost. Conversely, manually writing a string named `traceId` into MDC does not prove a real trace exists. Inspect the right layer: the tracer manages context, MDC supplies data to the logger, the log pattern decides display formatting, and the exporter is responsible for sending spans.
