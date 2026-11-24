# CapturedOutput or Log-Recording Utilities When Logs Are Behavior Worth Proving

## 1. When Is Logging a Behavior Worth Testing?

Normally, tests should prove **business outcomes**: an order was saved, an endpoint returned the right JSON, a transaction rolled back, a message was sent, or an event was published. Logs are diagnostic signals that can vary across loggers, backends, and formatters, and should not be the sole criterion for claiming business success.

However, under Spring Boot's **Events and Observability** group, logs sometimes form part of the **observability contract**. For example:

- A failed batch job must emit a `job_failed` log event at `ERROR` level with `jobId` and an appropriate error category so operations can diagnose root causes.
- A validation/business rejection must be logged at `WARN`, not disguised as `INFO job_completed`.
- When handling async requests, logs must retain `correlationId`/trace context to correlate steps across the same flow.
- A completed processing step must emit an event with stable names/fields feeding alerts, audit pipelines, or support runbooks.
- **Credentials, bearer tokens, passwords, payment secrets, and sensitive personal data must never appear** in log events controlled by the application.
- A structured JSON logging contract must expose the machine-readable fields that downstream queries and alerts depend on.

For these requirements, logging deserves **direct** testing, provided you choose the right observation level:

1. `OutputCaptureExtension` + `CapturedOutput` to verify text actually written to **`System.out` and `System.err`** in JUnit 5.
2. Logback `ListAppender<ILoggingEvent>` (or a dedicated test appender) to inspect the **log event** before formatting: level, logger name, message template, rendered message, arguments, MDC, and throwable.
3. A queue-backed test appender to await logs from background threads with a **timeout**, avoiding races in async code.
4. Integration tests of structured JSON encoders/formatters or collector pipelines when **JSON/log ingestion** is also part of the contract.

**Critical limitation:** Asserting an INFO line in stdout **does not prove** logs reached Elasticsearch/Loki/Cloud Logging, metrics incremented, traces exported, or durable audit events were saved. Each boundary needs its own test when required.

### Lesson Goals

After this lesson, you will be able to:

- Explain the differences among `System.out/err`, SLF4J, Logback/Log4j2, appenders, encoders, and log aggregation.
- Use `@ExtendWith(OutputCaptureExtension.class)` and inject `CapturedOutput` into JUnit 5 test methods.
- Distinguish `output.getOut()`, `output.getErr()`, `output.getAll()`, and `assertThat(output)`.
- Know when console output capture is sufficient and when to inspect raw logger events.
- Use Logback `ListAppender` with `getLevel()`, `getLoggerName()`, `getMessage()`, `getFormattedMessage()`, `getArgumentArray()`, `getMDCPropertyMap()`, and `getThrowableProxy()`.
- Attach, start, stop, and detach test appenders properly across the lifecycle without polluting other tests.
- Test async logs with `BlockingQueue`/`Future.get(timeout)` without using `Thread.sleep`.
- Verify correlation ID/MDC cleanup and propagation, log levels, exception types, redaction, and structured JSON fields.
- Write resilient assertions independent of timestamps, PIDs, interleaving from other threads, or non-contract log formatting.
- Distinguish testing log events from testing **business events** or **durable audit records**.
- Run the **Java 17 + Spring Boot 3.5.16 + Maven + JUnit Jupiter + AssertJ + SLF4J/Logback** sample project.

## 2. The Logging Pipeline in Spring Boot

### 2.1. Real Data Flow

~~~text
Application
  |
  +-- System.out.println(...) -------------------------+
  |                                                    |
  +-- System.err.println(...) -------------------------+--> System streams
  |                                                    |         |
  +-- SLF4J Logger.info/warn/error(...)                |         v
            |                                          |    OutputCaptureExtension
            v                                          |    CapturedOutput
        Logging implementation                         |    (captures streams only)
        Logback by default via Boot starters           |
            |                                          |
            +-- logger level/filter                     |
            +-- ILoggingEvent (template/args/MDC/error) |
                    |                                  |
                    +-- ListAppender (test event)      |
                    |                                  |
                    +-- ConsoleAppender/encoder -------+
                    |
                    +-- File/Socket/Async/remote appender
                                     |
                                     v
                          Log collector/aggregator
                          index, retention, alerts
~~~

Spring Boot uses Logback by default with standard starters. Boot configures console logging automatically and can configure file logging. Java Util Logging (JUL), Log4j2, and other adapters may route differently depending on classpath and logging configuration.

`CapturedOutput` **is not** a “logger spy”. It observes whatever passes through those two global streams. If a logger:
- Writes directly to a file or network appender;
- Is suppressed by a level filter;
- Uses an async appender that has not flushed yet;
- Already bound to an old output stream before JVM stream redirection;
- Or runs with a test logging config lacking a console appender;

then `CapturedOutput` may **miss** the event, even though the logging subsystem handled it elsewhere.

Conversely, a `ListAppender` attached to a Logback logger observes `ILoggingEvent` **when the logger dispatches the event to appenders**. It does not prove an encoder rendered valid JSON or that a collector received the event.

### 2.2. Layers of a Log Event

| Layer | Example Verification | Appropriate Tool |
| --- | --- | --- |
| Log decision | Job failure must call `log.error` | Appender event |
| Level | `WARN` rather than `INFO` | `ILoggingEvent.getLevel()` |
| Logger | `com.example.logging.JobLogService` | `getLoggerName()` |
| Message template | `event=job_completed jobId={} itemsProcessed={}` | `getMessage()` |
| Rendered message | `event=job_completed jobId=run1 itemsProcessed=2` | `getFormattedMessage()` |
| Arguments | Job ID, count | `getArgumentArray()` |
| Throwable | Root exception class/message | `getThrowableProxy()` |
| MDC | `correlationId=run1` | `getMDCPropertyMap()` |
| Console text | Actual INFO line printed to terminal | `CapturedOutput.getOut()/getAll()` |
| Structured JSON | JSON level, MDC, event, timestamp | Captured JSON + Jackson parse |
| Centralized ingestion | Event indexed/streamed under right tenant | Collector/shipper integration |
| Durable audit | Record persisted, queryable, recoverable | Database/outbox/readback |

Never use one tool to draw conclusions about every layer.

### 2.3. Business Events Differ from Log Events

`ApplicationEventPublisher.publishEvent(new OrderCreated(...))` is a Spring application event; `log.info("order created")` is a log event. They have different lifecycles and guarantees.

- Application events can have synchronous/asynchronous listeners per configuration.
- Log events can be filtered, sampled, dropped, reformatted, or shipped to files/collectors.
- Durable domain events via outbox/brokers typically need retries and idempotent delivery.
- Never treat “saw log line” as proof a business listener committed a transaction or an outbox published to a broker.

When a requirement calls for **testing logs as part of an observability contract**, test the logs; when the requirement is durable business events, assert business event storage/queues/consumers, treating logs purely as diagnostics.

## 3. When Should and Shouldn't You Assert Logs?

### 3.1. Cases Worth Asserting

- Runbooks require event key `job_failed` and `jobId`.
- Alerts trigger on log query `level=ERROR AND event=job_failed`.
- Compliance/security policies prohibit printing raw tokens or passwords.
- A warning is a product-committed signal when entering fallback/degraded mode.
- Correlation ID must exist to trace steps across a request/job.
- Exception type/reason code must distinguish permanent vs. retryable failures.
- Structured logs serve as the API for a downstream monitoring pipeline.

### 3.2. Cases Where Logs Should Not Be the Primary Assertion

- Controller returns HTTP 200 and exact JSON; no need to assert “Started controller” unless part of the contract.
- Repository persists an entity; query committed state rather than checking a “Saved entity” log line.
- Message producer sends successfully; check broker acknowledgement/consumer receipt instead of “Publishing message”.
- Transaction error; assert rollback rather than a “Rollback” log line.
- Unit testing addition; check the return value rather than internal debug logs.
- Spring/Tomcat/Hibernate framework logs changing across patch versions unrelated to the app contract.

**Review rule:** Every log assertion should answer: “If this log disappeared or had the wrong fields, what concrete impact would users, operators, or collectors suffer?” Without a concrete answer, the test creates maintenance noise.

### 3.3. A Test Often Needs Both Assertion Types

Example of a rejected job:

~~~text
Business assertion: result = REJECTED, no side effects.
Observability assertion: WARN event=job_rejected, exact jobId,
                         reason=invalid_input, no job_completed.
~~~

A log assertion alone could PASS even if the job corrupted data. A business assertion alone could PASS while the alerting pipeline misses a critical event. When both are required, verify both.

## 4. Spring Boot's CapturedOutput and OutputCaptureExtension

### 4.1. Exact Components

Spring Boot's test module provides:

~~~java
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
~~~

`OutputCaptureExtension` is a **JUnit Jupiter extension**, registered via:

~~~java
@ExtendWith(OutputCaptureExtension.class)
class StreamTest {
    @Test
    void writesExpectedOutput(CapturedOutput output) {
        System.out.println("job finished");
        assertThat(output.getOut()).contains("job finished");
    }
}
~~~

This is a snippet needing JUnit/AssertJ imports, not a standalone file in the project section. It does not need `@SpringBootTest` if you only capture stdout/stderr or test a POJO.

`CapturedOutput` exposes the captured content:
- `getOut()`: text from `System.out`.
- `getErr()`: text from `System.err`.
- `getAll()`: combined output from both streams in the order observed by capture.
- `CapturedOutput` itself implements `CharSequence`, so `assertThat(output).contains(...)` works cleanly on combined output.

It **does not** mean “captures events from every logger”, “waits for async logs automatically”, or “isolates logs from only the method under test”. The two streams are **JVM-global resources**.

### 4.2. Writing to Streams Differs from Logging Through a Backend

~~~java
System.out.println("STATUS_OK");
System.err.println("STATUS_ERROR");
logger.info("event=job_completed");
~~~

- Both `System.*.println` calls appear on the streams whenever capture is active.
- `logger.info` appears in `CapturedOutput` only if the backend/appender is configured to write to the captured stream and the event is not filtered out.
- Under Spring Boot's default Logback console setup, capturing log text usually works.
- In apps with custom Logback/Log4j2/JUL setups, verify stream binding, appender types, and initialization.

Hence when targeting `level=ERROR` or `MDC.correlationId`, a **log event appender** is usually far more reliable than scanning rendered text lines.

### 4.3. Exact JUnit Lifecycle Scope

Declare the extension on the class and inject `CapturedOutput` into methods. The extension manages capture across the test lifecycle. Never close or restore `System.out` manually inside tests; the extension handles that.

If testing console messages emitted during **Spring ApplicationContext startup**, pay close attention to context creation order, Boot logging initialization, JUnit extensions, and context caching. A reused context does not restart on a second test method, leaving no fresh startup message to capture. Do not assert “Started Application” in every test method as a business condition.

### 4.4. Avoid Asserting the Full Output String

Never do:

~~~java
assertThat(output.getAll()).isEqualTo(
        "2026-11-08 15:00:00 INFO main JobLogService ...");
~~~

Timestamps, timezones, PIDs, thread names, whitespace, ANSI colors, app names, and logger abbreviations all vary. Assert **stable markers/event names and fields** required by the contract.

Example:

~~~java
assertThat(output.getAll())
        .contains("event=job_completed")
        .contains("jobId=run_42");
~~~

Even so, if two separate lines contain those two fragments, asserting across **the whole output** does not prove they belong to the same event. Use an appender or filter individual lines by `jobId` when field co-occurrence matters.

### 4.5. Avoid Overly Vague Substrings

~~~java
assertThat(output).contains("failed");
~~~

“failed” could come from stack traces, framework startup, another test, or an unrelated message. Use a specific marker like `event=job_failed jobId=run_42 category=dependency_timeout`, or query events by logger/level/message template.

### 4.6. OutputCaptureExtension Does Not Override Logging Configuration

If `logging.level.com.example=ERROR` is set, a `log.info` call never reaches appenders. `CapturedOutput` cannot make INFO magically appear. Tests must configure logger levels matching the contract under test without cranking the entire root logger up to DEBUG just to catch one line.

## 5. Using Logback ListAppender

### 5.1. Why Use ListAppender?

With Spring Boot 3.5's default Logback backend, `ch.qos.logback.core.read.ListAppender<ILoggingEvent>` is a simple test appender storing log events in a list. It lets you assert **event data before formatting**:

~~~java
Logger logger = (Logger) LoggerFactory.getLogger(JobLogService.class);

ListAppender<ILoggingEvent> appender = new ListAppender<>();
appender.setContext(logger.getLoggerContext());
appender.start();
logger.addAppender(appender);

try {
    service.execute("job_1", "test-credential", false);
    assertThat(appender.list)
            .anySatisfy(event ->
                    assertThat(event.getLevel())
                            .isEqualTo(Level.INFO));
}
finally {
    logger.detachAppender(appender);
    appender.stop();
}
~~~

This is a snippet; full imports and classes appear in the lab below.

`appender.list` stores **events from the attached logger**. Attaching to the **root logger** floods tests with framework and unrelated bean logs, weakening assertions and adding noise. Attach specifically to the **target class logger** when the contract belongs to that class.

### 5.2. Each Part of ILoggingEvent Has Its Own Meaning

| API | Meaning | Reliable Assertion |
| --- | --- | --- |
| `getLevel()` | INFO/WARN/ERROR | WARN for validation rejection |
| `getLoggerName()` | Logger name | Event emitted by service under test |
| `getMessage()` | Raw message template | Verify marker/placeholder convention |
| `getFormattedMessage()` | Message after SLF4J formatting | Verify jobId/reason/count |
| `getArgumentArray()` | Arguments passed to logger | Verify real values regardless of timestamp |
| `getMDCPropertyMap()` | Event's MDC snapshot | Correlation ID properly attached |
| `getThrowableProxy()` | Throwable metadata | ERROR event has exact exception type |
| `getThreadName()` | Thread emitting event | Useful in async tests when required |
| `getTimeStamp()` | Event timestamp | Use time ranges when truly needed; never exact timestamp |

The message template can serve as a minimal **text event schema** when downstream searches by prefix. For stricter structured logging, use a JSON encoder/fields rather than parsing free-form strings.

### 5.3. Attach Before the Action, Detach Afterward

An appender only captures events emitted after it is attached—never retroactively. In JUnit:
- `@BeforeEach`: create, start, attach.
- Test method: trigger action, await completion, inspect events.
- `@AfterEach`: detach, stop—even if assertions fail.

Never alter root logger levels or leave appenders attached without detaching; later tests will receive events from earlier tests, leaking memory and breaking repeatability.

### 5.4. ListAppender Is Not an Async Wait Primitive

`ListAppender.list` is an in-memory list for reading events once emitted. If a worker on another thread has not run yet, calling `appender.list.size()` immediately can return 0. Unsynchronized polling across threads is also unsafe by default.

For async work, use:
- `Future.get(timeout)` or completion stages confirming the worker finished.
- Or a `BlockingQueue` populated by a test appender and awaited via `poll(timeout)`.
- When the backend uses an asynchronous appender/encoder, wait on the **exact layer** under test.

The lab includes a dedicated appender backed by `LinkedBlockingQueue` to demonstrate this.

## 6. Designing Log Contracts to Keep Tests Flake-Free

### 6.1. Stable Event Names and Fields

For a batch job, instead of:

~~~text
I think maybe item processing is finished for customer ABC
~~~

prefer a clear contract:

~~~text
event=job_started jobId=run_42
event=job_completed jobId=run_42 itemsProcessed=2
event=job_rejected jobId=run_43 reason=invalid_input
event=job_failed jobId=run_44 category=dependency_timeout
~~~

Exact English prose does not need to stay frozen; what matters is governed event names, business correlation IDs, error categories, schema/versions, and log levels.

### 6.2. Appropriate Log Levels

| Behavior | Typical Reasonable Level | Reason |
| --- | --- | --- |
| Routine job start | INFO/DEBUG depending on volume | Trace startup |
| Successful job completion | INFO or sampled telemetry event | Observe success |
| Input validation rejected | WARN or INFO per business semantics | Distinguish from infrastructure errors |
| Dependency timeout fails job | ERROR if operational response needed | Signal actionable failure with cause |
| Normal retry with backoff | WARN/INFO with attempt count | Avoid ERROR storms on recoverable issues |
| Routine step-by-step details | DEBUG/TRACE | Avoid production noise |
| Secrets/sensitive data | **Never log** | Security |

Log levels are a policy, not universal dogma across domains. An invalid user request might be INFO instead of WARN under high traffic; test against the **chosen contract** rather than assuming WARN is always right.

### 6.3. Correlation ID and MDC

Mapped Diagnostic Context (MDC) stores key/value pairs on the logging context, typically thread-bound. A `correlationId` links events across steps.

~~~java
String previous = MDC.get("correlationId");
MDC.put("correlationId", jobId);
try {
    // Work and log events.
}
finally {
    if (previous == null) {
        MDC.remove("correlationId");
    }
    else {
        MDC.put("correlationId", previous);
    }
}
~~~

Because thread pools reuse threads, **forgetting MDC cleanup** causes logs from request A to carry request B's correlation ID. If a library or servlet filter already owns MDC, never blindly wipe the caller's value; the pattern above **restores the previous value**.

Never assume MDC automatically propagates across `@Async`, `CompletableFuture`, Reactor, or executor threads. Use an appropriate `TaskDecorator`/context propagation mechanism and integration-test the real execution path.

### 6.4. Never Log Credentials

Avoid:

~~~java
log.info("Calling gateway with token={}", bearerToken);
log.error("Payment failed request={}", fullRequestDto, exception);
~~~

DTO `toString()` output and exception messages can contain passwords, authorization headers, customer names, account details, or payment data. Use an allowlist of safe fields:
- event name;
- non-sensitive synthetic/business IDs per policy;
- status/reason code;
- latency bucket, retry attempt;
- exception class/category;
- trace/correlation ID.

When logging exceptions with stack traces, review error messages/causes because **the exception itself** can hold secrets. A negative test checking “no token in the service's logger events” is useful yet limited in scope: it does not prove every gateway or framework logger is redacted.

### 6.5. Preventing Log Injection

Untrusted input containing newlines or ANSI control characters can forge fake log lines in text logs:

~~~text
jobId=order_42
ERROR Admin login succeeded
~~~

To mitigate risk:
- Validate/sanitize logged identifiers.
- Prefer structured logging/encoders with proper escaping.
- Bound the length of untrusted values.
- Never log raw request bodies as audit messages.
- Test malicious newline/CRLF payloads when your threat model calls for it.

In the lab, `JobLogService` accepts `jobId` matching only letters, digits, `_`, `-` up to 64 characters.

## 7. Java 17 + Spring Boot 3.5.16 Project: Verifying Log Behavior Properly

### 7.1. Scenario

A synchronous job service has three outcomes:
- `COMPLETED`: emits `INFO job_started` then `INFO job_completed`.
- `REJECTED`: emits `INFO job_started` then `WARN job_rejected`.
- Exception: emits `INFO job_started` then `ERROR job_failed` with `IllegalStateException`, then rethrows.

All three:
- Bind `correlationId=jobId` in MDC for the duration of processing.
- Restore the prior MDC value afterward.
- Never log `credential`, an intentionally sensitive parameter.
- Allow asserting both outcomes **and** log events.

Three JUnit classes:
1. `OutputCaptureExamplesTest` demonstrates `getOut/getErr/getAll` on streams.
2. `LogbackEventAssertionsTest` uses `ListAppender` with the Spring-managed bean to assert level, message, MDC, Throwable, and secret redaction.
3. `AsyncLogEventTest` uses a queue-backed test appender to await logs from a worker thread without reading the list prematurely.

No Docker/Redis/broker/HTTP server is needed. Logback is the default provider via Spring Boot starter, with no arbitrary Log4j2 version overrides in the main lab.

### 7.2. File Tree

~~~text
spring-boot-log-contract-lab/
├── pom.xml
├── src/main/
│   ├── java/com/example/logcontract/
│   │   ├── LogContractApplication.java
│   │   └── JobLogService.java
│   └── resources/
│       └── application.properties
└── src/test/java/com/example/logcontract/
    ├── OutputCaptureExamplesTest.java
    ├── LogbackEventAssertionsTest.java
    └── AsyncLogEventTest.java
~~~

### 7.3. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>spring-boot-log-contract-lab</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
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

`spring-boot-starter` pulls in `spring-boot-starter-logging`/Logback and SLF4J. `spring-boot-starter-test` brings in JUnit Jupiter, AssertJ, and `OutputCaptureExtension`. Logback classes such as `ListAppender` are on the test classpath. If a real project switches to Log4j2 and excludes Logback, you **cannot** cast loggers to `ch.qos.logback.classic.Logger`; use Log4j2's test appender instead.

`spring-boot-starter-web` is omitted because this lesson tests logging on a plain service without HTTP requests or an embedded servlet container.

### 7.4. application.properties

`src/main/resources/application.properties`:

~~~properties
spring.application.name=log-contract-lab
spring.main.web-application-type=none

# Keep the service's INFO/WARN/ERROR events enabled in the demo.
logging.level.com.example.logcontract=INFO

# Omit ANSI escape codes from console text in tests.
spring.output.ansi.enabled=never
~~~

This configuration keeps text output clean. It avoids forcing the root logger to DEBUG, logs no credentials, and enables no extra file appenders. `spring.main.web-application-type=none` speeds up integration context startup.

### 7.5. LogContractApplication.java

`src/main/java/com/example/logcontract/LogContractApplication.java`:

~~~java
package com.example.logcontract;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LogContractApplication {

    public static void main(String[] args) {
        SpringApplication.run(LogContractApplication.class, args);
    }
}
~~~

No test data is emitted in `main`, and no log collector is exposed. The lesson focuses on the observability behavior of a bean.

### 7.6. JobLogService.java

`src/main/java/com/example/logcontract/JobLogService.java`:

~~~java
package com.example.logcontract;

import java.util.Objects;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.stereotype.Service;

@Service
public class JobLogService {

    private static final Logger log =
            LoggerFactory.getLogger(JobLogService.class);

    public String execute(
            String jobId,
            String credential,
            boolean reject) {

        String safeId = checkedId(jobId);
        Objects.requireNonNull(credential, "credential");

        String previous = MDC.get("correlationId");
        MDC.put("correlationId", safeId);

        try {
            log.info("event=job_started jobId={}", safeId);

            if (reject) {
                log.warn(
                        "event=job_rejected jobId={} reason=invalid_input",
                        safeId);
                return "REJECTED";
            }

            // Demo: process two items, no external side effects.
            log.info(
                    "event=job_completed jobId={} itemsProcessed={}",
                    safeId, 2);

            return "COMPLETED";
        }
        finally {
            restoreCorrelationId(previous);
        }
    }

    public void failUnexpectedly(
            String jobId,
            String credential) {

        String safeId = checkedId(jobId);
        Objects.requireNonNull(credential, "credential");

        String previous = MDC.get("correlationId");
        MDC.put("correlationId", safeId);

        try {
            log.info("event=job_started jobId={}", safeId);

            IllegalStateException failure =
                    new IllegalStateException(
                            "simulated dependency timeout");

            log.error(
                    "event=job_failed jobId={} category=dependency_timeout",
                    safeId,
                    failure);

            throw failure;
        }
        finally {
            restoreCorrelationId(previous);
        }
    }

    private static String checkedId(String jobId) {
        if (jobId == null
                || !jobId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException(
                    "invalid job identifier");
        }
        return jobId;
    }

    private static void restoreCorrelationId(String previous) {
        if (previous == null) {
            MDC.remove("correlationId");
        }
        else {
            MDC.put("correlationId", previous);
        }
    }
}
~~~

### 7.7. Why Was the Service Designed This Way?

**Event convention**:
- `event=job_started`, `event=job_completed`, `event=job_rejected`, and `event=job_failed` are machine-searchable markers.
- `jobId` is a synthetic safe ID in this example.
- `itemsProcessed=2` is the count reported on success.
- `reason=invalid_input` and `category=dependency_timeout` are stable reason codes.

**Outcome independent of logs**:
- `execute` returns `COMPLETED`/`REJECTED`.
- `failUnexpectedly` throws the exact exception.
- Tests must assert both outcomes/exceptions **and** log events.

**Credential redaction**:
- `credential` simulates a boundary receiving a secret.
- Code deliberately **never passes `credential`** into SLF4J arguments, MDC, or exception messages.
- Checking secret absence covers only the service's own events in tests; it does not prove every other logging layer is safe.

**MDC**:
- Uses `try/finally` to prevent leaks when methods throw.
- Restores the caller's previous value instead of unconditionally calling `remove`.
- Executes on the current thread; when crossing to executors/`@Async`, propagate context per requirements.

**Log injection**:
- `checkedId` rejects IDs with newlines/CRLF or characters outside the allowlist.
- Never logs the ID before validation.
- This is a defensive sample, not a replacement for domain-specific schema/PII handling.

**Throwable**:
- `log.error("... {}", safeId, failure)` passes the exception last, so SLF4J/Logback records throwable metadata.
- The lab avoids putting credentials into exception messages.
- An ERROR log event never replaces propagating errors per contract; the method still rethrows.

### 7.8. OutputCaptureExamplesTest.java

`src/test/java/com/example/logcontract/OutputCaptureExamplesTest.java`:

~~~java
package com.example.logcontract;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;

import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;

import static org.assertj.core.api.Assertions.assertThat;

@ExtendWith(OutputCaptureExtension.class)
class OutputCaptureExamplesTest {

    @Test
    void capturesStdoutAndStderrSeparately(
            CapturedOutput output) {

        System.out.println("STDOUT_ONLY_MARKER_390");
        System.err.println("STDERR_ONLY_MARKER_390");

        assertThat(output.getOut())
                .contains("STDOUT_ONLY_MARKER_390")
                .doesNotContain("STDERR_ONLY_MARKER_390");

        assertThat(output.getErr())
                .contains("STDERR_ONLY_MARKER_390")
                .doesNotContain("STDOUT_ONLY_MARKER_390");

        assertThat(output.getAll())
                .contains("STDOUT_ONLY_MARKER_390")
                .contains("STDERR_ONLY_MARKER_390");

        // CapturedOutput implements CharSequence.
        assertThat(output)
                .contains("STDOUT_ONLY_MARKER_390");
    }

    @Test
    void checksStableTextWithoutTimestampAssumptions(
            CapturedOutput output) {

        System.out.println(
                "event=demo_started jobId=demo_390");
        System.out.println(
                "event=demo_completed jobId=demo_390");

        assertThat(output.getOut())
                .contains("event=demo_started jobId=demo_390")
                .contains("event=demo_completed jobId=demo_390")
                .doesNotContain(
                        "event=demo_failed jobId=demo_390");
    }
}
~~~

**What this proves precisely:**
- The extension captures both system streams.
- `getOut`/`getErr` stay distinct.
- `getAll` contains output from both.
- Tests require no Spring context, Docker, or logging backend.
- These tests do not check Logback `INFO/WARN/ERROR`—that is covered by the appender tests below.

If you want to verify **console-rendered text emitted by SLF4J**, attach `@ExtendWith(OutputCaptureExtension.class)` to a `@SpringBootTest` class, invoke the service, and assert `output.getAll()` contains stable event markers. With custom logging backends, verify ConsoleAppender actually writes to the captured stream. If not, use an event appender as below; never make a business test “green” by adding `System.out.println` as a stand-in for a logger.

### 7.9. LogbackEventAssertionsTest.java

`src/test/java/com/example/logcontract/LogbackEventAssertionsTest.java`:

~~~java
package com.example.logcontract;

import java.util.stream.Collectors;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest
class LogbackEventAssertionsTest {

    @Autowired
    JobLogService service;

    private Logger serviceLogger;
    private ListAppender<ILoggingEvent> appender;

    @BeforeEach
    void attachAppender() {
        serviceLogger = (Logger) LoggerFactory.getLogger(
                JobLogService.class);

        appender = new ListAppender<>();
        appender.setContext(
                serviceLogger.getLoggerContext());
        appender.setName("TEST_JOB_EVENTS");
        appender.start();

        serviceLogger.addAppender(appender);
    }

    @AfterEach
    void detachAppender() {
        if (serviceLogger != null && appender != null) {
            serviceLogger.detachAppender(appender);
            appender.stop();
        }
    }

    private ILoggingEvent findEvent(String eventName) {
        return appender.list.stream()
                .filter(event -> event.getFormattedMessage()
                        .contains("event=" + eventName + " "))
                .findFirst()
                .orElseThrow(() ->
                        new AssertionError(
                                "missing event: " + eventName));
    }

    @Test
    void completionHasInfoLevelExactArgumentsAndMdc() {
        String jobId = "job_success_390";

        String result = service.execute(
                jobId, "secret_not_for_logs", false);

        assertThat(result).isEqualTo("COMPLETED");
        assertThat(appender.list).hasSize(2);

        ILoggingEvent completed =
                findEvent("job_completed");

        assertThat(completed.getLevel())
                .isEqualTo(Level.INFO);

        assertThat(completed.getLoggerName())
                .isEqualTo(JobLogService.class.getName());

        assertThat(completed.getMessage())
                .isEqualTo(
                        "event=job_completed jobId={} itemsProcessed={}");

        assertThat(completed.getArgumentArray())
                .containsExactly(jobId, 2);

        assertThat(completed.getFormattedMessage())
                .isEqualTo(
                        "event=job_completed jobId="
                                + jobId + " itemsProcessed=2");

        assertThat(completed.getMDCPropertyMap())
                .containsEntry("correlationId", jobId);

        assertThat(MDC.get("correlationId"))
                .isNull();
    }

    @Test
    void rejectedJobWarnsAndDoesNotReportCompletion() {
        String jobId = "job_rejected_390";

        String result = service.execute(
                jobId, "secret_not_for_logs", true);

        assertThat(result).isEqualTo("REJECTED");
        assertThat(appender.list).hasSize(2);

        ILoggingEvent rejected =
                findEvent("job_rejected");

        assertThat(rejected.getLevel())
                .isEqualTo(Level.WARN);

        assertThat(rejected.getFormattedMessage())
                .contains("jobId=" + jobId)
                .contains("reason=invalid_input");

        assertThat(rejected.getMDCPropertyMap())
                .containsEntry("correlationId", jobId);

        assertThat(appender.list)
                .noneMatch(event ->
                        event.getFormattedMessage()
                                .contains("event=job_completed "));
    }

    @Test
    void unexpectedFailureContainsErrorAndThrowable() {
        String jobId = "job_failed_390";

        assertThatThrownBy(() ->
                service.failUnexpectedly(
                        jobId, "secret_not_for_logs"))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("simulated dependency timeout");

        ILoggingEvent failed =
                findEvent("job_failed");

        assertThat(failed.getLevel())
                .isEqualTo(Level.ERROR);

        assertThat(failed.getFormattedMessage())
                .contains("jobId=" + jobId)
                .contains("category=dependency_timeout");

        assertThat(failed.getThrowableProxy())
                .isNotNull();

        assertThat(failed.getThrowableProxy()
                .getClassName())
                .isEqualTo(
                        "java.lang.IllegalStateException");

        assertThat(failed.getMDCPropertyMap())
                .containsEntry("correlationId", jobId);

        // finally must execute even when throwing.
        assertThat(MDC.get("correlationId"))
                .isNull();
    }

    @Test
    void credentialIsNotInServiceLogMessages() {
        String secret = "Bearer_SUPER_SECRET_390";

        service.execute("job_redaction_390", secret, false);

        String messages = appender.list.stream()
                .map(ILoggingEvent::getFormattedMessage)
                .collect(Collectors.joining("\n"));

        assertThat(messages)
                .contains("event=job_completed")
                .doesNotContain(secret);

        assertThat(appender.list)
                .allSatisfy(event ->
                        assertThat(event.getMDCPropertyMap())
                                .doesNotContainValue(secret));
    }

    @Test
    void methodRestoresExistingCallerMdcValue() {
        String original = MDC.get("correlationId");
        MDC.put("correlationId", "caller_390");

        try {
            service.execute(
                    "inner_job_390", "secret", false);

            assertThat(MDC.get("correlationId"))
                    .isEqualTo("caller_390");

            ILoggingEvent completed =
                    findEvent("job_completed");

            assertThat(completed.getMDCPropertyMap())
                    .containsEntry(
                            "correlationId", "inner_job_390");
        }
        finally {
            if (original == null) {
                MDC.remove("correlationId");
            }
            else {
                MDC.put("correlationId", original);
            }
        }
    }

    @Test
    void unsafeIdentifierIsRejectedBeforeAnyLog() {
        assertThatThrownBy(() ->
                service.execute(
                        "job_390\nFAKE_ERROR",
                        "secret", false))
                .isInstanceOf(
                        IllegalArgumentException.class)
                .hasMessage("invalid job identifier");

        assertThat(appender.list).isEmpty();
    }
}
~~~

### 7.10. Analyzing the Logback Appender Tests

**Completion test**:
- Asserts business result `COMPLETED`.
- Event `job_completed` is at `INFO`.
- Logger name matches the service class.
- Template and argument array match: `jobId` + `itemsProcessed=2`.
- Formatted message matches without relying on timestamps/threads/PIDs.
- MDC at log time contains `correlationId=jobId`.
- After the method returns, the caller thread retains no stale MDC.

**Rejection test**:
- Business result `REJECTED`.
- Emits `WARN job_rejected` with reason code.
- No `job_completed` among the service's events during the test.
- Independent of framework text output.

**Error test**:
- Method actually throws `IllegalStateException`.
- Emits `ERROR job_failed` with `ThrowableProxy` matching the exception class.
- MDC is present in the event even though the method rethrows afterward.
- Cleanup runs inside `finally`.

**Secret test**:
- Raw credential never appears in rendered messages or MDC values of captured events.
- This is a **useful yet scoped negative regression test**: it does not cover other loggers, library stack traces, file appenders, or collector outputs. If credentials are logged in request DTO/HTTP client logs at another layer, test that layer separately.

**MDC restore test**:
- When the caller already had a correlation ID, the method preserves the caller's context.
- Log events inside the method carry the job-specific ID.
- Stronger contract than merely asserting MDC is null after execution.

**Log injection test**:
- CRLF in `jobId` is rejected before emitting any event.
- Non-conforming IDs are never printed verbatim.
- Production also needs escaping/truncation for user-provided messages in other fields.

**Isolation:** `@BeforeEach` attaches to a targeted logger; `@AfterEach` detaches even if assertions fail. JUnit Jupiter runs methods sequentially by default; if enabling parallel execution, use `@ResourceLock`/isolation to prevent two tests from mutating the same JVM-global logger.

### 7.11. AsyncLogEventTest.java

Some jobs dispatch via `ExecutorService`, `@Async`, or messaging listeners and log on another thread. Checking events **before the worker finishes** races. To illustrate, this class runs the service on a Java executor and uses a test-specific `QueueAppender`:

`src/test/java/com/example/logcontract/AsyncLogEventTest.java`:

~~~java
package com.example.logcontract;

import java.time.Duration;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.AppenderBase;

import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class AsyncLogEventTest {

    @Autowired
    JobLogService service;

    static final class QueueAppender
            extends AppenderBase<ILoggingEvent> {

        private final BlockingQueue<ILoggingEvent> queue =
                new LinkedBlockingQueue<>();

        @Override
        protected void append(ILoggingEvent event) {
            // Snapshot MDC/arguments while running on the current thread.
            event.prepareForDeferredProcessing();
            queue.offer(event);
        }

        ILoggingEvent await(Duration timeout)
                throws InterruptedException {
            return queue.poll(
                    timeout.toMillis(),
                    TimeUnit.MILLISECONDS);
        }
    }

    @Test
    void logFromWorkerThreadIsObservedWithBoundedWait()
            throws Exception {

        Logger logger = (Logger) LoggerFactory.getLogger(
                JobLogService.class);

        QueueAppender appender = new QueueAppender();
        appender.setContext(logger.getLoggerContext());
        appender.setName("ASYNC_TEST_QUEUE");
        appender.start();
        logger.addAppender(appender);

        ExecutorService executor =
                Executors.newSingleThreadExecutor();

        try {
            Future<String> work = executor.submit(
                    () -> service.execute(
                            "async_390",
                            "secret",
                            false));

            // Wait for business completion; do not sleep.
            assertThat(work.get(
                    5, TimeUnit.SECONDS))
                    .isEqualTo("COMPLETED");

            ILoggingEvent first =
                    appender.await(Duration.ofSeconds(3));
            ILoggingEvent second =
                    appender.await(Duration.ofSeconds(3));

            assertThat(first).isNotNull();
            assertThat(second).isNotNull();

            assertThat(first.getFormattedMessage())
                    .contains("event=job_started ")
                    .contains("jobId=async_390");

            assertThat(second.getFormattedMessage())
                    .contains("event=job_completed ")
                    .contains("jobId=async_390");

            assertThat(second.getLevel())
                    .isEqualTo(Level.INFO);

            assertThat(second.getMDCPropertyMap())
                    .containsEntry(
                            "correlationId", "async_390");
        }
        finally {
            executor.shutdownNow();
            logger.detachAppender(appender);
            appender.stop();
        }
    }
}
~~~

### 7.12. Why Is QueueAppender Better Than Thread.sleep?

- Submitting to the worker and calling `Future.get(timeout)` ensures the action returned or threw/timed out.
- The appender captures events directly as emitted; `BlockingQueue.poll(timeout)` awaits **real events**.
- Independent of whether a CI runner runs fast or slow during a fixed sleep.
- `prepareForDeferredProcessing()` captures deferred fields such as MDC before the logging thread finishes and clears context.
- Tests inspect event-level data rather than hoping an async console stream flushed.
- `finally` shuts down the executor and detaches the appender to avoid polluting other tests.

**Caveat:** This class illustrates work running on a Java `ExecutorService`, **not** `@Async` annotation and Spring `TaskExecutor`/`TaskDecorator` configuration. When production uses `@Async`, write a real integration test through the Spring proxy, configure executor context propagation, handle `CompletableFuture`/`AsyncUncaughtExceptionHandler`, and verify the resulting events. Never claim an executor sample proves propagation across every async framework.

### 7.13. Running the Project

From `spring-boot-log-contract-lab`:

~~~bash
mvn -q clean test

mvn -q -Dtest=OutputCaptureExamplesTest test
mvn -q -Dtest=LogbackEventAssertionsTest test
mvn -q -Dtest=AsyncLogEventTest test
~~~

Expected JUnit methods:
- `OutputCaptureExamplesTest`: 2 methods.
- `LogbackEventAssertionsTest`: 6 methods.
- `AsyncLogEventTest`: 1 method.
- **Total of 9 methods**.

When executed successfully, Maven exits with code 0 and Surefire reports appear in `target/surefire-reports`. Exact Spring Boot console lines vary by environment, yet lab assertions do not depend on full logger formats or fixed timestamps.

**QA status of sample code:** APIs/imports/lifecycles were reviewed for Java 17, Spring Boot 3.5, Logback, and JUnit 5; **Maven/JUnit was not executed during authoring**. When applying, run `mvn clean test` in your project and inspect test reports rather than treating this as an observed PASS result.

### 7.14. Why Not Put @SpringBootTest on Every Class?

`OutputCaptureExamplesTest` checks streams with a pure JUnit extension and needs no Spring context. The other two classes autowire the service from a real context to verify event emission from a Spring-managed bean. Each layer has a different cost; never boot a context just to call `System.out.println`.

## 8. CapturedOutput for Checking SLF4J Console Logs

### 8.1. Combined Example in Spring Boot

When an app uses a capture-compatible console appender:

~~~java
@SpringBootTest
@ExtendWith(OutputCaptureExtension.class)
class JobConsoleLogTest {

    @Autowired
    JobLogService service;

    @Test
    void successWritesContractMarker(
            CapturedOutput output) {

        String result = service.execute(
                "console_390", "synthetic_secret", false);

        assertThat(result).isEqualTo("COMPLETED");

        assertThat(output.getAll())
                .contains(
                        "event=job_completed jobId=console_390");
    }
}
~~~

This is an **extended snippet**, not a file in the runnable lab. It shows how to test **rendered console logs** when that is the requirement. If a custom appender/Log4j2/JUL does not write to the captured stream, the test misses events—that is a logging configuration issue, not proof the service skipped calling the logger.

### 8.2. Distinguishing getOut and getErr for ERROR Level

There is no universal rule that “`log.error` always goes to `System.err`”. Logback's default `ConsoleAppender` can write INFO/WARN/ERROR all to stdout depending on configuration. When checking **ERROR level**, check `ILoggingEvent.getLevel()`; do not assert `output.getErr()` contains ERROR as a logging contract unless stderr routing is explicitly configured.

Conversely, `System.err.println("ERROR")` prints to stderr, yet **is not** an SLF4J ERROR event with logger name, MDC, or Throwable.

### 8.3. A Snapshot Is Not the Service's Exclusive Stream

`CapturedOutput.getAll()` holds all stdout/stderr captured during the test lifecycle: framework logs, test fixtures, direct `System.out`, background workers, and third-party libraries. Therefore:
- Use unique job IDs.
- Filter by exact line/event marker.
- Avoid asserting global log counts.
- Never rely on full output equality.
- Never run tests in parallel that mutate global `System.out/err` without isolation.

## 9. Java Util Logging and Log4j2: Cases Needing Extra Config

### 9.1. Java Util Logging (JUL)

Spring Boot's `OutputCaptureExtension` docs note that JUL may need a logging configuration reset to capture console output reliably:

~~~java
@AfterEach
void resetJulLogging() throws Exception {
    java.util.logging.LogManager
            .getLogManager()
            .readConfiguration();
}
~~~

This is a **snippet for projects actually using JUL**, not part of the main Logback lab. JUL's `ConsoleHandler` can initialize early and retain an old stream reference. Never add JUL resets indiscriminately to Logback tests; resetting/reconfiguring global loggers can cause side effects for other tests.

If an app routes JUL through Spring Boot's Logback adapter, identify the real log route before choosing a fix.

### 9.2. Log4j2 ConsoleAppender follow=true

Per Spring Boot's `OutputCaptureExtension` Javadoc, Log4j2 should configure its console appender to follow the active stream using `follow="true"` for reliable capture:

~~~xml
<Appenders>
  <Console name="Console"
           target="SYSTEM_OUT"
           follow="true">
    <PatternLayout pattern="%d %-5p %c - %m%n"/>
  </Console>
</Appenders>
~~~

This belongs in `log4j2-spring.xml`/Log4j2 config alongside `Loggers` referencing the appender and Log4j2 dependencies. Never paste this XML into Logback's `logback-spring.xml`; they are two different backends.

When a project uses Log4j2:
- Exclude `spring-boot-starter-logging`/Logback cleanly.
- Add `spring-boot-starter-log4j2`.
- Use Log4j2 appenders/listeners to capture structured events.
- Add dedicated tests for formatter/JSON output when that is part of the contract.

### 9.3. Why Resetting/Reconfiguring Global Logging Is Risky

`LoggingSystem` is typically process-global or Spring ApplicationContext-scoped infrastructure. If two test classes run in parallel and one alters logger levels/appenders/streams, the other can see filtered or misrouted events. Use isolated test JVMs, sequential execution, `@ResourceLock`, or tightly scoped test appenders if parallel execution is enabled.

## 10. Structured Logging: Checking JSON Instead of Grepping Text When Needed

### 10.1. Spring Boot 3.5 Built-In Structured Log Formats

Spring Boot 3.5 includes built-in structured logging formats such as:
- **Elastic Common Schema (ECS)**;
- **Logstash JSON**;
- **Graylog Extended Log Format (GELF)**.

Example enabling ECS on console:

~~~properties
logging.structured.format.console=ecs
logging.structured.ecs.service.name=inventory-test
~~~

This is an **optional configuration** when testing structured JSON. Do not enable it alongside the lab's default text assertions without updating parsing/assertions; Boot logging config can affect global state and context caching.

### 10.2. JSON Is a Field Contract, Not a Whole-Line String

With ECS, a JSON line might look like:

~~~json
{
  "@timestamp": "2026-11-08T00:00:00Z",
  "log": {
    "level": "INFO",
    "logger": "com.example.logcontract.JobLogService"
  },
  "message": "event=job_completed jobId=job_390 itemsProcessed=2",
  "correlationId": "job_390",
  "service": {
    "name": "inventory-test"
  }
}
~~~

This is an **illustrative shape**, not measured stdout. Additional fields like process/thread/`ecs.version` may appear. `@timestamp` is just an example; tests must never assert exact date/time values.

Spring Boot structured logging can map MDC values into JSON output; field names can be customized. Downstream collectors may also rename or drop fields, so valid local JSON does not automatically prove the post-ingestion index schema.

### 10.3. Proper Assertions with Jackson

Once structured JSON output is enabled in an appropriate test profile/fork, parse individual lines instead of comparing full strings:

~~~java
String line = output.getOut().lines()
        .filter(value ->
                value.contains("event=job_completed"))
        .findFirst()
        .orElseThrow();

JsonNode node = new ObjectMapper().readTree(line);

assertThat(node.path("log").path("level").asText())
        .isEqualTo("INFO");

assertThat(node.path("message").asText())
        .contains("jobId=job_390");

assertThat(node.path("correlationId").asText())
        .isEqualTo("job_390");
~~~

This is an **extended snippet** needing Jackson dependencies/imports and injected `CapturedOutput output`, outside the minimal Maven lab. `ObjectMapper` requires `spring-boot-starter-json` or `jackson-databind` in test scope; never assume bare `spring-boot-starter` includes Jackson.

Do not parse the entire `CapturedOutput.getAll()` as a single JSON document when multiple log lines or framework startup text are present. Filter the event line, verify it is JSON, and assert specific fields. If `event` lives in structured key-value fields, parse that field rather than grepping `message`.

### 10.4. SLF4J 2 Fluent Key-Value Pairs

Spring Boot 3.5 structured logging can emit key/value pairs supplied via SLF4J's fluent API:

~~~java
log.atInfo()
        .addKeyValue("event", "job_completed")
        .addKeyValue("jobId", "job_390")
        .addKeyValue("itemsProcessed", 2)
        .log("Job completed");
~~~

Snippet inside a method with `Logger log`. Under structured logging, key/value pairs can become JSON fields; under default text formatting, they may not appear in console messages unless the pattern renders them. When fields are the contract, assert event key/value pairs or JSON encoder output—**never** assume `CapturedOutput.contains("event=job_completed")` catches fluent key/values not rendered by the formatter.

### 10.5. Checking Schema/Backward Compatibility

If alerts rely on `correlationId` and `event=job_failed`:
- Renaming fields breaks queries.
- Changing level from ERROR→INFO can silence alerts.
- Invalid JSON after logging config changes breaks ingestion.
- Dropped MDC on async switches loses correlation.
- Secrets/PII can slip through encoders depending on field allowlists.
- Timestamp parsing/timezones at the collector can skew dashboards.

Write contract tests for **fields downstream actually depends on**. Do not lock every default ECS field into a snapshot test, because Boot patch versions can legitimately add metadata.

## 11. MDC and Async Logging: Boundaries to Verify

### 11.1. MDC Is Usually Thread-Bound

In servlet handlers, MDC may be populated by filters/interceptors/tracing instrumentation. If code calls `CompletableFuture.supplyAsync(...)` without passing context, the worker thread may lack the correlation ID. That is not `CapturedOutput` dropping logs—it is **missing context propagation**.

~~~text
request-thread: MDC correlationId=abc
   |
   +-- submit task to executor
                   |
                   v
            worker-thread
            MDC may be empty
            (unless propagated)
~~~

### 11.2. TaskDecorator Is One Approach

In a Spring `TaskExecutor`, a `TaskDecorator` can snapshot the caller's MDC map before submission and restore it on the worker during execution. Clean up stale MDC on pooled workers afterward to prevent leaks.

Illustrative example of the idea:

~~~java
public final class MdcTaskDecorator
        implements org.springframework.core.task.TaskDecorator {

    @Override
    public Runnable decorate(Runnable task) {
        var callerContext = MDC.getCopyOfContextMap();

        return () -> {
            var previous = MDC.getCopyOfContextMap();

            try {
                if (callerContext == null) {
                    MDC.clear();
                }
                else {
                    MDC.setContextMap(callerContext);
                }
                task.run();
            }
            finally {
                if (previous == null) {
                    MDC.clear();
                }
                else {
                    MDC.setContextMap(previous);
                }
            }
        };
    }
}
~~~

This is an **extended snippet** needing `import org.slf4j.MDC` and Spring `TaskExecutor`/`TaskDecorator` registration; it is not in the runnable lab. With Micrometer context propagation, Reactor, or Java virtual threads, the right mechanism can differ; test against your real runtime.

### 11.3. Logback AsyncAppender Also Has a Queue

Logback's `AsyncAppender` enqueues events and writes them to console/files later. A test awaiting only the business `CompletableFuture` can finish **before** console output appears. When needed:
- Testing **application-emitted log events**: attach a test appender right on the logger/queue.
- Testing **encoder/console delivery**: flush/await the logging pipeline with a deadline.
- Testing **collector ingestion**: query the test collector/index after ingestion with a bounded wait.

Never use `Thread.sleep(3000)` and claim delivery is proven.

### 11.4. Correlation IDs Are Not Secrets

Correlation IDs serve tracing, yet can indirectly link to users/tenants. Never store raw emails, phone numbers, tokens, or passwords in MDC for “easier log searching”. For business IDs, follow data classification and retention policies.

### 11.5. Negative Assertions in Async Code Are Hard

~~~java
assertThat(output.getAll())
        .doesNotContain("event=job_failed");
~~~

If the worker has not finished, this assertion can PASS even though the error gets logged 200 ms later. Reliable negative assertions require a **completion signal** or observation window with clear semantics. For the lab's synchronous methods, return/exception is the natural boundary; for async, await `Future.get` and the event queue; for external collectors, wait for stabilization/ingestion watermarks when requirements demand it.

## 12. How to Assert Log Levels, Errors, and Stack Traces

### 12.1. Level Is a Field, Not a Substring

Avoid:

~~~java
assertThat(output.getAll()).contains("ERROR");
~~~

“ERROR” could appear in a payload, class name, or unrelated startup line. Logback event:

~~~java
assertThat(failedEvent.getLevel())
        .isEqualTo(Level.ERROR);
~~~

is far more accurate when targeting `log.error` from a specific class. If the contract is console text with an `ERROR` column, parse the line/formatter explicitly.

### 12.2. ThrowableProxy Differs from Raw Throwable

Logback's `ILoggingEvent.getThrowableProxy()` is logging-layer exception metadata. Do not compare full stack traces (line numbers shift on refactors). Test:
- Exception class.
- Error category/reason code.
- Presence or policy-compliant omission of stack traces.
- Absence of tokens/PII in messages.

If testing the exact stack-trace layout of a logging config, write dedicated encoder output tests rather than mixing them into business unit tests.

### 12.3. One Exception Can Produce Multiple Logs

A failure might be logged by the service, controller advice, and retry handler; double logging creates noise and skews alert counts. When a contract demands **one terminal failure event per operation**, scope assertions by `eventId`/`jobId` and check terminal event counts at the responsible boundary.

Do not assert one-ERROR-per-request across the entire JVM when multiple framework layers or concurrent requests emit other logs. Consider a “log once at the boundary, rethrow with context” architecture to reduce duplicate noise.

### 12.4. Preserving the Root Cause Throwable

When catching:

~~~java
catch (RemoteServiceException ex) {
    log.error(
            "event=job_failed category=remote_dependency",
            ex);
    throw ex;
}
~~~

This snippet requires a `RemoteServiceException` definition. Passing the exception as the final argument lets the logger record throwable metadata. Writing `log.error("... {}", ex.getMessage())` can omit the stack trace and type. Still, never log raw exceptions if they contain credentials; sanitize or map to structured error codes per security policy.

## 13. Testing Log Volume and Sampling

### 13.1. Do Not Turn INFO into Spam

A service handling 100,000 items/second and logging INFO per item drives up costs/latency, saturates collectors, and buries terminal events. For aggregate observability:
- Use metric counters/histograms for appropriate high-cardinality quantities.
- Use trace sampling for detailed workflows.
- Log structured terminal warnings/errors or sampled successes.
- Attach `eventId` and correlation for investigation.

### 13.2. Metrics Differ from Logs

If the requirement says “job failure counter increments”, test Micrometer `MeterRegistry`/`SimpleMeterRegistry` rather than asserting a “counter++” log line. If it says OpenTelemetry span attributes, test an in-memory tracer/exporter; logs are merely complementary signals.

### 13.3. Log Sampling Affects Test Expectations

If the logger samples events, a test demanding an INFO log on every success contradicts the design. Test sampling policy at the right layer or disable sampling **deliberately in test config** without extrapolating production ratios from tiny samples.

### 13.4. Logging Has No Global Multi-Threaded Total Order

On a single synchronous thread, events follow code order. With two workers, do not assert `first global line job A, second global line job B` unless scheduling guarantees it. Partition/trace by correlation ID, assert order **per operation** when required, or verify the set of events regardless of order.

## 14. Comparing Three Ways to Capture Logs

| Tool | Strengths | Drawbacks / Pitfalls | Choose When |
| --- | --- | --- | --- |
| `CapturedOutput` | Minimal setup, built into Spring Boot test, checks stdout/stderr | Global streams, depends on console appender, tied to format/timing | Console text is the contract |
| Logback `ListAppender` | Event-level assertions: level, logger, MDC, args, throwable | Tied to Logback, mutable list, needs attach/detach | Service log behavior is the contract |
| Custom queue appender | Thread-safe bounded wait for async events | Extra test utility, lifecycle management | Background/async logs needed |
| Log4j2 test appender | Event-level in Log4j2 | Backend-specific imports/config | App uses Log4j2 |
| Structured JSON capture | Verifies machine-readable contracts | Needs Boot encoder config, parser, line filtering | Collector queries depend on JSON schema |
| Test collector/OTLP sink | Proves ingestion/delivery | Slower, heavier dependencies and retries | Logs/traces must reach external sink |
| Mockito `verify(Logger)` | Can verify calls if a logger abstraction is injected | `static final` loggers are hard to mock; misses formatter/MDC/appenders | Only for explicit DI logger wrappers |

**Preference:** If you only need “ERROR log has category/id and throwable”, a Logback event appender beats matching full console strings. If you need “JSON lines to stdout match ingestion schema”, use output capture + a JSON parser. If logs are not part of the contract, **never capture logs to verify unrelated behavior**.

## 15. Anti-Patterns That Make Logging Tests Low-Value

### 15.1. Asserting Raw Full Log Lines

Timestamp, PID, thread, and ANSI changes break tests across patch upgrades. Assert only stable fields, levels, and event IDs.

### 15.2. Asserting Generic Words

`contains("error")` can match framework or test fixture logs. Use event markers + unique correlation IDs or logger-specific appenders.

### 15.3. Waiting on Async Logs with Sleep

Logs might not emit until after 1 second or might emit in 10 ms. Use `Future`/`BlockingQueue`/`poll` with timeouts.

### 15.4. Attaching Appenders to the Root Logger Without Cleanup

Pollutes JVM-wide events, leaks memory, and duplicates captures across tests. Attach to narrow loggers and detach in `finally`/`@AfterEach`.

### 15.5. Mutating Global Logger Levels Without Restoring

Subsequent tests may see INFO filtered out or unexpected DEBUG noise. Avoid mutating the root logger casually. If changed to test a policy, save and restore the prior level and avoid parallel execution.

### 15.6. Using getErr to Prove ERROR

ERROR events can be written to stdout. Check `getLevel()` on the event rather than guessing from destination streams.

### 15.7. Calling Mockito Verify on a Mock Logger “Log Integration”

Mockito verify only proves a method call on a mock; it never tests SLF4J/Logback/formatting. Valid only when a logger wrapper is an explicitly injected dependency—document that narrow scope.

### 15.8. Asserting Logs Instead of Database Side Effects

“Saved order” can be logged before transaction rollback. Query real data; logs are only diagnostic.

### 15.9. Using @SpringBootTest for Simple println Tests

Wastes context startup time. Plain JUnit + `OutputCaptureExtension` suffices for stream capture.

### 15.10. Claiming @SpringBootTest Reliably Captures Startup Logs

Contexts can be cached; startup runs once. Test startup events with dedicated process/context lifecycle tests.

### 15.11. Using OutputCapture with File-Only Appenders

`CapturedOutput` cannot see file logs bypassing `System.out/err`. Use matching appender/file-sink/collector tests.

### 15.12. Reading Logback ListAppender Before Workers Finish

A mutable list is not an await condition. Use Futures/queue latching; read after completion or via thread-safe test appenders.

### 15.13. Forgetting MDC Cleanup

Thread pool reuse leaks user/correlation contexts. Include tests for restoring previous MDC values and exception paths; use `try/finally`.

### 15.14. Comparing Structured JSON as Raw Strings

Valid changes to metadata, timestamps, or key order make tests brittle. Parse JSON and assert schema-required fields.

### 15.15. Testing Redaction on One Method and Claiming System-Wide Safety

Exceptions, access logs, HTTP client debug logs, SQL bind logs, and collectors can still leak secrets. Define a threat model and test/scan every layer.

### 15.16. Logging Full DTOs or Authorization Headers

Easily leaks PII/tokens, violating privacy/security. Use event field allowlists and log-sanitization tests.

### 15.17. Treating Logs as Durable Audit Events

Logs can be dropped, sampled, or short-lived. For legally durable audit trails, use an audit datastore/outbox with retention/access controls and readback tests.

### 15.18. Counting Events Across the Whole JVM

Frameworks and concurrent tests emit extra logs, causing false positives/negatives. Filter by logger + event ID/test run ID.

### 15.19. Ignoring JUL/Log4j2 Stream Binding

`ConsoleHandler`/Appenders can retain old streams. Reset JUL per docs; set Log4j2 `ConsoleAppender` `follow=true`. Never mix configs across backends.

### 15.20. Enabling Parallel Tests While Redirecting Global System Streams

Tests can capture each other's output or corrupt stream restoration. Use JUnit resource locks, sequential execution, or fork isolation; never assume `OutputCapture` separates streams per thread.

## 16. Diagnosing Empty CapturedOutput or Failing Assertions

| Symptom | Likely Cause | How to Check |
| --- | --- | --- |
| `getOut()` empty on `log.info` | Logger level/filter blocked it | Check INFO enabled / logger config |
| `getErr()` empty on `log.error` | Console appender writes to stdout | Check event level via appender |
| Present in `ListAppender` yet empty in `CapturedOutput` | File appender / stream binding / capture lifecycle | Check backend, console config, initialization |
| JUL logging not captured | `ConsoleHandler` holds old `System.err` | Reset JUL per `OutputCaptureExtension` docs |
| Log4j2 logging not captured | `ConsoleAppender` doesn't follow stream | Set `follow=true` |
| `@SpringBootTest` misses startup message | Context cached/created before capture | Run dedicated startup test/process |
| `ListAppender` sees zero events | Attached to wrong logger/class or filtered by level | Check logger hierarchy, exact class, filters |
| `ListAppender` sees too many events | Attached to root/shared logger | Attach to narrow service logger |
| INFO event exists yet format assertion fails | Brittle exact-line assertion | Assert event fields or stable substrings |
| MDC in event is empty | Never set or lost across async thread | Check MDC scope/context propagation |
| MDC lingers on thread after method | Missing cleanup | `try/finally` + restore previous |
| Async test intermittently empty | Asserted before worker/event finished | `Future.get` + `BlockingQueue` await |
| Test passes even though credentials leak elsewhere | Captured only one logger/sink | Expand log sources and redaction checks |
| JSON parsing fails | Text logs/ANSI/startup lines mixed with JSON | Isolate profile/fork, filter JSON lines |
| Subsequent tests fail after log test | Appender/level/global stream not restored | `@AfterEach`/`finally`, avoid parallel |
| “job_completed” logged when actually failed | Logged too early before commit | Move terminal event post-confirmation; assert business state |
| Duplicate error events | Multiple layers log the same exception | Define log-once boundary and test correlation |
| Maven tests green while logs are wrong | Log behavior untested | Add contract-specific assertions |
| Collector misses event despite console test pass | Shipper/transport/ingest failure | Test sink delivery/index queries separately |

### 16.1. Step-by-Step Debugging Order

1. Which log is actually required? Event name, level, fields, formatter, or collector?
2. Did the real service enter the logging branch? Assert business outcomes.
3. Is the logging backend Logback, Log4j2, JUL, or an adapter?
4. Do logger levels/filters allow the event to emit?
5. If using `CapturedOutput`, does the appender write to `System.out/err`?
6. If using `ListAppender`, was it attached to the right logger **before** the action?
7. Does the test run asynchronously? Did you await completion properly?
8. Are tests running in parallel or mutating global streams?
9. Is MDC set and restored properly?
10. For structured output, does JSON use the expected fields and encoding?
11. For collectors, did the test inspect the real sink or only the console?
12. Are secrets, PII, or sensitive error payloads being logged?

## 17. Practical Exercises

1. Run `OutputCaptureExamplesTest` and distinguish `getOut`, `getErr`, and `getAll`.
2. Add a `System.err.println` and verify it does not create a Logback `Level.ERROR` event.
3. Write a `CapturedOutput` test for INFO console logs under Spring Boot's default Logback; explain conditions that leave output empty.
4. Replace full log-line equality with assertions on event name and job ID.
5. Attach `ListAppender` to `JobLogService`'s logger; verify level and message template.
6. Compare `getMessage()` with `getFormattedMessage()` and `getArgumentArray()`.
7. In the completion branch, remove `jobId` from the logger format and see which regression assertion fails.
8. Change the job rejection level from WARN to INFO; confirm the level test catches the bug.
9. Simulate an exception and verify the ERROR event carries a `ThrowableProxy` of the right type.
10. Remove MDC cleanup in an experimental branch and watch the restore test catch the leak.
11. Seed a pre-existing caller MDC value and verify the service restores the exact prior value after the call.
12. Keep `correlationId` across two log events while moving execution to an executor thread; verify propagation.
13. Use the queue appender to await events from a worker thread without sleeping.
14. Try reading `ListAppender` right after submit before `Future.get`; explain the race.
15. Enable JUnit parallel execution across two tests sharing a logger to observe state pollution, then add resource isolation.
16. Check that no synthetic token appears in formatted messages, MDC, or exceptions.
17. Pass a `jobId` containing newline/CRLF; verify input is rejected before logging.
18. Enable `logging.structured.format.console=ecs` in a separate test profile/process and parse JSON with Jackson.
19. Assert ECS `log.level`, `message`, and `correlationId` without asserting exact timestamps.
20. Use SLF4J fluent `addKeyValue` and verify the JSON `eventName` field instead of grepping strings.
21. Switch to a Log4j2 test fixture, configure `ConsoleAppender` `follow=true`, and run `OutputCapture`.
22. Use JUL `ConsoleHandler` and test resetting configuration after tests for reliable capture.
23. Enforce a log-once policy: exceptions across service and controller advice must not emit two terminal events for the same `jobId`.
24. Replace INFO success logging with sampling and identify which tests must adjust per contract.
25. Write a collector integration test: emit a log, await ingestion, and query the index by correlation ID.
26. Use Micrometer `SimpleMeterRegistry` to test failure metrics separately rather than inferring metrics from logs.
27. Design a durable audit trail via database/outbox and contrast it with console log capture.
28. Write a test verifying secret redaction on HTTP client/access logs when an Authorization header is present.
29. Build a checklist covering log retention, sampling, structured schemas, and correlation IDs for on-call dashboards.
30. Review a test asserting only `"ERROR"` in stdout; refactor it into level + logger + reason code + outcome assertions.

## 18. Pre-Merge Checklist

- [ ] Is logging genuinely an observable behavior per requirements rather than an implementation detail?
- [ ] Do tests still assert business outcomes/side effects/exceptions separately?
- [ ] Chose the right layer: system streams, Logback events, JSON encoder, or collector?
- [ ] `OutputCaptureExtension` registered on the JUnit 5 class and `CapturedOutput` injected properly?
- [ ] Distinguished `getOut`, `getErr`, and `getAll`?
- [ ] Avoided treating `getErr` as equivalent to `ERROR` level?
- [ ] Confirmed `ConsoleAppender`/backend writes to the captured stream?
- [ ] Tests avoid depending on full timestamp/PID/thread/ANSI formats?
- [ ] Used stable event names and unique `jobId`/`correlationId`?
- [ ] Assertions bind fields to **the exact same event** when required by contract?
- [ ] Appender attached to the right logger before the action?
- [ ] Appender detached/stopped after tests, even on failures?
- [ ] Global root logger level never altered without restoring?
- [ ] When using `ListAppender` with async code, completion synchronization is present?
- [ ] Bounded queue/future awaits used instead of fixed sleeps?
- [ ] MDC set/propagated/restored properly without leaking across thread pools?
- [ ] Exception events have the exact level, reason/category, and throwable?
- [ ] Success/rejection/failure branches never emit the wrong terminal event?
- [ ] Verified secrets/PII are absent from covered log surfaces?
- [ ] Untrusted input sanitized/escaped against CRLF injection?
- [ ] For structured JSON, parsed fields rather than matching raw lines?
- [ ] JSON field names/versions match downstream contracts?
- [ ] JUL/Log4j2 console capture has appropriate backend configuration?
- [ ] Tests do not rely on startup logs hidden by Spring TestContext caching?
- [ ] Parallel JUnit classes isolate System streams and shared loggers?
- [ ] Log sampling/retention/ingestion tested at the appropriate layer when needed?
- [ ] Never treated console logs as durable audit or queue events?
- [ ] Maven/JUnit reports actually executed with a successful exit code?
- [ ] No real user data or real credentials in test fixtures?
- [ ] Assertions specific enough to catch regressions without breaking on valid formatter changes?

**Conclusion:** When logs form part of the observability contract, test them directly with tools matched to the right boundary. `OutputCaptureExtension` and `CapturedOutput` fit `System.out/err` text or console-rendered logs; Logback `ListAppender` is better for checking level, template, arguments, MDC, and throwables; queue-backed appenders enable bounded waits on async logs. Avoid snapshotting entire logs, avoid substituting logs for business outcomes, manage global streams and logger state carefully, and test structured JSON or collectors when genuinely needed. A logging test is most valuable when it fails only because the **observability contract was broken**, not because timestamps, threads, or console formatters shifted.

## 19. Official Documentation and References

- Spring Boot 3.5 — Test Utilities / OutputCaptureExtension: https://docs.spring.io/spring-boot/3.5/reference/testing/test-utilities.html
- Spring Boot 3.5 — CapturedOutput API (getOut/getErr/getAll): https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/system/CapturedOutput.html
- Spring Boot 3.5 — OutputCaptureExtension API: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/system/OutputCaptureExtension.html
- Spring Boot 3.5 — Logging, Logback defaults, MDC and structured formats: https://docs.spring.io/spring-boot/3.5/reference/features/logging.html
- Spring Boot 3.5 — Logging How-to, Log4j2 configuration: https://docs.spring.io/spring-boot/3.5/how-to/logging.html
- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 — Observability: https://docs.spring.io/spring-boot/3.5/reference/actuator/observability.html
- SLF4J — User manual (logger, MDC, fluent API): https://www.slf4j.org/manual.html
- Logback — Appenders manual: https://logback.qos.ch/manual/appenders.html
- Logback — MDC manual: https://logback.qos.ch/manual/mdc.html
- Logback — ILoggingEvent API: https://logback.qos.ch/apidocs/ch.qos.logback.classic/ch/qos/logback/classic/spi/ILoggingEvent.html
- Logback — ListAppender API: https://logback.qos.ch/apidocs/ch.qos.logback.core/ch/qos/logback/core/read/ListAppender.html
- JUnit Jupiter 5 — Extension Model: https://junit.org/junit5/docs/current/user-guide/#extensions
- JUnit Jupiter 5 — Parallel Execution and @ResourceLock: https://junit.org/junit5/docs/current/user-guide/#writing-tests-parallel-execution
