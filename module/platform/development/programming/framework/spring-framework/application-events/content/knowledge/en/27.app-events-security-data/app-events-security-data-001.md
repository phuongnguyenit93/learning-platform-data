# Do Not Put Secrets in Event Payloads

## 1. Why Can an Event Expose Secrets?

In Spring Framework, `ApplicationEventPublisher.publishEvent(...)` publishes an object so that interested listeners can react. A `CredentialRotated` event may be observed by audit, metrics, notification, an outbox bridge, or listeners added later:

~~~text
CredentialService
      |
      +-- publishEvent(CredentialRotated)
                  |
                  +-- AuditListener
                  +-- MetricsListener
                  +-- NotificationListener
                  +-- @Async SecurityListener
                  +-- Outbox/Broker Bridge (if any)
~~~

If the payload contains a password, token, or API key, the secret can flow into **every listener that receives the event**, and then into logs, tracing, queues, database outboxes, backups, dead-letter queues (DLQs), and integrated services. A single `log.info("event={}", event)` statement can accidentally log the entire credential, especially when the payload is a Java record with an auto-generated `toString()`.

**Principle:** an event is a contract for **sharing factual information about what happened**, not a container for authentication data. Keep secrets inside a dedicated boundary; an event only needs the minimal data for consumers to know **what occurred** and perform authorized work.

This lesson covers how to identify secrets; design payloads using an allowlist; inspect leak paths through logs, object graphs, serialization, outbox, and async execution; and build a Java 17+ Spring Framework example with tests that prevent adding secret fields to events.

## 2. Classifying Data Before Publishing an Event

| Category | Examples | Rule |
| --- | --- | --- |
| **Raw credentials** | passwords, API keys, client secrets, database passwords, private keys, SSH keys, webhook signing secrets | **Do not include in regular domain events** |
| **Authorization tokens** | access tokens, refresh tokens, session cookies, password-reset tokens, magic-link tokens, JWT bearer tokens, OTPs, recovery codes | Do not include in fan-out events |
| **Derived authentication data** | password hashes, token verifiers, peppers, key material | Do not broadcast to audit/metrics/notification; still must be protected |
| **Sensitive payment data** | CVV/CVC, PIN, full card numbers | Do not broadcast; comply with industry standards |
| **PII** | email, phone number, address, national/government IDs, health data | Consider purpose, processing authorization, and retention; prefer minimization |
| **Business IDs** | `accountId`, `orderId`, `paymentId` | Can be used when justified, with tenancy/privacy controls |
| **Event metadata** | `eventId`, `occurredAt`, event type, version | Usually appropriate; do not embed secrets/PII in IDs |
| **Opaque references** | `credentialRef`, `vaultVersion` | Only when the reference **does not itself grant retrieval access** |

Do not equate PII with credentials, but do not treat PII as public data either. A `sessionId`, although called an ID, can be a **bearer secret** if possessing that value allows using the session. Conversely, `accountId` may not be a credential yet still be private data in a multi-tenant system.

**Do not hash a password and then broadcast it.** A password hash is still sensitive data that can be used for offline attacks. **Base64 is not encryption.** Proper encryption protects certain transport/storage layers, but it does not replace asking whether a consumer actually needs to know that data.

## 3. Anti-Patterns to Eliminate

### 3.1 Stuffing Commands/Requests into an Event Record

~~~java
// ANTI-PATTERN: illustrative only, not a standalone program.
public record UserRegistered(
    long userId,
    String email,
    String rawPassword,
    String sessionToken
) {}
~~~

A Java record generates `toString()` and accessors. Someone else may accidentally log both `rawPassword` and `sessionToken`. Lombok `@Data` / `@ToString`, Kotlin data classes, or automatic serializers require the same scrutiny.

A more minimal version:

~~~java
public record UserRegistered(
    java.util.UUID eventId,
    long userId,
    java.time.Instant occurredAt
) {}
~~~

If a listener sends an email, it can look up the contact address from an authorized source when there is a clear business purpose. Not every subscriber needs to receive email/phone/raw profile data.

### 3.2 Publishing an Entire JPA Entity or HttpServletRequest

~~~java
// ANTI-PATTERN: assumes existing types.
publisher.publishEvent(new AccountUpdated(accountEntity));
publisher.publishEvent(new RequestCaptured(httpServletRequest));
~~~

An entity may contain password hashes, lazy-loaded collections, or customer information. `HttpServletRequest` may contain Authorization headers and cookies. When `@Async` uses an executor, the request may have already ended; `RequestContextHolder` does not automatically propagate across threads either. Do not keep raw requests/credentials inside background events.

### 3.3 Relying Solely on Redaction

`@JsonIgnore` may hide a field when using a particular Jackson configuration. However, `toString()`, reflection, debug loggers, AOP interceptors, or other serializers can still expose that field. **The strongest protection is not creating secret fields on the event in the first place.** Logging/redaction is only an additional defense layer.

## 4. Proper Design: Include Necessary Metadata, Not Secrets

Suppose an account rotates an API credential:

~~~text
RotateCredential command
  accountId=101
  newSecret=[SENSITIVE]
         |
         v
CredentialService (trusted boundary)
  validate/store via secret manager
         |
         v
CredentialRotated
  eventId=<UUID>
  accountId=101
  credentialVersion=3
  occurredAt=<Instant>
         |
         +--> audit: record version change
         +--> metrics: count credential rotation
         +--> cache invalidation: evict old version cache
~~~

The payload can be defined as:

~~~java
public record CredentialRotated(
    java.util.UUID eventId,
    long accountId,
    int credentialVersion,
    java.time.Instant occurredAt
) {}
~~~

The event contains **no** `newSecret`, `oldSecret`, `passwordHash`, `accessToken`, or `HttpServletRequest`. The service handles secret data in one privileged location; listeners only learn a fact and metadata.

Not every event is required to have all four fields. For example, a metrics listener might only need `event_type` and `outcome`, without needing `accountId` in logs. Design according to the specific recipients and trust boundaries.

### Checklist for Inspecting Each Field

1. Which listener needs this field and for what purpose?
2. If the value is leaked, can an unauthorized party log in, reset a password, or retrieve a secret?
3. Does the field contain an email, tenant ID, personal data, or identifying information?
4. Can it be replaced by a version, ID, or status to reduce read privileges?
5. If the event is printed by `toString()`, serialized to an outbox, replayed, or sent to a DLQ, does it cause a violation?
6. Is there a separate access control mechanism when sensitive data needs to be dereferenced?

**Never "temporarily add the password for easier debugging".** A single publish can create many copies that are much harder to revoke than the source object.

## 5. A Secret Reference Is Not a Silver Bullet

When a worker genuinely needs access to a secret, you can send an **opaque reference**, and the worker retrieves it through a secret manager:

~~~text
Event: CredentialSyncRequested
  credentialRef=cred/version-7
  eventId=...
        |
        v
Authorized worker
  - authenticate workload identity
  - authorize tenant/purpose/credential
  - fetch secret over a protected channel
  - use only for as long as needed
  - audit access, do not log raw material
~~~

Important conditions:

- Knowing only `credentialRef` **must not** automatically grant permission to read the secret. If the reference acts like a signed URL, reset link, or bearer token, then **it is itself a secret** and should not be broadcast.
- IAM/vault checks permissions at dereference time. Do not grant "read all secrets" by default to every listener.
- Restrict TTL, caching, export permissions, access logs, and copy count; ensure rotation/revocation exists.
- A reference can also reveal tenant or internal names; prefer opaque IDs that carry no private data.
- An event replayed months later may point to an expired/rotated secret; consumers must handle that case explicitly.

If a business flow needs to send a token to a specific recipient, separate the **general domain event** from a **dedicated secure delivery channel** with appropriate authentication, authorization, encryption, and retention.

## 6. Complete Java 17+ Spring Framework 6.2 Example

This example uses **Spring Framework 6.2.19**, **JUnit 5.12.2**, Gradle, and Java 17+. It does not require Spring Boot or a database. It illustrates how **secrets only pass through the processing component**, while the event contains allowlisted metadata.

**Warning:** `DemoVault` in this example is an **unencrypted in-memory** store intended solely to demonstrate data flow; it is not a safe secret store for production. Real systems must use an approved secret manager/credential storage with proper access control and rotation.

### Structure

~~~text
safe-event-payload/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/SafeEventPayloadDemo.java
    └── test/java/demo/SafeEventPayloadDemoTest.java
~~~

### settings.gradle

~~~groovy
rootProject.name = 'safe-event-payload'
~~~

### build.gradle

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.2'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.SafeEventPayloadDemo'
}

test {
    useJUnitPlatform()
}
~~~

### src/main/java/demo/SafeEventPayloadDemo.java

~~~java
package demo;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

@Configuration
public class SafeEventPayloadDemo {

    // Must not contain password, token, key material, or raw request.
    public record CredentialRotated(
        UUID eventId,
        long accountId,
        int credentialVersion,
        Instant occurredAt
    ) {}

    @Bean
    Clock clock() {
        return Clock.fixed(
            Instant.parse("2026-01-02T03:04:05Z"),
            ZoneOffset.UTC
        );
    }

    @Bean
    DemoVault demoVault() {
        return new DemoVault();
    }

    @Bean
    RotationService rotationService(
            DemoVault vault,
            ApplicationEventPublisher publisher,
            Clock clock) {
        return new RotationService(vault, publisher, clock);
    }

    @Bean
    AuditSink auditSink() {
        return new AuditSink();
    }

    @Bean
    AuditListener auditListener(AuditSink sink) {
        return new AuditListener(sink);
    }

    // DEMO ONLY: do not use an in-memory vault in production.
    public static final class DemoVault implements AutoCloseable {
        private final Map<Long, char[]> values = new HashMap<>();
        private final Map<Long, Integer> versions = new HashMap<>();

        public synchronized int rotate(long accountId, char[] secret) {
            Objects.requireNonNull(secret, "secret");

            if (accountId <= 0 || secret.length < 12) {
                throw new IllegalArgumentException(
                    "Invalid rotation request"
                );
            }

            char[] copy = Arrays.copyOf(secret, secret.length);
            char[] old = values.put(accountId, copy);

            if (old != null) {
                Arrays.fill(old, '\0');
            }

            int version = versions.getOrDefault(accountId, 0) + 1;
            versions.put(accountId, version);
            return version;
        }

        @Override
        public synchronized void close() {
            for (char[] item : values.values()) {
                Arrays.fill(item, '\0');
            }
            values.clear();
            versions.clear();
        }
    }

    public static final class RotationService {
        private final DemoVault vault;
        private final ApplicationEventPublisher publisher;
        private final Clock clock;

        RotationService(
                DemoVault vault,
                ApplicationEventPublisher publisher,
                Clock clock) {
            this.vault = vault;
            this.publisher = publisher;
            this.clock = clock;
        }

        public CredentialRotated rotate(
                long accountId, char[] newSecret) {

            int version = vault.rotate(accountId, newSecret);
            CredentialRotated event = new CredentialRotated(
                UUID.randomUUID(),
                accountId,
                version,
                Instant.now(clock)
            );

            // Publish only allowlisted metadata.
            publisher.publishEvent(event);
            return event;
        }
    }

    public static final class AuditSink {
        private final List<String> entries = new ArrayList<>();

        public synchronized void add(CredentialRotated event) {
            entries.add(
                "account=" + event.accountId()
                + " version=" + event.credentialVersion()
            );
        }

        public synchronized List<String> entries() {
            return List.copyOf(entries);
        }
    }

    public static final class AuditListener {
        private final AuditSink sink;

        AuditListener(AuditSink sink) {
            this.sink = sink;
        }

        @EventListener
        public void onCredentialRotated(CredentialRotated event) {
            sink.add(event);
        }
    }

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(
                SafeEventPayloadDemo.class)) {

            var service = ctx.getBean(RotationService.class);

            // Fake value for demonstration purposes only.
            char[] input =
                "FAKE_DEMO_CREDENTIAL_NOT_REAL".toCharArray();

            CredentialRotated event;
            try {
                event = service.rotate(101L, input);
            } finally {
                Arrays.fill(input, '\0');
            }

            boolean cleared = true;
            for (char value : input) {
                if (value != '\0') {
                    cleared = false;
                }
            }

            int audits = ctx.getBean(AuditSink.class)
                .entries().size();
            boolean leaked = event.toString().contains(
                "FAKE_DEMO_CREDENTIAL_NOT_REAL");

            System.out.println("audit entries=" + audits);
            System.out.println(
                "credential version=" + event.credentialVersion());
            System.out.println("event exposes secret=" + leaked);
            System.out.println("command buffer wiped=" + cleared);
            System.out.println("event time=" + event.occurredAt());
        }
    }
}
~~~

### Run Command and Output

~~~bash
gradle run --quiet
# Linux/macOS if wrapper is present: ./gradlew run --quiet
# Windows if wrapper is present: gradlew.bat run --quiet
~~~

Lines printed by the program (excluding environment logs):

~~~text
audit entries=1
credential version=1
event exposes secret=false
command buffer wiped=true
event time=2026-01-02T03:04:05Z
~~~

**Reason:** there is only one successful event; the audit listener records exactly one metadata line; the event record contains no secret; the caller zeroed the buffer it owned; `Clock.fixed` makes the timestamp predictable. `UUID.randomUUID()` generates a new event ID, though the ID is not printed.

`Arrays.fill(...)` only clears **that specific array**. It does not erase copies that were already made, String literals, heap dumps, or logs. That is why raw secrets should never take a detour through events. The `toString().contains(fake)` check only illustrates the risk; **it does not mean production should log `event.toString()`**.

The demo has no transaction, database, or secure vault; if a real system stores credentials and publishes events across two different systems, you must design consistency and handle the crash window separately.

## 7. JUnit: Locking Down the Schema, Checking the Payload, and Testing Error Branches

A test that only checks stdout is not enough. If a developer adds a `refreshToken` field to the event later, we want the schema test to **fail immediately**.

File `src/test/java/demo/SafeEventPayloadDemoTest.java`:

~~~java
package demo;

import java.lang.reflect.RecordComponent;
import java.util.Arrays;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SafeEventPayloadDemoTest {

    @Test
    void eventSchemaIsAllowlisted() {
        Set<String> names = Arrays.stream(
            SafeEventPayloadDemo.CredentialRotated.class
                .getRecordComponents()
        ).map(RecordComponent::getName)
         .collect(Collectors.toSet());

        assertEquals(
            Set.of("eventId", "accountId",
                   "credentialVersion", "occurredAt"),
            names
        );
    }

    @Test
    void publishedEventDoesNotExposeSecret() {
        try (var ctx = new AnnotationConfigApplicationContext(
                SafeEventPayloadDemo.class)) {

            var service = ctx.getBean(
                SafeEventPayloadDemo.RotationService.class);
            var audit = ctx.getBean(
                SafeEventPayloadDemo.AuditSink.class);

            char[] input =
                "FAKE_DEMO_CREDENTIAL_NOT_REAL".toCharArray();
            SafeEventPayloadDemo.CredentialRotated event;
            try {
                event = service.rotate(101L, input);
            } finally {
                Arrays.fill(input, '\0');
            }

            assertFalse(event.toString().contains(
                "FAKE_DEMO_CREDENTIAL_NOT_REAL"));
            assertEquals(
                List.of("account=101 version=1"),
                audit.entries()
            );
            for (char c : input) {
                assertTrue(c == '\0');
            }
        }
    }

    @Test
    void invalidRotationDoesNotPublishSuccessFact() {
        try (var ctx = new AnnotationConfigApplicationContext(
                SafeEventPayloadDemo.class)) {

            var service = ctx.getBean(
                SafeEventPayloadDemo.RotationService.class);
            var audit = ctx.getBean(
                SafeEventPayloadDemo.AuditSink.class);

            char[] invalid = "short".toCharArray();
            try {
                assertThrows(
                    IllegalArgumentException.class,
                    () -> service.rotate(101L, invalid)
                );
            } finally {
                Arrays.fill(invalid, '\0');
            }

            assertEquals(0, audit.entries().size());
        }
    }
}
~~~

Run:

~~~bash
gradle test
# Linux/macOS: ./gradlew test
# Windows: gradlew.bat test
~~~

Expected **three JUnit tests pass** in an environment with appropriate dependencies/Gradle:

- the record schema has only the four allowed fields;
- a successfully published event does not contain the fake credential and audit contains only metadata;
- a failed validation operation does not publish a success notification event.

**Limitations:** these three tests do not test a real security manager, vault access permissions, AOP logging, JSON serialization, DLQs, or heap dumps. For production integration, you must add tests against the actual serializer/broker/outbox and the real logging/tracing pipeline.

## 8. When a Consumer Needs Secret Information

Cases like password resets, OTPs, or initial API key issuance sometimes need to **deliver a secret to a designated recipient**. That is the job of a controlled delivery channel, not a domain event published to every listener.

~~~text
PasswordResetRequested
    accountId
    requestId
    occurredAt
         |
         +--> audit/metrics (does not see token)
         |
         +--> trusted reset service
                - generate token with a suitable CSPRNG
                - store verifier, TTL, one-time-use
                - send over a protected channel
                - do not log token / reset URL
~~~

Do not put the token into `PasswordResetRequested`. If there is a dedicated message containing an encrypted secret for one recipient, you must separately design key management, recipient authentication, ACLs, expiry, retries, and DLQ/redaction. **Do not treat message encryption as a reason to broadcast widely.**

A token must have adequate randomness, an expiration time, a specific purpose, and a revoke/expire mechanism. Do not invent cryptographic algorithms; use well-reviewed specialized libraries and solutions.

## 9. How Do Transactions, @Async, and Outbox Relate?

`@Async @EventListener` changes the execution thread; it does **not** change the sensitivity of data in the event. A task may run after the HTTP request finishes, which makes it even more important not to put raw requests or mutable credential-bearing objects into the payload.

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` binds the handler to the moment a transaction commits successfully. However:

- An `AFTER_COMMIT` listener can still log/serialize the payload; the phase does not automatically redact anything.
- Errors/side effects after commit cannot revert committed data in T1 back to an uncommitted state.
- An after-commit callback has a crash window and is not durable delivery.
- When using a transactional outbox, **store only the sanitized event right at outbox write time**. Never store a raw secret hoping to delete it later.
- With reactive transactions, context lives in the Reactor Context; the principle of keeping secrets out of payloads does not change.

If a workflow needs reliability, apply a durable outbox/queue and appropriate idempotency while still enforcing data minimization and access controls. A broker with TLS and encryption-at-rest **does not replace** restricting fields and consumer ACLs.

## 10. Controlling Observability and Copies

Data paths that are commonly overlooked:

- `log.info("event={}", event)` can trigger a record's `toString()`.
- AOP interceptors may record all method arguments, including raw commands.
- Exception reporters may dump events/requests when a listener throws an exception.
- Tracing baggage/span attributes may inadvertently receive an Authorization header.
- Metric tags carrying `accountId`, `email`, tokens, or arbitrary `correlationId` values increase cardinality and risk leaking data.
- Outboxes, brokers, DLQs, replay stores, analytics, and backups may retain copies of events longer than expected.
- Debug dumps/snapshots/test fixtures may contain real credentials if production data samples are used.

**Use an allowlist for logs and traces**, such as `eventType`, bounded error codes, timestamps, and permitted IDs. Do not log whole objects by default. Verify the actual serialization schema before forwarding externally.

### When a Secret Is Discovered to Have Been Written to an Event

1. Identify the secret type, time window, event type, consumers, logs, outbox, broker, DLQ, retry stores, and backups that may contain copies.
2. Limit further spread and restrict read access according to incident response procedures; do not copy raw values into support tools.
3. Rotate/revoke potentially exposed credentials and check for anomalous usage.
4. Handle copy retention/deletion in accordance with policy and applicable obligations; deleting the source event does not guarantee other copies disappear.
5. Fix the schema using an allowlist, add serialization/log capture tests, and conduct a security review.
6. Coordinate with the security/privacy team if personal data or high-impact credentials are involved.

Do not declare "the leak is over" merely because the source code changed; you must account for the lifecycle of copies as well as rotation/revocation.

## 11. Common Misconceptions

1. **"Events are JVM-internal, so they are safe."** A new listener or log bridge can expand who receives the data.
2. **"Adding @JsonIgnore is enough."** It only affects one serialization path; `toString()`/reflection can behave differently.
3. **"`char[]` can never leak."** Arrays can be copied, retained long-term, or dumped; only that specific buffer can be wiped.
4. **"Password hashes can be placed in events."** Verifiers are still sensitive and must be protected.
5. **"Base64 is encryption."** It is not; it is merely encoding.
6. **"`AFTER_COMMIT` + `@Async` solves confidentiality."** They only change timing/threads, not payload filtering.
7. **"A secret reference is always harmless."** A reference with bearer privileges is still a secret.
8. **"DEBUG is not enabled in production."** It can be turned on and shipped to a log collector.
9. **"Not seeing the token in stdout is enough testing."** You must test schemas, serializers, AOP, tracing, outboxes, and DLQs.
10. **"An `accountId` is not sensitive."** An ID can still be PII or reveal a tenant; consider permissions and retention.

## 12. Pre-Publish Event Checklist

- [ ] The event represents an accurate business fact, not a raw command or request.
- [ ] The payload is an immutable value DTO with reviewed allowlisted fields.
- [ ] No passwords, access tokens, refresh tokens, API keys, session tokens, OTPs, private keys, password hashes, or key material are present.
- [ ] No entire JPA entities, HTTP requests, headers, or nested objects that might contain credentials are published.
- [ ] Each field has an authorized processing purpose/consumer and retention limit.
- [ ] References do not self-authorize; dereferencing goes through IAM/vault with authorization checks.
- [ ] Whole events, whole commands, or method arguments containing secrets are never logged.
- [ ] Metrics/tracing/error handlers use approved attributes/tags.
- [ ] Serialized outbox/broker/DLQ payloads contain no secrets.
- [ ] JUnit/schema tests and real serialization/logging integration tests exist.
- [ ] Fake test values are used, never production credentials.
- [ ] Revocation/rotation, incident response, backup/retention, and access audit policies are in place.
- [ ] Data confidentiality is kept distinct from commit timing, async execution, and durable delivery.

### Key Takeaways

~~~text
Credential-handling command
            |
            v
Trusted boundary
   |                 |
   v                 v
Secret manager    Domain event
ACL/rotation       required metadata only
   |                 |
   |                 +--> audit / metrics / listeners
   |
   +--> do not expose raw secret in event

Do not put secrets into event payloads.
Do not log whole objects.
Do not treat encryption, @Async, or AFTER_COMMIT
as a reason to skip data minimization.
~~~

**Conclusion:** Clearly separate the **secret-handling boundary** from the **event contract**. Only facts and minimal metadata are distributed to listeners; authorization data exists solely within systems permitted to handle it, backed by ACLs, TTLs, rotation, and auditing.

## References

- [Spring — ApplicationEventPublisher Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring — EventListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/event/EventListener.html)
- [Spring — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
