# Handling Personal Data in Logs When Using Spring Application Events

## 1. Why Can Logging Events Become a Security Incident?

Spring Application Events enable parts of an application to react to a business fact such as `CustomerProfileUpdated`, `PaymentCaptured`, or `AccountAccessDenied`. Listeners often log for diagnostics: which event type was published, where it was handled, how long it took, and why it failed.

However, **being in the event payload does not mean the data is safe to log**. Payloads can include names, emails, phone numbers, addresses, identification numbers, health information, notification bodies, payment histories, or indirect fields that help identify an individual. An unsafe log line can create a new copy of data outside the access controls of the business database.

Counterexample design:

```java
@EventListener
public void on(CustomerProfileUpdated event) {
    logger.info("Received event: {}", event);
}
```

This is an **incomplete illustrative snippet**: the class, logger, and event are application-defined. If `CustomerProfileUpdated` is a Java record, a Lombok `@Data` class, or an object whose `toString()` prints all fields, this style can push raw emails, addresses, phone numbers, or customer notes straight into logs.

Even when intended only for debugging, logs can be copied across consoles, container runtimes, log collectors, monitoring SaaS platforms, archives, backups, and search indexes. Log access permissions often differ from database access permissions, so leaks happen even when the primary API enforces access control properly.

**Core principle:** log **what is needed to operate and investigate**, never dump entire domain events. Practice data minimization, use an allowlist of permitted fields, define purpose/retention, protect storage, and write tests against leaks.

## 2. Three Layers of Information to Distinguish

| Data Layer | Examples | Should It Be Logged? |
| --- | --- | --- |
| **Domain payload** | Old/new email, address, amount, user profile | Only when genuinely required and authorized; never dump wholesale by default |
| **Event/operation metadata** | Event type, random event ID, outcome code, duration | Usually helpful; still classify and bound |
| **Execution/tracing context** | Trace ID, correlation ID, tenant, actor, MDC | Conditionally useful; do not assume it is anonymous |
| **Secrets/credentials** | JWT, session cookies, API keys, passwords, encryption keys | **Never log directly** |
| **Operational diagnostics** | Exception type, stable error code, consumer name | Usually safer than raw exception messages/HTTP bodies |
| **Audit evidence** | Actor, action, target, timestamp, result | Needs its own contract, permissions, and retention; not automatically equivalent to debug logs |

An **opaque customer ID** can still be considered personal data if it can be linked back to a person. Replacing an email with `customerId` reduces direct exposure, yet **does not turn the log into anonymous data**. Likewise, tenant IDs and trace IDs can correlate behavior across services; govern them according to internal policy.

### Direct and Indirect Personal Data

Direct personal data may include emails, phone numbers, photos, or government ID numbers. Indirect data may include IPs, device identifiers, a stable identifier, or a combination of attributes sufficient to identify someone. Sensitivity also depends on applicable laws, context, and data linkability.

Avoid applying a rigid rule like "only emails and phone numbers are sensitive." A customer code may look meaningless, yet if someone reading logs also has CRM query access, they can immediately identify the user.

## 3. What Should Be Logged to Diagnose Application Events?

A helpful log line when a listener succeeds might look like:

```text
event_type=CustomerProfileUpdated
event_id=6244b752-bd2b-4aa3-8120-a835ca600ce2
handler=profile-audit
outcome=SUCCESS
duration_ms=14
```

Here the event ID is an illustrative UUID, not a customer ID. The log line **does not** need old/new emails, full names, addresses, or profile content to answer "did the handler process this event?".

If the listener fails:

```text
event_type=CustomerProfileUpdated
event_id=6244b752-bd2b-4aa3-8120-a835ca600ce2
handler=profile-audit
outcome=FAILED
error_code=PROFILE_AUDIT_UNAVAILABLE
```

You do not necessarily need to log the raw payload or `exception.getMessage()`. For real errors, stack traces are sometimes needed for debugging, yet exception messages, causal chains, and stack frames can also contain query parameters, URLs, file paths, usernames, or customer-supplied data. Have a safe exception-handling policy.

### Recommended Log Contract

| Field | Example | Constraints |
| --- | --- | --- |
| `event_type` | `CustomerProfileUpdated` | Value from a defined enum/constant |
| `event_id` | UUID v4/v7 or opaque ID | Do not embed emails/user identifiers inside the ID |
| `handler` | `profile-audit` | Low cardinality; never use customer names |
| `outcome` | `STARTED/SUCCESS/FAILED/SKIPPED` | Finite set of values |
| `error_code` | `DOWNSTREAM_TIMEOUT` | Stable error code rather than raw response body |
| `duration_ms` | `14` | Timing measurement; carries no payload |
| `correlation_id` | Tracing ID issued at ingress | Never treat an arbitrary string as authenticated |
| `tenant_ref` | Opaque tenant ID, if truly required | May be sensitive depending on the system |
| `subject_ref` | Pseudonymous reference, if required | Potentially re-identifiable; restrict access and retention |

Not all fields are mandatory. A successful event-processing log may only need `event_type`, `event_id`, `outcome`, and duration. Adding a field requires a concrete operational reason, not "more data is always better."

## 4. Data That Should Never Be Logged Directly

Following OWASP Logging Cheat Sheet practices, many categories of data should be excluded or protected before writing logs:

- Passwords, OTPs, recovery codes, security answers.
- Access/refresh tokens, JWTs, bearer headers, session IDs, and cookies.
- Encryption keys, API secrets, private keys, and connection strings containing credentials.
- Payment card numbers, security codes, bank accounts, or sensitive payment payloads.
- Government IDs, health records, and highly protected personal data.
- Full request/response bodies, file uploads, and webhook payloads that may carry user data.
- Raw `Authentication`, `SecurityContext`, principals, or sensitive authorities.
- Internal data exceeding the classification level permitted for the logging platform.

For names, emails, phone numbers, addresses, or IPs, policy may depend on logging purpose and legal obligations. **Never assume "partially masked" means safe to store indefinitely.** Prefer not collecting it when unnecessary.

### Dangerous Examples in Spring

```java
logger.debug("event={}", event);
logger.error("request failed: {}", request.getParameterMap());
logger.info("headers={}", headers);
logger.warn("failed to authenticate {}", authentication);
logger.error("external call failed: {}", responseBody);
```

These are counterexample snippets; the variables on each line are purely illustrative. They can dump every domain/request/transport field into logs. Even at `DEBUG` severity, the data remains dangerous: enabling debug once to investigate an incident can produce numerous copies that are hard to purge.

**Alternative:** log a predefined operation type and outcome, plus an ID that does not directly contain personal data. If you need to inspect the actual record, access business data through tools with proper authorization and auditing rather than building a copy of the data inside logs.

## 5. Distinguishing Payload Protection from Log Protection

A domain event may need to carry data that another listener must use:

```java
public record CustomerEmailChanged(
        UUID eventId,
        String customerRef,
        String previousEmail,
        String newEmail,
        Instant occurredAt) {
}
```

This is an illustrative record; it requires importing `UUID` and `Instant`. An email in the **event** may have a clear business purpose, such as updating a contact index. However, the **log listener** does not need the email to prove processing completed.

```java
@EventListener
public void on(CustomerEmailChanged event) {
    updateIndex(event.customerRef(), event.newEmail());

    logger.info(
            "event_type=CustomerEmailChanged event_id={} outcome=SUCCESS",
            event.eventId());
}
```

This is a snippet requiring a logger, `updateIndex(...)`, and an appropriate listener bean. It is not a standalone program.

If a consumer only needs to know "the email changed" and can query an authorized source, the event could even carry just **customer ID + event ID** instead of raw emails. That is a separate architectural decision: querying at processing time might observe a *newer* state than the original fact, so some consumers genuinely require a snapshot. Either way, logging is not automatically entitled to dump the whole payload.

**Two-tier data minimization:** minimize the published payload to what consumers need, and minimize what part of the payload may be emitted to logs/traces/metrics.

## 6. Counterpattern: toString(), Records, and Lombok

Java records automatically generate `toString()` exposing all components. Lombok `@Data` or `@ToString` can also generate representations containing sensitive fields. Thus:

```java
record UserRegistered(String email, String phone) {}

logger.info("{}", new UserRegistered(
        "person@example.invalid", "+10000000000"));
```

The log line can contain both the raw email and phone number. Do not merely customize `toString()` to mask fields and keep dumping whole objects everywhere. A later class adding an `accessToken` field could introduce new risk; nested objects can also print unexpected details.

With Lombok, `@ToString.Exclude` can be used on sensitive fields where debugging requires it, yet this is only an **extra defensive layer**. The primary strategy remains never passing raw objects to loggers.

### JSON Serialization Carries the Same Risk

```java
logger.debug("event_json={}", objectMapper.writeValueAsString(event));
```

This is an illustrative snippet with Jackson. Turning an object into JSON **does not automatically make the payload safe**. JSON can serialize every field, including credentials or nested PII. Similarly, annotations controlling API serialization do not automatically protect every other logging path.

For safe structured logging, **build a small allowlisted log DTO**, separate from the domain event, and let the logging backend encode it properly.

## 7. Allowlists Beat End-of-Pipeline Blacklists/Redaction

Two strategies:

| Strategy | How It Works | Weaknesses / Strengths |
| --- | --- | --- |
| **Blacklist** | Log all fields, then regex-mask known emails/tokens | Easily misses new formats, nested fields, encoded secrets, unknown keys |
| **Allowlist** | Build logs strictly from permitted fields | Safer by default; new fields are not exposed automatically |
| **Collector redaction** | Ingest raw logs and mask in the pipeline | Raw data may already exist on container/stdout/agent before masking |
| **Logger/encoder masking** | Transform sensitive fields before output | Useful secondary layer; still needs policy and tests |
| **Do not log the data** | Avoid creating a copy at the source | Lowest risk when the field is unnecessary |

If masking is chosen, evaluate its adequacy against your threat model. For instance, masking an email to `a***@example.invalid` may still allow identifying an individual when combined with domain, tenant, timestamps, and other logs. That is **masking**, not true anonymization.

You cannot assume a regex matching `@` will catch all personal data. Data can appear in free text, nested JSON, URL queries, stack traces, or encoded payloads.

### When Tracking a Subject Across Logs Is Truly Required

A stable reference without an email can be used **if** operational needs genuinely demand it. However:

- A raw `customerId` is still potentially linkable PII.
- Plain SHA-256 hashing of an email **does not** guarantee anonymity: emails have low entropy and can be guessed from common lists.
- HMAC-based pseudonymization with a well-managed secret key reduces direct guessing, yet the output remains **linkable** and must be protected.
- Stable pseudonyms enable long-term tracking; scope/retention/rotation policies and privacy reviews are required.
- Never put HMAC keys, salts/peppers, or mapping tables into logs.

If per-person correlation is not needed, using only event ID + outcome is usually safer.

## 8. Runnable Maven Example: @EventListener Logs Only Allowed Metadata

This example uses **Java 17+**, **Spring Framework 6.2.12**, and **SLF4J 2.0.16 with SimpleLogger**. It intentionally puts emails inside the domain event to demonstrate that **data processed inside the application is not automatically permitted in logs**.

Goals:

1. Publish a Java record `CustomerEmailChanged` via a Spring context.
2. `@EventListener` receives the event and builds a log summary **strictly from the event type, UUID, and fixed outcome**.
3. Use SLF4J parameterized logging without passing the raw event or emails to the logger.
4. Check the summary string itself to prevent emails from appearing.
5. Print deterministic verification output independent of logging-backend timestamps.

### 8.1. Project Structure

```text
privacy-safe-event-log/
├── pom.xml
└── src/main/java/demo/PrivacySafeEventLogDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>privacy-safe-event-log</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>2.0.16</version>
        </dependency>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-simple</artifactId>
            <version>2.0.16</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.PrivacySafeEventLogDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/PrivacySafeEventLogDemo.java`:

```java
package demo;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class PrivacySafeEventLogDemo {

    public record CustomerEmailChanged(
            UUID eventId,
            String customerRef,
            String previousEmail,
            String newEmail,
            Instant occurredAt) {

        public CustomerEmailChanged {
            Objects.requireNonNull(eventId, "eventId");
            Objects.requireNonNull(customerRef, "customerRef");
            Objects.requireNonNull(previousEmail, "previousEmail");
            Objects.requireNonNull(newEmail, "newEmail");
            Objects.requireNonNull(occurredAt, "occurredAt");
        }
    }

    public static final class SafeEventLogListener {
        private static final Logger log =
                LoggerFactory.getLogger(SafeEventLogListener.class);

        private volatile String lastSafeSummary;

        @EventListener
        public void on(CustomerEmailChanged event) {
            // Do not call event.toString(); do not log emails or PII fields.
            String safeSummary =
                    "event_type=CustomerEmailChanged"
                    + " event_id=" + event.eventId()
                    + " outcome=OBSERVED";

            lastSafeSummary = safeSummary;
            log.info("{}", safeSummary);
        }

        public String lastSafeSummary() {
            return lastSafeSummary;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        SafeEventLogListener safeEventLogListener() {
            return new SafeEventLogListener();
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            CustomerEmailChanged event = new CustomerEmailChanged(
                    UUID.fromString(
                            "6244b752-bd2b-4aa3-8120-a835ca600ce2"),
                    "customer-42",
                    "old@example.invalid",
                    "new@example.invalid",
                    Instant.parse("2026-01-01T10:00:00Z"));

            context.publishEvent(event);

            String summary = context
                    .getBean(SafeEventLogListener.class)
                    .lastSafeSummary();

            if (summary == null) {
                throw new IllegalStateException("Listener not invoked");
            }

            boolean leaked = summary.contains(event.previousEmail())
                    || summary.contains(event.newEmail());

            System.out.println("SAFE_SUMMARY=" + summary);
            System.out.println("EMAIL_LEAKED=" + leaked);
            System.out.println(
                    "HAS_LINE_BREAK=" + (summary.contains("\n")
                            || summary.contains("\r")));
        }
    }
}
```

Run:

```bash
mvn -q compile exec:java
```

Lines produced by **`System.out.println(...)`** (the logging backend may emit an extra `INFO` line with its own formatting):

```text
SAFE_SUMMARY=event_type=CustomerEmailChanged event_id=6244b752-bd2b-4aa3-8120-a835ca600ce2 outcome=OBSERVED
EMAIL_LEAKED=false
HAS_LINE_BREAK=false
```

### 8.2. Why Is This Example Directly On-Topic?

- `AnnotationConfigApplicationContext` builds the context and registers the bean's `@EventListener` method.
- `context.publishEvent(event)` publishes a plain Java record. Spring supports payloads that do not extend `ApplicationEvent`.
- The default multicaster runs listeners **synchronously** on the same thread, so `lastSafeSummary()` can be read immediately in `main` after publishing.
- The listener **can access** `previousEmail` and `newEmail` on the event, yet omits them when constructing the summary for logging.
- The event ID is a valid UUID from a trusted source in the demo. No email data or CR/LF characters appear in the summary.
- SLF4J only receives an allowlist-constructed summary. In production, use a proper structured logging/encoder setup instead of manually assembling a large string from many dynamic fields.

**Important limitations:** the demo checks the summary string passed to the logger; it **does not capture every log emitted by all libraries, frameworks, exception handlers, or logging pipelines**. It does not prove the entire system leaks no PII. The fake values use the `.invalid` domain rather than real people's details. The project has no HTTP, database, or transactions. In production, add integration tests capturing appender output and scanning the entire pipeline.

### 8.3. Why Not Log customerRef Even Though It Is "Just an ID"?

For the sole goal of "did the listener receive the event?", the event UUID suffices for incident tracing. `customerRef` can be used to look up a real person in a CRM, making it a pseudonymous reference that requires protection. Keeping it out of logs reduces the ability to track individual behavior by people who can read logs without having CRM permissions.

If the business genuinely needs per-subject auditing, design a **separate audit trail** with appropriate access control and retention, rather than relying on debug loggers whose log levels shift during incidents.

## 9. Protecting Logs Against CRLF/Log Injection

Beyond data leaks, logging raw input can allow an attacker to forge a "fake log line":

```text
displayName = "Alice\nERROR admin-login-success user=attacker"
```

If code concatenates input directly into log text, the forged line can mislead incident analysis or alerting.

### 9.1. Parameterized Logging Does Not Sanitize Automatically

```java
logger.warn("Profile update failed for name={}", displayName);
```

This is better than string concatenation for message templates, yet it **does not automatically escape CR/LF characters** across all logging backends and formats. If `displayName` is unvalidated or the encoder does not escape it, log injection remains a risk.

### 9.2. Prefer Typed Allowlists and Structured Encoding

A safer approach:

```java
logger.warn(
        "event_type={} outcome={} error_code={}",
        "CustomerProfileUpdated",
        "FAILED",
        "INVALID_DISPLAY_NAME");
```

Values are literals or enums from a finite set; no untrusted display name is logged. If an input must be recorded, validate its size/type, encode it for the output format, enforce length limits, and use a structured JSON encoder that escapes properly. Never strip `\n` manually and assume all log injection forms are solved (Unicode controls, delimiters, and log-viewer parsing can still apply).

### 9.3. Structured JSON Does Not Solve Privacy Automatically

A structured logger can safely serialize newlines and quotes, yet if a JSON field contains a card number, token, or email, it **still leaks data**, just in a different representation. You need both: a **data allowlist** and **proper output encoding**.

## 10. Exceptions Can Leak Data into Logs

A common pattern:

```java
try {
    remoteClient.updateCustomer(event);
} catch (Exception ex) {
    logger.error("Could not update customer {}", event, ex);
}
```

This is a counterexample snippet and not standalone. It can log all event PII via `toString()`, while the exception/stack trace may contain URLs, response bodies, or SDK details.

A controlled approach:

```java
try {
    remoteClient.updateCustomer(event);
} catch (ExternalServiceException ex) {
    logger.error(
            "event_type={} event_id={} outcome={} error_code={}",
            "CustomerEmailChanged",
            event.eventId(),
            "FAILED",
            "CONTACT_INDEX_UNAVAILABLE");

    // Retry/escalation policy belongs in a separate error-handling layer;
    // do not silently swallow the exception and report business success.
    throw ex;
}
```

This is an illustrative snippet; `remoteClient` and `ExternalServiceException` are application-defined. If a stack trace is needed for triage, emit it to a restricted-access channel after reviewing exception sources and messages; **never** assume every `Throwable.toString()` is harmless.

### Validation Errors and Exception Messages

Validation frameworks may include the rejected value in error descriptions. For instance, on an invalid email, a message might include the exact email string the customer entered. If a logger prints `exception.getMessage()` or `BindingResult.toString()`, the input can leak.

Better practice: log the allowlisted field name + a stable validation error code + event ID, instead of the raw invalid value. When investigating input errors, use authorized data-query channels if seeing the value is truly required.

## 11. Spring Boot Logging and Log Levels Are Not an Access Control Mechanism

Spring Boot usually configures a logging backend (Logback is the common default starter choice) and lets you control log levels via configuration. Example:

```yaml
logging:
  level:
    root: INFO
    demo.customer: INFO
```

This is illustrative YAML for a Spring Boot application, **not part of the plain Spring Maven project in section 8**. Setting `DEBUG`/`TRACE` can increase detailed logging from libraries or custom listeners; toggling a level once via dynamic config can also leave data behind in the log collector.

Do not rely on log levels as your only barrier:

- PII at `DEBUG` is still PII.
- Someone authorized to enable debug may not be authorized to read personal records.
- Libraries or SDKs may log HTTP headers/bodies under their own configuration.
- An error path may log data at `ERROR` even when normal business loggers stay quiet.
- Collectors may retain copies after you turn debug back off.

**Strong strategy:** do not emit sensitive data in default code paths; audit logging configurations, code reviews, and security tests with debug/trace enabled; restrict production level changes through an approved workflow.

### Especially for SQL Logging

Parameterized SQL queries do not mean JDBC/ORM logs are always safe. Enabling trace logging for SQL bind values or JDBC proxies can expose emails, account numbers, or PII fields. Verify the **bind-parameter logging configuration** of Hibernate and your database libraries for the actual versions in use.

If you truly need SQL performance diagnostics, prefer query shapes, durations, error classes, and query fingerprints without sensitive literals. Never send bind values to standard log stores.

## 12. HTTP Access Logs, Request Bodies, and Headers

An event listener is often triggered from an HTTP request, so PII leak paths are not limited to `@EventListener`. Other places can log the same data:

- Servlet filters or Spring MVC interceptors logging raw requests.
- Logback access logs or web server access logs containing query strings.
- HTTP client interceptors logging URLs/requests/responses.
- Retry interceptors or circuit breakers logging response messages.
- Spring Boot error handlers logging exception descriptions.
- Log collectors capturing headers, cookies, and trace baggage.

Example URL:

```text
GET /customers?email=person@example.invalid
```

Even when the event listener does not log the email, **an access log recording the full query string** still leaks it. Therefore, avoid passing secrets/PII in query parameters when better protocol options exist, and apply allowlisting/redaction at ingress/egress.

### Do Not Log All Headers

`Authorization`, `Cookie`, `Set-Cookie`, internal exchange tokens, and custom headers may carry secrets. Log only headers strictly justified by policy, with allowlisting and validation.

### ContentCachingRequestWrapper Is Not a Privacy Solution

In Spring MVC, `ContentCachingRequestWrapper` lets a filter re-read a consumed body, yet using it to print whole bodies into logs keeps the same leak risk. Even holding raw bodies in filter memory can introduce extra concerns. Never enable broad request/response payload logging merely to debug an event.

## 13. MDC and Context Propagation: Cross-Request Leak Risks

Mapped Diagnostic Context (MDC) helps attach `traceId` or `correlationId` to log lines. However, many logging implementations rely on `ThreadLocal`, requiring lifecycle management.

Illustrative example using SLF4J:

```java
try (MDC.MDCCloseable ignored =
        MDC.putCloseable("correlationId", correlationId)) {
    service.handle(command);
}
```

This snippet uses `MDC`, `service`, `command`, and `correlationId` supplied by the application. It uses try-with-resources to restore/remove the set field, though care is needed if a prior value existed and must be restored per policy. Never put emails, tokens, phone numbers, or raw request headers into MDC.

### 13.1. Synchronous Listeners

By default, Spring Application Events execute listeners synchronously on the publisher thread. If MDC already holds a correlation ID in this scope, the listener sees the same MDC. That does not mean MDC is clean or safe: if the publisher sets an unauthorized PII field, downstream listeners and loggers can spread it too.

### 13.2. Asynchronous Listeners

When `@Async`, a task executor, or a custom multicaster runs a listener on another thread, MDC and `ThreadLocal` values **are not guaranteed to propagate automatically**. Spring Framework offers `ContextPropagatingTaskDecorator` / Micrometer Context Propagation for configured contexts, yet not every key/security/tenant context is supported out of the box.

Worse still, if a task sets `customerId` or tenant without clearing it, the thread pool can reuse that worker for another user, causing **cross-request/cross-tenant leakage**.

Example of MDC cleanup in a task:

```java
Map<String, String> previous = MDC.getCopyOfContextMap();
try {
    MDC.put("correlationId", safeCorrelationId);
    processEvent(event);
} finally {
    if (previous == null) {
        MDC.clear();
    } else {
        MDC.setContextMap(previous);
    }
}
```

This is a snippet requiring `java.util.Map` and `org.slf4j.MDC`; `processEvent` and `safeCorrelationId` are application-defined. It restores the previous state, yet **does not legitimize PII** if any was inside the previous map. Propagate only allowlisted context belonging to the right execution boundary.

## 14. Traces, Metrics, and Logs Are Three Different Data Stores

A single action can simultaneously produce:

```text
Domain event
  +--> Listener application log
  +--> Distributed tracing span attributes
  +--> Metrics tags/labels
  +--> Audit table
  +--> Message broker / event publication registry
```

Blocking PII in the logger **does not automatically block** it in span attributes, exception recording, or metrics. For instance, attaching `customerEmail` to an OpenTelemetry span can export it to the tracing backend. Putting raw user/tenant IDs into metric labels also causes very high cardinality.

### Recommended Approach

- **Metrics:** use only low-cardinality tags such as event type, outcome, listener name, and normalized error class. Never use email, customerId, eventId, or tokens as labels.
- **Traces:** use traceId/spanId for correlation; record only essential event metadata. Restrict raw payloads and exception bodies.
- **Logs:** allowlisted fields, structured encoding, access controls, retention.
- **Audit:** dedicated schema and permissions driven by clear legal/business needs; never use debug logs as the sole audit source.
- **Events/outbox:** store only data needed for consumers and reliability; protect according to data policies and authorization.

Instrumenting an event flow for observability does not make tracing attributes an acceptable place for PII. Evaluate every sink where data is exported.

## 15. Audit Logs Differ from Operational Logs

In systems requiring action accountability, distinguish:

| Aspect | Operational Log | Audit Trail |
| --- | --- | --- |
| Purpose | Debugging, performance, error triage | Recording who did what, to which target, and the outcome |
| Schema stability | May change across releases/log backends | Needs a stable, versioned contract |
| Access rights | Devs/operations by role | Dedicated permissions, typically more sensitive |
| Retention | Based on operational needs | Based on applicable laws/policies/contracts |
| Integrity protection | Present, though level varies | Often requires strong tamper/modification controls |
| Transaction status | Not automatically tied to commit | Must define fact and commit semantics |
| PII | Minimal | Strictly fields required for audit obligations, protected |

For example, "support agent accessed customer profile" may need an audit record with actor ID and target ID, yet that does not justify an application log saying `fullCustomer={...}`.

If the organization must record PII access actions, log the **access event** and outcome, not the **PII content accessed**.

## 16. Multi-Tenant Logging: Tenant IDs Can Be Sensitive

In multi-tenant systems:

- A tenant ID may point to a specific business or group of people.
- Due to an application bug, an event might involve an actor from tenant A but data from tenant B.
- Centralized logs can hold records from many tenants inside the same index.

Therefore, safe logging must address both **write permissions** and **read permissions**:

1. Obtain the tenant from an authenticated source matching the resource owner; never trust arbitrary headers.
2. If logs include a tenant reference, enforce appropriate partitioning/access rules.
3. Log viewers of tenant A must not be able to query logs of tenant B.
4. Check log consoles, exporters, dashboards, saved searches, and log-platform API tokens.
5. Do not place tenant IDs into unbounded metric labels when tenant counts are large.
6. Never let an untrusted event pick a logging backend index/bucket solely via a `tenantId` field.

An application event carrying `tenantId` **is not proof** that the consumer is allowed to process that tenant. It is metadata, not an authorization token.

## 17. Lifecycle and Transactions: Logs Can Record Facts Before Commit

A synchronous `@EventListener` can run while the publisher is still inside a transaction. If the transaction rolls back after the listener logs:

```text
OrderUpdated event observed
```

then the log line does not prove the business state committed durably.

Example:

```java
@Transactional
public void changeEmail(...) {
    repository.save(...);
    publisher.publishEvent(new CustomerEmailChanged(...));
}
```

This is pseudocode; variables and types belong to the application. If the transaction rolls back after publishing, the listener's log may already exist even though the DB did not change.

A `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` listener can fit when you only want to log a milestone after commit. Yet an after-commit callback does not automatically guarantee the log was written, retried after a crash, or delivered durably.

**Log phrasing should be honest:** `event_received`, `handler_completed`, and `business_committed` are different states. Never log `outcome=SUCCESS` right when a task has merely been submitted to an executor.

### Do Not Log Passwords Under the Guise of Auditing

When a credential change succeeds, the audit log can record `CredentialChanged`, actor/subject ID, and timestamp per policy. **Never** write old/new passwords, password hashes, reset tokens, or recovery codes, not even into an audit table.

## 18. When Using ErrorHandler or Async Executors

A listener error can surface in:

- `SimpleApplicationEventMulticaster.setErrorHandler(...)`.
- `AsyncUncaughtExceptionHandler` for `@Async void`.
- `Future.get()` / `CompletionException`.
- Task decorator/worker logs.
- Retry schedulers, message listener containers, and outbox publishers.

These components can log the `Throwable` or the entire payload **even if the primary listener logged safely**.

Example to avoid:

```java
multicaster.setErrorHandler(error -> {
    logger.error("Listener failed: {}", error.getMessage());
});
```

If the message contains an email or response body, it leaks. Moreover, logging like this drops the stack trace/causal chain, making debugging harder.

Controlled handling:

```java
multicaster.setErrorHandler(error -> {
    String code = classifyToStableErrorCode(error);
    logger.error("application_event_listener_failed error_code={}", code);
    recordFailureMetric(code);
});
```

This is an illustrative snippet; `classifyToStableErrorCode` and `recordFailureMetric` must be defined by the application. Here the handler returns, meaning it **suppresses the error** inside the multicaster; retry/escalation must be decided per business rules. Never silently drop an important failed task just to avoid leaking PII.

### Exception Class vs Exception Message

`error.getClass().getSimpleName()` is usually less sensitive than `error.getMessage()`, yet mapping to an allowlisted error code is still preferable for metric labels or stable log contracts. Class names can reveal internal details; stack traces must be kept in an appropriate channel and follow redaction policies.

## 19. Governing Log Pipelines, Retention, and Data Deletion

Code-level protection is the first layer. Next, govern the full log path:

```text
Spring listener
   |
   v
SLF4J / Logback / encoder
   |
   v
stdout / log file / sidecar
   |
   v
collector / agent / pipeline processor
   |
   v
index / object storage / SIEM / monitoring vendor
   |
   v
dashboards / exports / backups
```

Every hop can create copies with different retention and access controls. Required measures:

- **Data classification:** which fields are logged, which are excluded, rationale, and owner.
- **Least privilege:** who can read which logs, scoped by environment and tenant where needed.
- **Encryption in transit/at rest:** transport and storage meet organizational policy.
- **Retention:** minimum storage period necessary for a clear purpose, aligned with laws/contracts; never keep indefinitely just for convenient debugging.
- **Deletion/rectification:** processes to fulfill valid personal-data requests, including archives/backups and legal holds if applicable.
- **Access audit:** record who viewed/exported sensitive logs when required.
- **Vendor review:** a log aggregator is a data processor; evaluate its role, storage location, access controls, and contracts.
- **Incident response:** assess scope, contain, revoke/rotate credentials if tokens leaked, and handle stored copies.

**There is no single universal retention period.** Exact obligations depend on applicable laws, data classification, log type, and organizational procedures. The technical rules here do not replace legal review or data-protection policies.

## 20. Testing Against PII Leaks in Logs

Testing solely by eyeballing `System.out.println` in a demo is not enough. A production system should test the **actual output of the logging backend** and relevant pipelines.

### 20.1. Canary Data

Use obvious synthetic data, never real people's records:

```text
canary.email@example.invalid
+10000000000
CANARY-SECRET-DO-NOT-LOG
```

Inject canaries into payloads or exception responses inside an integration test. After running the operation, scan the **captured log output** and assert none of these values appear. If canaries can reach a collector, verify export points under isolated test conditions too.

Never log canaries as a live "test" directly in production if it risks affecting alerts/retention; use test environments and proper permissions.

### 20.2. JUnit Assertions at the Formatter Layer

You can extract log-field construction into a pure function:

```java
static String safeSummary(CustomerEmailChanged event) {
    return "event_type=CustomerEmailChanged"
            + " event_id=" + event.eventId()
            + " outcome=OBSERVED";
}
```

This is a snippet requiring the corresponding record. Test:

```java
String text = safeSummary(event);

assertFalse(text.contains(event.previousEmail()));
assertFalse(text.contains(event.newEmail()));
assertFalse(text.contains("CANARY-SECRET-DO-NOT-LOG"));
assertFalse(text.contains("\n"));
assertFalse(text.contains("\r"));
```

This is a JUnit snippet, not part of the section 8 Maven demo; it needs matching test data and JUnit imports. Unit-testing the formatter catches regressions if someone adds a sensitive field to logs later.

### 20.3. Integration Tests Capturing Real Logs

With Logback, you can attach a `ListAppender<ILoggingEvent>` to the tested logger and inspect `getFormattedMessage()`. This is **Logback-specific**: the project needs `logback-classic` on the test classpath and must detach/stop the appender after the test to prevent state bleed across test methods.

Tests should distinguish:

- Message template vs formatted message.
- Exception stack traces written by the encoder after the message.
- MDC/markers/key-value pairs added by the backend outside the text.
- Logs emitted by other libraries, not only the listener's logger.
- Nested JSON structure and actual output encoding.

To prove logs as a whole do not leak PII, capture the **final appender output**, not only one field of `ILoggingEvent`.

### 20.4. Scenarios to Test

| Scenario | Expected Outcome |
| --- | --- |
| Successful event with email in payload | Log contains only allowlisted metadata |
| Listener throws exception with email in message | Logger/error handler does not emit raw email |
| Input contains `\r`, `\n`, or delimiters | No forged log entry created / JSON escaped properly |
| DEBUG/TRACE enabled on service and HTTP client | No secrets or full request bodies logged |
| Event runs via `@Async`/executor | MDC does not leak from prior request/tenant |
| User belongs to tenant A, event from tenant B | Authorization and log access remain tenant-isolated |
| JSON event adds an `accessToken` field | Allowlisted logs do not automatically include the new field |
| Webhook/HTTP error response contains token | Logs do not print raw response |
| Old event replayed | Sensitive data is not dumped on retry/error paths |
| Tracing enabled | Span attributes/baggage contain no canaries |
| Metric labels | No user IDs/emails/per-event UUIDs used |
| Log level configuration changed | No unexpected data exposure |

## 21. Code Review Workflow for Event Listener Logging

**Step 1 — Define the purpose.** Is the log for measuring throughput, finding an event ID, diagnosing errors, or auditing? Each purpose requires its own data contract.

**Step 2 — Classify the event payload.** Look for personal fields, secrets, free text, nested objects, and derived identifiers. Do not inspect only `String` fields; `Map` and object wrappers can carry data too.

**Step 3 — Design a minimal log schema.** Start with event type, event ID, handler, outcome, duration, and normalized error code.

**Step 4 — Ban object dumps.** Search for `logger.*("...{}", event)`, `event.toString()`, JSON serializers, request/response body logging, and full exception messages.

**Step 5 — Check error paths.** Inspect `ErrorHandler`, async executors, retries, fallbacks, exception mappers, tracing, and HTTP client logs.

**Step 6 — Verify encoding.** Untrusted fields must be validated/size-bounded and encoders must escape properly for the output format to prevent log injection.

**Step 7 — Classify IDs.** Event UUIDs differ from user/tenant IDs; stable identifiers capable of re-identification still need protection.

**Step 8 — Control context.** MDC/baggage may hold only allowlisted metadata, cleaned up between requests and executor tasks.

**Step 9 — Canary test at appender/pipeline level.** Exercise success, failure, async, DEBUG/TRACE, and stack traces.

**Step 10 — Govern storage.** Define owners, access controls, retention, encryption, exports, and incident response for every log sink.

## 22. Common Mistakes

1. **Logging record events directly** because Java generates `toString()`.
2. **Logging full JSON** assuming JSON serialization masks PII automatically.
3. **Regex-masking only emails** while missing phone numbers, nested payloads, free text, tokens, and URL queries.
4. **Treating raw `SHA-256(email)` as anonymization** when dictionary attacks are trivial.
5. **Logging a stable customer ID and claiming logs contain no personal data.**
6. **Enabling SQL bind-parameter logging** in production, exposing real values.
7. **Logging `Authorization`/`Cookie` headers** via filters or HTTP client interceptors.
8. **Assuming DEBUG is harmless** because production normally runs at INFO.
9. **Logging `exception.getMessage()`** when messages carry input or response bodies.
10. **Putting email/tenant/customerId into metric tags**, causing high cardinality and leaks.
11. **Putting PII into tracing baggage or span attributes**, even when business loggers are safe.
12. **Not clearing MDC in thread pools**, attributing logs to the wrong user/tenant.
13. **Assuming SLF4J placeholders prevent all log injection**, even though raw CRLF can still be printed.
14. **Masking at the collector while ignoring raw copies on stdout/agents**, where the data already exists.
15. **Keeping logs indefinitely** because no retention policy exists.
16. **Granting full log read access to users unauthorized to view source data.**
17. **Using audit logs as debug logs or vice versa**, weakening integrity and data protection.
18. **Testing only the happy path**, letting error/async/retry logs leak data.
19. **Changing log formats without testing encoders/structured fields**, breaking redaction.
20. **Logging success before transaction commit**, misleading audits about state.
21. **Logging raw HTTP request bodies from `ContentCachingRequestWrapper`** to debug an event.
22. **Ignoring third-party library logging**, especially around requests/responses and retries.
23. **Believing expired tokens are safe to log**, when tokens, secrets, and identifiers can still pose risks.
24. **Deleting a "sensitive" log line without checking copies and backups**, leaving incident response incomplete.

## 23. Pre-Deployment Checklist

- [ ] Is there an allowlist of loggable fields per event type and use case?
- [ ] Are raw events, entities, requests, principals, and exception response bodies kept out of loggers?
- [ ] Are emails, phone numbers, IDs/documents, addresses, tokens, cookies, and secrets excluded from routine logs?
- [ ] Are opaque IDs evaluated as potentially linkable data rather than assumed anonymous by default?
- [ ] When correlation is needed, are event IDs and trace IDs generated cleanly without PII?
- [ ] Are error codes and outcomes fixed/allowlisted values?
- [ ] Is untrusted text never used as a log message template?
- [ ] Does the structured encoder escape CRLF and control characters appropriately?
- [ ] Have MDC cleanup, async listeners, and executor context propagation been verified?
- [ ] Have SQL bind logs, HTTP body/header logs, exceptions, and third-party libraries been audited?
- [ ] Do traces and metrics avoid accidentally emitting PII in attributes/tags?
- [ ] Does the audit trail have its own schema, authorization, and retention?
- [ ] Does access to log storage, dashboards, and exports follow least privilege?
- [ ] Are retention periods and procedures for data handling, backups, and legal holds defined?
- [ ] Have canary tests checked appender/pipeline output on both success and failure?
- [ ] Have DEBUG/TRACE settings, logging backends, and dependencies been verified for the deployed versions?
- [ ] Do operators have an incident response procedure if tokens/PII are discovered in logs?

**Conclusion:** With Spring Application Events, a listener may need to read personal data to fulfill business logic, yet **reading it does not mean writing it to logs is permitted**. Treat event payloads, log records, tracing attributes, and audits as distinct data contracts. Build logs from a **minimal metadata allowlist**, avoid `event.toString()` and raw exception/request dumps, prevent log injection, restrict access and retention, and test the entire pipeline with canary data. When investigating a specific incident, use a safe event/correlation ID to look up authorized data systems rather than turning logs into a replica of customer records.

## References

- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP Developer Guide — Security Logging and Monitoring](https://devguide.owasp.org/en/04-design/02-web-app-checklist/09-logging-monitoring/)
- [Spring Framework — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [SLF4J Manual](https://www.slf4j.org/manual.html)
- [OpenTelemetry — Semantic Conventions](https://opentelemetry.io/docs/concepts/semantic-conventions/)
