# Publishing Domain-Specific Audit Events via ApplicationEventPublisher

When someone exports a report, operators may need to answer: who performed it, which action completed, on which report, and under which request? Free-form log lines are often hard to query consistently. An audit event represents that information as a structured record.

This lesson uses Spring Boot Actuator 3.3.x to publish business events via `ApplicationEventPublisher`. After this lesson, you will be able to construct `AuditApplicationEvent`, provide a sink for records, verify stored data, and choose a publication point aligned with the event's meaning.

## 1. From a business action to an audit record

Suppose the system has a report export action. The application's convention is:

- `REPORT_EXPORT_REQUESTED`: the export request has been accepted.
- `REPORT_EXPORTED`: the export has completed per business criteria.
- `REPORT_EXPORT_DENIED`: the export request was denied.

These names are chosen by the application; Actuator does not automatically infer them from method names or HTTP status codes. A successful login also does not mean the user exported a report. Therefore, built-in security events and business audit events complement each other.

Spring Boot supports business auditing by writing directly to `AuditEventRepository` or publishing `AuditApplicationEvent` through Spring's event mechanism. With event publication, the business layer only needs to know the publisher; persistence is delegated to the listener side. [Spring Boot 3.3 Auditing Documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/auditing.html).

Standard flow once auditing infrastructure is configured:

```text
Business action reaches a milestone worth recording
    -> ApplicationEventPublisher.publishEvent(AuditApplicationEvent)
    -> event dispatching mechanism in ApplicationContext
    -> Actuator's AuditListener
    -> AuditEventRepository.add(AuditEvent)
```

`ApplicationEventPublisher` dispatches events. `AuditEventRepository` stores and queries records. These two responsibilities must be kept distinct: calling `publishEvent(...)` does not by itself prove a durable record exists.

## 2. Three data types to distinguish

| Component | Role | Usage in this lesson |
| --- | --- | --- |
| `ApplicationEventPublisher` | Spring's event-publishing interface | Injected via constructor, calls `publishEvent(...)` |
| `AuditApplicationEvent` | Spring event wrapping an `AuditEvent` | Object published for Actuator's audit listener to receive |
| `AuditEvent` | Audit data | Object stored in the repository and read back for verification |

An `AuditEvent` has four key fields:

| Field | Meaning | Example |
| --- | --- | --- |
| `principal` | Identity of the performing actor | `alice` or a system job identity |
| `type` | Event type following a stable convention | `REPORT_EXPORTED` |
| `timestamp` | Record timestamp of type `Instant` | Generated when building the record if not passed explicitly |
| `data` | Supplementary info of type `Map<String, Object>` | Report ID, request ID, outcome |

Common construction pattern:

```java
Map<String, Object> data = Map.of(
        "reportId", "report-42",
        "requestId", "req-001",
        "outcome", "SUCCESS");
publisher.publishEvent(
        new AuditApplicationEvent("alice", "REPORT_EXPORTED", data));
```

The snippet above is an excerpt inside a bean injected with `ApplicationEventPublisher`; it requires importing `java.util.Map` and `org.springframework.boot.actuate.audit.listener.AuditApplicationEvent`.

You can also construct `AuditEvent` first and wrap it with `new AuditApplicationEvent(auditEvent)`. This is useful when passing a specific business timestamp using the constructor that accepts `Instant`. Do not pass a client-supplied timestamp as trusted time evidence without clearly verifying the data source. [`AuditApplicationEvent` API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/actuate/audit/listener/AuditApplicationEvent.html). The constructors used here exist in Spring Boot 3.3.0.

### Why not publish AuditEvent directly?

```java
publisher.publishEvent(new AuditEvent(
        "alice", "REPORT_EXPORTED", Map.of("reportId", "report-42")));
```

This snippet can compile with the corresponding imports, yet it does not enter `AuditListener`'s default handling path. `AuditEvent` is data; `AuditApplicationEvent` is the event type that this listener subscribes to. Spring's event mechanism can wrap ordinary objects into payload events, but it does not automatically convert them into `AuditApplicationEvent`. When using the default listener, publish the proper wrapper class.

### Data conventions for consistent querying

- Keep `type` stable; put target IDs in `data`, such as `type=REPORT_EXPORTED` and `data.reportId=report-42`. Avoid creating a new type per report.
- Obtain `principal` from an identity source verified by the application. In an application with Spring Security, take the name from verified authentication info; do not trust an arbitrary `username` field in the request body.
- For scheduled jobs, use a clearly defined system identity, such as `system:report-job`.
- Put only data needed to explain the action into `data`; choose strings, numbers, or simple values supported by the store. Avoid putting JPA entities, request objects, or the entire report payload.
- Do not put passwords, access tokens, session IDs, or secrets into records. Request IDs correlate observations and do not replace authorization checks.
- Snapshot data at publication time; do not continue mutating nested structures and expect receivers to see the original state. `Map.of(...)` creates an unmodifiable map, but objects inside it can still change if you pass stateful objects.

`Map.of(...)` does not accept `null` keys or values. If a request ID can be missing, decide to omit that field or reject the input per the application's contract; do not let a map-creation error happen unexpectedly after the business action.

## 3. Conditions for Actuator to store events automatically

In Spring Boot 3.3's default configuration, adding the Actuator starter alone is not enough to have an audit store. You must provide an `AuditEventRepository` bean.

```java
@Bean
AuditEventRepository auditEventRepository() {
    return new InMemoryAuditEventRepository(100);
}
```

This is a configuration method excerpted from the complete example in the next section. This in-memory store suits testing: it needs no database and can be read back immediately in the same process.

`AuditAutoConfiguration` requires an `AuditEventRepository` bean and `management.auditevents.enabled` not disabled. The default `AuditListener` bean is created only when no bean of type `AbstractAuditListener` already exists. If you replace this listener, verify whether the replacement still performs storage as desired. [`AuditAutoConfiguration` 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/audit/AuditAutoConfiguration.html).

Commonly confused cases:

- No repository: this automatic storage path is not configured; publishing an event may still complete without a corresponding listener.
- Repository present, `management.auditevents.enabled=false`: auditing auto-configuration is disabled, so you cannot expect the default listener to call `add(...)`.
- Custom listener present: the result depends on how that listener is registered and implemented.
- In-memory repository present: records exist only in process memory and are bounded by configured capacity. Another instance does not automatically see this data.

To store long-term or aggregate across multiple instances, implement `AuditEventRepository` backed by the system's store. When choosing storage, define querying, retention, and error handling according to real needs. Spring Boot recommends the in-memory store for development environments. [Guide to choosing an audit repository](https://docs.spring.io/spring-boot/3.3/reference/actuator/auditing.html).

## 4. Runnable standalone example

The example verifies only publishing and receiving the event. `recordExportCompleted(...)` records work already confirmed complete by the business side; it does not generate a report file and does not pretend to perform actual report-export business logic.

Requirements: JDK 17 or later and Maven. The code uses Java 17 language level and can run on JDK 21. The Spring Boot version is pinned to 3.3.0 to reproduce an example in the 3.3.x line.

The application runs as a command-line app without starting an HTTP server. Thus you can learn the auditing mechanism without creating controllers, configuring endpoints, or introducing Spring Security into the example.

Standalone test project structure:

```text
audit-publisher-demo/
├── pom.xml
└── src/main/java/example/audit/AuditDemoApplication.java
```

### 4.1. Declaring dependencies

Contents of `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>audit-publisher-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
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
```

The Actuator starter brings the components needed for the example onto the classpath. Do not manually add separate versions for individual Spring libraries, since the Spring Boot parent manages the aligned version set.

### 4.2. Configuring the repository and publishing the event

Contents of `src/main/java/example/audit/AuditDemoApplication.java`:

```java
package example.audit;

import java.time.Instant;
import java.util.List;
import java.util.Map;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.actuate.audit.AuditEvent;
import org.springframework.boot.actuate.audit.AuditEventRepository;
import org.springframework.boot.actuate.audit.InMemoryAuditEventRepository;
import org.springframework.boot.actuate.audit.listener.AuditApplicationEvent;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication(proxyBeanMethods = false)
public class AuditDemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(AuditDemoApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);
        application.setDefaultProperties(
                Map.of("logging.level.root", "OFF"));

        try (ConfigurableApplicationContext context =
                     application.run(args)) {
            context.getBean(ReportAuditService.class)
                    .recordExportCompleted("alice", "report-42", "req-001");

            AuditEventRepository repository =
                    context.getBean(AuditEventRepository.class);
            List<AuditEvent> events = repository.find(
                    "alice", Instant.EPOCH, "REPORT_EXPORTED");
            if (events.size() != 1) {
                throw new IllegalStateException(
                        "Expected one audit event, got " + events.size());
            }

            AuditEvent event = events.get(0);
            System.out.println("count=" + events.size());
            System.out.println("principal=" + event.getPrincipal());
            System.out.println("type=" + event.getType());
            System.out.println("reportId=" + event.getData().get("reportId"));
            System.out.println("requestId=" + event.getData().get("requestId"));
            System.out.println("outcome=" + event.getData().get("outcome"));
        }
    }

    @Bean
    AuditEventRepository auditEventRepository() {
        return new InMemoryAuditEventRepository(100);
    }

    @Bean
    ReportAuditService reportAuditService(
            ApplicationEventPublisher publisher) {
        return new ReportAuditService(publisher);
    }

    public static class ReportAuditService {
        private final ApplicationEventPublisher publisher;

        public ReportAuditService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void recordExportCompleted(
                String principal, String reportId, String requestId) {
            requireText(principal, "principal");
            requireText(reportId, "reportId");
            requireText(requestId, "requestId");

            Map<String, Object> data = Map.of(
                    "reportId", reportId,
                    "requestId", requestId,
                    "outcome", "SUCCESS");
            publisher.publishEvent(new AuditApplicationEvent(
                    principal, "REPORT_EXPORTED", data));
        }

        private static void requireText(String value, String name) {
            if (value == null || value.isBlank()) {
                throw new IllegalArgumentException(name + " is required");
            }
        }
    }
}
```

Key points to follow:

1. `ReportAuditService` receives `ApplicationEventPublisher` via its constructor. Since the object is declared with `@Bean`, Spring injects the publisher; there is no need to implement `ApplicationEventPublisherAware` just to obtain it.
2. `requireText(...)` validates inputs before publishing. In the example, `alice` is fixed data to observe the flow; in real integration, the caller must pass an identity from a trusted source.
3. The event carries `principal=alice`, type `REPORT_EXPORTED`, and three data fields. There is no direct `repository.add(...)` call inside the service.
4. The `InMemoryAuditEventRepository(100)` bean enables Actuator auto-configuration to set up the audit storage listener. Capacity 100 is an example choice.
5. After publishing, `main` reads back the repository and verifies there is exactly one record. This verifies both the publish path and the storage path, going beyond merely seeing that `publishEvent(...)` was called.
6. `Instant.EPOCH` is chosen as a boundary before the newly created record. Filtering by principal and type prevents picking up unrelated events. The example does not print the whole map, so it does not depend on `Map.of(...)` iteration order.
7. Upon exiting the `try` block, the context closes and the application terminates. The in-memory store does not preserve history for the next run.

### 4.3. Compiling and running

In the directory containing `pom.xml`, run:

```shell
mvn -q package
java -jar target/audit-publisher-demo-1.0.0.jar
```

Maven needs to download plugins and dependencies on the first run if not already cached. Because the project depends on Spring, it cannot be compiled using `javac AuditDemoApplication.java` alone without providing the classpath.

Program stdout with the configuration above:

```text
count=1
principal=alice
type=REPORT_EXPORTED
reportId=report-42
requestId=req-001
outcome=SUCCESS
```

The banner and startup logs were turned off in code so the output is easy to inspect. The timestamp is not printed because it is generated at runtime; do not write down a fixed timestamp and treat it as the output of every run.

### 4.4. Why is /actuator/auditevents not needed yet?

Storing records and allowing access to records over HTTP are two separate concerns. The example reads `AuditEventRepository` directly, so exposing the endpoint is unnecessary. In a web application, exposure and access permissions only need configuration when you want to provide a read interface via Actuator; do not use exposing the endpoint as a substitute for configuring the repository. Audit records can contain sensitive data, so grant read permission only to appropriate principals when deploying that interface.

## 5. What does calling publishEvent mean for execution timing?

With Spring's default dispatcher, regular listeners are invoked synchronously on the publishing thread. Therefore, right after the example publishes and reads the repository, the record has already been added by the in-memory listener. If the dispatcher configuration is changed or asynchronous handling is used, that timing can differ. The publisher interface itself does not guarantee every application always processes events the same way. [Event Mechanism in ApplicationContext](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events).

Integration consequences to consider:

- A slow storage listener can slow down the business call under synchronous configuration.
- Errors from a synchronous listener can propagate back to the publisher unless another error-handling mechanism exists.
- Adding asynchronous processing requires accounting for read timing, error handling, and identity context. Put required data into the event instead of assuming another thread still has the original request's context.
- This internal event does not automatically become a message sent to another process. Sending to external systems requires a dedicated integration mechanism.

Because `publishEvent(...)` does not return a storage receipt, the observability criterion should be that the record appeared in the right store, with the right content, and at the right time required by design.

## 6. Placing publication timing according to business meaning

In the example, the caller confirmed the action completed before calling `recordExportCompleted(...)`. With transactional data, clarify whether "completed" means execution reached a line of code or the transaction committed.

### 6.1. Publishing inside a transaction does not mean committed

Scenario to avoid:

```text
Begin transaction
    -> update report status
    -> publish REPORT_EXPORTED
    -> listener writes to in-memory store
    -> error occurs in next step
Transaction rolls back
```

An in-memory store does not automatically roll back alongside the database. The result can be a record claiming export succeeded even though the business update was aborted. Placing the publish call after `save(...)` also does not prove a commit happened.

Decide based on the semantics you need:

| What needs recording | Timing to consider |
| --- | --- |
| An attempt was accepted | After identifying request and actor; use a name indicating request or attempt |
| A denial decision was made | At the denial decision point, with minimal data explaining the decision |
| Database change has committed | After commit or designed to store in the same transaction as business data |
| Evidence must remain even if business transaction rolls back | A storage path with an independent transaction policy and separate verification |

### 6.2. When recording after commit is needed

One approach is to publish a domain event inside the transaction and translate it into an audit event in an after-commit listener:

```text
Business method runs inside transaction
    -> publish domain event ReportExportCompleted
    -> transaction commits
    -> bean with @TransactionalEventListener(AFTER_COMMIT) receives domain event
    -> publish AuditApplicationEvent
    -> AuditListener stores audit record
```

This is an integration diagram, not code running inside the command-line example. Suitable transaction management and registered listener beans are required.

`@TransactionalEventListener` executes at `AFTER_COMMIT` by default; when there is no transaction, the listener is not invoked by default unless `fallbackExecution` is enabled. If writing to a database after commit, design a separate write transaction appropriately, because you cannot rely on the old transaction to commit further changes. [Spring Framework 6.1 TransactionalEventListener API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html).

Do not merely add a second after-commit listener for `AuditApplicationEvent` and assume the default listener will wait alongside it. The built-in storage listener still has its own execution path. The diagram keeps domain events and audit events separated in timing: publish `AuditApplicationEvent` only once the milestone to record is reached.

After commit, a window still exists where the process could stop before audit storage finishes. If losing an event on process crash is unacceptable, design durable storage—such as saving an outbox record in the same business transaction and processing it onward. `ApplicationEventPublisher` alone does not provide that guarantee.

## 7. Avoiding duplicate writes and understanding failure policies

### 7.1. Choose one storage path per recorded action

Do not do both of the following for the same recorded action while the default listener is active:

```java
repository.add(auditEvent);
publisher.publishEvent(new AuditApplicationEvent(auditEvent));
```

This is an erroneous snippet, not code to add to the example. The first call already added the record; the subsequent publish can cause the listener to add it again. A custom observer-only listener should also not call `add(...)` again while the default storage path is running.

Similarly, calling `recordExportCompleted(...)` twice produces two publications. `requestId` is just accompanying data; Actuator does not automatically deduplicate simply because two records share the same request ID.

Distinguish two business questions:

- Two genuinely distinct export requests: two records may be needed, even for the same report.
- The same event resent due to a retry: identification may be needed to avoid storing twice per chosen policy.

If deduplication is required, define a stable event ID and enforce the rule in the appropriate storage layer. Do not assume using an unmodifiable map creates a deduplication mechanism.

### 7.2. Deciding behavior when storage fails

The in-memory store example illustrates the success path and does not describe the failure policy of a remote store. Before integrating a real store, decide:

- Should the business action proceed if audit writing fails?
- If business work committed but audit writing failed, where is the information retained for reprocessing?
- How can failures be observed without writing extra secret data to logs?
- On retry, how is a replay distinguished from a new action?

Do not catch and ignore all exceptions just to keep output clean. Also do not assume an error on the caller side means business work did not occur: a listener can fail after business work already completed.

## 8. Verification and diagnostic practice

Each experiment below starts from a fresh run to avoid mixing data from prior experiments.

| Change | What to observe | Explanation |
| --- | --- | --- |
| Keep example as-is | One record, six stdout lines as above | Correct publish path, listener, and storage |
| Call service twice with same args | Repository holds two records | No deduplication mechanism yet |
| Pass blank string for `principal` | `IllegalArgumentException` before publishing | Input guard checked by service |
| Publish plain `AuditEvent` instead of `AuditApplicationEvent` | Default listener does not add that record | Wrong event type published for standard audit path |
| Disable `management.auditevents.enabled` | Repository may still exist but receives no record via default listener | Disabling auto-config does not delete your declared repository bean |
| Re-run the process | In-memory data from prior run is gone | No durable storage |

When testing two calls, update the check in `main` to expect two records; if you keep `events.size() != 1`, the program intentionally throws an error. When testing auditing disabled, the current check also reports `Expected one audit event, got 0`; that matches the experiment.

You can pass the property disabling auditing to the packaged JAR:

```shell
java -jar target/audit-publisher-demo-1.0.0.jar --management.auditevents.enabled=false
```

If you expect data yet queries find nothing, inspect along the record's path:

1. Is the publishing bean actually managed by Spring and was the publish method invoked?
2. Is the published object actually an `AuditApplicationEvent`?
3. Is there an `AuditEventRepository` bean, is auditing disabled, and was the default listener replaced?
4. Do the `principal`, `type`, and timestamp query filters match the record?
5. Are you reading the same process/instance that wrote it, and was data evicted by capacity limits or lost after restart?
6. Was handling switched to asynchronous, or did the store report an error?

To verify at different levels, you can unit-test the event object produced by the service, then integration-test by starting the context and reading the repository as in the example. When replacing the in-memory store with durable storage or adding transactions, add verification for commit, rollback, write failures, and retries per real requirements.

## 9. Self-check on understanding

**Why is there still no data after calling `publishEvent(...)`?** The publisher does not automatically create a repository or guarantee a storage listener exists. Check event type, auditing configuration, query filters, and the storage target as well.

**Is `ApplicationEventPublisherAware` mandatory?** No. In the example, Spring supplies `ApplicationEventPublisher` as a `@Bean` method parameter and passes it to the service constructor.

**Is Spring Security required for the business event in the example?** No. The publisher supplies the identity; if the application has authentication, connect the verified identity into the audit data.

**What does a record existing in memory suffice to prove?** It proves the publish and receive path inside the running process worked. It does not prove data survives restarts, was shared across instances, or that the business operation committed.

**What is the decisive point when designing an event?** The event name must accurately reflect what happened at the moment of publication. Only then choose the accompanying data, storage path, and durability guarantees needed to preserve that meaning.
